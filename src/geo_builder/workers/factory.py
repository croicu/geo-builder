from __future__ import annotations

from ..contracts import AcquisitionTask, AggregationTask, DedupingTask, PoiTask, SearchTask, Task, VoidTask, Worker
from ..errors import WorkerError
from .acquisition import AcquisitionWorker
from .aggregation import AggregationWorker
from .deduping import DedupingWorker
from .poi import PoiWorker
from .search import SearchWorker
from .void import VoidWorker


class WorkerFactory:
    def create(self, task: Task) -> Worker:

        if isinstance(task, AcquisitionTask):
            return AcquisitionWorker(task)

        if isinstance(task, AggregationTask):
            return AggregationWorker(task)

        if isinstance(task, DedupingTask):
            return DedupingWorker(task)

        if isinstance(task, PoiTask):
            return PoiWorker(task)

        if isinstance(task, VoidTask):
            return VoidWorker(task)

        if isinstance(task, SearchTask):
            return SearchWorker(task)

        raise WorkerError(f"Unknown task type: {task.type}")
