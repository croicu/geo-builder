# WriteTelemetryRecord

## Status: Ready to Submit

## Problem statement

geo-browser's `docs/MESSAGING.md` proposed a new method, `__geo_write_telemetry_record__`, that
forwards the browser's own `Logger` output — plus a new pair of `window.onerror`/
`onunhandledrejection` handlers — to geo-builder over the existing JS→Python gateway, design mode
only (`?design=1`). Today that log stream is only visible in browser devtools; the goal is to let
a geo-builder end user inspect it from the Python side while running the designer, without
opening devtools.

**Browser side implemented and verified** (2026-07-23): `src/api.ts`,
`src/runtime/gatewayTelemetrySink.ts`, wired in `src/runtime/context.ts` on the geo-browser side.
`docs/MESSAGING.md`'s `WriteTelemetryRecord` section moved from "Proposal, not yet implemented" to
real documentation; its types were added to the "Current shared types" block. Diff reviewed
directly — matches every design decision below, no surprises.

**Builder side implemented** (2026-07-23), unblocked by [Logging Categories](logging_categories.md)
landing first.

## Open questions from the proposal — resolved

1. **What should `on_write_telemetry_record` do with a record?** → Route it through geo-builder's
   existing `Logger` (`src/geo_builder/diagnostics.py`), at the matching level.
2. **Per-record `invoke`, no batching — acceptable given volume under `?debug`?** → Yes. Bounded by
   geo-browser's existing category gating (`?logCategory=`/`?debug`) applied *before* `invoke` is
   ever called — an ordinary session only forwards `"general"`-category records.
3. **Does the output need a real failure code beyond `OK`?** → No — `OK` only.
4. **Does the id collide with anything reserved?** → No.

## Design decisions

- `WriteTelemetryRecordInput`/`WriteTelemetryRecordOutput` added to `api.py`, mirroring
  `docs/MESSAGING.md`'s Python section exactly: `timestamp`, `level`, `category`, `message`,
  `errorDetail` (required, nullable), `props: dict | None = None` (default needed — the browser
  omits the key entirely when there's nothing to attach, and `gateway.py`'s
  `method.input_type(**data)` would otherwise raise on the missing kwarg).
- Level mapping, browser string → `Logger` method: a `dict[str, Callable]` literal
  (`"diagnostic"` → `Logger.diagnostic`, `"info"` → `Logger.info`, `"warning"` → `Logger.warning`,
  `"error"` → `Logger.error`, `"fatal"` → `Logger.fatal`) inside `on_write_telemetry_record`. No
  validation for an unrecognized `level` — the TS type is a closed union, and `gateway.py`'s
  `_dispatch` already wraps every handler call in a try/except that logs a warning on `KeyError`.
- `category` passes the browser's own `data.category` straight through to `Logger` unmodified
  (e.g. `"general"`, `"AreaLifecycle"`). This is the third iteration of this specific decision,
  after test-driving live:
  1. First cut: pass `data.category` through, but prefix the message with `"[browser] "` as a
     text marker, since `ConsoleLogSink`'s print format only showed `[LEVEL] message`.
  2. After the user saw that literal `"[browser]"` text in a real console line: override
     `category="browser"` instead (a fixed, filterable category — single on/off toggle for all
     forwarded logs via `logCategories`), and change `ConsoleLogSink`'s print format
     (project-wide, see [Logging Categories](logging_categories.md)) to `[LEVEL][category]
     message` so the origin shows without a text hack.
  3. Final: the user wanted `logCategories` to filter on geo-browser's *own* category values
     directly (e.g. isolate just `"AreaLifecycle"` chatter) rather than only a blunt
     all-or-nothing `"browser"` bucket — and didn't want a closed enum shared with geo-browser's
     open-ended `LogCategory` set, since keeping the two in sync across repos would be a burden.
     So `category=data.category` again, this time for real. **Trade-off accepted**: a
     browser-originated `"general"`-category record now prints identically to one of
     geo-builder's own (`[INFO][general] ...` either way) — there is no separate origin marker.
     User confirmed this is fine ("Yes, let's get rid of 'browser'").
- `props`/`errorDetail` still have no structured home in `Logger`, so `on_write_telemetry_record`
  appends `props=<dict>` and/or `errorDetail=<string>` to the plain message when present.
- Registered in `designer/host.py`'s `_register_designer_handlers`, alongside
  `SetAreaBbox`/`AddArea`/etc. — not area-scoped, so it doesn't go through
  `Catalog.register_handlers`.
- Returns `WriteTelemetryRecordOutput(error=OK)` via the existing `MethodResult` wrapper
  (logs a warning automatically if `error != OK` — moot today since there's only one code).

## Test results

- `ruff format src/ tests/` / `ruff check src/ tests/` — clean.
- `pytest` — 457 passed (up from 450). New: `tests/unit/test_write_telemetry_record.py` covers the
  `api.py` dataclass shapes/id, and — importantly — that `WriteTelemetryRecordInput(**data)`
  succeeds when the gateway-shaped dict omits `props` (regression guard for the default-value
  reasoning above). `[LEVEL][category]` print-format coverage lives in `test_diagnostics.py`
  (added as part of the [Logging Categories](logging_categories.md) follow-up).
- **Not tested**: `on_write_telemetry_record`'s actual level-mapping/message-formatting logic and
  `_format_browser_telemetry_message`, since both are closures nested inside
  `_register_designer_handlers` (needs a live `Gateway`/`GeoCatalog`/window setup to exercise).
  This matches existing coverage for every other handler in that function
  (`on_set_area_bbox`/`on_add_area`/`on_remove_user_point`/etc. — none are unit-tested directly
  either); a pre-existing gap in `host.py`'s testability, not a regression introduced here.
- Docs: `docs/MESSAGING.md` already fully documented by geo-browser's own update — no further
  changes needed from the builder side.
