# Void Layer Precompute

## Status: Ready to Submit

## Problem statement

`__void__` (the "Mundane" fog-of-war layer) is currently computed live in `geo-browser` as a
progressive rectangle grid, which produces jagged contours and main-thread jank at scale (see
`docs/LAYERS.md`). The fix is to precompute the void geometry once, offline, in
`geo-builder`, and ship it as an ordinary GeoJSON `Polygon`/`MultiPolygon` — no runtime
computation in the browser.

`VoidWorker` (`src/geo_builder/workers/void.py`) currently only ensures a placeholder `__void__`
layer entry exists per area (`visible: false`, no `url`, no geometry) — it does no geometry work
at all. The multi-variant naming convention (`__void__`, `__void__2__`, `__void__2_3__`, ...)
described in `docs/LAYERS.md` and `docs/MANIFEST.md` is entirely unimplemented.
This task moves the real computation into `VoidWorker`.

---

## Findings from investigation

- **Duplicated stub logic.** The current "build a `__void__` stub from `template.json`" logic is
  independently reimplemented three times: `Builder._void_style_from_template`
  (`builder.py:133-145`), and twice in `designer/host.py` (`_build_void_stub`/
  `_inject_missing_void_layers` at 108-155, and `on_add_area` at 428-438). Worth consolidating
  once the real worker exists.
- **No polygon support in the data model.** `protocols.py`'s `Geometry`/`Feature`/`GeoJson`
  classes only support `Point` coordinates today (`Geometry.coordinates: list[float]`, a single
  lon/lat pair). Loading (`geo_area.py:48-55`, `persistence.py:194-203`) hard-codes 2-element
  point parsing. This must be extended to support `Polygon`/`MultiPolygon` coordinate arrays
  before `VoidWorker` can write real geometry, and `GeoArea.save()`'s geojson-write path
  (`geo_area.py:254-262`) needs to serialize it correctly.
- **No real polygon exclusion features exist.** `overpass.py:190-197,231` shows that even
  way/relation (polygon-shaped) OSM elements are already collapsed to a centroid `Point` with a
  derived `radius_m`/`area_sqm` property — geo-builder's data model has no actual `Polygon`
  features anywhere. The exclusion mask is therefore just **circles**: `radius_m` around
  way-derived points, a fixed default radius around plain points. The doc's "real
  Polygon/MultiPolygon features exclude area" rule doesn't apply to geo-builder's current data —
  only the "point + radius" rule does.
- **No geometry library** (shapely, numpy, etc.) is in `pyproject.toml`. Confirmed decision below:
  hand-roll grid + marching squares rather than add a dependency.
- **`Layer.id_from_merge_key` referenced in `CLAUDE.md:177` does not exist in the code** — stale
  doc, not a real helper to reuse. `AggregationWorker` just reuses an existing id directly. A new
  void-id builder (sorted ids joined by `_`, wrapped in `__void__...__`) will need to be written
  from scratch.
- **Pipeline fit.** `VoidTask`/`VoidStyle` already exist (`contracts.py:71-76`,
  `protocols.py:39-43`) and `VoidWorker` is already wired into `WorkerFactory`
  (`workers/factory.py:27-28`) and into `Builder._tasks_from_catalog()` (`builder.py:108-115`,
  runs after Aggregation/Deduping/Poi). No new task/worker wiring needed — this is a rewrite of
  `VoidWorker.execute()`'s body, not new plumbing.

---

## Design decisions (confirmed)

1. **Algorithm: hand-rolled grid + marching squares.** No new dependency (shapely rejected).
   Rasterize the area's `bbox` into a grid, compute a signed-distance-style scalar field per
   cell (distance to nearest excluded circle, positive = void), run marching squares to extract
   zero-crossing contours, assemble into `Polygon`/`MultiPolygon` rings, simplify.
2. **V1 scope: bare `__void__` + one variant per non-virtual layer.** Every non-virtual,
   point-bearing layer (`type in ("heatmap", "circle")`) in the area gets its own
   `__void__<id>__` entry in the same `VoidWorker` pass, plus the required bare `__void__`
   (union of all such layers). No curated multi-layer combinations in v1.
3. **Default exclusion radius: fixed constant, configurable via `VoidStyle`.** Add a field to
   `VoidStyle` (e.g. `defaultRadiusM`, default ~50m) used for any point without its own
   `radius_m` property. Points with `radius_m` use their own value.

---

