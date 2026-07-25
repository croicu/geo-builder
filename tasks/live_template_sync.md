# Live Template Sync

## Status: Implementation

## GitHub Issue: [tpl-py#2](https://github.com/croicu/tpl-py/issues/2)

## Problem statement

`tpl-py` isn't meant to be a one-shot snapshot — it should keep evolving (bug fixes to the base
modules, new/changed CLAUDE.md rules, obsoleted patterns), and repos already instantiated from
it should have a way to notice those changes and pull them in. GitHub's template mechanism
(fork-and-rename) severs git history on instantiation, so an instance has no built-in git
relationship back to `tpl-py` and no `git log`/`git diff` to lean on.

This mechanism is designed here (geo-builder), but the actual outcome — the protocol itself —
gets written into `tpl-py/CLAUDE.md` directly, since that's the file every instance already
inherits and every Claude session already reads. No separate pointer file (e.g. a `TEMPLATE.md`)
is needed; `CLAUDE.md` carries it all.

## Design decisions

- **No hard dependency on `gh`, for either `tpl-py` itself or any instance.** The source link
  lives baked into `ADDENDUM.md` itself (see below), so nothing needs `gh` to even discover
  where the template is. Reaching the source to check for updates is a plain HTTPS GET (e.g.
  `WebFetch`, `curl`, Python `requests`) against the source repo — not `gh api`, not `git
  clone`, not a persistent git remote.
- **Two protocols, one CLAUDE.md section**: `tpl-py/CLAUDE.md` gets a new section documenting
  both sides of the mechanism, since the same file ships to both roles:
  - **Reading** (applies when working in an *instance*): how to check `tpl-py` for updates and
    apply them.
  - **Writing** (applies when working in `tpl-py` itself): how to add an addendum entry when
    making a change meant for downstream instances.
  Each side is only ever relevant depending on which repo you're actually in — documenting both
  in the shared file is harmless, since the irrelevant half just doesn't apply.
- **No persistent git remote / no separate pointer file**: reaching the source is an on-demand
  action (`gh api` / a throwaway shallow clone against `croicu/tpl-py`), not a standing git
  relationship kept in every instance.
- **Addendum shape**: `tpl-py/ADDENDUM.md` at the repo root — a lightweight index (the source
  repo link, so this file alone is the pointer back — no separate `TEMPLATE.md` — plus a table
  of timestamp/title/filename) — plus one plain `.md` file per entry under `tpl-py/addendum/`.
  Checking for updates only ever requires reading the cheap root index; an entry's full file is
  only read if its timestamp is newer than the instance's last sync — deliberately token-cheap
  to apply.
- **Entry trigger**: curated, not automatic. Only changes meant for downstream instances (new
  rules, base-module fixes, obsoleted patterns) get an addendum entry, added as a conscious step
  alongside that change in `tpl-py`. Routine housekeeping, drill artifacts, docs wording tweaks,
  etc. don't need one.
- **Sync state**: recorded in the instance's own `CLAUDE.md`, in a new `## Template Sync`
  section (`Source` + `Synced to` timestamp). `tpl-py`'s own master copy of `CLAUDE.md` leaves
  `Synced to` unset (it's the source, not an instance) — `repo_setup.md` fills it in at
  instantiation time, from the latest `ADDENDUM.md` entry at that moment (or the instantiation
  time itself if the addendum is empty yet), so a brand-new instance never looks "behind" on
  history that predates it.
- **Read protocol** (documented in `CLAUDE.md`):
  1. Fetch `tpl-py`'s `ADDENDUM.md` over plain HTTPS (e.g. `WebFetch` against the raw content URL).
  2. Compare each entry's timestamp against this repo's own `Synced to` value.
  3. For entries newer than that, fetch only that entry's individual file and decide whether/how to apply it here.
  4. After applying (or deliberately skipping) everything newer, bump `Synced to` to the latest entry's timestamp.
- **Write protocol** (documented in `CLAUDE.md`, applies only in `tpl-py` itself):
  1. When making a change meant for downstream instances, add a new file under `addendum/`
     (timestamped filename) describing what changed, why, and what an instance should do about it.
  2. Append a row to `ADDENDUM.md`'s table (timestamp, title, filename).

## Open questions

None outstanding.

## Implementation plan

- `tpl-py/ADDENDUM.md` — source link + empty table (header row only) to start.
- `tpl-py/CLAUDE.md` — new section with both protocols + `Template Sync` state block.
- `tpl-py/tasks/repo_setup.md` — new step to set the initial `Synced to` timestamp.

## Test results

Docs/process-only change (no code touched). Re-ran `ruff check`, `ruff format --check`, and
`pytest` in `tpl-py` after the edits — all still pass clean, confirming nothing broke.
