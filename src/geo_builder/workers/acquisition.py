from ..contracts import Executor, Worker, WorkerResult
from ..errors import ProviderError
from ..providers.factory import ProviderFactory
from ..tasks import AcquisitionTask


class AcquisitionWorker(Worker):
    _task: AcquisitionTask
    _provider_factory: ProviderFactory

    def __init__(self, task: AcquisitionTask) -> None:
        super().__init__()

        self._task = task
        self._provider_factory = ProviderFactory()

    def execute(self, executor: Executor) -> WorkerResult:
        print("AcquisitionWorker: execute")

        if len(self._task.filters) > 1:
            executor.push_tasks(self._split_by_key(self._task))
            return WorkerResult()

        area = executor.add_area(self._task)
        provider = self._provider_factory.create(self._task.provider)

        try:
            layer = provider.fetch(self._task)
        except ProviderError as error:
            child_tasks = self._split_task(self._task)

            if len(child_tasks) == 0:
                return WorkerResult(fatal=True, error=str(error))

            executor.push_tasks(child_tasks)
            return WorkerResult()

        executor.add_layer(area, layer)

        if len(self._task.filters) == 1:
            key = next(iter(self._task.filters))
            color = self._task.filters[key].color
            if color:
                layer.style["color"] = color

        return WorkerResult()

    def _split_by_key(self, task: AcquisitionTask) -> list[AcquisitionTask]:
        return [
            AcquisitionTask(
                areaId=task.areaId,
                areaName=task.areaName,
                provider=task.provider,
                bbox=task.bbox,
                filters={key: style},
            )
            for key, style in task.filters.items()
        ]

    def _split_task(self, task: AcquisitionTask) -> list[AcquisitionTask]:
        bbox = task.bbox

        width = bbox.east - bbox.west
        height = bbox.north - bbox.south

        if width <= 0 or height <= 0:
            return []

        mid_lon = bbox.west + width / 2
        mid_lat = bbox.south + height / 2

        return [
            AcquisitionTask(
                areaId=task.areaId,
                areaName=task.areaName,
                provider=task.provider,
                bbox=type(bbox)(west=bbox.west, south=bbox.south, east=mid_lon, north=mid_lat),
                filters=task.filters,
            ),
            AcquisitionTask(
                areaId=task.areaId,
                areaName=task.areaName,
                provider=task.provider,
                bbox=type(bbox)(west=mid_lon, south=bbox.south, east=bbox.east, north=mid_lat),
                filters=task.filters,
            ),
            AcquisitionTask(
                areaId=task.areaId,
                areaName=task.areaName,
                provider=task.provider,
                bbox=type(bbox)(west=bbox.west, south=mid_lat, east=mid_lon, north=bbox.north),
                filters=task.filters,
            ),
            AcquisitionTask(
                areaId=task.areaId,
                areaName=task.areaName,
                provider=task.provider,
                bbox=type(bbox)(west=mid_lon, south=mid_lat, east=bbox.east, north=bbox.north),
                filters=task.filters,
            ),
        ]
