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


class TestLogCategoriesParsing:
    def test_log_categories_defaults_to_general_when_debug_false(self, isolated_paths):
        settings_path, _ = isolated_paths
        _write(settings_path, {"settings": {}})

        settings = Settings.load()

        assert settings.log_categories == ["general"]

    def test_log_categories_defaults_to_unfiltered_when_debug_true(self, isolated_paths):
        settings_path, _ = isolated_paths
        _write(settings_path, {"settings": {"debug": True}})

        settings = Settings.load()

        assert settings.log_categories == []

    def test_explicit_log_categories_wins_regardless_of_debug(self, isolated_paths):
        settings_path, _ = isolated_paths
        _write(settings_path, {"settings": {"debug": False, "logCategories": ["overpass"]}})

        settings = Settings.load()

        assert settings.log_categories == ["overpass"]

    def test_no_settings_files_defaults_to_general(self, isolated_paths):
        settings = Settings.load()

        assert settings.log_categories == ["general"]

    def test_log_categories_parsed_from_settings_json(self, isolated_paths):
        settings_path, _ = isolated_paths
        _write(settings_path, {"settings": {"logCategories": ["overpass", "acquisition"]}})

        settings = Settings.load()

        assert settings.log_categories == ["overpass", "acquisition"]

    def test_local_log_categories_overrides_base(self, isolated_paths):
        settings_path, local_path = isolated_paths
        _write(settings_path, {"settings": {"logCategories": ["overpass"]}})
        _write(local_path, {"settings": {"logCategories": ["acquisition"]}})

        settings = Settings.load()

        assert settings.log_categories == ["acquisition"]

    def test_non_list_log_categories_raises(self, isolated_paths):
        settings_path, _ = isolated_paths
        _write(settings_path, {"settings": {"logCategories": "overpass"}})

        with pytest.raises(TaskError, match="logCategories"):
            Settings.load()

    def test_explicit_log_categories_appended_to_design_url(self, isolated_paths):
        settings_path, _ = isolated_paths
        _write(
            settings_path,
            {"settings": {"logCategories": ["overpass"], "designUrl": "http://localhost:5173/?design=1"}},
        )

        settings = Settings.load()

        assert settings.design_url == "http://localhost:5173/?design=1&logCategory=overpass"

    def test_multiple_explicit_log_categories_comma_joined(self, isolated_paths):
        settings_path, _ = isolated_paths
        _write(
            settings_path,
            {"settings": {"logCategories": ["overpass", "AreaLifecycle"], "designUrl": "http://localhost:5173/?design=1"}},
        )

        settings = Settings.load()

        assert settings.design_url == "http://localhost:5173/?design=1&logCategory=overpass,AreaLifecycle"

    def test_debug_gated_default_not_appended_to_design_url(self, isolated_paths):
        """The implicit debug-gated default (["general"] or []) is a console-only concern — never sent to geo-browser."""
        settings_path, _ = isolated_paths
        _write(settings_path, {"settings": {"designUrl": "http://localhost:5173/?design=1"}})

        settings = Settings.load()

        assert settings.design_url == "http://localhost:5173/?design=1"
        assert settings.log_categories == ["general"]

    def test_explicit_log_categories_and_debug_both_appended(self, isolated_paths):
        """debug=true keeps CATEGORY_GENERAL alongside an explicit narrower category, in both
        the effective filter and the emitted query string."""
        settings_path, _ = isolated_paths
        _write(
            settings_path,
            {"settings": {"debug": True, "logCategories": ["overpass"], "designUrl": "http://localhost:5173/?design=1"}},
        )

        settings = Settings.load()

        assert settings.log_categories == ["general", "overpass"]
        assert settings.design_url == "http://localhost:5173/?design=1&logCategory=general,overpass&debug=1"

    def test_explicit_log_categories_without_debug_does_not_add_general(self, isolated_paths):
        settings_path, _ = isolated_paths
        _write(
            settings_path,
            {"settings": {"debug": False, "logCategories": ["overpass"], "designUrl": "http://localhost:5173/?design=1"}},
        )

        settings = Settings.load()

        assert settings.log_categories == ["overpass"]
        assert settings.design_url == "http://localhost:5173/?design=1&logCategory=overpass"

    def test_explicit_general_and_debug_not_duplicated(self, isolated_paths):
        settings_path, _ = isolated_paths
        _write(settings_path, {"settings": {"debug": True, "logCategories": ["general", "overpass"]}})

        settings = Settings.load()

        assert settings.log_categories == ["general", "overpass"]


