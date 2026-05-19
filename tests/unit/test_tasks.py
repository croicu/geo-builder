import pytest

from geo_builder.errors import TaskError
from geo_builder.protocols import AreaStyle
from geo_builder.tasks import Tasks


def _acquisition_payload(filters: dict | None = None) -> dict:
    return {
        "type": "acquisition",
        "areaId": "napoli",
        "areaName": "Napoli",
        "provider": "overpass",
        "bbox": {"west": 0.0, "south": 0.0, "east": 1.0, "north": 1.0},
        "filters": filters or {},
    }


def _template_payload(filters: dict | None = None, provider: str = "overpass") -> dict:
    return {
        "type": "template",
        "provider": provider,
        "filters": filters or {},
    }


class TestFromPayload:
    def test_acquisition_task_parsed(self):
        payload = {"fetch": _acquisition_payload()}

        tasks = Tasks.from_payload(payload)

        assert len(tasks) == 1
        assert tasks[0].type == "acquisition"

    def test_template_task_skipped(self):
        payload = {"default": _template_payload()}

        tasks = Tasks.from_payload(payload)

        assert tasks == []

    def test_template_and_acquisition_in_same_payload(self):
        payload = {
            "default": _template_payload(),
            "fetch": _acquisition_payload(),
        }

        tasks = Tasks.from_payload(payload)

        assert len(tasks) == 1
        assert tasks[0].type == "acquisition"

    def test_unknown_type_raises(self):
        payload = {"bad": {"type": "unknown"}}

        with pytest.raises(TaskError, match="unknown"):
            Tasks.from_payload(payload)

    def test_filter_values_parsed(self):
        payload = {
            "fetch": _acquisition_payload({"amenity": {"values": ["restaurant", "cafe"], "type": "heatmap"}}),
        }

        tasks = Tasks.from_payload(payload)

        assert tasks[0].filters["amenity"].values == ["restaurant", "cafe"]

    def test_filter_unknown_type_raises(self):
        payload = {
            "fetch": _acquisition_payload({"amenity": {"values": [], "type": "unknown"}}),
        }

        with pytest.raises(TaskError, match="unknown type"):
            Tasks.from_payload(payload)


class TestTemplatesFromPayload:
    def test_returns_empty_when_no_templates(self):
        payload = {"fetch": _acquisition_payload()}

        templates = Tasks.templates_from_payload(payload)

        assert templates == {}

    def test_returns_template_by_name(self):
        payload = {"default": _template_payload()}

        templates = Tasks.templates_from_payload(payload)

        assert "default" in templates

    def test_template_provider_parsed(self):
        payload = {"default": _template_payload(provider="fake")}

        templates = Tasks.templates_from_payload(payload)

        assert templates["default"].provider == "fake"

    def test_template_filters_parsed(self):
        payload = {
            "default": _template_payload(filters={
                "amenity": {"values": ["restaurant"], "type": "heatmap"},
            }),
        }

        templates = Tasks.templates_from_payload(payload)

        assert "amenity" in templates["default"].filters

    def test_template_filter_all_style_fields(self):
        payload = {
            "default": _template_payload(filters={
                "leisure": {
                    "values": ["park"],
                    "name": "Parks",
                    "color": "#007f00",
                    "scale": 2.0,
                    "surface": True,
                    "type": "circle",
                },
            }),
        }

        templates = Tasks.templates_from_payload(payload)
        style = templates["default"].filters["leisure"]

        assert style.values == ["park"]
        assert style.name == "Parks"
        assert style.color == "#007f00"
        assert style.scale == pytest.approx(2.0)
        assert style.surface is True
        assert style.type == "circle"

    def test_multiple_templates(self):
        payload = {
            "default": _template_payload(),
            "minimal": _template_payload(provider="fake"),
        }

        templates = Tasks.templates_from_payload(payload)

        assert len(templates) == 2
        assert "default" in templates
        assert "minimal" in templates

    def test_acquisition_tasks_ignored(self):
        payload = {
            "default": _template_payload(),
            "fetch": _acquisition_payload(),
        }

        templates = Tasks.templates_from_payload(payload)

        assert "fetch" not in templates
        assert "default" in templates
