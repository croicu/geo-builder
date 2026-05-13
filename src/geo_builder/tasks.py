import json
from dataclasses import dataclass
from pathlib import Path

from .contracts import AcquisitionTask, AggregationTask, DedupingTask, Task
from .errors import TaskError


@dataclass
class BoundingBox:
    west: float
    south: float
    east: float
    north: float


@dataclass
class BuildTask:
    provider: str
    bbox: BoundingBox
    filter: dict[str, object]


class Tasks:
    @staticmethod
    def load(path: str | Path) -> list[Task]:
        with Path(path).open("r", encoding="utf-8") as file:
            payload = json.load(file)

        if not isinstance(payload, list):
            raise TaskError("Task file must contain a JSON array.")

        tasks: list[Task] = []

        for item in payload:
            if not isinstance(item, dict):
                raise TaskError("Each task must be a JSON object.")

            task_type = str(item.get("type", "acquisition"))

            if task_type == "acquisition":
                bbox_data = item["bbox"]

                bbox = BoundingBox(
                    west=float(bbox_data["west"]),
                    south=float(bbox_data["south"]),
                    east=float(bbox_data["east"]),
                    north=float(bbox_data["north"]),
                )

                task = AcquisitionTask(
                    areaId=str(item["areaId"]),
                    areaName=str(item["areaName"]),
                    provider=str(item["provider"]),
                    bbox=bbox,
                    filter=dict(item.get("filter", {})),
                )
                tasks.append(task)

                continue

            if task_type == "aggregation":
                task = AggregationTask()
                tasks.append(task)

                continue

            if task_type == "deduping":
                task = DedupingTask()
                tasks.append(task)

                continue

            raise TaskError(f"Unknown task type: {task_type}")

        return tasks