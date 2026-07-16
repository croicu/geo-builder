import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from geo_builder.cli import CliArguments, main, parse_args
from geo_builder.entities import GeoCatalog
from geo_builder.errors import GeoError


class StubSettings:
    def __init__(
        self,
        debug: bool = False,
        design_url: str | None = None,
        break_on_load: bool = False,
        dev_tools: bool = False,
        logging=None,
        assets_url: str | None = None,
    ) -> None:
        from geo_builder.diagnostics import TelemetryLevel

        self.debug = debug
        self.design_url = design_url
        self.break_on_load = break_on_load
        self.dev_tools = dev_tools
        self.logging = logging or TelemetryLevel.ERROR
        self.assets_url = assets_url


class StubBuilder:
    def __init__(self, errors: list[str] | None = None, raises: Exception | None = None) -> None:
        self.errors = errors or []
        self._raises = raises
        self.catalog = GeoCatalog()
        self.run_rebuild_areas: list[str] | None = None

    def run(self, rebuild_areas: list[str] | None = None) -> GeoCatalog:
        self.run_rebuild_areas = rebuild_areas
        if self._raises:
            raise self._raises
        return self.catalog


class TestParseArgs:
    def test_tasks_path_parsed(self):
        args = parse_args(["template.json"])

        assert args.tasks_path == Path("template.json")

    def test_edit_defaults_to_false(self):
        args = parse_args(["template.json"])

        assert args.edit is False

    def test_edit_flag_parsed(self):
        args = parse_args(["template.json", "--edit"])

        assert args.edit is True

    def test_in_directory_defaults_to_none(self):
        args = parse_args(["template.json"])

        assert args.in_directory is None

    def test_noninvasive_defaults_to_false(self):
        args = parse_args(["template.json"])

        assert args.noninvasive is False

    def test_noninvasive_flag_parsed(self):
        args = parse_args(["template.json", "--noninvasive"])

        assert args.noninvasive is True

    def test_out_directory_defaults_to_out(self):
        args = parse_args(["template.json"])

        assert args.out_directory == Path("./out")

    def test_in_directory_parsed(self):
        args = parse_args(["template.json", "--in", "/tmp/in"])

        assert args.in_directory == Path("/tmp/in")

    def test_out_directory_parsed(self):
        args = parse_args(["template.json", "--out", "/tmp/out"])

        assert args.out_directory == Path("/tmp/out")

    def test_returns_cli_arguments(self):
        assert isinstance(parse_args(["template.json"]), CliArguments)

    def test_rebuild_areas_defaults_to_none(self):
        args = parse_args(["template.json"])

        assert args.rebuild_areas is None

    def test_rebuild_areas_single(self):
        args = parse_args(["template.json", "--rebuild", "prague"])

        assert args.rebuild_areas == ["prague"]

    def test_rebuild_areas_repeated_flag(self):
        args = parse_args(["template.json", "--rebuild", "prague", "--rebuild", "berlin"])

        assert args.rebuild_areas == ["prague", "berlin"]


