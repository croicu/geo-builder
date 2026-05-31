from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, NamedTuple
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


class PipelineResult(NamedTuple):
    data: bytes
    content_type: str
    cache_control: str | None  # None = omit header; non-None = use this value


class DataPipeline:
    def __init__(self, out_dir: Path, in_dir: Path | None) -> None:
        self._out_dir = out_dir
        self._in_dir = in_dir
        self._memory: dict[str, bytes] = {}

    def set(self, url: str, data: bytes) -> None:
        """Store data in L1 memory for the given URL (in-session edits)."""
        self._memory[_to_path(url)] = data

    def handle(self, url: str, complete: Callable[[PipelineResult | None], None]) -> None:
        threading.Thread(target=self._run, args=(url, complete), daemon=True).start()

    def _run(self, url: str, complete: Callable[[PipelineResult | None], None]) -> None:
        result = None
        try:
            result = self._resolve(url)
        except Exception as exc:
            Logger.warning(f"data pipeline: '{url}': {exc}")
        complete(result)

    def _resolve(self, url: str) -> PipelineResult | None:
        path = _to_path(url)

        data = self._memory.get(path)
        if data is not None:
            Logger.info(f"data pipeline: memory '{url}'")
            return PipelineResult(data, _JSON, cache_control="no-store")

        out_path = self._out_dir / path
        data = _read_file(out_path)
        if data is not None:
            Logger.info(f"data pipeline: out path '{url}', {out_path}")
            return PipelineResult(data, _JSON, cache_control="no-store")

        if self._in_dir is not None:
            in_path = self._in_dir / path
            data = _read_file(in_path)
            if data is not None:
                Logger.info(f"data pipeline: in path '{url}', {in_path}")
                return PipelineResult(data, _JSON, cache_control="no-store")

        return _from_network(url)


def _from_network(url: str) -> PipelineResult | None:
    try:
        Logger.info(f"data pipeline: network '{url}'")
        resp = _session.get(url, timeout=_TIMEOUT)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", _JSON).split(";")[0].strip()
        cache_control = resp.headers.get("Cache-Control")
        return PipelineResult(resp.content, content_type, cache_control=cache_control)
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