## Open questions (resolved)

1. **Grid resolution / performance budget.** Bucket-index the distance-field lookup (grid-cell
   buckets keyed by rounded lon/lat, analogous to `DedupingWorker`'s lat-band windowing) so each
   grid corner only checks nearby points, not the full point list. Cap grid dimensions so total
   corner count stays bounded (~200×200), scaling cell size up for larger bboxes.
2. **Empty-source areas.** Skip void computation entirely for a layer/variant with zero
   contributing points — no `__void__*` entry emitted for that combination.
3. **File naming.** `void/void.geojson` for the bare case, `void/layer-<ids>.geojson` (ids
   joined by `_`) for variants.
4. **Stale variant cleanup.** `VoidWorker` fully regenerates the `__void__*` set every run.
5. **Simplification tolerance.** Fixed default (~5 m), not exposed as a setting in v1.
6. **Edge closure** (surfaced during implementation planning — the hardest part of the
   algorithm): marching squares does not automatically close a contour where a void region
   reaches the grid boundary. Resolved as: pad the sampled grid by exactly one extra ring of
   cells beyond the area's true bbox; force that outermost ring's corner values to "excluded"
   unconditionally (ignoring the real distance field there). This guarantees every contour closes
   using only the standard interior marching-squares case table — no boundary-walking needed.
   The corners *at* the true bbox edge still use the real computed distance field (only the one
   extra ring *beyond* the bbox is forced), so after generating closed polygons on the padded
   grid, clipping them back down to the true bbox rectangle (Sutherland–Hodgman, run per ring)
   yields a polygon that can legitimately touch the true edge with accurate values — the forced
   ring never appears in the final output, only its closure effect does.

---

## Design decisions (algorithm detail)

- **No real polygon exclusion features exist** in geo-builder's data model (confirmed:
  `overpass.py` collapses ways/relations to a centroid `Point` + `radius_m`). Exclusion mask =
  union of circles: `radius_m` from feature properties if present, else `VoidStyle.default_radius_m`
  (new field, meters, default ~50).
- **Scalar field**: for each grid corner, `field = min_i(distance_to_point_i - radius_i)` across
  all contributing points (haversine distance in meters). Positive = void (far from everything),
  negative/zero = excluded. This is a true signed-distance-to-nearest-circle-boundary field, so
  marching squares' linear interpolation produces smooth circular arcs at exclusion boundaries,
  not a blocky grid artifact.
- **Grid**: corners cover the area bbox plus one padding ring (see resolved question 6). Cell
  size in degrees is derived from a target physical size (meters) at the area's center latitude
  (longitude degrees scaled by `cos(latitude)`, same convention as `overpass.py`'s
  `_polygon_area_sqm` and `deduping.py`'s lat-band window), capped so total corner count stays
  bounded.
- **Marching squares**: standard 16-case square lookup table over 2×2 corner blocks, linear
  interpolation along each crossing edge for the contour point position, one 2-endpoint segment
  per crossing case (ambiguous saddle cases resolved using the cell-center average, the common
  convention). Segments are linked end-to-end (matching interpolated endpoint coordinates) into
  closed rings.
- **Exterior/hole classification**: shoelace signed area per assembled ring — positive-area rings
  are exterior boundaries of a void blob, negative-area rings are holes (an excluded "island"
  fully inside a void region, e.g. an isolated point surrounded by empty space); a hole is
  assigned to whichever exterior ring's bbox contains it (point-in-polygon test on one hole
  vertex). Multiple exteriors ⇒ `MultiPolygon`, one ⇒ `Polygon`.
- **Bbox clip**: Sutherland–Hodgman, applied per ring against the four bbox half-planes, after
  marching squares (so it only ever needs to clip against a convex rectangle, not do general
  polygon boolean ops).
- **Simplify**: Douglas-Peucker with a fixed tolerance (~5 m, converted to degrees at the area's
  center latitude) as the last step before emitting coordinates.
- **Scope (from earlier decision)**: bare `__void__` (union of all non-virtual point-bearing
  layers, i.e. `type in ("heatmap", "circle")`) plus one `__void__<id>__` variant per such layer,
  computed in the same `VoidWorker` pass. No curated multi-layer combinations in v1.
