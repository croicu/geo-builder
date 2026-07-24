# Logging Categories

## Status: Ready to Submit

## Problem statement

`Logger`/`DiagnosticsLogSink` (`src/geo_builder/diagnostics.py`) currently filter only by level
(`logLevel` in `settings.json` → `ConsoleLogSink(min_level=...)`). With many concurrent threads
(data pipeline, workers, WebView2 events) all logging to the same console, level alone isn't
enough to isolate noise — flagged previously as a future feature (companion to `logLevel`).

Immediate trigger: the [WriteTelemetryRecord proposal](write_telemetry_record.md) forwards
geo-browser's `Logger` output to geo-builder, and geo-browser's records already carry a
`category: string` field (`LogCategory` in geo-browser's `src/logging.ts`, open string set,
`"general"` = default/untagged). Without a matching concept on the geo-builder side, that field
would have to be folded into the plain message string. Adding `category` as a first-class,
structured part of geo-builder's own logging API lets it pass through unchanged instead.

## Design decisions

- **Shape**: open string, default `"general"` — mirrors geo-browser's `LogCategory` exactly
  rather than a fixed enum. Any subsystem (or a forwarded browser record) can introduce a new
  category value without touching a central definition.
- **Scope**: API surface only. `category` becomes an optional parameter defaulting to
  `"general"` on every `Logger` method; **no retrofit** of existing call sites in this task. They
  keep behaving exactly as today (implicit `"general"`).
- **`TelemetryRecord`**: gains a `category: str = "general"` field.
- **`DiagnosticsLogSink.log(level, message, category="general")`**: threads the field through to
  the record.
- **`Logger.diagnostic/info/warning/error/fatal(message, category="general")`**: same optional
  param on every static method, passed through to `Logger._sink().log(...)`.
- **`ConsoleLogSink`**: gains `categories: list[str] | None = None`. `None`/empty = no filtering
  (show every category) — deliberately **not** symmetric with geo-browser's own default (which
  shows only `"general"` unless `?debug`/`?logCategory` is present); an all-permissive default
  here means existing users see no change in console output after upgrading. A record passes the
  filter when `categories` is empty/`None`, or when the record's category is in `categories`.
  Combined with the existing level check (both must pass).
- **`settings.json`**: new optional field `logCategories: list[str]` (default `[]`), parsed in
  `settings.py` next to `logLevel` (same validation shape as `group`: must be a list, coerced to
  `list[str]`). Wired into both existing `ConsoleLogSink(min_level=...)` construction sites:
  `cli.py:164` and `designer/host.py:941`.

## Not in scope for this task

- Retrofitting existing `Logger` call sites across `src/` with real categories (e.g. `overpass`,
  `acquisition`, `data_pipeline`) — deferred; can be done incrementally once the API exists.
- Any change to `WriteTelemetryRecord` itself — that task will consume this once both land, but
  is tracked separately in `tasks/write_telemetry_record.md`.

## Implementation

- `diagnostics.py` — `TelemetryRecord`, `DiagnosticsLogSink.log`, and every convenience method
  (`diagnostic/info/warning/error/fatal`) gained `category: str = "general"`. `Logger`'s static
  methods mirror the same signature. `ConsoleLogSink` gained `categories: list[str] | None = None`;
  a record prints only when both the level filter and the category filter (empty/`None` = pass)
  allow it.
- `settings.py` — new `Settings.log_categories: list[str]` field, parsed from `logCategories` in
  `settings.json`/`settings.local.json` next to `logLevel`, same validation shape as `group`
  (must be a list, coerced to `list[str]`, `TaskError` otherwise). Deliberately **not** appended to
  `design_url` — unlike `group`/`debug`, this is local-only console config with no browser-visible
  effect.
- `cli.py` — `_launch_designer` and `main()`'s build-mode path both thread
  `settings.log_categories` through to `ConsoleLogSink(..., categories=...)`.
- `designer/host.py` — `launch()` gained `log_categories: list[str] | None = None`, passed to its
  own `ConsoleLogSink(...)` construction.
- No retrofit of existing call sites, per the scoped decision above — everything stays in
  `"general"` unless a caller opts in.

