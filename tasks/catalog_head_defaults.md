# Catalog Head Defaults & Path Mirroring

## Status: Done

## Problem Statement

Currently `save_catalog` hard-codes a subdirectory layout (`./release/` or `./debug/`)
and always writes head files pointing there. `load_catalog` requires the head file to
exist or it throws. `pull.py` silently skips a head file if the service returns 404.

The desired behavior:

1. **Head file defaults** — if a head file does not exist on the service, `pull.py`
   writes a local default so `in_dir` always has one after a pull:
   - `catalog.head.json` → `{ "version": 1, "catalogUrl": "./catalog.json" }`
   - `catalog.head.debug.json` → `{ "version": 1, "catalogUrl": "./catalog.debug.json" }`
   Only writes the default if the file does not already exist locally.

2. **`load_catalog` graceful fallback** — if the head file is absent, fall back to
   the default `catalogUrl` instead of throwing.

3. **`save_catalog` mirrors `in_dir`** — instead of hard-coding `./release/` or
   `./debug/`, `save_catalog` reads the `catalogUrl` from `in_dir`'s head file (when
   provided) and writes to the same relative path under `output_dir`. If no `in_dir`
   is given (or no head file exists there), falls back to defaults (`./catalog.json`
   / `./catalog.debug.json`). The head file must be read **before** `_clean_dir` is
   called.

4. **`save_catalog_meta`** — same mirroring logic; reads `catalogUrl` from
   `output_dir`'s head file (already present, no clean step).

5. **Callers updated**:
   - `cli.py` → passes `in_dir=arguments.in_directory` to `save_catalog`
   - `host.py` `_rebuild_area` / `on_add_area` (lines ~155, ~313) → pass
     `in_dir=in_dir` to `save_catalog` for `out_dir` writes
   - `host.py` line ~315 `save_catalog(result, in_dir)` — no change needed; reads
     head from `output_dir` (which is `in_dir`) before cleaning

## Decisions

- Default URLs: `./catalog.json` (release), `./catalog.debug.json` (debug) — flat
  layout alongside the head files.
- `pull.py` writes default only if file does not exist (incremental pulls that get
  404 do not overwrite an existing local head file).
- `save_catalog` signature: add optional `in_dir: str | Path | None = None` parameter.
- `save_catalog_meta` signature: no new parameter needed (always writes to the same
  dir it reads from).
- Remove `_CATALOG_FILENAME` constant (no longer a single fixed name); replace with
  `_DEFAULT_CATALOG_URL` and `_DEFAULT_CATALOG_URL_DEBUG`.
- `catalog_dir` ("release"/"debug") variable eliminated from `save_catalog` and
  `save_catalog_meta`.

## Files Affected

| File | Change |
|---|---|
| `src/geo_builder/persistence.py` | Add defaults, `_resolve_catalog_url()` helper, update `load_catalog`, `save_catalog`, `save_catalog_meta` |
| `src/geo_builder/designer/pull.py` | Write default head file on 404 |
| `src/geo_builder/cli.py` | Pass `in_dir` to `save_catalog` |
| `src/geo_builder/designer/host.py` | Pass `in_dir` to `save_catalog` calls that write to `out_dir` |
| `tests/` | Update path expectations from `out/release/...` to `out/...` |

## Implementation Plan

### 1. `persistence.py`

```python
_CATALOG_HEAD = "catalog.head.json"
_CATALOG_HEAD_DEBUG = "catalog.head.debug.json"
_DEFAULT_CATALOG_URL = "./catalog.json"
_DEFAULT_CATALOG_URL_DEBUG = "./catalog.debug.json"

def _default_catalog_url(debug: bool) -> str:
    return _DEFAULT_CATALOG_URL_DEBUG if debug else _DEFAULT_CATALOG_URL

def _resolve_catalog_url(directory: Path, debug: bool) -> str:
    head_name = _CATALOG_HEAD_DEBUG if debug else _CATALOG_HEAD
    head_path = directory / head_name
    if not head_path.exists():
        return _default_catalog_url(debug)
    try:
        payload = read_json(head_path)
        if isinstance(payload, dict):
            url = str(payload.get("catalogUrl", ""))
            if url:
                return url
    except Exception:
        pass
    return _default_catalog_url(debug)
```

`load_catalog`: replace `read_json(input_dir / catalog_head_path)` + the missing-key
error with `_resolve_catalog_url(input_dir, debug)`.

`save_catalog(geo_catalog, output_dir, debug=False, in_dir=None)`:
1. `source_dir = Path(in_dir) if in_dir else Path(output_dir)`
2. `catalog_url = _resolve_catalog_url(source_dir, debug)` — before `_clean_dir`
3. `_clean_dir(output_dir)`
4. Write head file: `save_json(output_dir / head_name, {"version": 1, "catalogUrl": catalog_url})`
5. `catalog_path = child_path(output_dir, catalog_url)`
6. Write catalog JSON to `catalog_path`
7. `catalog_base = catalog_path.parent`
8. Iterate areas: `geo_area.save(catalog_base)`; `save_area_csv(geo_area, catalog_base)`

`save_catalog_meta(geo_catalog, output_dir, debug=False)`:
1. `catalog_url = _resolve_catalog_url(Path(output_dir), debug)` — no clean, file exists
2. Write head file and catalog JSON using same relative path logic

### 2. `pull.py`

Add:
```python
_HEAD_DEFAULTS = {
    "catalog.head.json": {"version": 1, "catalogUrl": "./catalog.json"},
    "catalog.head.debug.json": {"version": 1, "catalogUrl": "./catalog.debug.json"},
}
```

In `_pull_head`: if `_fetch_and_save` returns `None`, check if the file exists
locally; if not, write the default and still attempt to pull the default `catalogUrl`.

### 3. `cli.py`

```python
save_catalog(geo_catalog, arguments.out_directory, debug=settings.debug, in_dir=arguments.in_directory)
```

### 4. `host.py`

Lines ~155 and ~313:
```python
save_catalog(result, out_dir, debug=debug, in_dir=in_dir)
```
Lines ~314-315 (`if in_dir is not None: save_catalog(result, in_dir, ...)`): **removed**.
`save_catalog` cleans and writes `out_dir` only; `in_dir` is read-only for structure.

### 5. Tests

Any test asserting `out/release/catalog.json` or `out/debug/catalog.json` must be
updated to `out/catalog.json` or `out/catalog.debug.json` respectively, unless the
test explicitly provides a custom head file.
