from collections import defaultdict

from ..contracts import Executor, Task, Worker, WorkerResult
from ..diagnostics import Logger
from ..entities import GeoLayer
from ..protocols import GeoJson


class AggregationWorker(Worker):
    _task: Task

    def __init__(self, task: Task) -> None:
        super().__init__()
        self._task = task

    def execute(self, executor: Executor) -> WorkerResult:
        Logger.info("AggregationWorker: execute.")

        catalog = executor.catalog
        if catalog is None:
            return WorkerResult()

        for area in list(catalog.areas):
            self._aggregate_area(area)

        Logger.info("AggregationWorker: completed.")
        return WorkerResult()

    def _aggregate_area(self, area) -> None:
        groups = defaultdict(list)

        for geo_layer in area.layers:
            acq = geo_layer.layer.acquisition
            if acq is None:
                continue
            filters_frozen = frozenset((k, tuple(sorted(v))) for k, v in acq["filters"].items())
            group_key = (acq["provider"], filters_frozen)
            groups[group_key].append(geo_layer)

        for group_key, geo_layers in groups.items():
            if len(geo_layers) < 2:
                continue

            merged_geo_layer = self._merge_layers(geo_layers)

            source_ids = {gl.layer.id for gl in geo_layers}

            filtered = []
            for gl in area.layers:
                if gl.layer.id not in source_ids:
                    filtered.append(gl)
            area.layers = filtered

            area.layers.append(merged_geo_layer)

    def _merge_layers(self, geo_layers: list) -> GeoLayer:
        first = geo_layers[0]
        merged_geojson = self._merge_geojson(geo_layers)
        first.layer.geojson = merged_geojson
        first.layer.url = f"./layers/{first.layer.id}.geojson"
        return first

    def _merge_geojson(self, geo_layers: list) -> GeoJson:
        features = []

        for geo_layer in geo_layers:
            if geo_layer.layer.geojson is None:
                continue

            features.extend(geo_layer.layer.geojson.features)

        return GeoJson(type="FeatureCollection", features=features)