- **Layer naming for variants**: bare uses `VoidStyle.name` ("Mundane"); a per-layer variant uses
  `f"No {source_layer.name}"` (matches the doc's "No Restaurants, Food" example).

## Correctness fixes required alongside this feature

Extending `Geometry.coordinates` beyond `Point` exposes two places that assumed every feature is
a point and would misbehave once a real `__void__` layer carries `Polygon`/`MultiPolygon`
geojson:

- **`DedupingWorker`** (`workers/deduping.py`) iterates every layer with non-`None` geojson and
  calls `float(feature.geometry.coordinates[1])` unconditionally — this **crashes** (`TypeError`)
  on a `Polygon` feature's nested coordinate rings on any incremental rebuild once a real
  `__void__` layer exists on disk. Fix: skip `type == "__void__"` layers in the area loop.
  (`AggregationWorker` is unaffected — it already only processes layers with `acquisition is not
  None`, which `__void__` never has.)
- **CSV export** (`persistence.py:save_area_csv`, `builder.py:_save_debug_layer`) reads
  `feature.geometry.coordinates[0]`/`[1]` directly into the `lon`/`lat` columns — doesn't crash
  (no `float()` call) but silently writes a garbled nested-list string for non-`Point` features.
  Fix: skip features whose `geometry.type != "Point"` when building CSV rows.

## Implementation plan

1. `protocols.py` — broaden `Geometry.coordinates` type alias to accept `Point`/`Polygon`/
   `MultiPolygon` coordinate shapes; add `VoidStyle.default_radius_m: float = 50.0`.
2. `entities/geo_area.py` — `_load_geometry` stops hard-coding 2-element point parsing; normalize
   coordinates generically (recursively cast leaf values to `float`, preserving nesting depth) so
   it round-trips any of the three shapes.
3. `persistence.py` (`save_area_csv`) and `builder.py` (`_save_debug_layer`) — skip non-`Point`
   features when building CSV rows.
4. `workers/deduping.py` — skip `type == "__void__"` layers in the area loop.
5. New module `workers/void_geometry.py` — pure geometry functions (no `Worker`/`Task`
   coupling), covering: meters↔degrees conversion, spatial bucket index, distance-field grid
   construction (with forced-excluded padding ring), marching squares contour extraction, ring
   assembly, exterior/hole classification, Sutherland–Hodgman bbox clip, Douglas-Peucker
   simplify, and a top-level `compute_void_polygon(bbox, points) -> Feature | None` (returns
   `None` when there are no contributing points or the result is empty).
6. `workers/void.py` (`VoidWorker`) — rewrite `_process_area`: gather non-virtual point-bearing
   sibling layers; for the bare case and for each individual layer, call
   `compute_void_polygon`; build/replace `__void__`/`__void__<id>__` `Layer` entries (`url`,
   `geojson`, `name`) in the area; remove any existing `__void__*` entries not regenerated this
   run.
7. `builder.py` (`_void_style_from_template`) and `designer/host.py` (`_build_void_stub`) — parse
   `defaultRadiusM` from the template's `__void__` style block alongside the existing fields.
8. `template.json` — no required change (default applies), but add an explicit `defaultRadiusM`
   to the `__void__` entry for discoverability.
9. Tests — unit tests for `void_geometry.py` (small synthetic point sets: single isolated point,
   two points close together, no points, a "hole" case with one point centered in a bbox
   surrounded by nothing else), and `VoidWorker` tests (bare + per-layer variants generated,
   stale variant removed when its source layer disappears, skip when no point-bearing layers).
10. Docs — `docs/MANIFEST.md` and `docs/LAYERS.md` status notes updated to reflect
    the geo-builder side is implemented; `CLAUDE.md` Worker Responsibilities section gets a
    `VoidWorker` line.

---

## Test results

- `ruff format src/ tests/` and `ruff check src/ tests/` — clean.
- `pytest` — 364 passed (was 348 before this task; added `tests/unit/workers/test_void_geometry.py`
  and `tests/unit/workers/test_void.py`, plus incidental coverage from the `DedupingWorker`/CSV
  fixes exercised by existing suites).
- `test_void_geometry.py` covers: no points → `None`; a single centered point → `Polygon` with
  exactly one hole (exercises the padded-grid closure *and* the exterior/hole containment
  classification together — the exterior ring is the bbox itself, closed via the forced-excluded
  padding ring, while the small excluded circle around the point comes out as a hole); an
  exclusion radius covering the whole bbox → `None`; two points near opposite corners → doesn't
  crash, produces valid `Polygon`/`MultiPolygon`; larger `radius_m` → larger hole.
- `test_void.py` covers: no source layers → no `__void__*` entries; one source layer → bare +
  one per-layer variant, correctly named/urled; `__poi__`/`__user__` excluded from source
  layers; a radius covering the whole area → no variant emitted; stale variant removed when its
  source layer disappears; re-running doesn't duplicate entries; `VoidStyle.default_radius_m`
  applied when a feature has no `radius_m` of its own.
- No end-to-end CLI smoke test was run against `FakeProvider`'s real Naples fixture data — the
  unit-level coverage above exercises the same code paths with concrete geometric assertions,
  judged sufficient given the scope already covered. Flag if a full CLI run is wanted before
  Done.
- Open item carried forward (not blocking): `docs/LAYERS.md` open question 1
  (per-layer coverage curation, multi-layer combinations) is still unresolved — v1 intentionally
  generates a variant for every non-virtual point-bearing layer, uncurated.

## Post-review refinement: contour smoothing

Manual testing against real Redmond data (opacity bumped to 0.5 in `template.json` to inspect
the shape) showed the boundary overfitting to individual points — jagged curves tracing fine
point-cluster structure rather than reading as one coherent void region. User diagnosed this
correctly as under-smoothed SDF contouring and proposed three fixes; two were implemented:

- **Morphological closing** (`_apply_morphological_closing`, `void_geometry.py`) — grayscale
  dilate then erode the field with a 1-cell (3x3) window before marching squares. Merges nearby
  void lobes and removes small excluded slivers between close-together points. Only applied to
  the real (non-padding) grid corners; neighbor lookups near the interior boundary clamp to the
  interior range so the forced-excluded padding ring never bleeds into real edge data during
  erosion.
- **`_SIMPLIFY_TOLERANCE_M` bumped 5m → 10m** — cheap complementary cleanup of residual
  sub-tolerance zigzag after closing.
- **Not implemented** (user's third option, `defaultRadiusM`): already a live `template.json`
  knob, no code needed — left as a separate/orthogonal tuning decision.
- Both constants stayed fixed/private (not exposed via `VoidStyle`) per explicit confirmation —
  can be promoted to tunable fields later if per-area tuning turns out to be needed.

## Post-review refinement: `default_radius_m` moved off `VoidStyle`

While testing `defaultRadiusM` via the designer's `PutAreaJson` style editor, discovered it had
no effect either way it was tried — not because of a bug, but two separate, correct behaviors
compounding: (1) `apply_manifest()` only triggers a rebuild on `acquisition` changes, never
`style`-only edits, by design; (2) even after a real rebuild, `VoidWorker` always reads
`defaultRadiusM` fresh from `template.json`, never from a manifest's existing `__void__` style —
so a per-area UI edit could never have propagated regardless of (1).

This surfaced the original design choice — putting `default_radius_m` on `VoidStyle`
(`protocols.py`, a *persisted* data contract per `CLAUDE.md` invariant 3) — as wrong: unlike
`color`/`opacity`, it never gets written into a layer's `style` and has no meaning to
`geo-browser`; it's purely a `VoidWorker` algorithm input. Moved to `VoidTask.default_radius_m`
(`contracts.py` — runtime behavioral interface, not persisted data) instead:

- `VoidStyle` reverted to just `name`/`color`/`opacity` (its state before this task).
- `VoidTask.__init__` gained `default_radius_m: float = 50.0` as its own parameter — this is now
  the single place the `50.0` literal is written; `builder.py`/`host.py`'s `template.json`
  parsers reference `VoidTask().default_radius_m` rather than repeating the literal.
- `VoidWorker.execute()` reads `self._task.default_radius_m` directly instead of
  `style.default_radius_m`.
- `docs/MANIFEST.md`'s note on `defaultRadiusM` updated to point at `VoidTask`, not `VoidStyle`.
- Test fallout: `test_void.py`'s `VoidStyle(default_radius_m=...)` construction became
  `VoidTask(default_radius_m=...)`; unused `VoidStyle` import dropped from that test file.
- Test fallout: `test_void_geometry.py`'s hole-radius tests used radii (30m, 150m) small enough
  to be fully erased by the new closing pass at the default grid resolution — bumped to 100m/300m
  so the tests still exercise real hole geometry. Comment added at the test explaining the
  constraint (radius must clear ~2x the closing kernel's effective removal size) so it doesn't
  look like an arbitrary magic number later.
- 371 tests pass, ruff clean, after this refinement.
