# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Mission

Build a simple, deterministic Python application that creates static geographic datasets for the geo ecosystem.

## Collaboration rules

- Before implementing any feature or non-trivial change, ask clarifying questions until the intent is unambiguous.
- If anything is unclear or could be interpreted multiple ways, ask — do not assume and implement.

### Task workflow

For any non-trivial feature or change, follow these stages:

1. **Brainstorm** — create a `Current Task` entry in `CLAUDE.md` with `Status: Brainstorm`. Create `tasks/<task-name>.md` with the problem statement. Update `tasks/<task-name>.md` with conclusions as the design discussion progresses.
2. **Implementation** — advance status to `Implementation`. Add an implementation plan to `tasks/<task-name>.md`. Write the code.
3. **Testing** — advance status to `Testing`. Verify correctness; update task file with test results and any open issues.
4. **Ready to Submit** — advance status to `Ready to Submit`. Run lint + tests; confirm docs are up to date.
5. **Done** — advance status to `Done` after merge/close.

## Before committing

Run these before every commit:

```bash
ruff format src/ tests/
ruff check src/ tests/
pytest
```

## Documentation rule

After any change that affects the public interface, CLI, file formats, or core architecture, update the relevant docs:

- `CLAUDE.md` — commands, pipeline, architecture notes
- `docs/ARCHITECTURE.md` — modules, data flow, contracts
- `docs/PROTOCOL.md` — CLI signature, build file schema
- `docs/MESSAGING.md` — anything that affects browser code (API shapes, wire protocol, error codes, architectural decisions visible to the TypeScript side) must be reflected here; this file is shared with geo-browser to keep contracts in sync. This includes but is not limited to changes to `src/geo_builder/api.py`

## Off-limits directories

Never read, glob, or search inside `./in/` or `./out/`. They contain large volumes of generated data and are not part of the source tree.

## Commands

```bash
# Install (editable, with dev deps)
pip install -e ".[dev]"

# Build
geo-builder template.json                        # fresh build to ./out
geo-builder template.json --in ./in --out ./out  # incremental build

# Designer (requires designUrl in settings.json)
geo-builder template.json --edit                        # pull on first run, then open WebView
geo-builder template.json --in ./in --out ./out --edit  # same with explicit paths

# Lint
ruff check src/ tests/
ruff format src/ tests/

# Test
pytest
pytest tests/test_foo.py::test_bar   # single test
```

## Core Invariants

1. `geo-builder` builds; `geo-browser` displays.
2. Internal processing uses strongly typed dataclasses.
3. `protocols.py` contains persisted/shared data contracts — pure data only, no behavior. Behavior that operates on protocol types belongs in entity classes under `geo_builder/entities/` (e.g. `catalog_entity.py`). *(Entity layer not yet implemented — existing methods on protocol classes are technical debt.)*
4. `contracts.py` contains runtime behavioral interfaces.
5. Execution mutates an in-memory catalog.
6. Persistence occurs only after successful completion.
7. Child paths are relative to their parent files.
8. Prefer explicit, readable Python over clever abstractions.
9. Tests must run offline.
10. Static artifacts are immutable and deterministic.

## Logging

Logging is essential for diagnosing build failures, provider errors, and unexpected behavior in production runs.

- **Use `Logger`** (`from geo_builder.diagnostics import Logger`) — not bare `print()`. Every worker and provider must log through `Logger`.
- **All features must log** — every feature logs success and errors. No silent success, no swallowed errors.
- **Message length by severity**:
  - **Success (info)** — short: feature started, feature ended. Features that run frequently (hot paths, per-item loops) are exempt from start/end logging.
  - **Recoverable issues (warning)** — medium: enough context to understand what went wrong and why it was non-fatal (e.g., HTTP status, what was retried or skipped).
  - **Errors (error/fatal)** — detailed: full context needed to reproduce and diagnose (e.g., inputs, HTTP status, exception text, what was abandoned).
- **Workers** — log start (`Logger.info("XyzWorker: execute.")`) and completion (`Logger.info("XyzWorker: completed. ...")`). Include a useful summary on completion (e.g., counts of items processed or created).
- **Providers** — log every HTTP interaction: request size, URL, response size, and any error with its HTTP status code.
- **Errors and retries** — always log the HTTP status code and the action taken (`Logger.warning`). Never swallow a status code silently.
- **Level guide**:
  - `Logger.info` — normal notable events (start, end, success, counts)
  - `Logger.warning` — recoverable problems (retries, splits, skipped items)
  - `Logger.error` / `Logger.fatal` — unrecoverable failures

