from .contracts import AcquisitionTask, AggregationTask, AreaStyle, BoundingBox, DedupingTask, Task
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

                _LAYER_TYPES = ("heatmap", "circle")

                filters: dict[str, AreaStyle] = {}
                for key, style_data in dict(item.get("filters", {})).items():
                    if not isinstance(style_data, dict):
                        raise TaskError(f"Filter '{key}' in task '{name}' must be a JSON object.")
                    layer_type = str(style_data.get("type", "heatmap"))
                    if layer_type not in _LAYER_TYPES:
                        raise TaskError(f"Filter '{key}' in task '{name}' has unknown type '{layer_type}'.")
                    filters[str(key)] = AreaStyle(
                        values=[str(v) for v in style_data.get("values", [])],
                        name=str(style_data["name"]) if "name" in style_data else None,
                        color=str(style_data["color"]) if "color" in style_data else None,
                        scale=float(style_data["scale"]) if "scale" in style_data else None,
                        surface=bool(style_data.get("surface", False)),
                        type=layer_type,
                    )

                tasks.append(
                    AcquisitionTask(
                        areaId=str(item["areaId"]),
                        areaName=str(item["areaName"]),
                        provider=str(item["provider"]),
                        bbox=bbox,
                        filters=filters,
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
