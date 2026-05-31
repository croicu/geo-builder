from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from .diagnostics import TelemetryLevel
from .errors import TaskError

_SETTINGS_PATH = Path("./settings.json")
_LOCAL_PATH = Path("./settings.local.json")


@dataclass
class Settings:
    debug: bool
    providers: dict[str, dict[str, object]]
    template: dict | None = None
    break_on_load: bool = False
    dev_tools: bool = False
    design_url: str | None = None
    logging: TelemetryLevel = TelemetryLevel.ERROR
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
        providers: dict[str, dict[str, object]] = {}
        log_level = TelemetryLevel.ERROR
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

            if debug and design_url is not None:
                sep = "&" if "?" in design_url else "?"
                design_url = f"{design_url}{sep}debug=1"

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
            template=template,
            providers=providers,
            logging=log_level,
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
