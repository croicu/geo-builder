from __future__ import annotations

import json
from pathlib import Path

from ..errors import ProviderError
from .overpass import OverpassProvider


class FakeProvider(OverpassProvider):
    name = "fake"

    def __init__(self, config: dict[str, object]) -> None:
        data_path = config.get("dataPath")
        if not data_path:
            raise ProviderError("fake requires 'dataPath' in providers config.")
        self._data_path = Path(str(data_path))

    def _execute_query(self, query: str) -> dict:
        with self._data_path.open("r", encoding="utf-8") as f:
            return json.load(f)
