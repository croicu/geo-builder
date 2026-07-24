from datetime import datetime, timezone

import pytest

from geo_builder.diagnostics import ConsoleLogSink, DiagnosticsLogSink, Logger, TelemetryLevel


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
        record = sink.log(TelemetryLevel.INFO, "ts")

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
            ("info", TelemetryLevel.INFO),
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

    def test_log_category_defaults_to_general(self):
        sink = DiagnosticsLogSink()
        record = sink.log(TelemetryLevel.WARNING, "boom")

        sink.drain()
        assert record.category == "general"

    def test_log_category_is_recorded(self):
        sink = DiagnosticsLogSink()
        record = sink.log(TelemetryLevel.WARNING, "boom", category="overpass")

        sink.drain()
        assert record.category == "overpass"

    def test_convenience_methods_pass_through_category(self):
        sink = DiagnosticsLogSink()
        sink.info("msg", category="acquisition")

        record = DiagnosticsLogSink._pending[-1]
        assert record.category == "acquisition"
        sink.drain()


class TestConsoleLogSinkCategoryFiltering:
    def test_no_filter_prints_every_category(self, capsys):
        sink = ConsoleLogSink(min_level=TelemetryLevel.WARNING)
        sink.warning("boom", category="overpass")

        sink.drain()
        assert "boom" in capsys.readouterr().out

    def test_matching_category_prints(self, capsys):
        sink = ConsoleLogSink(min_level=TelemetryLevel.WARNING, categories=["overpass"])
        sink.warning("boom", category="overpass")

        sink.drain()
        assert "boom" in capsys.readouterr().out

    def test_non_matching_category_is_silent(self, capsys):
        sink = ConsoleLogSink(min_level=TelemetryLevel.WARNING, categories=["overpass"])
        sink.warning("boom", category="acquisition")

        sink.drain()
        assert capsys.readouterr().out == ""

    def test_level_filter_still_applies_alongside_category(self, capsys):
        sink = ConsoleLogSink(min_level=TelemetryLevel.ERROR, categories=["overpass"])
        sink.warning("boom", category="overpass")

        sink.drain()
        assert capsys.readouterr().out == ""

    def test_print_format_includes_level_and_category(self, capsys):
        sink = ConsoleLogSink(min_level=TelemetryLevel.WARNING)
        sink.warning("boom", category="overpass")

        sink.drain()
        assert capsys.readouterr().out == "[WARNING][overpass] boom\n"

    def test_print_format_defaults_to_general_category(self, capsys):
        sink = ConsoleLogSink(min_level=TelemetryLevel.WARNING)
        sink.warning("boom")

        sink.drain()
        assert capsys.readouterr().out == "[WARNING][general] boom\n"


class TestConsoleLogSinkExcludedCategories:
    def test_excluded_category_is_silent_when_unfiltered(self, capsys):
        sink = ConsoleLogSink(min_level=TelemetryLevel.WARNING, excluded_categories=["overpass"])
        sink.warning("boom", category="overpass")

        sink.drain()
        assert capsys.readouterr().out == ""

    def test_non_excluded_category_still_prints_when_unfiltered(self, capsys):
        sink = ConsoleLogSink(min_level=TelemetryLevel.WARNING, excluded_categories=["overpass"])
        sink.warning("boom", category="acquisition")

        sink.drain()
        assert "boom" in capsys.readouterr().out

    def test_excluded_categories_inert_alongside_explicit_allow_list(self, capsys):
        """excludedCategories only applies when the sink is otherwise unfiltered (categories=None) —
        an explicit allow-list is never narrowed by it, even if the same category is in both."""
        sink = ConsoleLogSink(min_level=TelemetryLevel.WARNING, categories=["overpass"], excluded_categories=["overpass"])
        sink.warning("boom", category="overpass")

        sink.drain()
        assert "boom" in capsys.readouterr().out


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
