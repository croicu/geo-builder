import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from geo_builder.cli import CliArguments, main, parse_args
from geo_builder.errors import GeoError
from geo_builder.protocols import Catalog, Result


class StubSettings:
    def __init__(self, debug: bool = False) -> None:
        self.debug = debug


class StubBuilder:
    def __init__(self, errors: list[str] | None = None, raises: Exception | None = None) -> None:
        self.errors = errors or []
        self._raises = raises
        self.catalog = Catalog()

    def run(self) -> Result:
        if self._raises:
            raise self._raises
        return Result(catalog=self.catalog)


class TestParseArgs:
    def test_settings_path_parsed(self):
        args = parse_args(["build.json"])

        assert args.settings_path == Path("build.json")

    def test_in_directory_defaults_to_none(self):
        args = parse_args(["build.json"])

        assert args.in_directory is None

    def test_out_directory_defaults_to_current(self):
        args = parse_args(["build.json"])

        assert args.out_directory == Path("./")

    def test_in_directory_parsed(self):
        args = parse_args(["build.json", "--in", "/tmp/in"])

        assert args.in_directory == Path("/tmp/in")

    def test_out_directory_parsed(self):
        args = parse_args(["build.json", "--out", "/tmp/out"])

        assert args.out_directory == Path("/tmp/out")

    def test_returns_cli_arguments(self):
        assert isinstance(parse_args(["build.json"]), CliArguments)


class TestMain:
    @pytest.fixture(autouse=True)
    def argv(self):
        original = sys.argv
        sys.argv = ["geo-builder", "build.json", "--out", "/tmp/out"]
        yield
        sys.argv = original

    def test_returns_0_on_success(self):
        builder = StubBuilder()

        with patch("geo_builder.cli.Settings") as MockSettings, \
             patch("geo_builder.cli.Builder", return_value=builder), \
             patch("geo_builder.cli.save_catalog"):
            MockSettings.load.return_value = StubSettings()

            assert main() == 0

    def test_save_catalog_called_with_out_directory(self):
        builder = StubBuilder()

        with patch("geo_builder.cli.Settings") as MockSettings, \
             patch("geo_builder.cli.Builder", return_value=builder), \
             patch("geo_builder.cli.save_catalog") as mock_save:
            MockSettings.load.return_value = StubSettings()

            main()

            mock_save.assert_called_once_with(builder.catalog, Path("/tmp/out"))

    def test_settings_load_error_returns_1(self, capsys):
        with patch("geo_builder.cli.Settings") as MockSettings:
            MockSettings.load.side_effect = GeoError("bad config")

            assert main() == 1

        assert "bad config" in capsys.readouterr().err

    def test_builder_errors_returns_1(self, capsys):
        builder = StubBuilder(errors=["something failed"])

        with patch("geo_builder.cli.Settings") as MockSettings, \
             patch("geo_builder.cli.Builder", return_value=builder), \
             patch("geo_builder.cli.save_catalog"):
            MockSettings.load.return_value = StubSettings()

            assert main() == 1

        assert "something failed" in capsys.readouterr().err

    def test_in_directory_loads_catalog(self):
        sys.argv = ["geo-builder", "build.json", "--in", "/tmp/in", "--out", "/tmp/out"]
        loaded_catalog = Catalog()

        with patch("geo_builder.cli.Settings") as MockSettings, \
             patch("geo_builder.cli.Builder") as MockBuilder, \
             patch("geo_builder.cli.load_catalog", return_value=loaded_catalog), \
             patch("geo_builder.cli.save_catalog"):
            MockSettings.load.return_value = StubSettings()
            MockBuilder.return_value = StubBuilder()

            main()

            MockBuilder.assert_called_once_with(loaded_catalog)

    def test_no_in_directory_creates_empty_builder(self):
        with patch("geo_builder.cli.Settings") as MockSettings, \
             patch("geo_builder.cli.Builder") as MockBuilder, \
             patch("geo_builder.cli.save_catalog"):
            MockSettings.load.return_value = StubSettings()
            MockBuilder.return_value = StubBuilder()

            main()

            MockBuilder.assert_called_once_with()

    def test_geo_error_in_non_debug_mode_returns_1(self, capsys):
        builder = StubBuilder(raises=GeoError("run failed"))

        with patch("geo_builder.cli.Settings") as MockSettings, \
             patch("geo_builder.cli.Builder", return_value=builder), \
             patch("geo_builder.cli.save_catalog"):
            MockSettings.load.return_value = StubSettings()

            assert main() == 1

        assert "run failed" in capsys.readouterr().err

    def test_geo_error_in_debug_mode_reraises(self):
        builder = StubBuilder(raises=GeoError("run failed"))

        with patch("geo_builder.cli.Settings") as MockSettings, \
             patch("geo_builder.cli.Builder", return_value=builder), \
             patch("geo_builder.cli.save_catalog"):
            MockSettings.load.return_value = StubSettings(debug=True)

            with pytest.raises(GeoError):
                main()
