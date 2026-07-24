# Pull: Skip catalog.head.json Fetch

## Status: Brainstorm

## Problem statement

`pull.py`'s `pull()` always starts with `_pull_head()`, an HTTP fetch of `catalog.head.json`
against whatever `base_url` was resolved (production `assetsUrl`, i.e. geo-places today). Flagged
by the user: `catalog.head.json` is never actually served by geo-places — its real, meaningful
location is geo-browser (the frontend), not the data host. Beyond that, geo-builder shouldn't need
to consult it at all: on every fresh pull it already falls back to writing its own default
(`{"version": 1, "catalogUrl": "./catalog.json"}`) whenever the fetch 404s (see
[geo-builder#44](https://github.com/croicu/geo-builder/issues/44), Catalog Head Defaults & Path Mirroring), and `save_catalog`/
`save_catalog_meta` always write flat, default-shaped head files on the way back out regardless of
what an upstream head said. So the HTTP round-trip only ever ends in the same fallback it would
have used anyway — it's dead weight that also generates a `Logger.warning` noise entry
(`pull: '<url>': 404 ...`) on every single pull against geo-places.

## Design decision (confirmed with user)

Skip fetching `catalog.head.json` over HTTP entirely. `pull()` should:
1. Write the local default head file to `in_dir` unconditionally (no network attempt, no 404
   warning).
2. Go straight to fetching `catalog.json` at the known default relative path
   (`urljoin(base, "catalog.json")`).
3. Continue the existing chain unchanged from there (`_pull_catalog` → `_pull_manifest` →
   `_fetch_and_save`).

## Implementation-stage considerations (not yet resolved)

- `_pull_head`'s current absolute-`catalogUrl` normalization branch (lines ~35-49 in `pull.py`)
  exists because of a prior fix ([geo-builder#46](https://github.com/croicu/geo-builder/issues/46), Pull Origin Fix) for a real bug: a fetched
  head file could carry an absolute `catalogUrl` pointing at a *different* host than the one being
  pulled from, and needed rewriting to a local-relative path before being saved. If the head is
  never fetched, this whole branch becomes unreachable and should be deleted, not just dead-coded —
  but worth a final sanity check before deletion that no real deployment currently depends on a
  non-default, non-relative `catalogUrl` reaching geo-builder through this path (per
  [[feedback_verify_against_real_behavior]] — architecturally-motivated removal, confirm against
  actual behavior, not just reasoning, before deleting).
- `_HEAD_FILE`/`_HEAD_DEFAULT` constants and the "write default on 404" fallback path stay — they
  still describe what gets written to `in_dir`, just unconditionally instead of only on fetch
  failure.
- Existing `pull.py` tests likely assert on `_pull_head`'s fetch-then-fallback behavior directly;
  those will need rewriting rather than just passing incidentally.

## Next step

Advance to Implementation: simplify `pull()`/remove `_pull_head`'s fetch attempt and the
now-unreachable normalization branch, update/rewrite affected tests, confirm no regression against
the `assetsUrl`-preferred-origin behavior from [geo-builder#46](https://github.com/croicu/geo-builder/issues/46) (Pull Origin Fix) (that fix's
core concern — preferring `assetsUrl` as the pull origin over `designUrl`'s host — is orthogonal
to this change and should be preserved).
