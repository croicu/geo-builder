from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from .contracts import Task
from .diagnostics import TelemetryLevel
from .errors import TaskError
from .protocols import Acquisition
from .tasks import Tasks

_BUILD_PATH = Path("./build.json")


@dataclass
class Settings:
    debug: bool
    tasks: list[Task]
    providers: dict[str, dict[str, object]]
    templates: dict[str, Acquisition] = field(default_factory=dict)
    break_on_load: bool = False
    dev_tools: bool = False
    design_url: str | None = None
    logging: TelemetryLevel = TelemetryLevel.ERROR

    _instance: ClassVar[Settings | None] = None

    @classmethod
    def load(cls, tasks_path: str | Path | None = None) -> Settings:
        debug = False
        break_on_load = False
        dev_tools = False
        design_url: str | None = None
        providers: dict[str, dict[str, object]] = {}
        log_level = TelemetryLevel.ERROR

        if _BUILD_PATH.exists():
            with _BUILD_PATH.open("r", encoding="utf-8") as f:
                build_payload = json.load(f)
            if not isinstance(build_payload, dict):
                raise TaskError("build.json must contain a JSON object.")
            settings_payload = build_payload.get("settings", {})
            if not isinstance(settings_payload, dict):
                raise TaskError("'settings' in build.json must be a JSON object.")
            providers_payload = build_payload.get("providers", {})
            if not isinstance(providers_payload, dict):
                raise TaskError("'providers' in build.json must be a JSON object.")
            debug = bool(settings_payload.get("debug", False))
            break_on_load = bool(settings_payload.get("break", False))
            dev_tools = bool(settings_payload.get("devTools", False))
            design_url = str(settings_payload["designUrl"]) if "designUrl" in settings_payload else None
            providers = providers_payload
            try:
                log_level = TelemetryLevel(settings_payload.get("logging", "error"))
            except ValueError:
                raise TaskError(f"'settings.logging' in build.json must be one of: {', '.join(l.value for l in TelemetryLevel)}")

        tasks: list[Task] = []
        templates: dict[str, Acquisition] = {}
        if tasks_path is not None:
            with Path(tasks_path).open("r", encoding="utf-8") as f:
                tasks_payload = json.load(f)
            if not isinstance(tasks_payload, dict):
                raise TaskError("Tasks file must contain a JSON object.")
            tasks = Tasks.from_payload(tasks_payload)
            templates = Tasks.templates_from_payload(tasks_payload)

        cls._instance = cls(
            debug=debug,
            break_on_load=break_on_load,
            dev_tools=dev_tools,
            design_url=design_url,
            tasks=tasks,
            templates=templates,
            providers=providers,
            logging=log_level,
        )

        return cls._instance

    @classmethod
    def current(cls) -> Settings:
        if cls._instance is None:
            raise RuntimeError("Settings.load() must be called first.")
        return cls._instance
