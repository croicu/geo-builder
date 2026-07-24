from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from .diagnostics import CATEGORY_GENERAL, TelemetryLevel
from .errors import TaskError

_SETTINGS_PATH = Path("./settings.json")
_LOCAL_PATH = Path("./settings.local.json")


@dataclass
class Settings:
    debug: bool
    providers: dict[str, dict[str, object]]
    group: list[str] = field(default_factory=list)
    template: dict | None = None
    break_on_load: bool = False
    dev_tools: bool = False
    design_url: str | None = None
    assets_url: str | None = None
    logging: TelemetryLevel = TelemetryLevel.ERROR
    log_categories: list[str] = field(default_factory=list)
    excluded_categories: list[str] = field(default_factory=list)
    window_left: int | None = None
    window_top: int | None = None
    window_width: int | None = None
    window_height: int | None = None

    _instance: ClassVar[Settings | None] = None

    @classmethod
    def load(cls, tasks_path: str | Path | None = None) -> Settings:
        debug = False
        break_on_load = False
        dev_tools = False
        design_url: str | None = None
        assets_url: str | None = None
        group: list[str] = []
        providers: dict[str, dict[str, object]] = {}
        log_level = TelemetryLevel.ERROR
        log_categories: list[str] = []
        excluded_categories: list[str] = []
        window_left: int | None = None
        window_top: int | None = None
        window_width: int | None = None
        window_height: int | None = None

        settings_payload: dict = {}

        if _SETTINGS_PATH.exists():
            with _SETTINGS_PATH.open("r", encoding="utf-8") as f:
                build_payload = json.load(f)
            if not isinstance(build_payload, dict):
                raise TaskError("settings.json must contain a JSON object.")
            base_settings = build_payload.get("settings", {})
            if not isinstance(base_settings, dict):
                raise TaskError("'settings' in settings.json must be a JSON object.")
            providers_payload = build_payload.get("providers", {})
            if not isinstance(providers_payload, dict):
                raise TaskError("'providers' in settings.json must be a JSON object.")
            providers = providers_payload
            settings_payload = dict(base_settings)

        if _LOCAL_PATH.exists():
            with _LOCAL_PATH.open("r", encoding="utf-8") as f:
                local_payload = json.load(f)
            if isinstance(local_payload, dict):
                local_settings = local_payload.get("settings", {})
                if isinstance(local_settings, dict):
                    settings_payload.update(local_settings)
                local_providers = local_payload.get("providers", {})
                if isinstance(local_providers, dict):
                    providers.update(local_providers)

        if settings_payload:
            debug = bool(settings_payload.get("debug", False))
            break_on_load = bool(settings_payload.get("break", False))
            dev_tools = bool(settings_payload.get("devTools", False))
            design_url = str(settings_payload["designUrl"]) if "designUrl" in settings_payload else None
            try:
                log_level = TelemetryLevel(settings_payload.get("logLevel", "error"))
            except ValueError:
                valid_levels = []
                for level in TelemetryLevel:
                    valid_levels.append(level.value)
                raise TaskError(f"'settings.logLevel' in settings.json must be one of: {', '.join(valid_levels)}")

            log_categories_payload = settings_payload.get("logCategories", [])
            if not isinstance(log_categories_payload, list):
                raise TaskError("'settings.logCategories' in settings.json must be an array of strings.")
            log_categories = []
            for category_name in log_categories_payload:
                log_categories.append(str(category_name))

            if log_categories:
                # debug=true always keeps CATEGORY_GENERAL alongside an explicit narrower list —
                # debug mode's baseline info should stay visible even while zoomed into one
                # category, not be silently dropped by naming a single other category.
                if debug and CATEGORY_GENERAL not in log_categories:
                    log_categories = [CATEGORY_GENERAL] + log_categories

                # Only an explicit, non-empty logCategories is forwarded to geo-browser — the
                # debug-gated default applied below is a geo-builder-console-only concern.
                # geo-browser already defaults to "general"-only without any query param, and
                # debug=1 (appended just below) already makes it show everything on its own, so
                # there is nothing to add for the common (non-explicit) case.
                if design_url is not None:
                    sep = "&" if "?" in design_url else "?"
                    design_url = f"{design_url}{sep}logCategory={','.join(log_categories)}"

            if debug and design_url is not None:
                sep = "&" if "?" in design_url else "?"
                design_url = f"{design_url}{sep}debug=1"

            excluded_categories_payload = settings_payload.get("excludedCategories", [])
            if not isinstance(excluded_categories_payload, list):
                raise TaskError("'settings.excludedCategories' in settings.json must be an array of strings.")
            excluded_categories = []
            for category_name in excluded_categories_payload:
                excluded_categories.append(str(category_name))

            if excluded_categories and design_url is not None:
                sep = "&" if "?" in design_url else "?"
                design_url = f"{design_url}{sep}logCategoryExclude={','.join(excluded_categories)}"

            group_payload = settings_payload.get("group", [])
            if not isinstance(group_payload, list):
                raise TaskError("'settings.group' in settings.json must be an array of strings.")
            group = []
            for group_name in group_payload:
                group.append(str(group_name))

            if group and design_url is not None:
                sep = "&" if "?" in design_url else "?"
                design_url = f"{design_url}{sep}group={','.join(group)}"

            assets_url = str(settings_payload["assetsUrl"]) if "assetsUrl" in settings_payload else None
            if assets_url is not None and design_url is not None:
                sep = "&" if "?" in design_url else "?"
                design_url = f"{design_url}{sep}assetsBase={assets_url}"

            map_payload = settings_payload.get("map", {})
            if isinstance(map_payload, dict) and design_url is not None:
                map_center = map_payload.get("center")
                map_zoom = map_payload.get("zoom")
                sep = "&" if "?" in design_url else "?"
                if map_center is not None:
                    design_url = f"{design_url}{sep}center={map_center}"
                    sep = "&"
                if map_zoom is not None:
                    design_url = f"{design_url}{sep}zoom={map_zoom}"

            window_payload = settings_payload.get("window", {})
            if isinstance(window_payload, dict):
                raw_left = window_payload.get("left")
                raw_top = window_payload.get("top")
                raw_width = window_payload.get("width")
                raw_height = window_payload.get("height")
                window_left = int(raw_left) if raw_left is not None else None
                window_top = int(raw_top) if raw_top is not None else None
                window_width = int(raw_width) if raw_width is not None else None
                window_height = int(raw_height) if raw_height is not None else None

        if not log_categories:
            # No explicit override: debug=false restricts console noise to CATEGORY_GENERAL
            # (matching geo-browser's own default-to-general behavior); debug=true shows
            # everything, same as an empty filter always has.
            log_categories = [] if debug else [CATEGORY_GENERAL]

        template: dict | None = None
        if tasks_path is not None:
            with Path(tasks_path).open("r", encoding="utf-8") as f:
                template_payload = json.load(f)
            if not isinstance(template_payload, dict):
                raise TaskError("Template file must contain a JSON object.")
            template = template_payload

        cls._instance = cls(
            debug=debug,
            break_on_load=break_on_load,
            dev_tools=dev_tools,
            design_url=design_url,
            assets_url=assets_url,
            group=group,
            template=template,
            providers=providers,
            logging=log_level,
            log_categories=log_categories,
            excluded_categories=excluded_categories,
            window_left=window_left,
            window_top=window_top,
            window_width=window_width,
            window_height=window_height,
        )

        return cls._instance

    @classmethod
    def save_local(cls, left: int, top: int, width: int, height: int) -> None:
        local: dict = {}
        if _LOCAL_PATH.exists():
            with _LOCAL_PATH.open("r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                local = loaded
        settings_section = local.get("settings", {})
        if not isinstance(settings_section, dict):
            settings_section = {}
        settings_section["window"] = {"left": left, "top": top, "width": width, "height": height}
        local["settings"] = settings_section
        with _LOCAL_PATH.open("w", encoding="utf-8") as f:
            json.dump(local, f, indent=2)

    @classmethod
    def current(cls) -> Settings:
        if cls._instance is None:
            raise RuntimeError("Settings.load() must be called first.")
        return cls._instance