## Test results

- `ruff format src/ tests/` and `ruff check src/ tests/` — clean.
- `pytest` — 450 passed (up from 440). New coverage: `test_diagnostics.py` (`category` defaults to
  `"general"`, is recorded, passes through convenience methods; `ConsoleLogSink` category
  filtering — no filter prints everything, matching category prints, non-matching category is
  silent, level filter still applies alongside category filter) and `test_settings.py`
  (`logCategories` default/parsing/local-override/non-list-raises/not-appended-to-`design_url`).
- Incidental fix: `tests/unit/test_cli.py`'s `StubSettings` test double and one `assert_called_once_with`
  expectation needed `log_categories` added — pre-existing tests broke on the new required kwarg
  passed from `main()`/`_launch_designer`, unrelated to any behavior change.
- Docs updated: `CLAUDE.md` Logging section (new `category` bullet), `docs/CLI.md` (`logCategories`
  settings.json row). `docs/ARCHITECTURE.md`/`docs/PROTOCOL.md` had no existing Logger/settings
  schema content to update. `docs/MESSAGING.md` intentionally untouched — this feature has no
  wire-protocol or browser-visible surface.

## Follow-up (post test-drive, 2026-07-23)

After test-driving `WriteTelemetryRecord` live and seeing a real console line, the user asked for
two changes beyond this task's original scope:

1. **`ConsoleLogSink`'s print format** changed from `[LEVEL] message` to `[LEVEL][category]
   message` (`diagnostics.py`) — category is now visible on every printed log line, not just used
   for filtering. Universal, not just for browser-forwarded records.
2. **Partial retrofit**, reversing the "no retrofit" scoping decision above for exactly three
   subsystems (everything else remains implicitly `"general"`):
   - `"data_pipeline"` — all of `designer/data_pipeline.py`, plus `host.py`'s
     `_on_web_resource_requested` (`WebResourceRequested` line + its nested `"data pipeline:
     response error"` line).
   - `"api"` — `designer/gateway.py`'s dispatch logging (`ready`, `_process_call`, `_dispatch`),
     `host.py`'s `_on_web_message_received`.
   - `"browser"` — every record forwarded via `WriteTelemetryRecord`, briefly (see below —
     superseded within the same session).

Retrofitting further call sites (`overpass`, `acquisition`, etc.) is still out of scope unless
asked for again.

## Follow-up 2: consolidate + drop the "browser" category (same session, 2026-07-23)

Two more changes right after the above landed:

1. **Consolidated geo-builder's own known categories as plain string constants** in
   `diagnostics.py`: `CATEGORY_GENERAL`, `CATEGORY_DATA_PIPELINE`, `CATEGORY_API`. Explicitly
   **not** a closed enum (the user considered and rejected this) — geo-browser's own `LogCategory`
   set is open-ended and evolves independently; a Python enum would either need to track it in
   sync (rejected as "too hard to keep in sync") or reject unknown values, defeating the goal of
   filtering on arbitrary browser categories. All internal call sites (`data_pipeline.py`,
   `gateway.py`, `host.py`) now import and use these constants instead of repeating string
   literals.
2. **Dropped the fixed `"browser"` category** from `WriteTelemetryRecord`'s handler (see
   [write_telemetry_record.md](write_telemetry_record.md) for the full three-step history) — it
   now passes the browser's own `data.category` straight through, so `logCategories` can filter
   on geo-browser's actual category values (e.g. `"AreaLifecycle"`) directly. Trade-off accepted:
   no separate marker distinguishes browser-origin `"general"` records from geo-builder's own.

## Test results (follow-up 2)

