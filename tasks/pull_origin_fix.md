# Pull Follows a Stale Absolute catalogUrl Instead of the Local Origin

## Status: Done

## Problem statement

User pointed `designUrl` at `http://localhost:5173` (local Vite dev server) expecting the whole
pull to come from there, but logs showed it fetching `catalog.json`/`manifest.json` from
`https://geo-places.croicu.com` (production) instead.

Root cause in `pull.py::_pull_head`: when a head file's `catalogUrl` is absolute, the code
normalizes it to a relative path *for the copy saved to disk* (`"./catalog.json"`, logged as
"normalized absolute catalogUrl to..."), but then called `_pull_catalog(urljoin(url, catalog_rel),
...)` using the **original, un-normalized** `catalog_rel`. Since that's already an absolute URL,
`urljoin` returns it unchanged — so the actual fetch, and everything chained after it
(catalog → every manifest → every layer), followed the absolute URL regardless of normalization.
The saved head file on disk was correct; the live fetch wasn't.

This wasn't a typo-level bug — an existing test,
`test_catalog_still_fetched_from_absolute_url_after_normalization`, explicitly locked in the old
behavior, matching commit 8d00f347's stated intent ("keeping `in_dir` layout independent of the
service's own URL scheme"), which reads like it targeted a scenario where the head's origin and
the data's canonical host are intentionally different (e.g. a CDN). Confirmed with the user this
scenario isn't real for this project — an absolute `catalogUrl` in practice is just a stale head
file (itself pulled from production at some point, sitting as static content in
`geo-places/public/`) that happens to get served verbatim by whatever's currently hosting it,
local dev server included.

## Decision

Always follow the local fetch origin: once `catalog_rel` is normalized to `local_rel` for saving,
reuse `local_rel` (not the original absolute value) for the follow-up `_pull_catalog` call too.
`designUrl` becomes the single source of truth for every request `pull()` makes.

## Fix

`pull.py::_pull_head` — after writing the normalized head file, reassign
`catalog_rel = local_rel` before the `_pull_catalog(urljoin(url, catalog_rel), ...)` call.

Updated the test that encoded the old behavior (renamed to
`test_catalog_fetched_from_local_origin_after_normalization`, now asserts the local host is used
and the absolute host is never requested) and added a note to `docs/CLI.md`'s already-resolved
checklist item explaining the follow-on fix.

## Test results

`ruff format`/`ruff check` clean, 385 tests pass (no count change — one test updated in place,
none added).

## Follow-up: `assetsUrl` wrongly removed as a pull-origin candidate, then restored

Fixing the bug above didn't fully solve the user's actual problem: with the `catalogUrl` bug
fixed, `pull()` correctly stayed on `designUrl`'s origin (`http://localhost:5173`, their local
Vite dev server) — but that origin still failed, because Vite only serves the SPA. Any unmatched
path (including `/catalog.json`) falls back to `index.html` (`Content-Type: text/html`), which
`pull.py` correctly rejects and logs as "unexpected Content-Type."

Root cause: earlier in this same session, `host.launch()`'s pull-origin selection was changed to
always derive from `designUrl`'s origin, removing `assetsUrl` as a candidate entirely (reasoning:
`WebResourceRequested` interception resolves by path once `--in` has content, so the origin only
matters for the very first fetch — true, but that first fetch is a plain `requests.get()` in
`pull.py`, outside the WebView/interception layer, so it only succeeds if the origin can actually
serve the catalog JSON). This missed that in local dev, `designUrl` (Vite) and `assetsUrl` (a
separate static file server, e.g. `:5174`) are genuinely different servers with different
capabilities — Vite can't serve arbitrary JSON files, only the assets server can. Confirmed
against a real run: `designUrl`-origin pull failed with `text/html` responses; the fix is to
prefer `assetsUrl` when configured, matching the *original* pre-session behavior that had been
removed.

**Reverted**: `host.launch()`/`cli.py`'s `_launch_designer()`/`main()` — restored the
`assets_url` parameter end-to-end and the `if assets_url is not None: pull_origin = assets_url`
preference in `host.launch()`. Restored/added `test_cli.py` coverage
(`test_launches_webview_with_design_url`'s `assets_url=None` assertion,
`test_assets_url_passed_through_to_launch_designer`). Corrected `docs/CLI.md`'s checklist item 2,
which had documented the (wrong) removal as resolved-and-intentional.

386 tests pass, ruff clean.
