# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Mission

Build a simple, deterministic Python application that creates static geographic datasets for the geo ecosystem.

## Collaboration rules

- Before implementing any feature or non-trivial change, ask clarifying questions until the intent is unambiguous.
- If anything is unclear or could be interpreted multiple ways, ask — do not assume and implement.

### Task workflow

Tasks are tracked as GitHub issues in this repo (`croicu/geo-builder`), status via labels: `status:brainstorm`, `status:implementation`, `status:testing`, `status:ready-to-submit`. There is no `status:done` label — reaching Done means closing the issue.

For any non-trivial feature or change, follow these stages:

1. **Brainstorm** — copy `tasks/new_task.md` to `tasks/<task-name>.md` with the problem statement; update it with conclusions as the design discussion progresses. This is scratch space for live back-and-forth — an issue isn't required at this stage, but a lightweight tracking issue labeled `status:brainstorm` can be opened for backlog visibility if wanted; either way, `tasks/<task-name>.md` (not the issue) stays the working document until the design converges.
2. **Implementation** — open a GitHub issue (`gh issue create`) with the converged problem statement + conclusions as the body, labeled `status:implementation`. Write the code. `tasks/<task-name>.md` is no longer the source of truth once the issue exists — trim it to a one-line pointer at the issue (or delete it) rather than maintaining both.
3. **Testing** — relabel the issue `status:testing`. Verify correctness; post test results and any open issues as an issue comment.
4. **Ready to Submit** — relabel `status:ready-to-submit`. Run lint + tests; confirm docs are up to date; post a closing summary comment.
5. **Done** — close the issue after merge. Delete `tasks/<task-name>.md` once the issue is closed — the issue (body + comments) is the sole source of truth from that point on, so there's no reason to keep a stale duplicate on disk. (Only applies when a real issue holds the full history; a Done task with no issue keeps its local file.)

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
- **Categories** — every `Logger` method takes an optional `category: str = "general"` (e.g. `Logger.warning(msg, category=CATEGORY_DATA_PIPELINE)`), filterable via `settings.json`'s `logCategories` (see `docs/CLI.md`). Existing call sites are not required to pass one — untagged calls stay in `"general"`. Console output is `[LEVEL][category] message` (e.g. `[WARNING][data_pipeline] ...`). Deliberately **not** a closed enum: `diagnostics.py` only consolidates geo-builder's own known values as plain string constants (`CATEGORY_GENERAL`, `CATEGORY_DATA_PIPELINE`, `CATEGORY_API`) so call sites don't repeat string literals, but the field stays an open `str` — `WriteTelemetryRecord` forwards geo-browser's own arbitrary category values (e.g. `"AreaLifecycle"`) straight through unmodified, so `logCategories` can filter on those too without geo-builder having to track geo-browser's category set in sync. Established geo-builder-side categories: `CATEGORY_DATA_PIPELINE` (`designer/data_pipeline.py`, plus two related lines in `host.py`'s `WebResourceRequested` handler), `CATEGORY_API` (`designer/gateway.py`'s dispatch logging, `host.py`'s `WebMessageReceived`). Note: a browser-originated `"general"`-category record and a geo-builder-originated one print identically — no origin marker, by design (see [geo-builder#49](https://github.com/croicu/geo-builder/issues/49)). **Effective default depends on `debug`**: if `settings.json`'s `logCategories` is left empty/absent, `debug: false` resolves it to `["general"]` (only `general` shown — matches geo-browser's own default), `debug: true` resolves it to `[]` (unfiltered, show everything); an explicit non-empty `logCategories` always overrides this regardless of `debug` (`settings.py`'s `Settings.load()`) — except that `debug: true` additionally unions `CATEGORY_GENERAL` into an explicit list if not already present (e.g. `{"debug": true, "logCategories": ["overpass"]}` → `["general", "overpass"]`), so debug mode's baseline info never disappears just because you narrowed to one other category; `debug: false` does not do this. **Query-string propagation**: an explicit non-empty `logCategories` (after the debug/general union above) is also appended to `designUrl` as `?logCategory=<comma-joined>` — the implicit debug-gated *default* (not an explicit setting) is console-only and never sent, since geo-browser's own defaults already match it without any param. See `docs/MESSAGING.md`'s `WriteTelemetryRecord` → Categories section for the full precedence rules with `?debug=1` and the "unrecognized category is not an error" contract. **`excludedCategories`** — complementary deny-list, only in effect when the *resolved* `logCategories` is `[]` (the true unfiltered state, i.e. `debug: true` with no explicit `logCategories`); inert against an explicit non-empty `logCategories` or the plain `debug: false` default of `["general"]` — a category named in both `logCategories` and `excludedCategories` is not a conflict, since exclusion simply never gets a chance to apply in that case. Forwarded to geo-browser as `?logCategoryExclude=<comma-joined>` whenever non-empty, independent of whether `logCategories` itself was explicit (see [geo-builder#56](https://github.com/croicu/geo-builder/issues/56), `docs/MESSAGING.md`).

## Coding Style

- **Protocols are pure data** — `protocols.py` holds dataclasses only. No methods, no logic. Behavior lives in entity classes (`geo_builder/entities/`).
- **Explicit over brief** — if two implementations are equivalent, choose the one that is easier to read and debug, even if it is longer.
- **No list/dict/set comprehensions** — use explicit `for` loops. Comprehensions obscure control flow and make multi-step logic harder to follow.
- **No lambdas** — use named functions or plain `for` loops. Lambdas hide intent and cannot be stepped through in a debugger.
- **Import count as SRP signal** — more than 5–10 imports in a file is a hint that the file may be doing too much. Not a hard rule, but worth pausing to consider whether responsibilities should be split.

## New Task

## Pending Tasks
- **File**: [Python Repo Template](tasks/python_repo_template.md)
- **Status**: Implementation
- **GitHub Issue**: [geo-builder#60](https://github.com/croicu/geo-builder/issues/60)
- **Key Context**: Abstract python repo template for new repos, built out under `./tpl-py` (its own git repo). Design converged: fork-and-rename (no cookiecutter), dunder-wrapped placeholder tokens (`__package_name__`, `__project_name__`, `__description__`, `__mission__`) with replacement instructions in `tpl-py/tasks/repo_setup.md`, generic skeletons for `cli`/`errors`/`settings`/`diagnostics` ported from geo-builder with domain-specific fields stripped, `contracts.py`/`protocols.py` as convention-only stubs (geo-builder's real content is 100% pipeline-specific, nothing generic to port), CI/CD copied near-verbatim, `.vscode/` genericized. See issue for full design + file inventory.

- **File**: [Pull: Skip catalog.head.json Fetch](tasks/pull_skip_head.md)
- **Status**: Brainstorm
- **GitHub Issue**: [geo-builder#42](https://github.com/croicu/geo-builder/issues/42)
- **Key Context**: `pull.py` always HTTP-fetches `catalog.head.json` against the production data host (geo-places) before falling back to a local default — but geo-places never serves that file (its real location is geo-browser, not the data host), and geo-builder's own default/fallback always wins anyway, so the round-trip is dead weight that also spams a 404 warning on every pull. Confirmed fix direction with user: skip the fetch entirely, always write the local default, go straight to `catalog.json`. Flagged for a pre-implementation check: the existing absolute-`catalogUrl` normalization branch in `_pull_head` (from [geo-builder#46](https://github.com/croicu/geo-builder/issues/46), Pull Origin Fix) becomes unreachable and should be deleted, but verify no real deployment depends on it first. Not yet implemented.

- **File**: [Default Layers](tasks/default_layers.md)
- **Status**: Brainstorm
- **GitHub Issue**: [geo-builder#43](https://github.com/croicu/geo-builder/issues/43)
- **Key Context**: Rationalize the default layers created when a new area is being created (template.json). Features reference is located at: https://wiki.openstreetmap.org/wiki/Category:Features

## Completed Tasks

All entries below are closed GitHub issues — the full history (problem statement, design decisions, test results) lives there, not in this file. `tasks/*.md` files are deleted once their issue is created, per the task workflow above.

- **Task**: Area-Scoped Rebuild — [geo-builder#51](https://github.com/croicu/geo-builder/issues/51) (closed)
- **Status**: Done
- **Key Context**: Designer-triggered single-area changes (`SetAreaBbox`, `AddArea`, void-geometry-only reprocess) were reprocessing and re-persisting *every* area, not just the changed one, violating the "areas are isolated" invariant. Fix: `area_ids: list[str] | None` on the five fixed-tail tasks, filtered per-worker; designer persistence swapped from full `save_catalog` to a `_save_area_only` helper so only the changed area's files touch disk. Verified merged to `main` via commit `66a7790`.

- **Task**: Area Grouping — [geo-builder#50](https://github.com/croicu/geo-builder/issues/50) (closed)
- **Status**: Done
- **Key Context**: Replaced the separate debug catalog with a single catalog plus an optional per-area `group: list[str]` field; `settings.json`'s `"group"` array stamps new areas at creation only, never re-stamped. `?group=<comma-joined>` appended to `designUrl` independent of `?debug=1`. Verified merged to `main` via commits `f9ff202`/`ec9da8b`/`b145831`.

- **Task**: `--rebuild` flag for selective acquisition — [geo-builder#32](https://github.com/croicu/geo-builder/issues/32) (closed)
- **Status**: Done
- **Key Context**: New build-mode-only `--rebuild <id>` flag (repeatable) forces re-acquisition of listed areas regardless of existing `--in` data; `--rebuild all` forces every area; unknown ids or unlisted no-data areas are hard errors. Verified merged to `main` via commit `96852f2`.

- **Task**: Search Layer Stub — [geo-builder#53](https://github.com/croicu/geo-builder/issues/53) (closed)
- **Status**: Done
- **Key Context**: `__search__` template.json entry was completely inert. New `SearchTask`/`SearchWorker` copies it into the manifest as a static stub, mirroring the pre-rework `VoidWorker` pattern. Verified merged to `main` via commit `80d3bb5`.

- **Task**: Void Radius: Per-Area Geometry Override — [geo-builder#55](https://github.com/croicu/geo-builder/issues/55) (closed)
- **Status**: Done
- **Key Context**: `defaultRadiusM` renamed to `radius`; new `Layer.geometry` carries a per-area `{"radius": ...}` override that `VoidWorker` resolves and persists across reruns. `GeoArea.apply_manifest` returns a 3-state `ManifestChange` (NONE/REPROCESS/REACQUIRE). Verified merged to `main` via commit `80d3bb5`.

- **Task**: Rate-Limit Defer — [geo-builder#52](https://github.com/croicu/geo-builder/issues/52) (closed)
- **Status**: Done
- **Key Context**: `AcquisitionWorker` was splitting the bbox on *any* `ProviderError`, including 429/504-after-retries. `ProviderError` now carries a `reason`; rate-limited tasks defer (capped at 3 requeues) instead of splitting, inserted just ahead of the fixed tail. Verified merged to `main` via commit `80d3bb5`.

- **Task**: Void Layer Precompute — [geo-builder#54](https://github.com/croicu/geo-builder/issues/54) (closed)
- **Status**: Done
- **Key Context**: `VoidWorker` now precomputes real `__void__`/`__void__<id>__` GeoJSON `Polygon`/`MultiPolygon` polygons (grid + hand-rolled marching squares, no shapely; padded grid ring for guaranteed contour closure + Sutherland-Hodgman clip back to bbox). Verified merged to `main` via commit `80d3bb5`.

- **Task**: Logging: excludedCategories — [geo-builder#56](https://github.com/croicu/geo-builder/issues/56) (closed)
- **Status**: Done
- **Key Context**: `settings.json` `excludedCategories` deny-list, complementing `logCategories`; only has effect when resolved `log_categories` is empty (the true unfiltered `debug: true` state). Forwarded to geo-browser as `?logCategoryExclude=` whenever non-empty. 477 tests pass, live-tested and confirmed working. Merged to `main` via PR (merge commit 92ed532).

- **Task**: Logging Categories — [geo-builder#6](https://github.com/croicu/geo-builder/issues/6) (closed; #45 was a duplicate, consolidated there)
- **Status**: Done
- **Key Context**: Added `category: str = "general"` as a first-class field on `Logger`/`DiagnosticsLogSink`/`TelemetryRecord`, plus a `logCategories` `settings.json` filter on `ConsoleLogSink`. Triggered by WriteTelemetryRecord's forwarded browser records already carrying `category`. Merged to `main` via PR (merge commit 92ed532).

- **Task**: WriteTelemetryRecord — [geo-builder#49](https://github.com/croicu/geo-builder/issues/49) (closed)
- **Status**: Done
- **Key Context**: New `__geo_write_telemetry_record__` handler forwards geo-browser's own `Logger` output to geo-builder in design mode. `category` passes through to `Logger` unmodified (final design after two iterations post-test-drive). Merged to `main` via PR (merge commit 92ed532).

- **Task**: Void Grid Field Construction Perf — [geo-builder#48](https://github.com/croicu/geo-builder/issues/48) (closed)
- **Status**: Done
- **Key Context**: `compute_void_feature`'s `grid` stage was 90-99% of total runtime. Rewrote as point-splatting: each point updates only the grid corners within its own `radius_m + padding`, instead of every corner querying nearby points. Berlin bare `__void__` grid 145.4s → 3.9s (37x). Committed as 37d923a.

- **Task**: Pull Origin Fix — [geo-builder#46](https://github.com/croicu/geo-builder/issues/46) (closed)
- **Status**: Done
- **Key Context**: `pull.py` normalized an absolute `catalogUrl` for the saved head file but kept fetching from the original absolute URL anyway, silently redirecting the pull to production. Also restored `assetsUrl` as the preferred pull origin (Vite can't serve arbitrary JSON in local dev).

- **Task**: User Layer — [geo-builder#47](https://github.com/croicu/geo-builder/issues/47) (closed)
- **Status**: Done
- **Key Context**: `__user__` layer stub injected at area creation and on startup for pulled areas; `GetUserPoints`/`AddUserPoint` APIs.

- **Task**: Catalog Head Defaults & Path Mirroring — [geo-builder#44](https://github.com/croicu/geo-builder/issues/44) (closed)
- **Status**: Done
- **Key Context**: `pull.py` writes default head files on 404; `load_catalog` falls back to defaults if head file absent; `save_catalog` mirrors `in_dir` path structure instead of hard-coding subdirs.

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
- VoidWorker: precompute the `__void__*` fog-of-war polygons (see `docs/LAYERS.md`, [geo-builder#54](https://github.com/croicu/geo-builder/issues/54))
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