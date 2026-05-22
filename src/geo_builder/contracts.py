from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .entities import GeoArea
from .protocols import AreaStyle, Layer, PoiStyle


@dataclass
class Task:
    type: str


@dataclass
class BoundingBox:
    west: float
    south: float
    east: float
    north: float


class AcquisitionTask(Task):
    areaId: str
    areaName: str
    provider: str
    bbox: BoundingBox
    filters: dict[str, AreaStyle]
    depth: int

    def __init__(
        self,
        areaId: str,
        areaName: str,
        provider: str,
        bbox: BoundingBox,
        filters: dict[str, AreaStyle],
        depth: int = 0,
    ) -> None:
        super().__init__("acquisition")
        self.areaId = areaId
        self.areaName = areaName
        self.provider = provider
        self.bbox = bbox
        self.filters = filters
        self.depth = depth


class AggregationTask(Task):
    def __init__(
        self,
    ) -> None:
        super().__init__("aggregation")


class DedupingTask(Task):
    def __init__(
        self,
    ) -> None:
        super().__init__("deduping")


class PoiTask(Task):
    style: PoiStyle

    def __init__(self, style: PoiStyle | None = None) -> None:
        super().__init__("poi")
        self.style = style if style is not None else PoiStyle()


class Map(Protocol):
    def add_area(self, task: AcquisitionTask) -> GeoArea: ...
    def add_layer(self, area: GeoArea, layer: Layer) -> None: ...


class Executor(Map, Protocol):
    def push_task(self, task: Task) -> None: ...
    def push_tasks(self, tasks: list[Task]) -> None: ...


@dataclass
class WorkerResult:
    fatal: bool = False
    error: str | None = None


class Worker(Protocol):
    def execute(self, executor: Executor) -> WorkerResult: ...


class Provider(Protocol):
    name: str

    def fetch(self, task: AcquisitionTask) -> Layer: ...
