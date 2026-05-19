from .contracts import AcquisitionTask, AggregationTask, BoundingBox, DedupingTask, Task
from .errors import TaskError
from .protocols import Acquisition, AreaStyle


def _parse_filters(filters_data: object, task_name: str) -> dict[str, AreaStyle]:
    _LAYER_TYPES = ("heatmap", "circle")
    filters: dict[str, AreaStyle] = {}
    for key, style_data in dict(filters_data if isinstance(filters_data, dict) else {}).items():
        if not isinstance(style_data, dict):
            raise TaskError(f"Filter '{key}' in task '{task_name}' must be a JSON object.")
        layer_type = str(style_data.get("type", "heatmap"))
        if layer_type not in _LAYER_TYPES:
            raise TaskError(f"Filter '{key}' in task '{task_name}' has unknown type '{layer_type}'.")
        values: list[str] = []
        for v in style_data.get("values", []):
            values.append(str(v))
        filters[str(key)] = AreaStyle(
            values=values,
            name=str(style_data["name"]) if style_data.get("name") is not None else None,
            color=str(style_data["color"]) if style_data.get("color") is not None else None,
            scale=float(style_data["scale"]) if style_data.get("scale") is not None else None,
            surface=bool(style_data.get("surface", False)),
            type=layer_type,
        )
    return filters


class Tasks:
    @staticmethod
    def from_payload(payload: dict[str, object]) -> list[Task]:
        tasks: list[Task] = []

        for name, item in payload.items():
            if not isinstance(item, dict):
                raise TaskError(f"Task '{name}' must be a JSON object.")

            task_type = str(item.get("type", "acquisition"))

            if task_type == "template":
                continue

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
                        filters=_parse_filters(item.get("filters", {}), name),
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

    @staticmethod
    def templates_from_payload(payload: dict[str, object]) -> dict[str, Acquisition]:
        templates: dict[str, Acquisition] = {}

        for name, item in payload.items():
            if not isinstance(item, dict):
                continue
            if str(item.get("type", "acquisition")) != "template":
                continue

            filters = _parse_filters(item.get("filters", {}), name)
            templates[name] = Acquisition(
                provider=str(item["provider"]),
                filters=filters,
            )

        return templates
