from geo_builder import diagnostics, errors


class TestError:
    def test_error_creates_record(self):
        exc = errors.GeoError("something failed")
        assert exc.record.message == "something failed"
        assert exc.record.level == diagnostics.TelemetryLevel.WARNING
