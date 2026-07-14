# Search Layer Stub

## Status: Ready to Submit

## Problem statement

`__search__` is documented in `docs/MESSAGING.md` as a browser-synthesized virtual layer
(ephemeral Nominatim search results) that geo-builder "is not required to emit." In practice
this meant its `template.json` entry was completely inert — no worker or injection path in
`src/` ever reads it, confirmed by grep (zero hits outside `template.json` and the doc).

Decision: `geo-builder` should copy the `__search__` entry from `template.json` into the
manifest as-is (a static stub — `url: null`, `visible: false`, style from the template),
mirroring the browser's own synthesized default (pasted by the user from geo-browser source):

```ts
return new GeoLayer({
    id: "__search__",
    name: "Search Results",
    type: "__search__",
    url: null,
    visible: false,
    style: { opacity: 0.3, color: "#00007f" },
});
```

Unlike `__void__`, there is no real computation — this is exactly the old (pre-rework)
`VoidWorker` pattern: if the area already has a `__search__` layer, leave it alone; otherwise
inject the stub from the template.

## Design decisions

- New `SearchStyle` dataclass in `protocols.py` (`name`, `color`, `opacity`) — pure data, mirrors
  `PoiStyle`/`VoidStyle`.
- New `SearchTask(Task)` in `contracts.py`, `type="search"`, carries `style: SearchStyle`.
- New `SearchWorker` in `workers/search.py` — mirrors the *original* stub-only `VoidWorker`: per
  area, if a layer with `id == "__search__"` already exists, do nothing; otherwise append the
  stub (`visible: false`, `url: None`, no `geojson`).
- Wired into `WorkerFactory.create()`.
- Wired into `Builder._tasks_from_catalog()`'s fixed tail (`Aggregation → Deduping → Poi → Void →
  Search`) and into `designer/host.py`'s `on_add_area`, exactly matching how `PoiTask`/`VoidTask`
  are appended today — confirmed with the user (chose "full-build pipeline + AddArea" over a
  separate startup-injection pass like `__user__`/`__void__` have). No separate startup
  injection function: `__search__` is lower-stakes than `__void__`/`__poi__` since geo-browser
  already has a robust runtime fallback if the manifest lacks it entirely.

## Implementation order

1. `protocols.py` — `SearchStyle`
2. `contracts.py` — `SearchTask`
3. `workers/search.py` — `SearchWorker`
4. `workers/factory.py` — register `SearchTask` → `SearchWorker`
5. `builder.py` — `_search_style_from_template`, append `SearchTask` in `_tasks_from_catalog()`
6. `designer/host.py` — build `search_style` from template, append `SearchTask` in `on_add_area`
7. Tests (mirroring old `test_void.py` stub-only test shape)
8. Docs — `docs/MANIFEST.md` note that geo-builder now emits `__search__`; `CLAUDE.md` Worker
   Responsibilities / Task Types

---

## Test results

- `ruff format src/ tests/` and `ruff check src/ tests/` — clean.
- `pytest` — 371 passed (up from 364; added `tests/unit/workers/test_search.py`, 7 tests: stub
  added when missing, default style matches the browser's own fallback exactly, style from
  `SearchTask` applied, no duplication on repeated runs, existing stub left untouched).
- Incidental fix found and applied while wiring `on_add_area`: its inline `VoidStyle`-from-template
  block (a third, separate duplicate of the same parsing logic already fixed in `builder.py` and
  `_build_void_stub`) was still missing `defaultRadiusM` parsing — fixed alongside the new
  `SearchStyle` block in the same function.
- Not done: no separate `_inject_missing_search_layers` startup pass (matches the wiring decision
  above) — a pre-existing pulled area with a manifest older than this feature and no pending
  re-acquisition will not get `__search__` injected until its next real rebuild. Accepted as
  low-risk since geo-browser already has its own runtime fallback for an absent `__search__`
  layer.
