# Rate-Limit Defer (stop splitting on 429/504)

## Status: Ready to Submit

## Problem statement

`AcquisitionWorker.execute()` caught *any* `ProviderError` from `provider.fetch()` and responded
by splitting the bbox into four quadrants — correct for HTTP 400 (query genuinely too large),
wrong for HTTP 429/504 after `_execute_query`'s retry-with-backoff was exhausted. Rate limiting
isn't caused by query size, so splitting doesn't help; it turns one rate-limited request into
four, each of which retries 3× (5s/15s/45s) against a server that's already limiting the client,
then *also* splits into four more on exhaustion — an exponential cascade that hammers the same
rate-limited server harder with every failure. Surfaced during manual designer testing when
Overpass started returning 429 persistently (possibly an IP-level block, in which case no
in-process fix can unblock it — this only stops the self-inflicted cascade for ordinary
transient rate-limiting).

## Design decisions

- `ProviderError` gains a `reason: ProviderErrorReason` (`TOO_LARGE` / `RATE_LIMITED` / `FATAL`,
  default `FATAL`). `overpass.py` tags its two recoverable raise sites explicitly; the
  "unknown provider" (`factory.py`) and "missing dataPath" (`fake.py`) errors get `FATAL` by
  default, which is also a correctness improvement — previously *any* `ProviderError` triggered
  pointless recursive bbox-splitting even for config errors that splitting could never fix.
- `AcquisitionWorker.execute()` branches on `error.reason`:
  - `TOO_LARGE` → existing split behavior, unchanged.
  - `RATE_LIMITED` → **defer, don't split.** `AcquisitionTask` gains `rate_limit_attempts: int`
    (mutated in place, not reset on defer); `Executor` gains `defer_task()`, implemented by
    `Builder` as `self._stack.insert(0, task)` — pushes to the *bottom* of the stack (opposite
    end from `push_task`/`push_tasks`, which append to the top where `.pop()` reads from), so
    the same task only runs again once every other currently-queued task has run first. Capped
    at `_MAX_RATE_LIMIT_REQUEUES = 3`; beyond that, fatal.
  - Anything else (`FATAL`) → immediately fatal, no split, no defer.
- No extra sleep was added before deferring — `_execute_query`'s existing 65s of retry backoff
  per attempt already provides real wall-clock cooldown; three deferrals naturally accumulate up
  to ~195s before giving up.

## Test results

- `ruff format`/`ruff check` — clean.
- `pytest` — 375 passed (was 371; net +4 in `test_acquisition.py`: existing "too large" tests
  renamed and updated to pass `reason=ProviderErrorReason.TOO_LARGE` explicitly since the
  default changed to `FATAL`; added rate-limited-defers-not-splits, attempt-count-increments,
  fatal-after-max-requeues, and fatal-error-neither-splits-nor-defers).
- `StubExecutor` gained `deferred_tasks` tracking alongside existing `pushed_tasks`.

## Post-review fix: `defer_task` ordering bug (real-world build)

First real geo-places build after this landed surfaced a genuine bug: `defer_task` originally
pushed to the *absolute* bottom of the stack (`insert(0, task)`). But the fixed tail
(Aggregation/Deduping/Poi/Void/Search) is queued as part of the *original* task list built by
`_tasks_from_catalog()`, before any acquisition runs — so it already occupies stack positions
below any *other* still-pending acquisition, but above index 0. Deferring to index 0 put the
retried task even deeper than the fixed tail, so it always ended up running dead last, after
Aggregation/Deduping/Poi/Void/Search — not before them.

Observed effect on a real Redmond build: `filters=[tourism]` hit HTTP 504, exhausted retries,
and deferred. `filters=[amenity]` (Culture) and `filters=[shop]` then completed, and the fixed
tail ran — `VoidWorker` computed void geometry from whatever layers existed *at that moment*
(Parks/Restaurants/Culture/Shops, four layers) with Attractions/tourism entirely absent, since
its data hadn't landed yet. Only *after* the fixed tail finished did the deferred tourism task
finally get popped and succeed — too late to be counted. The final catalog did still contain the
tourism layer's data (added before `save_catalog`), but the bare `__void__` union was computed
without it and no `__void__<tourism-id>__` variant was ever generated for that build.

Fix: `defer_task` now scans the stack from the bottom (index 0) for the first task whose `type`
isn't in `_FIXED_TAIL_TASK_TYPES` (`aggregation`/`deduping`/`poi`/`void`/`search`) and inserts
right there — behind any other still-pending acquisition, but strictly ahead of the fixed tail.
Handles the fixed-tail-only-remaining case (insert at the top, before all of it) and the
empty-stack case (insert-into-empty is a no-op-equivalent) correctly by falling back to
`insert_at = len(self._stack)` when no non-fixed-tail task is found.

4 new white-box tests in `test_builder.py::TestDeferTask` construct a `Builder._stack` directly
with real `Task` objects (no worker execution needed) and assert pop order. 379 tests pass.
