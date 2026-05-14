from collections import defaultdict

from ..contracts import Executor, Task, Worker, WorkerResult


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
        if area.manifest is None:
            return

        groups = defaultdict(list)

        for layer in area.manifest.layers:
            merge_key = getattr(layer, "mergeKey", None)
            if merge_key is None:
                continue

            groups[merge_key].append(layer)

        for merge_key, layers in groups.items():
            if len(layers) < 2:
                continue

            merged_layer = self._merge_layers(area, merge_key, layers)

            source_ids = {layer.id for layer in layers}

            area.manifest.layers = [layer for layer in area.manifest.layers if layer.id not in source_ids]

            area.manifest.layers.append(merged_layer)

    def _merge_layers(self, area, merge_key: str, layers: list):
        first = layers[0]

        geojson = self._merge_geojson(layers)

        first.geojson = geojson
        first.id = self._create_layer_id(merge_key)
        first.name = self._create_layer_name(first)
        first.url = f"./layers/{first.id}.geojson"
        first.mergeKey = merge_key

        return first

    def _merge_geojson(self, layers: list):
        features = []

        for layer in layers:
            if layer.geojson is None:
                continue

            features.extend(layer.geojson.features)

        return type(layers[0].geojson)(
            type="FeatureCollection",
            features=features,
        )

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

    def _create_layer_name(self, layer) -> str:
        return layer.name
