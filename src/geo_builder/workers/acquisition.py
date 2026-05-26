from ..contracts import AcquisitionTask, Executor, Worker, WorkerResult
from ..diagnostics import Logger
from ..entities import GeoArea, GeoLayer
from ..errors import ProviderError
from ..providers.factory import ProviderFactory


class AcquisitionWorker(Worker):
    _task: AcquisitionTask
    _provider_factory: ProviderFactory

    def __init__(self, task: AcquisitionTask) -> None:
        super().__init__()

        self._task = task
        self._provider_factory = ProviderFactory()

    def execute(self, executor: Executor) -> WorkerResult:
        task = self._task
        bbox = task.bbox
        filter_keys = ", ".join(task.filters.keys())
        Logger.info(
            f"AcquisitionWorker [{task.areaId}] depth={task.depth} "
            f"bbox=[{bbox.west:.5f},{bbox.south:.5f},{bbox.east:.5f},{bbox.north:.5f}] "
            f"filters=[{filter_keys}]"
        )

        if len(task.filters) > 1:
            area = executor.add_area(task)
            Logger.info(f"AcquisitionWorker [{task.areaId}] splitting {len(task.filters)} filters into per-key tasks")
            executor.push_tasks(self._split_by_key(task))
            return self._result()

        area = executor.add_area(task)
        provider = self._provider_factory.create(task.provider)

        try:
            layer = provider.fetch(task)
        except ProviderError as error:
            child_tasks = self._split_task(task)

            if len(child_tasks) == 0:
                Logger.warning(f"AcquisitionWorker [{task.areaId}] depth={task.depth} bbox too small to split further — giving up")
                return self._result(fatal=True, error=str(error))

            Logger.info(f"AcquisitionWorker [{task.areaId}] depth={task.depth} → {len(child_tasks)} quadrants at depth={task.depth + 1}")
            executor.push_tasks(child_tasks)
            return self._result()

        # Single-filter task: set acquisition dict and assign stable layer id.
        filter_key = next(iter(task.filters))
        filter_values = sorted(task.filters[filter_key].values)
        acquisition = {"provider": task.provider, "filter": filter_key, "values": filter_values}
        layer.acquisition = acquisition

        existing = self._find_existing_layer(area, acquisition)
        if existing is not None:
            layer.id = existing.layer.id
            layer.style = dict(existing.layer.style)
            layer.name = existing.layer.name
            layer.type = existing.layer.type
            layer.visible = existing.layer.visible
        else:
            layer.id = self._next_id(area)
            color = task.filters[filter_key].color
            if color:
                layer.style["color"] = color

        layer.url = f"./layers/{layer.id}.geojson"

        executor.add_layer(area, layer)
        return self._result()

    def _result(self, fatal: bool = False, error: str | None = None) -> WorkerResult:
        task = self._task

        Logger.info(f"AcquisitionWorker [{task.areaId}] depth={task.depth} Completed. Error: {error}")
        return WorkerResult(fatal, error)

    def _find_existing_layer(self, area: GeoArea, acquisition: dict) -> GeoLayer | None:
        for geo_layer in area.layers:
            if geo_layer.layer.acquisition == acquisition:
                return geo_layer
        return None

    def _next_id(self, area: GeoArea) -> str:
        max_id = 0
        for geo_layer in area.layers:
            try:
                n = int(geo_layer.layer.id)
                if n > max_id:
                    max_id = n
            except (ValueError, TypeError):
                pass
        return str(max_id + 1)

    def _split_by_key(self, task: AcquisitionTask) -> list[AcquisitionTask]:
        result: list[AcquisitionTask] = []
        for key, style in task.filters.items():
            result.append(
                AcquisitionTask(
                    areaId=task.areaId,
                    areaName=task.areaName,
                    provider=task.provider,
                    bbox=task.bbox,
                    filters={key: style},
                    depth=task.depth,
                )
            )
        return result

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
                depth=task.depth + 1,
            ),
            AcquisitionTask(
                areaId=task.areaId,
                areaName=task.areaName,
                provider=task.provider,
                bbox=type(bbox)(west=mid_lon, south=bbox.south, east=bbox.east, north=mid_lat),
                filters=task.filters,
                depth=task.depth + 1,
            ),
            AcquisitionTask(
                areaId=task.areaId,
                areaName=task.areaName,
                provider=task.provider,
                bbox=type(bbox)(west=bbox.west, south=mid_lat, east=mid_lon, north=bbox.north),
                filters=task.filters,
                depth=task.depth + 1,
            ),
            AcquisitionTask(
                areaId=task.areaId,
                areaName=task.areaName,
                provider=task.provider,
                bbox=type(bbox)(west=mid_lon, south=mid_lat, east=bbox.east, north=bbox.north),
                filters=task.filters,
                depth=task.depth + 1,
            ),
        ]
