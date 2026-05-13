from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .protocols import Area, Layer


@dataclass
class Task:
    type: str
@dataclass


@dataclass
class BoundingBox:
    west: float
    south: float
    east: float
    north: float


class AcquisitionTask(Task):
    areaId:str
    areaName: str
    provider: str
    bbox: BoundingBox
    filter: dict[str, list[str]]

    def __init__(
        self,
        areaId: str,
        areaName: str,
        provider: str,
        bbox: BoundingBox,
        filter: dict[str, list[str]],
    ) -> None:
        super().__init__("acquisition")
        self.areaId = areaId
        self.areaName = areaName
        self.provider = provider
        self.bbox = bbox
        self.filter = filter


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

class ExecutorContract(Protocol):
    def push_task(self, task: Task) -> None: ...
    def push_tasks(self, tasks: list[Task]) -> None: ...
    def add_area(self, task: AcquisitionTask) -> Area: ...
    def add_layer(self, area: Area, layer: Layer) -> None: ...


@dataclass
class WorkerResult:
    fatal: bool = False
    error: str | None = None


class Worker(Protocol):
    def execute(self, executor: ExecutorContract) -> WorkerResult: ...

class Provider(Protocol):
    name: str
    def fetch(self, task: AcquisitionTask) -> Layer: ...