from datetime import datetime, timezone

import pytest

from geo_builder import diagnostics, errors


class TestError:
    def test_error_creates_record(self):
        exc = errors.GeoError("something failed")
        assert exc.record.message == "something failed"
        assert exc.record.level == diagnostics.TelemetryLevel.WARNING

    def test_record_timestamp_is_utc(self):
        exc = errors.GeoError("ts check")
        assert isinstance(exc.record.timestamp, datetime)
        assert exc.record.timestamp.tzinfo == timezone.utc

    @pytest.mark.parametrize("cls", [
        errors.TaskError,
        errors.CatalogError,
        errors.ProviderError,
        errors.WorkerError,
    ])
    def test_subclasses_are_geo_errors(self, cls):
        exc = cls("sub")
        assert isinstance(exc, errors.GeoError)
        assert exc.record.message == "sub"

    def test_telemetry_session_clears_log(self):
        with errors.telemetry_session():
            errors.GeoError("inside session")

        assert diagnostics.Logger.drain() == []
