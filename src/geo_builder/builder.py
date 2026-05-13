from __future__ import annotations

from dataclasses import dataclass, field
from math import atan2, cos, radians, sin, sqrt

from .contracts import AcquisitionTask, BoundingBox
from .errors import GeoError
from .protocols import Area, Catalog, JsonObject, Layer, Manifest, Result
from .workers.factory import WorkerFactory


@dataclass
class Builder:
    catalog: Catalog = field(default_factory=Catalog)
    errors: list[str] = field(default_factory=list)

    _stack: list[JsonObject] = field(default_factory=list)
    _worker_factory: WorkerFactory = field(default_factory=WorkerFactory)

    def run(self) -> Result:
        from .settings import Settings

        settings = Settings.current()
        debug = settings.debug

        self.errors.clear()
        self._stack = list(reversed(settings.tasks))

        while self._stack:
            task = self._stack.pop()

            if debug:
                worker = self._worker_factory.create(task)
                result = worker.execute(self)
            else:
                try:
                    worker = self._worker_factory.create(task)
                    result = worker.execute(self)
                except GeoError as error:
                    self.errors.append(str(error))
                    break

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
        for existing in area.manifest.layers:
            if existing.mergeKey == layer.mergeKey:
                existing.geojson.features.extend(layer.geojson.features)
                return
        area.manifest.layers.append(layer)

    def _create_result(self) -> Result:
        return Result(catalog=self.catalog)

    def _bbox_radius_meters(self, bbox: BoundingBox) -> float:
        center_lat = (bbox.south + bbox.north) / 2.0
        center_lon = (bbox.west + bbox.east) / 2.0

        corners = [
            (bbox.south, bbox.west),
            (bbox.south, bbox.east),
            (bbox.north, bbox.west),
            (bbox.north, bbox.east),
        ]

        return max(self._haversine_meters(center_lat, center_lon, lat, lon) for lat, lon in corners)

    def _haversine_meters(
        self,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> float:
        earth_radius_meters = 6_371_000.0

        d_lat = radians(lat2 - lat1)
        d_lon = radians(lon2 - lon1)

        r_lat1 = radians(lat1)
        r_lat2 = radians(lat2)

        a = sin(d_lat / 2.0) ** 2 + cos(r_lat1) * cos(r_lat2) * sin(d_lon / 2.0) ** 2

        c = 2.0 * atan2(sqrt(a), sqrt(1.0 - a))

        return earth_radius_meters * c
