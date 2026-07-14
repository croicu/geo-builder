from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

from ..diagnostics import Logger

_HEAD_FILES = ("catalog.head.json", "catalog.head.debug.json")
_HEAD_DEFAULTS = {
    "catalog.head.json": {"version": 1, "catalogUrl": "./catalog.json"},
    "catalog.head.debug.json": {"version": 1, "catalogUrl": "./catalog.json"},
}
_TIMEOUT = 30


def pull(base_url: str, in_dir: Path) -> None:
    """Fetch all service artifacts into in_dir. Overwrites existing files."""
    base = base_url.rstrip("/") + "/"
    seen: set[str] = set()
    for name in _HEAD_FILES:
        _pull_head(urljoin(base, name), name, in_dir, seen)


def _pull_head(url: str, name: str, in_dir: Path, seen: set[str]) -> None:
    data = _fetch_and_save(url, in_dir, seen)
    if data is None:
        dest = in_dir / name
        if not dest.exists():
            default = _HEAD_DEFAULTS.get(name, {})
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(default, indent=2), encoding="utf-8")
            Logger.info(f"pull: '{name}' not on service, wrote default.")
            catalog_rel = str(default.get("catalogUrl", ""))
            if catalog_rel:
                _pull_catalog(urljoin(url, catalog_rel), in_dir, seen)
        return
    try:
        payload = json.loads(data)
        catalog_rel = payload.get("catalogUrl", "")
        if catalog_rel:
            parsed_catalog = urlparse(catalog_rel)
            if parsed_catalog.scheme:
                local_rel = "./" + parsed_catalog.path.lstrip("/")
                payload["catalogUrl"] = local_rel
                dest = in_dir / name
                dest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                Logger.info(f"pull: '{name}': normalized absolute catalogUrl to '{local_rel}'")
                catalog_rel = local_rel
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
    if dest.exists() and dest.is_file():
        Logger.info(f"pull: '{path}' already present, skipping fetch.")
        return dest.read_bytes()
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