class TestMain:
    @pytest.fixture(autouse=True)
    def argv(self):
        original = sys.argv
        sys.argv = ["geo-builder", "template.json", "--in", "/tmp/in", "--out", "/tmp/out"]
        yield
        sys.argv = original

    def test_returns_0_on_success(self):
        builder = StubBuilder()

        with patch("geo_builder.cli.Settings") as MockSettings, patch("geo_builder.cli.Builder", return_value=builder), patch("geo_builder.cli.save_catalog"):
            MockSettings.load.return_value = StubSettings()

            assert main() == 0

    def test_save_catalog_called_with_out_directory(self):
        builder = StubBuilder()

        with (
            patch("geo_builder.cli.Settings") as MockSettings,
            patch("geo_builder.cli.Builder", return_value=builder),
            patch("geo_builder.cli.save_catalog") as mock_save,
        ):
            MockSettings.load.return_value = StubSettings()

            main()

            mock_save.assert_called_once_with(builder.catalog, Path("/tmp/out"), in_dir=Path("/tmp/in"))

    def test_settings_load_error_returns_1(self, capsys):
        with patch("geo_builder.cli.Settings") as MockSettings:
            MockSettings.load.side_effect = GeoError("bad config")

            assert main() == 1

        assert "bad config" in capsys.readouterr().err

    def test_builder_errors_returns_1(self, capsys):
        builder = StubBuilder(errors=["something failed"])

        with patch("geo_builder.cli.Settings") as MockSettings, patch("geo_builder.cli.Builder", return_value=builder), patch("geo_builder.cli.save_catalog"):
            MockSettings.load.return_value = StubSettings()

            assert main() == 1

        assert "something failed" in capsys.readouterr().err

    def test_missing_in_directory_returns_1(self, capsys):
        sys.argv = ["geo-builder", "template.json", "--out", "/tmp/out"]

        with patch("geo_builder.cli.Settings") as MockSettings:
            MockSettings.load.return_value = StubSettings()

            assert main() == 1

        assert "--in" in capsys.readouterr().err

    def test_in_directory_loads_catalog(self):
        sys.argv = ["geo-builder", "template.json", "--in", "/tmp/in", "--out", "/tmp/out"]
        loaded_catalog = GeoCatalog()

        with (
            patch("geo_builder.cli.Settings") as MockSettings,
            patch("geo_builder.cli.Builder") as MockBuilder,
            patch("geo_builder.cli.load_catalog", return_value=loaded_catalog),
            patch("geo_builder.cli.save_catalog"),
        ):
            MockSettings.load.return_value = StubSettings()
            MockBuilder.return_value = StubBuilder()

            main()

            MockBuilder.assert_called_once_with(loaded_catalog)

    def test_empty_in_directory_creates_empty_builder(self):
        with (
            patch("geo_builder.cli.Settings") as MockSettings,
            patch("geo_builder.cli.Builder") as MockBuilder,
            patch("geo_builder.cli.load_catalog", side_effect=GeoError("not found")),
            patch("geo_builder.cli.save_catalog"),
        ):
            MockSettings.load.return_value = StubSettings()
            MockBuilder.return_value = StubBuilder()

            main()

            MockBuilder.assert_called_once_with()

    def test_geo_error_in_non_debug_mode_returns_1(self, capsys):
        builder = StubBuilder(raises=GeoError("run failed"))

        with patch("geo_builder.cli.Settings") as MockSettings, patch("geo_builder.cli.Builder", return_value=builder), patch("geo_builder.cli.save_catalog"):
            MockSettings.load.return_value = StubSettings()

            assert main() == 1

        assert "run failed" in capsys.readouterr().err

    def test_geo_error_in_debug_mode_reraises(self):
        builder = StubBuilder(raises=GeoError("run failed"))

        with patch("geo_builder.cli.Settings") as MockSettings, patch("geo_builder.cli.Builder", return_value=builder), patch("geo_builder.cli.save_catalog"):
            MockSettings.load.return_value = StubSettings(debug=True)

            with pytest.raises(GeoError):
                main()

    def test_rebuild_areas_passed_through_to_builder_run(self):
        sys.argv = ["geo-builder", "template.json", "--in", "/tmp/in", "--out", "/tmp/out", "--rebuild", "prague", "--rebuild", "berlin"]
        builder = StubBuilder()

        with patch("geo_builder.cli.Settings") as MockSettings, patch("geo_builder.cli.Builder", return_value=builder), patch("geo_builder.cli.save_catalog"):
            MockSettings.load.return_value = StubSettings()

            assert main() == 0

        assert builder.run_rebuild_areas == ["prague", "berlin"]

    def test_rebuild_all_combined_with_specific_id_returns_1(self, capsys):
        sys.argv = ["geo-builder", "template.json", "--in", "/tmp/in", "--out", "/tmp/out", "--rebuild", "all", "--rebuild", "prague"]

        with patch("geo_builder.cli.Settings") as MockSettings:
            MockSettings.load.return_value = StubSettings()

            assert main() == 1

        assert "--rebuild all" in capsys.readouterr().err


class TestDesignMode:
    @pytest.fixture(autouse=True)
    def argv(self):
        original = sys.argv
        sys.argv = ["geo-builder", "template.json", "--edit"]
        yield
        sys.argv = original

    def test_launches_webview_with_design_url(self):
        with patch("geo_builder.cli.Settings") as MockSettings, patch("geo_builder.cli._launch_designer") as mock_launch:
            MockSettings.load.return_value = StubSettings(design_url="http://localhost:5173/")

            result = main()

            from geo_builder.diagnostics import TelemetryLevel

            mock_launch.assert_called_once_with(
                "http://localhost:5173/",
                catalog=mock_launch.call_args.kwargs["catalog"],
                out_dir=Path("./out"),
                in_dir=Path("./in"),
                debug=False,
                break_on_load=False,
                dev_tools=False,
                log_level=TelemetryLevel.ERROR,
                noninvasive=False,
                assets_url=None,
            )
            assert result == 0

    def test_assets_url_passed_through_to_launch_designer(self):
        with patch("geo_builder.cli.Settings") as MockSettings, patch("geo_builder.cli._launch_designer") as mock_launch:
            MockSettings.load.return_value = StubSettings(design_url="http://localhost:5173/", assets_url="http://localhost:5174/")

            main()

            assert mock_launch.call_args.kwargs["assets_url"] == "http://localhost:5174/"

    def test_no_design_url_returns_1(self, capsys):
        with patch("geo_builder.cli.Settings") as MockSettings:
            MockSettings.load.return_value = StubSettings(design_url=None)

            assert main() == 1

        assert "designUrl" in capsys.readouterr().err

    def test_rebuild_with_edit_returns_1(self, capsys):
        sys.argv = ["geo-builder", "template.json", "--edit", "--rebuild", "prague"]

        with patch("geo_builder.cli.Settings") as MockSettings:
            MockSettings.load.return_value = StubSettings(design_url="http://localhost:5173/")

            assert main() == 1

        assert "--rebuild" in capsys.readouterr().err
