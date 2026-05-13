from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from .contracts import Task
from .errors import TaskError
from .tasks import Tasks


@dataclass
class Settings:
    debug: bool
    tasks: list[Task]
    providers: dict[str, dict[str, object]]

    _instance: ClassVar[Settings | None] = None

    @classmethod
    def load(cls, path: str | Path) -> Settings:
        with Path(path).open("r", encoding="utf-8") as f:
            payload = json.load(f)

        if not isinstance(payload, dict):
            raise TaskError("Settings file must contain a JSON object.")

        settings_payload = payload.get("settings", {})
        if not isinstance(settings_payload, dict):
            raise TaskError("'settings' must be a JSON object.")

        providers_payload = payload.get("providers", {})
        if not isinstance(providers_payload, dict):
            raise TaskError("'providers' must be a JSON object.")

        tasks_payload = payload.get("tasks", {})
        if not isinstance(tasks_payload, dict):
            raise TaskError("'tasks' must be a JSON object.")

        cls._instance = cls(
            debug=bool(settings_payload.get("debug", False)),
            tasks=Tasks.from_payload(tasks_payload),
            providers=providers_payload,
        )

        return cls._instance

    @classmethod
    def current(cls) -> Settings:
        if cls._instance is None:
            raise RuntimeError("Settings.load() must be called first.")
        return cls._instance
