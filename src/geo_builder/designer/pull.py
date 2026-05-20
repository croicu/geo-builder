from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

from ..diagnostics import Logger

_HEAD_FILES = ("catalog.head.json", "catalog.head.debug.json")
_TIMEOUT = 30


def pull(base_url: str, in_dir: Path) -> None:
    """Fetch all service artifacts into in_dir. Overwrites existing files."""
    base = base_url.rstrip("/") + "/"
    seen: set[str] = set()
    for name in _HEAD_FILES:
        _pull_head(urljoin(base, name), in_dir, seen)


def _pull_head(url: str, in_dir: Path, seen: set[str]) -> None:
    data = _fetch_and_save(url, in_dir, seen)
    if data is None:
        return
    try:
        catalog_rel = json.loads(data).get("catalogUrl", "")
        if catalog_rel:
            _pull_catalog(urljoin(url, catalog_rel), in_dir, seen)
    except Exception as exc:
        Logger.warning(f"pull: head parse '{url}': {exc}")


def _pull_catalog(url: str, in_dir: Path, seen: set[str]) -> None:
    data = _fetch_and_save(url, in_dir, seen)
    if data is None:
        return
    try:
        for area in json.loads(data).get("areas", []):
            rel = area.get("manifestUrl", "")
            if rel:
                _pull_manifest(urljoin(url, rel), in_dir, seen)
    except Exception as exc:
        Logger.warning(f"pull: catalog parse '{url}': {exc}")


def _pull_manifest(url: str, in_dir: Path, seen: set[str]) -> None:
    data = _fetch_and_save(url, in_dir, seen)
    if data is None:
        return
    try:
        for layer in json.loads(data).get("layers", []):
            rel = layer.get("url", "")
            if rel:
                _fetch_and_save(urljoin(url, rel), in_dir, seen)
    except Exception as exc:
        Logger.warning(f"pull: manifest parse '{url}': {exc}")


def _fetch_and_save(url: str, in_dir: Path, seen: set[str]) -> bytes | None:
    if url in seen:
        return None
    seen.add(url)
    path = urlparse(url).path.lstrip("/")
    dest = in_dir / path
    try:
        Logger.info(f"pull: fetch '{url}'")
        resp = requests.get(url, timeout=_TIMEOUT)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        if "json" not in content_type:
            Logger.warning(f"pull: '{url}': unexpected Content-Type '{content_type}', skipping")
            return None
        data = resp.content
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return data
    except Exception as exc:
        Logger.warning(f"pull: '{url}': {exc}")
        return None
