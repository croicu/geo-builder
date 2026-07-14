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
11. The browser is the authority for UI state — there is no notion of "current area" (or any other selection/focus state) in the builder. Any API that requires UI context (e.g. which area is active) must receive it explicitly from the browser as a parameter.

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
- **Import count as SRP signal** — more than 5–10 imports in a file is a hint that the file may be doing too much. Not a hard rule, but worth pausing to consider whether responsibilities should be split.

## New Task
- **File**: [Void Grid Field Construction Perf](tasks/void_grid_perf.md)
- **Status**: Ready to Submit
- **GitHub Issue**: N/A
- **Key Context**: `compute_void_feature`'s `grid` stage (distance-field construction) was 90-99% of total runtime — Berlin's bare `__void__` took 145-277s just for `grid`, ~9-13 min total across a 6-area catalog. Root cause: per-corner bucket queries scanned every point in a 3x3 neighborhood, blowing up for dense urban data. Rewrote as point-splatting (`_Grid._splat_point`): each point updates only the grid corners within its own `radius_m + padding` instead of every corner querying nearby points. 387 tests pass unchanged (exact hole-shape assertions confirm equivalence, not just "doesn't crash"). Real re-measurement against the same baseline (`radius_200_baseline.txt` vs `radius_200_improvements.txt`): Berlin bare `__void__` grid 145.4s → 3.9s (37x); whole-catalog VoidWorker pass ~565s → ~48s (~12x end-to-end). Follow-up: `VoidTask.default_radius_m` changed 200→100 (`contracts.py`) — re-measured and confirmed this is *not* a perf lever (grid time is set by the `_MAX_GRID_CELLS_PER_AXIS` cell-size cap, not `radius_m`); kept at 100 anyway as the intended void-circle sizing value.

- **File**: [Default Layers](tasks/default_layers.md)
- **Status**: Brainstorm
- **GitHub Issue**: N/A
- **Key Context**: Rationalize the default layers created when a new area is being created (template.json). Features reference is located at: https://wiki.openstreetmap.org/wiki/Category:Features

- **File**: [Search Layer Stub](tasks/search_layer_stub.md)
- **Status**: Ready to Submit
- **GitHub Issue**: N/A
- **Key Context**: `__search__` template.json entry was completely inert (nothing in `src/` read it). New `SearchTask`/`SearchWorker` copies it into the manifest as a static stub (no computation), mirroring the pre-rework `VoidWorker` pattern. Wired into `Builder._tasks_from_catalog()` and `on_add_area`, matching Poi/Void. 371 tests pass, ruff clean, docs updated. Incidentally fixed a missed `defaultRadiusM` gap in `on_add_area`'s void-style parsing.

- **File**: [Void Radius: Per-Area Geometry Override](tasks/void_radius_geometry_override.md)
- **Status**: Ready to Submit
- **GitHub Issue**: N/A
- **Key Context**: `defaultRadiusM` renamed to `radius` everywhere (template.json style + new manifest field); new `Layer.geometry` (sibling to `style`, not in it) carries a per-area `{"radius": ...}` override that `VoidWorker` resolves and persists across reruns (even when the resolved radius blanks out every variant — always keeps a stub bare `__void__` so the override survives). `GeoArea.apply_manifest` now returns a 3-state `ManifestChange` (NONE/REPROCESS/REACQUIRE); geometry-only edits trigger a new `_reprocess_area` path in `host.py` (Agg→Dedup→Poi→Void→Search, no provider fetch) instead of a full rebuild or a no-op. 385 tests pass, ruff clean, docs updated.

- **File**: [Rate-Limit Defer](tasks/rate_limit_defer.md)
- **Status**: Ready to Submit
- **GitHub Issue**: N/A
- **Key Context**: `AcquisitionWorker` was splitting the bbox on *any* `ProviderError`, including 429/504-after-retries — wrong, since rate limiting isn't fixed by smaller queries and splitting only multiplies load against the same limit. `ProviderError` now carries a `reason` (`TOO_LARGE`/`RATE_LIMITED`/`FATAL`); rate-limited tasks defer (capped at 3 requeues) instead of splitting. Follow-up fix from a real geo-places build: `defer_task` was landing deferred tasks *after* the fixed tail (Agg/Dedup/Poi/Void/Search), causing them to silently run without the deferred layer's data — now inserts just ahead of the fixed tail instead of at the absolute bottom. 379 tests pass, ruff clean.

