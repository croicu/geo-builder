from ..contracts import Executor, PoiTask, Task, Worker, WorkerResult
from ..diagnostics import Logger
from ..entities import GeoArea, GeoLayer
from ..protocols import Layer, PoiStyle

_POI_HEAT_ID = "poi"
_POI_HEAT_MERGE_KEY = "poi"


class PoiWorker(Worker):
    def __init__(self, task: Task) -> None:
        super().__init__()
        self._task = task

    def execute(self, executor: Executor) -> WorkerResult:
        Logger.info("PoiWorker: execute.")

        catalog = executor.catalog
        if catalog is None:
            Logger.warning("PoiWorker: no catalog, skipping.")
            return WorkerResult()

        style = self._task.style if isinstance(self._task, PoiTask) else PoiStyle()

        stub_count = 0
        for area in list(catalog.areas):
            had_details = self._process_area(area, style)
            if had_details:
                stub_count += 1

        Logger.info(f"PoiWorker: completed. poi stub added to {stub_count}/{len(catalog.areas)} area(s).")
        return WorkerResult()

    def _process_area(self, area: GeoArea, style: PoiStyle) -> bool:
        has_details = self._area_has_details(area)

        filtered = []
        for geo_layer in area.layers:
            if geo_layer.layer.id != _POI_HEAT_ID:
                filtered.append(geo_layer)
        area.layers = filtered

        if has_details:
            area.layers.append(GeoLayer(self._create_stub(style)))

        return has_details

    def _area_has_details(self, area: GeoArea) -> bool:
        for geo_layer in area.layers:
            if geo_layer.layer.geojson is None:
                continue
            for feature in geo_layer.layer.geojson.features:
                if feature.properties.get("hasDetails"):
                    return True
        return False

    def _create_stub(self, style: PoiStyle) -> Layer:
        layer_style: dict = {"opacity": style.opacity, "type": style.type}
        if style.color is not None:
            layer_style["color"] = style.color
        if style.radius is not None:
            layer_style["radius"] = style.radius
        return Layer(
            id=_POI_HEAT_ID,
            name=style.name,
            type="poi",
            visible=True,
            style=layer_style,
            mergeKey=_POI_HEAT_MERGE_KEY,
        )