## Coding Style

- **Protocols are pure data** — `protocols.py` holds dataclasses only. No methods, no logic. Behavior lives in entity classes (`geo_builder/entities/`).
- **Explicit over brief** — if two implementations are equivalent, choose the one that is easier to read and debug, even if it is longer.
- **No list/dict/set comprehensions** — use explicit `for` loops. Comprehensions obscure control flow and make multi-step logic harder to follow.
- **No lambdas** — use named functions or plain `for` loops. Lambdas hide intent and cannot be stepped through in a debugger.

## Current Task
- **File**: [Catalog Head Defaults & Path Mirroring](tasks/catalog_head_defaults.md)
- **Status**: Ready to Submit
- **GitHub Issue**: N/A
- **Key Context**: `pull.py` writes default head files on 404; `load_catalog` falls back to defaults if head file absent; `save_catalog` mirrors `in_dir` path structure instead of hard-coding `./release/` or `./debug/` subdirs; defaults are flat (`./catalog.json`, `./catalog.debug.json`).

## Processing Pipeline

```text
Task[]
    → Builder (stack-based DFS)
    → WorkerFactory
    → Worker.execute(executor)
    → Catalog mutation
    → persistence.save_catalog()
```

## Task Types

- AcquisitionTask
- DedupingTask
- AggregationTask

## Worker Responsibilities

- AcquisitionWorker: provider fetch + area creation + layer insertion
- DedupingWorker: remove near-duplicates within each layer (10 m Haversine threshold)
- AggregationWorker: merge compatible layers within an area (grouped by `mergeKey`)

## Provider Strategy

Providers are isolated under `providers/`.

Current:
- OverpassProvider — fetches OSM amenity data via Overpass API; supports meta amenity expansion (e.g. `sustenance` → bar, cafe, …)
- FakeProvider — offline stub that reads a local JSON file; used in tests and local dev

Future:
- FlickrProvider
- NominatimProvider

## Designer

See `docs/IMPLEMENTATION.md` for designer-specific implementation rules (handler pattern, threading model).

## Key Architecture Notes

**Coordinate conventions** — Area `center` is `[lat, lon]`; GeoJSON `coordinates` are `[lon, lat]`. The conversion happens at provider boundaries (`overpass.py`).

**Bbox decomposition** — When OverpassProvider receives HTTP 400 (query rejected / data too large), AcquisitionWorker splits the bbox into four quadrants and pushes them back onto the executor stack. HTTP 429 (rate limited) and 504 (timeout) trigger a retry-with-backoff inside `_execute_query` (delays: 5 s, 15 s, 45 s) before the split path is reached.

**AreaStyle** — Each filter key in an acquisition task carries an `AreaStyle(values, color, scale)` record. `color` overrides the auto-assigned layer color; `scale` overrides `radiusScale` in the heatmap style (useful for sparse layers like historic places). Both are optional.

**MergeKey format** — `"provider:key1=val1,val2"` (e.g., `"overpass:amenity=restaurant,cafe"`). AggregationWorker groups layers within an area by this key and concatenates their features into a single layer.

**Layer id/url derived from mergeKey** — `Layer.id_from_merge_key(merge_key)` sanitizes the mergeKey into a filesystem-safe string used as both the layer `id` and the `.geojson` filename. This ensures two providers covering the same amenity set (e.g. `overpass` vs `fake`) produce distinct files and never overwrite each other on disk.

**Debug output** — When `settings.debug: true`, each worker step writes a snapshot to `./build/{task_type}/{counter:03d}/`: a `catalog.json` (no embedded geojson), plus `.geojson` and `.csv` for any layer that was added or modified.

**Output layout**

```
{out_dir}/
├── catalog.json
└── areas/{areaId}/
    ├── manifest.json
    ├── {areaId}.csv
    └── layers/{layerId}.geojson
```

`manifest` is not embedded in `catalog.json`; `geojson` is not embedded in `manifest.json`. Each is a separate file loaded on demand.