- `ruff format`/`ruff check` — clean. `pytest` — 457 passed (no count change — this was a rename/
  reversion, not new coverage; existing category tests already used literal strings that match
  the new constants' values).

## Follow-up 3: debug-gated default (same session, 2026-07-23)

User request: "If debug=false only the general category should be displayed" — applying to both
geo-builder's own logs and forwarded browser logs uniformly, since both already flow through the
same `ConsoleLogSink` filter (confirmed with user: "For you and for browser").

- `Settings.load()` now resolves the *effective* `log_categories` after all parsing: if
  `logCategories` was left empty (absent or `[]`), the result depends on `debug` —
  `debug: false` → `[CATEGORY_GENERAL]` (matches geo-browser's own default-to-`general`
  behavior), `debug: true` → `[]` (unfiltered, today's existing default). An explicit non-empty
  `logCategories` always wins over this, regardless of `debug`.
- This computation had to move **outside** the `if settings_payload:` block — an empty/absent
  `settings.json` (or an empty `"settings": {}` object) is falsy in Python, so the block never
  runs at all, and the debug-gating logic would otherwise silently never apply for that case
  (caught by re-checking `test_log_categories_default_empty`, which wrote `{"settings": {}}` and
  would have kept passing against the *old*, wrong assumption if left as `[]`).

## Test results (follow-up 3)

- `ruff format`/`ruff check` — clean. `pytest` — 460 passed (+3). Replaced
  `test_log_categories_default_empty` (asserted the now-incorrect unconditional `[]`) with four
  cases: defaults to `["general"]` when `debug` is false, defaults to `[]` when `debug` is true,
  explicit `logCategories` wins regardless of `debug`, and no settings files at all still resolves
  to `["general"]` (the falsy-empty-dict edge case above).
- Docs updated: `CLAUDE.md` Categories bullet, `docs/CLI.md`'s `logCategories` row.

## Follow-up 4: propagate to geo-browser via `?logCategory=` (same session, 2026-07-23)

The debug-gating in follow-up 3 only affected geo-builder's own `ConsoleLogSink`. But geo-browser
gates what it even *sends* via `WriteTelemetryRecord` using its own independent client-side
`?logCategory=`/`?debug` query string (per `docs/MESSAGING.md`) — so without also telling
geo-browser, geo-builder's `logCategories` setting could never actually surface a non-`general`
browser category (geo-browser's own default without `?logCategory=`/`?debug` is `general`-only).
User: "we need to pass the categories via the query string. Some categories the javascript might
not be aware of... it should not be an error."

- `settings.py`: an **explicit, non-empty** `logCategories` is now also appended to `design_url`
  as `?logCategory=<comma-joined>` — right where `group`/`debug`/`assetsUrl`/`map` already get
  appended. Deliberately **not** triggered by the debug-gated *default* (only by an explicit
  setting) — geo-browser's own pre-existing defaults already match the debug-gated default
  without any query param (general-only absent `?debug`, everything with `?debug=1`, which is
  already appended independently whenever `settings.debug` is true), so sending it again would be
  redundant and would have broken every existing `design_url`-assertion test for no behavioral
  gain.
- **Precedence with `?debug=1`** (documented in `docs/MESSAGING.md`, mirroring the existing
  `group`/`debug` precedent): explicit `?logCategory=` wins outright over `?debug`'s "show every
  category" shorthand, exactly like `?group=` already wins over `?debug`'s implicit
  `group=["debug"]` shorthand. `Context.debug`'s own diagnostics stay unaffected.
- **Unrecognized categories are not an error** — documented explicitly in `docs/MESSAGING.md`:
  geo-browser should treat any `?logCategory=` value it doesn't recognize (e.g. geo-builder's
  Python-only `data_pipeline`/`api`) as simply matching nothing.

## Test results (follow-up 4)

- `ruff format`/`ruff check` — clean. `pytest` — 463 passed (+3). New/changed in
  `test_settings.py`: explicit `logCategories` → `?logCategory=...` appended (single and
  comma-joined multi-value), debug-gated default never appended, explicit `logCategories` +
  `debug=true` → both `?logCategory=` and `?debug=1` present. Replaced the now-obsolete
  `test_log_categories_not_appended_to_design_url` (asserted the old "never appended" behavior).
- Docs updated: `docs/MESSAGING.md` (`WriteTelemetryRecord` → Categories — full format,
  precedence table, "not an error" contract), `docs/CLI.md`'s `logCategories` row, `CLAUDE.md`
  Categories bullet.

## Next step

Ready for `WriteTelemetryRecord`'s builder side to resume, now that `category` is a structured
`Logger` param.