- **File**: [Void Layer Precompute](tasks/void_layer_precompute.md)
- **Status**: Ready to Submit
- **GitHub Issue**: N/A
- **Key Context**: `VoidWorker` now precomputes real `__void__`/`__void__<id>__` GeoJSON `Polygon`/`MultiPolygon` polygons (grid + hand-rolled marching squares, no shapely; padded grid ring for guaranteed contour closure + Sutherland-Hodgman clip back to bbox). Also fixed a latent `DedupingWorker` crash risk on non-Point geometry. 364 tests pass, ruff clean, docs updated. `geo-browser`-side runtime changes from `docs/LAYERS.md` are still outstanding (separate repo).

## Completed Tasks

- **File**: [Pull Origin Fix](tasks/pull_origin_fix.md)
- **Status**: Done
- **GitHub Issue**: N/A
- **Key Context**: Two related fixes. (1) `pull.py` normalized an absolute `catalogUrl` for the *saved* head file but kept fetching from the original absolute URL anyway, silently redirecting the pull to production even when `designUrl` pointed elsewhere; reversed a previously-deliberate test expectation after confirming the "intentionally different data host" scenario isn't real here. (2) Follow-up: fixing (1) exposed that `assetsUrl` had been wrongly removed as a pull-origin candidate earlier in this same session — in local dev, `designUrl` (Vite) can't serve `catalog.json` at all (SPA fallback returns `text/html`), only a separate `assetsUrl` static server can. Restored `assetsUrl` as the preferred pull origin when set. 386 tests pass.

- **File**: [User Layer](tasks/user_layer.md)
- **Status**: Done
- **GitHub Issue**: N/A
- **Key Context**: `__user__` layer stub injected at area creation and on startup for pulled areas; `GetUserPoints`/`AddUserPoint` APIs; `AddUserPointInput.__post_init__` coerces nested dict from gateway dispatch; 325 tests pass.

- **File**: [Catalog Head Defaults & Path Mirroring](tasks/catalog_head_defaults.md)
- **Status**: Done
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
- PoiTask
- VoidTask
- SearchTask

## Worker Responsibilities

- AcquisitionWorker: provider fetch + area creation + layer insertion
- DedupingWorker: remove near-duplicates within each layer (10 m Haversine threshold); skips `__void__` layers (non-`Point` geometry)
- AggregationWorker: merge compatible layers within an area (grouped by `mergeKey`)
- PoiWorker: derive `__poi__` stub visibility from sibling layers' `hasDetails` features
- VoidWorker: precompute the `__void__*` fog-of-war polygons (see `docs/LAYERS.md`, `tasks/void_layer_precompute.md`)
- SearchWorker: copy the `__search__` stub from `template.json` into the manifest if missing; never recomputed

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

**Bbox decomposition vs. rate-limit deferral** — `ProviderError` carries a `reason` (`TOO_LARGE`, `RATE_LIMITED`, or `FATAL`), and `AcquisitionWorker` branches on it. HTTP 400 (query rejected / data too large) → `TOO_LARGE`: split the bbox into four quadrants and push them back onto the executor stack — a smaller query may fit. HTTP 429/504, after `_execute_query`'s in-process retry-with-backoff (delays: 5 s, 15 s, 45 s) is exhausted → `RATE_LIMITED`: do **not** split (splitting a rate-limited request into four just multiplies load against the same limit); instead `defer_task` it behind every other currently-pending acquisition, but still strictly ahead of the fixed tail (Aggregation/Deduping/Poi/Void/Search — deferring behind *those* would let them run without this task's data, since they were queued as part of the original task list before any acquisition started), up to `_MAX_RATE_LIMIT_REQUEUES` (3) deferrals before giving up fatally. Any other `ProviderError` defaults to `FATAL` — neither splits nor defers, fails immediately (e.g. misconfigured provider).

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