from geo_builder.api import (
    OK,
    WRITE_TELEMETRY_RECORD_ID,
    WriteTelemetryRecordInput,
    WriteTelemetryRecordOutput,
)


class TestWriteTelemetryRecordApi:
    def test_id(self):
        assert WRITE_TELEMETRY_RECORD_ID == "__geo_write_telemetry_record__"

    def test_output_defaults(self):
        out = WriteTelemetryRecordOutput(error=OK)
        assert out.error == OK
        assert out.errorDescription is None

    def test_input_props_defaults_to_none(self):
        inp = WriteTelemetryRecordInput(
            timestamp="2026-07-23T00:00:00Z",
            level="error",
            category="general",
            message="image_overlay.paste.error",
            errorDetail=None,
        )
        assert inp.props is None

    def test_input_shape_with_props_and_error_detail(self):
        inp = WriteTelemetryRecordInput(
            timestamp="2026-07-23T00:00:00Z",
            level="fatal",
            category="general",
            message="uncaught exception",
            errorDetail="TypeError: boom\n  at ...",
            props={"areaId": "redmond"},
        )
        assert inp.level == "fatal"
        assert inp.category == "general"
        assert inp.errorDetail == "TypeError: boom\n  at ..."
        assert inp.props == {"areaId": "redmond"}

    def test_input_constructible_from_gateway_dict(self):
        """Gateway dispatch does WriteTelemetryRecordInput(**data); omitted optional keys must not error."""
        data = {
            "timestamp": "2026-07-23T00:00:00Z",
            "level": "warning",
            "category": "overpass",
            "message": "retrying request",
            "errorDetail": None,
        }
        inp = WriteTelemetryRecordInput(**data)
        assert inp.props is None
        assert inp.category == "overpass"
