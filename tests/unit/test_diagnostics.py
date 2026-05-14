from datetime import datetime, timezone

import pytest

from geo_builder.diagnostics import DiagnosticsLogSink, Logger, TelemetryLevel


@pytest.fixture(autouse=True)
def clean_log():
    Logger.drain()
    yield
    Logger.drain()


class TestDiagnosticsLogSink:
    def test_log_captures_level_and_message(self):
        sink = DiagnosticsLogSink()
        sink.log(TelemetryLevel.WARNING, "boom")

        messages = sink.drain()
        assert messages == ["boom"]

    def test_log_timestamp_is_utc(self):
        sink = DiagnosticsLogSink()
        record = sink.log(TelemetryLevel.INFORMATIONAL, "ts")

        sink.drain()
        assert isinstance(record.timestamp, datetime)
        assert record.timestamp.tzinfo == timezone.utc

    def test_drain_clears_pending(self):
        sink = DiagnosticsLogSink()
        sink.log(TelemetryLevel.WARNING, "x")
        sink.drain()

        assert sink.drain() == []

    def test_clear_discards_without_returning(self):
        sink = DiagnosticsLogSink()
        sink.log(TelemetryLevel.WARNING, "x")
        sink.clear()

        assert sink.drain() == []

    @pytest.mark.parametrize(
        "method,expected_level",
        [
            ("diagnostic", TelemetryLevel.VERBOSE),
            ("info", TelemetryLevel.INFORMATIONAL),
            ("warning", TelemetryLevel.WARNING),
            ("error", TelemetryLevel.ERROR),
            ("fatal", TelemetryLevel.CRITICAL),
        ],
    )
    def test_convenience_methods_log_correct_level(self, method, expected_level):
        sink = DiagnosticsLogSink()
        getattr(sink, method)("msg")

        record = DiagnosticsLogSink._pending[-1]
        assert record.level == expected_level
        sink.drain()


class TestLogger:
    def test_log_appears_in_drain(self):
        Logger.log(TelemetryLevel.WARNING, "via logger")

        assert Logger.drain() == ["via logger"]

    def test_drain_clears_log(self):
        Logger.log(TelemetryLevel.WARNING, "x")
        Logger.drain()

        assert Logger.drain() == []

    def test_set_logger_pushes_new_sink(self):
        custom = DiagnosticsLogSink()
        Logger.set_logger(custom)
        try:
            Logger.warning("routed")
            assert custom.drain() == ["routed"]
        finally:
            Logger.set_logger(None)

    def test_set_logger_none_restores_previous_sink(self):
        custom = DiagnosticsLogSink()
        Logger.set_logger(custom)
        Logger.set_logger(None)

        # Logger is functional again after the custom sink is popped
        Logger.warning("back to default")
        assert Logger.drain() == ["back to default"]
