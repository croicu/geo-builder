from ..contracts import Executor, Task, VoidTask, Worker, WorkerResult
from ..diagnostics import Logger
from ..entities import GeoArea, GeoLayer
from ..protocols import Layer, VoidStyle

_VOID_ID = "__void__"
_VOID_TYPE = "__void__"


class VoidWorker(Worker):
    def __init__(self, task: Task) -> None:
        super().__init__()
        self._task = task

    def execute(self, executor: Executor) -> WorkerResult:
        Logger.info("VoidWorker: execute.")

        catalog = executor.catalog
        if catalog is None:
            Logger.warning("VoidWorker: no catalog, skipping.")
            return WorkerResult()

        style = self._task.style if isinstance(self._task, VoidTask) else VoidStyle()

        stub_count = 0
        for area in list(catalog.areas):
            self._process_area(area, style)
            stub_count += 1

        Logger.info(f"VoidWorker: completed. void stub added/retained for {stub_count}/{len(catalog.areas)} area(s).")
        return WorkerResult()

    def _process_area(self, area: GeoArea, style: VoidStyle) -> None:
        for geo_layer in area.layers:
            if geo_layer.layer.id == _VOID_ID:
                return

        stub = Layer(
            id=_VOID_ID,
            name=style.name,
            type=_VOID_TYPE,
            visible=False,
            style={
                "opacity": style.opacity,
                "color": style.color,
            },
        )
        area.layers.append(GeoLayer(stub))
