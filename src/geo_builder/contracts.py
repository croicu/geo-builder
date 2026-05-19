from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .entities import GeoArea
from .protocols import Layer


@dataclass
class Task:
    type: str


@dataclass
class BoundingBox:
    west: float
    south: float
    east: float
    north: float


@dataclass
class AreaStyle:
    values: list[str]
    name: str | None = None
    color: str | None = None
    scale: float | None = None
    surface: bool = False
    type: str = "heatmap"


class AcquisitionTask(Task):
    areaId: str
    areaName: str
    provider: str
    bbox: BoundingBox
    filters: dict[str, AreaStyle]

    def __init__(
        self,
        areaId: str,
        areaName: str,
        provider: str,
        bbox: BoundingBox,
        filters: dict[str, AreaStyle],
    ) -> None:
        super().__init__("acquisition")
        self.areaId = areaId
        self.areaName = areaName
        self.provider = provider
        self.bbox = bbox
        self.filters = filters


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
