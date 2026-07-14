# `--rebuild` flag for selective acquisition in build mode

## Status: Ready to Submit

## GitHub Issue

[geo-builder#32](https://github.com/croicu/geo-builder/issues/32)

## Problem statement

geo-places (a consumer of this CLI) wants to stop rebuilding its entire catalog on every deploy.
The plan: seed `--in` with the *previously deployed* output (already-acquired — `url` populated,
`layers/*.geojson` present) for every area except the one(s) actually changing this run, and seed
only the changing area(s) from a hand-authored manifest (no `url`).

This partially works today as a side effect of existing behavior: `Builder._tasks_from_catalog()`
skips generating acquisition tasks for a whole area if any of its non-`__poi__`/`__void__` layers
already has `geojson` loaded, and loading a manifest with `url` populated auto-reads the referenced
`.geojson`. So "does this area's `--in` manifest already carry data" is a real, working skip
signal — but it's entirely implicit, keyed off whatever happens to already be in `--in`:

- No way to force-refresh an area whose manifest hasn't changed (e.g. "the data is stale,
  re-acquire anyway") — the moment `--in` has geojson for it, it's skipped, full stop.
- No way to assert "acquire exactly this set, nothing else" as an explicit precondition. If an
  orchestration script makes an assembly mistake, it silently gets skipped instead of failing loud.
- No feedback for a typo — asking to rebuild an area id that doesn't exist in the catalog currently
  produces no signal either way.

## Design decisions (resolved via clarifying questions)

- **Syntax**: repeated flag, not comma-separated — `--rebuild prague --rebuild berlin`
  (argparse `action="append"`).
- **`--rebuild all`**: a reserved literal value that forces re-acquisition of every loaded area,
  regardless of whether `--in` is fully pre-seeded with data. Equivalent in effect to running with
  an empty `--in`, but without needing to touch `--in`'s contents.
- **`all` combined with specific ids** (e.g. `--rebuild all --rebuild prague`) is rejected as
  ambiguous input — exit 1 at CLI-argument-validation time, before the catalog is even loaded.
- **Error handling** — both hard-fail, matching the issue's rationale (geo-places' deploy is fully
  transactional, so silent skips or empty areas shipping to `--out` are the real failure mode to
  prevent):
  - An id in `--rebuild` that doesn't match any loaded area → exit 1
    (`--rebuild area '<id>' not found in catalog`).
  - A loaded area with no data that is **not** listed in `--rebuild` (and `--rebuild all` isn't
    active) → exit 1 (`--rebuild given but area '<id>' has no data and is not listed in --rebuild`).
- **`--edit` (designer mode)**: out of scope, rejected — `--rebuild` is a build-mode-only flag.
  Designer mode has its own re-acquisition triggers (bbox/acquisition-block edits via
  `apply_manifest`).
- Omitting `--rebuild` entirely preserves today's implicit, data-presence-based behavior exactly —
  fully backward compatible, opt-in only.
- Fixed-tail tasks (aggregation/dedupe/poi/void/search) keep their current scope — still run
  across every loaded area whenever at least one acquisition task exists anywhere; `--rebuild`
  doesn't narrow that (those are pure CPU, not provider calls).

## Implementation plan

1. `cli.py`:
   - `CliArguments` gains `rebuild_areas: list[str] | None = None`.
   - New argparse argument `--rebuild` (`dest="rebuild_areas"`, `action="append"`, `default=None`,
     `metavar="id"`).
   - In `main()`, before dispatching to build/designer mode:
     - If `--edit` and `rebuild_areas` is set → error, exit 1.
     - If `rebuild_areas` contains `"all"` alongside other values → error, exit 1.
   - In build mode, pass `rebuild_areas=arguments.rebuild_areas` through to `Builder(...).run(...)`.
2. `builder.py`:
   - `Builder.run()` gains a `rebuild_areas: list[str] | None = None` parameter, forwarded to
     `_tasks_from_catalog()`.
   - `_tasks_from_catalog(rebuild_areas)`:
     - `rebuild_areas is None` → behavior unchanged (today's implicit skip logic).
     - `rebuild_areas == ["all"]` → force every area through the acquisition-task-generation path
       regardless of `has_data_layers`.
     - Otherwise → validate every id against `self.catalog.areas`; raise `TaskError` for any
       unknown id. For each area, `forced = area.id in rebuild_areas`; if not forced and the area
       has no data layers, raise `TaskError` (unlisted area with no data). Build acquisition tasks
       when `forced or not has_data_layers` (identical condition shape to today's `not
       has_data_layers`, just widened by `forced`).
   - `TaskError` (already defined in `errors.py`, subclass of `GeoError`) propagates up through
     `run()` uncaught (raised before the per-task try/except loop) to `main()`'s existing outer
     `except GeoError` handler — same exit-1-with-message path as every other CLI-level error.
3. Tests: `test_builder.py` (new `TestTasksFromCatalog` class covering skip/force/all/error cases),
   `test_cli.py` (argparse parsing, edit-mode rejection, all+ids rejection, pass-through to
   `Builder.run`).
4. Docs: `docs/CLI.md` (new `--rebuild` row in Arguments table + usage section), `docs/ARCHITECTURE.md`
   (`_tasks_from_catalog()` description).

## Test results

- `ruff format src/ tests/` — clean (58 files, 0 changed).
- `ruff check src/ tests/` — clean.
- `pytest` — 400 passed (was 385 at session start on `main`'s last recorded count; net +15: 7 new
  `TestTasksFromCatalog` cases in `test_builder.py` covering skip/force/all/unknown-id/unlisted-
  no-data, and 8 new/updated `test_cli.py` cases covering argparse repeated-flag parsing,
  `--edit`+`--rebuild` rejection, `all`+specific-id rejection, and pass-through to `Builder.run`).
