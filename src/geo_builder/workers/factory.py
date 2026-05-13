from __future__ import annotations

from ..contracts import AcquisitionTask, AggregationTask, DedupingTask, Task, Worker
from ..errors import WorkerError
from .acquisition import AcquisitionWorker
from .aggregation import AggregationWorker
from .deduping import DedupingWorker


class WorkerFactory:
    def create(self, task: Task) -> Worker:

        if isinstance(task, AcquisitionTask):
            return AcquisitionWorker(task)

        if isinstance(task, AggregationTask):
            return AggregationWorker(task)

        if isinstance(task, DedupingTask):
            return DedupingWorker(task)

        raise WorkerError(f"Unknown task type: {task.type}")