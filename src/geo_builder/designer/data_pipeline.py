from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import requests as _requests
from requests.adapters import HTTPAdapter

from ..diagnostics import Logger

_JSON = "application/json"
_TIMEOUT = 30

_session = _requests.Session()
_session.headers.update({"User-Agent": "GeoBrowser/1.0 (https://github.com/croicu/geo-browser)"})
_session.mount("https://", HTTPAdapter(pool_connections=4, pool_maxsize=16))
_session.mount("http://", HTTPAdapter(pool_connections=4, pool_maxsize=16))


def _to_path(url: str) -> str:
    return urlparse(url).path.lstrip("/")


class DataPipeline:
    def __init__(self, out_dir: Path, in_dir: Path | None) -> None:
        self._out_dir = out_dir
        self._in_dir = in_dir
        self._memory: dict[str, bytes] = {}

    def set(self, url: str, data: bytes) -> None:
        """Store data in L1 memory for the given URL (in-session edits)."""
        self._memory[_to_path(url)] = data

    def handle(self, url: str, complete: Callable[[tuple[bytes, str] | None], None]) -> None:
        threading.Thread(target=self._run, args=(url, complete), daemon=True).start()

    def _run(self, url: str, complete: Callable[[tuple[bytes, str] | None], None]) -> None:
        result = None
        try:
            result = self._resolve(url)
        except Exception as exc:
            Logger.warning(f"data pipeline: '{url}': {exc}")
        complete(result)

    def _resolve(self, url: str) -> tuple[bytes, str] | None:
        path = _to_path(url)

        data = self._memory.get(path)
        if data is not None:
            return data, _JSON

        data = _read_file(self._out_dir / path)
        if data is not None:
            return data, _JSON

        if self._in_dir is not None:
            data = _read_file(self._in_dir / path)
            if data is not None:
                return data, _JSON

        return _from_network(url)


def _from_network(url: str) -> tuple[bytes, str] | None:
    try:
        Logger.info(f"data pipeline: network '{url}'")
        resp = _session.get(url, timeout=_TIMEOUT)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", _JSON).split(";")[0].strip()
        return resp.content, content_type
    except Exception as exc:
        Logger.warning(f"data pipeline: network error '{url}': {exc}")
        return None


def _read_file(path: Path) -> bytes | None:
    try:
        if path.exists() and path.is_file():
            return path.read_bytes()
    except Exception as exc:
        Logger.warning(f"data pipeline: file read '{path}': {exc}")
    return None
