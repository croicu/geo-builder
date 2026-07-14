from ..contracts import Executor, SearchTask, Task, Worker, WorkerResult
from ..diagnostics import Logger
from ..entities import GeoArea, GeoLayer
from ..protocols import Layer, SearchStyle

_SEARCH_ID = "__search__"
_SEARCH_TYPE = "__search__"


class SearchWorker(Worker):
    def __init__(self, task: Task) -> None:
        super().__init__()
        self._task = task

    def execute(self, executor: Executor) -> WorkerResult:
        Logger.info("SearchWorker: execute.")

        catalog = executor.catalog
        if catalog is None:
            Logger.warning("SearchWorker: no catalog, skipping.")
            return WorkerResult()

        style = self._task.style if isinstance(self._task, SearchTask) else SearchStyle()

        stub_count = 0
        for area in list(catalog.areas):
            if self._process_area(area, style):
                stub_count += 1

        Logger.info(f"SearchWorker: completed. stub added to {stub_count}/{len(catalog.areas)} area(s).")
        return WorkerResult()

    def _process_area(self, area: GeoArea, style: SearchStyle) -> bool:
        for geo_layer in area.layers:
            if geo_layer.layer.id == _SEARCH_ID:
                return False

        stub = Layer(
            id=_SEARCH_ID,
            name=style.name,
            type=_SEARCH_TYPE,
            visible=False,
            style={
                "opacity": style.opacity,
                "color": style.color,
            },
        )
        area.layers.append(GeoLayer(stub))
        return True
