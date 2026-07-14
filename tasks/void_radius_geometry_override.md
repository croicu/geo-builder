# Void Radius: Per-Area Geometry Override

## Status: Ready to Submit

## Problem statement

`VoidWorker`'s exclusion radius (`VoidTask.default_radius_m`) was template.json-only — no way to
override it per area, and per-area style edits through the designer's `PutAreaJson` never even
reached it (confirmed while debugging why a manually-set `defaultRadiusM` in a `__void__` layer's
`style` block had no effect: `apply_manifest` only triggers a rebuild on `acquisition` changes,
and even if it had, `VoidWorker` always re-read `template.json` fresh, ignoring whatever was in
the manifest). User's diagnosis: the radius value belongs in the manifest, but not in `style`
(style is presentational/persisted-as-is; radius affects computed geometry) — and editing it
should trigger *reprocessing* (Aggregation→Deduping→Poi→Void→Search against existing data), not a
full re-acquisition from the provider.

Also folded in a naming cleanup requested alongside this: `defaultRadiusM` → `radius` everywhere
(manifest and `template.json`) — "not default" (once overridable per-area, "default" undersells
it) and "meters implicit" (no unit suffix needed in a human-edited JSON key).

## Design decisions

- **New `Layer.geometry: dict | None` field** (`protocols.py`) — sibling to `style`, not nested
  in it. Only the bare `__void__` entry ever carries one (`{"radius": <meters>}`); per-layer
  `__void__<id>__` variants don't need their own copy since one radius applies to the whole
  area's void computation.
- **`radius` key everywhere**, replacing `defaultRadiusM`: `template.json`'s `__void__.style`
  (fallback), and `geometry.radius` on an area's own `__void__` layer (override). Kept as a
  `style`-nested key in `template.json` (unlike the manifest, template style genuinely is just
  build-config there, not a persisted/rendered artifact) but a top-level `geometry` sibling in
  the manifest, per the user's specific request.
- **`VoidWorker._resolve_area_radius_m`**: reads the area's existing `__void__` layer's
  `geometry.radius` (before the run's stub-clearing step discards it) and uses that instead of
  the task-level template fallback when present. The newly-built bare `__void__` layer always
  carries `geometry={"radius": <resolved value>}` forward, so the override survives indefinitely
  across reruns — including the edge case where the resolved radius is so large the computed void
  is empty for every variant: `VoidWorker` now always keeps a stub bare `__void__` entry
  (`url`/`geojson` absent) specifically so the override is never silently lost just because
  nothing happened to compute this run. This also restores a pre-existing documented invariant
  (`docs/LAYERS.md`: "every area must have" the bare `__void__`) that the real-geometry rework
  had quietly broken.
- **`ManifestChange` tri-state** (`entities/geo_area.py`, replaces the old boolean
  `_acquisition_changed`): `NONE` (presentational-only), `REPROCESS` (only the `__void__` layer's
  `geometry` changed), `REACQUIRE` (any layer's `acquisition` changed, or layers added/removed —
  takes priority over `REPROCESS` if both are true). `GeoArea.apply_manifest` returns this enum
  instead of `bool`.
- **`host.py`'s `on_put_area_json`** branches on all three: `NONE` → existing copy-manifest-only
  path; `REPROCESS` → new `_reprocess_area` (builds `[Aggregation, Deduping, Poi, Void, Search]`
  directly via `Builder.run(tasks=...)`, bypassing `_tasks_from_catalog`'s acquisition-gated tail
  entirely — no provider fetch); `REACQUIRE` → existing `_rebuild_area` full pipeline. Extracted
  `_poi_task_from_template`/`_void_task_from_template`/`_search_task_from_template` and
  `_fire_area_changed` as shared module-level helpers (were duplicated inline in `on_add_area`
  and now also needed by `_reprocess_area`).

## Test results

- `ruff format`/`ruff check` — clean.
- `pytest` — 385 passed (was 382 after the rate-limit-defer task; +3 in `test_geo_area.py`
  covering the tri-state classification and `geometry` round-tripping through save/load, and
  several `test_void.py` tests updated/added for the always-present-stub invariant and per-area
  override resolution/persistence — including one that caught a real bug during review: the
  override was silently lost across reruns when the resolved radius was large enough to blank out
  every variant, since no `__void__` layer survived to carry it forward. Fixed by always emitting
  a stub in that case rather than omitting the bare entry entirely.
