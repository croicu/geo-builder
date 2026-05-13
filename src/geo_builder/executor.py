from __future__ import annotations

from dataclasses import dataclass, field

from .contracts import AcquisitionTask
from .protocols import Area, Catalog, JsonObject, Layer, Manifest, Result
from .workers.factory import WorkerFactory


@dataclass
class Executor:
    catalog: Catalog = field(default_factory=Catalog)
    errors: list[str] = field(default_factory=list)

    _stack: list[JsonObject] = field(default_factory=list)
    _worker_factory: WorkerFactory = field(default_factory=WorkerFactory)

    def execute(
        self,
        tasks: list[JsonObject]
    ) -> Result:
        self.errors.clear()
        self._stack = list(reversed(tasks))

        while self._stack:
            task = self._stack.pop()

            # try:
            worker = self._worker_factory.create(task)
            result = worker.execute(self)
            # except Exception as error:
            #     self.errors.append(str(error))
            #     break

            if result.fatal:
                if result.error is not None:
                    self.errors.append(result.error)
                break

        return self._create_result()

    def push_task(self, task: JsonObject) -> None:
        self._stack.append(task)

    def push_tasks(self, tasks: list[JsonObject]) -> None:
        self._stack.extend(tasks)

    def add_area(self, task: AcquisitionTask) -> Area:
        area_id = task.areaId

        for area in self.catalog.areas:
            if area.id == area_id:
                return area

        bbox = task.bbox

        center = [
            (bbox.south + bbox.north) / 2.0,
            (bbox.west + bbox.east) / 2.0,
        ]

        radius_meters = int(self._bbox_radius_meters(bbox))

        area = Area(
            id=area_id,
            name=task.areaName,
            center=center,
            radiusMeters=radius_meters,
            minRadiusPx=32,
            maxRadiusPx=512,
            liveMapRadiusPx=640,
            manifestUrl=f"./areas/{area_id}/manifest.json",
            manifest=Manifest(
                version=1,
                layers=[],
            ),
        )

        self.catalog.areas.append(area)

        return area

    def add_layer(self, area: Area, layer: Layer) -> None:
        area.manifest.layers.append(layer)

    def _create_result(self) -> Result:
        return Result(catalog=self.catalog)
    
