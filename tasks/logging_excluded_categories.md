# Logging: `excludedCategories`

## Status: Ready to Submit

## Problem statement

`settings.json`'s `logCategories` (see [Logging Categories](logging_categories.md)) is an allow-list: when
non-empty, only listed categories print to console (and, if explicit, are forwarded to geo-browser via
`?logCategory=`). There's no way to say "show everything except X" — the closest today is `debug: true` with
an empty `logCategories` (unfiltered), but that has no way to suppress one noisy category (e.g. a verbose
per-frame trace category) while still seeing everything else.

Request: add a complementary `excludedCategories` deny-list field.

## Open design questions

1. **Scope of effect** — does `excludedCategories` only apply to the "show everything" case (empty
   `logCategories`, typically `debug: true`), or does it also subtract from an explicit non-empty
   `logCategories` allow-list?
2. **Conflict handling** — if a category appears in both `logCategories` and `excludedCategories`, does
   exclusion win, is it an error, or something else?
3. **Interaction with the debug→general union** — `debug: true` currently unions `CATEGORY_GENERAL` into an
   explicit `logCategories` (see `Settings.load`). If `excludedCategories` contains `"general"`, does that
   override the union (excluded wins) or does the union override the exclusion (general always survives)?
4. **Wire protocol** — `logCategories` propagates to geo-browser as `?logCategory=`. Does `excludedCategories`
   need a matching `?logCategoryExclude=`-style query param forwarded to geo-browser (which has its own,
   independent category-gating logic per `docs/MESSAGING.md`), or is this a geo-builder-console-only feature?

## Conclusions

- New `settings.json` field `excludedCategories: list[str]` (same base/local merge behavior as `logCategories`
  — local's key, if present, replaces base's entirely; not unioned).
- New `Settings.excluded_categories: list[str]` field (default `[]`).
- **Scope**: `excludedCategories` only has effect when the *resolved* `log_categories` is empty (`[]`) — i.e.
  only the true "unfiltered" state, which happens exclusively when `debug: true` and the user gave no explicit
  `logCategories`. It has **zero** effect in every other case: an explicit non-empty `logCategories` (whether
  or not debug's general-union widened it), or the plain `debug: false` default of `["general"]`. In those
  cases `excludedCategories` is parsed and stored but inert for console filtering.
  - Filtering rule (`ConsoleLogSink`): a category is shown if `log_categories` is non-empty → `category in
    log_categories` (existing allow-list logic, `excluded_categories` ignored entirely); if `log_categories`
    is empty → `category not in excluded_categories` (deny-list over "show all").
- **Conflict handling**: moot under the scope rule above — `excludedCategories` never overlaps in effect with
  an explicit `logCategories`, since it's inert whenever `logCategories` resolved non-empty. (Original Q2 in
  this doc is resolved by Q1's answer, not by a separate precedence rule.)
- **Wire protocol**: forwarded to geo-browser as a new `?logCategoryExclude=<comma-joined>` query param,
  appended to `designUrl` whenever `settings.excludedCategories` is non-empty — independent of whether
  `logCategories` itself was explicit (unlike `?logCategory=`'s "only when explicit" rule, since exclusion is
  its own independent signal). geo-browser-side interpretation (how `LogCategory` gating combines an allow-list
  and a deny-list) is out of scope for geo-builder per [[feedback_geo_builder_stays_agnostic]] — geo-builder
  only emits the param. Requires a `docs/MESSAGING.md` update mirroring the existing `?logCategory=` section.

## Implementation plan

1. `settings.py`: parse `excludedCategories` (list-of-str, `TaskError` on non-list, same shape as
   `logCategories`'s parsing); add `excluded_categories` field to `Settings`; append `?logCategoryExclude=` to
   `design_url` whenever non-empty (own `if` block, not gated on `log_categories` being explicit).
2. `diagnostics.py`: `ConsoleLogSink`'s category-visibility check gains the empty-`log_categories` deny-list
   branch described above. Needs access to `excluded_categories` — thread it through the same way
   `log_categories` currently reaches the sink.
3. Tests: mirror the existing `TestLogCategoriesParsing` cases for the new field — parsing, non-list rejection,
   local-overrides-base, query-string emission (present/absent/comma-joined), and the two-branch filtering
   rule in whatever test module covers `ConsoleLogSink` (`test_diagnostics.py`).
4. Docs: `docs/CLI.md` (settings.json field reference, mirroring `logCategories`'s entry), `docs/MESSAGING.md`
   (new `?logCategoryExclude=` row/section mirroring `?logCategory=`'s), `CLAUDE.md` Logging section (extend
   the existing category-precedence paragraph).

## Test results

477 tests pass (+8: `TestExcludedCategoriesParsing`, `TestExcludedCategoriesQueryParam` in `test_settings.py`,
`TestConsoleLogSinkExcludedCategories` in `test_diagnostics.py`; `test_cli.py`'s `StubSettings` and one
call-site assertion updated for the new parameter). `ruff format`/`ruff check` clean. Live-tested in the app —
confirmed working. `docs/MESSAGING.md`'s new `?logCategoryExclude=` section is being handed to the geo-browser
team next, for their side of the implementation (interpretation/gating logic, out of scope here per
[[feedback_geo_builder_stays_agnostic]]).
