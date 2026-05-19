from collections import defaultdict

from ..contracts import Executor, Task, Worker, WorkerResult
from ..entities import GeoLayer
from ..protocols import GeoJson


class AggregationWorker(Worker):
    _task: Task

    def __init__(self, task: Task) -> None:
        super().__init__()
        self._task = task

    def execute(self, executor: Executor) -> WorkerResult:
        print("AggregationWorker: execute")

        catalog = executor.catalog
        if catalog is None:
            return WorkerResult()

        for area in list(catalog.areas):
            self._aggregate_area(area)

        return WorkerResult()

    def _aggregate_area(self, area) -> None:
        groups = defaultdict(list)

        for geo_layer in area.layers:
            merge_key = geo_layer.layer.mergeKey
            if merge_key is None:
                continue

            groups[merge_key].append(geo_layer)

        for merge_key, geo_layers in groups.items():
            if len(geo_layers) < 2:
                continue

            merged_geo_layer = self._merge_layers(merge_key, geo_layers)

            source_ids = {gl.layer.id for gl in geo_layers}

            filtered = []
            for gl in area.layers:
                if gl.layer.id not in source_ids:
                    filtered.append(gl)
            area.layers = filtered

            area.layers.append(merged_geo_layer)

    def _merge_layers(self, merge_key: str, geo_layers: list) -> GeoLayer:
        first = geo_layers[0]
        merged_geojson = self._merge_geojson(geo_layers)

        first.layer.geojson = merged_geojson
        first.layer.id = self._create_layer_id(merge_key)
        first.layer.name = self._create_layer_name(first)
        first.layer.url = f"./layers/{first.layer.id}.geojson"
        first.layer.mergeKey = merge_key

        return first

    def _merge_geojson(self, geo_layers: list) -> GeoJson:
        features = []

        for geo_layer in geo_layers:
            if geo_layer.layer.geojson is None:
                continue

            features.extend(geo_layer.layer.geojson.features)

        return GeoJson(type="FeatureCollection", features=features)

    def _create_layer_id(self, merge_key: str) -> str:
        value = merge_key.lower()
        value = value.replace(":", "_")
        value = value.replace("=", "_")
        value = value.replace(",", "_")
        value = value.replace(" ", "_")
        value = value.replace("-", "_")

        while "__" in value:
            value = value.replace("__", "_")

        return value.strip("_")

    def _create_layer_name(self, geo_layer: GeoLayer) -> str:
        return geo_layer.layer.name
