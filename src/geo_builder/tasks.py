from .contracts import AcquisitionTask, AggregationTask, BoundingBox, DedupingTask, Task
from .errors import TaskError


class Tasks:
    @staticmethod
    def from_payload(payload: dict[str, object]) -> list[Task]:
        tasks: list[Task] = []

        for name, item in payload.items():
            if not isinstance(item, dict):
                raise TaskError(f"Task '{name}' must be a JSON object.")

            task_type = str(item.get("type", "acquisition"))

            if task_type == "acquisition":
                bbox_data = item["bbox"]

                bbox = BoundingBox(
                    west=float(bbox_data["west"]),
                    south=float(bbox_data["south"]),
                    east=float(bbox_data["east"]),
                    north=float(bbox_data["north"]),
                )

                tasks.append(
                    AcquisitionTask(
                        areaId=str(item["areaId"]),
                        areaName=str(item["areaName"]),
                        provider=str(item["provider"]),
                        bbox=bbox,
                        filter=dict(item.get("filter", {})),
                    )
                )
                continue

            if task_type == "aggregation":
                tasks.append(AggregationTask())
                continue

            if task_type == "deduping":
                tasks.append(DedupingTask())
                continue

            raise TaskError(f"Unknown task type: '{task_type}' in task '{name}'.")

        return tasks
