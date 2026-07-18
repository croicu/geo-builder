# Area-Scoped Rebuild

## Status: Ready to Submit

## Problem statement

Areas are isolated by design (no cross-area data dependency), so adding a new area or editing one
area's bbox in the designer should only build that area. In practice, two layers of the pipeline
violate this:

1. **Compute** — `AggregationWorker`, `DedupingWorker`, `PoiWorker`, `VoidWorker`, `SearchWorker`
   all unconditionally loop `for area in catalog.areas`. `Builder._tasks_from_catalog` correctly
   scopes *acquisition* to only the areas that need it (missing data, or forced via `--rebuild`),
   but the fixed-tail tasks it appends (Aggregation/Deduping/Poi/Void/Search) carry no area scope
   at all, so every designer-triggered single-area change (`SetAreaBbox`, `AddArea`, and the
   void-geometry-only `_reprocess_area` path) still reprocesses every other area's data — including
   `VoidWorker`, whose per-area cost was expensive enough to need a dedicated perf pass
   ([[project_session_2026_07_13_void_perf]]).
2. **Persistence** — `persistence.save_catalog` calls `_clean_dir(output_dir)` (deletes the whole
   `--out` tree) and then rewrites every area's manifest/geojson/CSV, every time. A single-area
   bbox edit deletes and rewrites every other area's output files on disk. Two helpers already
   exist that do the narrow thing (`save_area_to_catalog` — one area's files, no clean;
   `save_catalog_meta` — head + `catalog.json` only) and are already used for `in_dir` mirroring in
   `on_add_area`, just never applied to `out_dir`.

## Design decisions

- **`area_ids: list[str] | None` on the tail tasks** (`AggregationTask`, `DedupingTask`, `PoiTask`,
  `VoidTask`, `SearchTask` in `contracts.py`). `None` = unscoped (process every area — the existing
  behavior, used for full/default builds). Each of the five workers filters its
  `for area in catalog.areas` loop: skip when `task.area_ids is not None and area.id not in
  task.area_ids`.
- **`Builder._tasks_from_catalog`** tracks which area ids actually got an `AcquisitionTask` this
  run (forced via `--rebuild`, or simply missing data) and stamps that list onto the tail tasks it
  appends — `None` only when `--rebuild all` (explicit, unambiguous "every area"). This is derived
  from the existing forced/has-data-layers logic already in that method, so `--rebuild <id>`
  (single or repeated) is scoped for free, with no separate host.py change needed for
  `_rebuild_area` (it already goes through `_tasks_from_catalog`).
- **`host.py`'s `on_add_area` and `_reprocess_area`** build their own explicit 5-task tail list
  (bypassing `_tasks_from_catalog`) — both now pass `area_ids=[area_id]` explicitly.
  `_poi_task_from_template`/`_void_task_from_template`/`_search_task_from_template` gain an
  `area_ids` parameter to thread through.
- **Persistence**: `_rebuild_area`, `_reprocess_area`, and `on_add_area` each replace their
  `save_catalog(result, out_dir, in_dir=in_dir)` call (full clean + rewrite-everything) with the
  same pattern already used for `in_dir`: `save_area_to_catalog(target_area, out_dir)` +
  `save_catalog_meta(result, out_dir)`. No new persistence function needed.
- **Out of scope**: the plain CLI build path (`cli.py::main`, `--in`/`--out` without `--edit`) keeps
  calling full `save_catalog` — that path can add or remove areas from the catalog between runs,
  and the full clean is what safely purges stale area directories for removed areas. Only the
  designer's three known-single-area entry points switch to partial persistence.

## Implementation plan

1. `contracts.py`: add `area_ids: list[str] | None = None` to the five tail task constructors.
2. Workers (`aggregation.py`, `deduping.py`, `poi.py`, `void.py`, `search.py`): filter the per-area
   loop by `task.area_ids`.
3. `builder.py::_tasks_from_catalog`: collect acquired area ids, stamp onto tail tasks (`None` for
   `force_all`).
4. `host.py`: thread `area_ids=[area_id]` through `on_add_area` and `_reprocess_area`'s task
   construction (including the three `_..._task_from_template` helpers); swap the three
   `save_catalog(...)` calls for `save_area_to_catalog` + `save_catalog_meta`.
5. Tests: extend `test_builder.py` (tail task scoping derived from acquisition), per-worker tests
   for `area_ids` filtering, and host.py designer-flow tests confirming only the target area's
   files change on disk (and others are untouched, not just unchanged-in-content).
6. `ruff format`/`ruff check`, `pytest`, update docs (`ARCHITECTURE.md` processing-pipeline notes
   if the tail-task contract is documented there).

## Test results

- `ruff format`/`ruff check` — clean.
- `pytest` — 438 passed (was 414 before this task; +24 new: `TestTasksFromCatalog` tail-scoping
  cases in `test_builder.py`, an `TestAreaScoping` class in each of the five worker test files
  (`test_aggregation.py`/`test_deduping.py`/`test_poi.py`/`test_void.py`/`test_search.py`), and
  `TestSaveAreaToCatalog`/`TestSaveCatalogMeta` in `test_persistence.py` covering the new `in_dir`
  mirror parameter and the "other area's files untouched" guarantee).
- No existing test regressions — all worker `run(...)` test helpers pass `task=None`, which
  `isinstance(self._task, XyzTask)` correctly treats as unscoped (matches pre-existing behavior).
- `docs/ARCHITECTURE.md` updated: new "Area-scoped tail tasks" subsection under Build modes, the
  `Persistence` section now documents `save_area_to_catalog`/`save_catalog_meta` as the
  single-area-safe alternative to `save_catalog`, and the Runtime Contracts task list now includes
  `PoiTask`/`VoidTask`/`SearchTask` with the new `area_ids` field.
- `docs/PROTOCOL.md`/`docs/MESSAGING.md` — no changes needed; `--rebuild` CLI semantics and the
  designer wire protocol (API shapes, error codes, `AreaChanged` payload) are unchanged, this task
  is an internal compute/persistence optimization only.