class TestExcludedCategoriesParsing:
    def test_defaults_to_empty(self, isolated_paths):
        settings_path, _ = isolated_paths
        _write(settings_path, {"settings": {}})

        settings = Settings.load()

        assert settings.excluded_categories == []

    def test_parsed_from_settings_json(self, isolated_paths):
        settings_path, _ = isolated_paths
        _write(settings_path, {"settings": {"excludedCategories": ["overpass", "AreaLifecycle"]}})

        settings = Settings.load()

        assert settings.excluded_categories == ["overpass", "AreaLifecycle"]

    def test_local_overrides_base(self, isolated_paths):
        settings_path, local_path = isolated_paths
        _write(settings_path, {"settings": {"excludedCategories": ["overpass"]}})
        _write(local_path, {"settings": {"excludedCategories": ["acquisition"]}})

        settings = Settings.load()

        assert settings.excluded_categories == ["acquisition"]

    def test_non_list_raises(self, isolated_paths):
        settings_path, _ = isolated_paths
        _write(settings_path, {"settings": {"excludedCategories": "overpass"}})

        with pytest.raises(TaskError, match="excludedCategories"):
            Settings.load()

    def test_does_not_affect_log_categories(self, isolated_paths):
        settings_path, _ = isolated_paths
        _write(settings_path, {"settings": {"debug": True, "logCategories": ["overpass"], "excludedCategories": ["overpass"]}})

        settings = Settings.load()

        assert settings.log_categories == ["general", "overpass"]
        assert settings.excluded_categories == ["overpass"]


class TestExcludedCategoriesQueryParam:
    def test_appended_when_non_empty(self, isolated_paths):
        settings_path, _ = isolated_paths
        _write(
            settings_path,
            {"settings": {"excludedCategories": ["overpass"], "designUrl": "http://localhost:5173/?design=1"}},
        )

        settings = Settings.load()

        assert settings.design_url == "http://localhost:5173/?design=1&logCategoryExclude=overpass"

    def test_multiple_comma_joined(self, isolated_paths):
        settings_path, _ = isolated_paths
        _write(
            settings_path,
            {
                "settings": {
                    "excludedCategories": ["overpass", "AreaLifecycle"],
                    "designUrl": "http://localhost:5173/?design=1",
                }
            },
        )

        settings = Settings.load()

        assert settings.design_url == "http://localhost:5173/?design=1&logCategoryExclude=overpass,AreaLifecycle"

    def test_not_appended_when_empty(self, isolated_paths):
        settings_path, _ = isolated_paths
        _write(settings_path, {"settings": {"designUrl": "http://localhost:5173/?design=1"}})

        settings = Settings.load()

        assert settings.design_url == "http://localhost:5173/?design=1"

    def test_appended_independent_of_explicit_log_categories(self, isolated_paths):
        """excludedCategories is forwarded whenever non-empty, even without an explicit logCategories —
        unlike ?logCategory=, which only appears when logCategories itself was explicit."""
        settings_path, _ = isolated_paths
        _write(
            settings_path,
            {"settings": {"debug": True, "excludedCategories": ["overpass"], "designUrl": "http://localhost:5173/?design=1"}},
        )

        settings = Settings.load()

        assert settings.design_url == "http://localhost:5173/?design=1&debug=1&logCategoryExclude=overpass"


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
