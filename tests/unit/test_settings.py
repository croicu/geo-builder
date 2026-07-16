import json

import pytest

from geo_builder.errors import TaskError
from geo_builder.settings import Settings


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    local_path = tmp_path / "settings.local.json"
    monkeypatch.setattr("geo_builder.settings._SETTINGS_PATH", settings_path)
    monkeypatch.setattr("geo_builder.settings._LOCAL_PATH", local_path)
    yield settings_path, local_path
    Settings._instance = None


def _write(path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


class TestGroupParsing:
    def test_group_default_empty(self, isolated_paths):
        settings_path, _ = isolated_paths
        _write(settings_path, {"settings": {}})

        settings = Settings.load()

        assert settings.group == []

    def test_group_parsed_from_settings_json(self, isolated_paths):
        settings_path, _ = isolated_paths
        _write(settings_path, {"settings": {"group": ["debug", "Europe"]}})

        settings = Settings.load()

        assert settings.group == ["debug", "Europe"]

    def test_local_group_overrides_base(self, isolated_paths):
        settings_path, local_path = isolated_paths
        _write(settings_path, {"settings": {"group": ["debug"]}})
        _write(local_path, {"settings": {"group": ["Europe", "Sept_2026_Trip"]}})

        settings = Settings.load()

        assert settings.group == ["Europe", "Sept_2026_Trip"]

    def test_non_list_group_raises(self, isolated_paths):
        settings_path, _ = isolated_paths
        _write(settings_path, {"settings": {"group": "debug"}})

        with pytest.raises(TaskError, match="group"):
            Settings.load()


class TestDesignUrlQueryParams:
    def test_group_appended_when_group_present(self, isolated_paths):
        settings_path, _ = isolated_paths
        _write(settings_path, {"settings": {"group": ["debug", "Europe"], "designUrl": "http://localhost:5173/?design=1"}})

        settings = Settings.load()

        assert settings.design_url == "http://localhost:5173/?design=1&group=debug,Europe"

    def test_single_group_appended_without_comma(self, isolated_paths):
        settings_path, _ = isolated_paths
        _write(settings_path, {"settings": {"group": ["debug"], "designUrl": "http://localhost:5173/?design=1"}})

        settings = Settings.load()

        assert settings.design_url == "http://localhost:5173/?design=1&group=debug"

    def test_group_not_appended_when_group_empty(self, isolated_paths):
        settings_path, _ = isolated_paths
        _write(settings_path, {"settings": {"designUrl": "http://localhost:5173/?design=1"}})

        settings = Settings.load()

        assert settings.design_url == "http://localhost:5173/?design=1"

    def test_debug_appended_when_true(self, isolated_paths):
        settings_path, _ = isolated_paths
        _write(settings_path, {"settings": {"debug": True, "designUrl": "http://localhost:5173/?design=1"}})

        settings = Settings.load()

        assert settings.design_url == "http://localhost:5173/?design=1&debug=1"
        assert settings.debug is True

    def test_debug_not_appended_when_false(self, isolated_paths):
        settings_path, _ = isolated_paths
        _write(settings_path, {"settings": {"debug": False, "designUrl": "http://localhost:5173/?design=1"}})

        settings = Settings.load()

        assert settings.design_url == "http://localhost:5173/?design=1"

    def test_debug_and_group_both_appended(self, isolated_paths):
        settings_path, _ = isolated_paths
        _write(
            settings_path,
            {"settings": {"debug": True, "group": ["debug", "Europe"], "designUrl": "http://localhost:5173/?design=1"}},
        )

        settings = Settings.load()

        assert settings.design_url == "http://localhost:5173/?design=1&debug=1&group=debug,Europe"
