# Void Layer — Move to Precompute (geo-builder ↔ geo-browser contract)

Status: **shipped on both sides.** `geo-builder` precomputes the polygons (`VoidWorker`, see
`tasks/void_layer_precompute.md` for the algorithm); `geo-browser` renders them via the runtime
changes in the "`geo-browser` runtime changes" section below (minimal-superset resolution via
`VoidVariantResolver`, live grid computation deleted). See CLAUDE.md's "Mundane (Void) Layer"
completed-task entry. Kept in sync the same way `MESSAGING.md` is.

geo-builder's v1 coverage (see "What geo-builder produces" below): the bare `__void__` plus one
`__void__<id>__` per non-virtual point-bearing layer — no curated multi-layer combinations yet
(open question 1 below, still open). Algorithm used: a signed distance-field grid + hand-rolled
marching squares (no external geometry library) — full design detail in
`tasks/void_layer_precompute.md`.

## Why

`__void__` used to be computed live in `geo-browser` as a progressive rectangle grid
(`voidLayerView.ts` / `voidSpatialIndex.ts`, see `tasks/void_layer.md`). Two problems surfaced
testing against real data (Berlin, 35,642 points):

- **Jagged contours.** Axis-aligned grid rectangles can't produce a smooth boundary; finer
  grid spacing only makes the steps smaller, at quadratic cost.
- **Main-thread jank.** Even with a bucket index and a shared canvas renderer, computing and
  rendering hundreds of thousands of cells is felt by the user during the progressive passes.

Both go away if the geometry is computed once, offline, in `geo-builder`, and shipped as an
ordinary GeoJSON polygon — no runtime computation, and any contour-smoothing algorithm
(marching squares, simplification, corner rounding) is affordable since it's a batch step.

## Desired runtime semantics

- Exactly **one** non-virtual sibling layer visible → show void relative to *just that layer*
  (e.g. toggle on only "Restaurants, Food" → the layer reads "No Restaurants, Food").
- **Zero or multiple** non-virtual sibling layers visible → show void relative to the *union*
  of all currently-visible non-virtual layers (today's "Mundane" / "nothing at all" reading).
- **The UI still exposes exactly one toggle.** However many `__void__*` variants exist in the
  manifest, the layer flyout shows a single "Mundane" button, same as today. Which precomputed
  variant backs it, and what label it shows, changes underneath as siblings toggle — but the
  user only ever sees and interacts with one row.

Rather than a URL map on one manifest entry, this is expressed as **multiple ordinary `Layer`
entries**, distinguished by an `id` naming convention. No schema change to `Layer` at all, and
it's open-ended: `geo-builder` can ship as many or as few precomputed combinations as it wants,
and can add more later (e.g. curated pairs) without any contract change.

## Naming convention

```text
__void__               the base/combined case ("the Sahara") — void relative to the union
                        of ALL non-virtual layers in the area, regardless of visibility.
__void__2__             void relative to just layer id "2" (e.g. Restaurants).
__void__2_3__           void relative to the union of layer ids "2" and "3" (e.g.
                        Restaurants + Tourism).
```

Rule: `__void__` + sorted source layer ids joined by `_` + `__`, wrapped around a bare
`__void__` for the all-layers case. Sort ids ascending so the id string is canonical
(`__void__2_3__`, never `__void__3_2__`).

Every one of these is a normal `Layer` entry: `type: "__void__"`, its own `url` pointing at its
precomputed GeoJSON, `visible: false` (browser-managed, same as today), and its own `name` for
the label geo-browser should show while that variant is active (e.g. `"No Restaurants, Food"`
for `__void__2__`, `"Mundane"` for the bare `__void__`).

## What `geo-builder` produces (per area)

- Always: the bare `__void__` — void relative to the union of all non-virtual layers. This is
  the required fallback; every area must have one.
- Optionally: `__void__<id>__` per non-virtual, point-bearing layer, and/or curated
  multi-layer combinations (`__void__<id>_<id>__`, ...) — `geo-builder`'s choice of coverage,
  extensible later without touching this contract.
- Each is a GeoJSON `Polygon`/`MultiPolygon` representing the "far from any point in the
  referenced layer(s)" region, honoring the same exclusion-mask rules the current browser
  implementation uses: real `Polygon`/`MultiPolygon` features (parks, water) exclude area, and
  `radius_m`/`area_sqm` point-tagged features exclude a circle around themselves.

Algorithm is `geo-builder`'s choice (marching squares / isoline extraction + simplification is
the expected approach) — the contract here is only the output shape, not the method.

## `geo-browser` runtime changes (shipped)

- Deleted: the live grid computation (`VoidLayerView`'s old `compute`/`runPass`, `VoidSpatialIndex`,
  the dedicated canvas pane/renderer plumbing that had been added in `contracts.ts` / `leafletFactories.ts`
  for it). None of it remains — `VoidLayerView` is now a thin fetch-and-render of a precomputed
  GeoJSON polygon.
- All manifest layers matching `__void__` or `__void__<ids>__` are treated as one internal
  group, never surfaced individually in the layer flyout — only a single synthesized "Mundane"
  toggle appears, same as today's single entry.
- On toggle-on and on sibling-visibility-change (same trigger points as today): compute the
  set of currently-visible non-virtual layer ids, then **resolution is a minimal-superset
  search**, not a plain exact-match lookup: among all `__void__`/`__void__<ids>__` entries in
  the area's manifest, pick the one whose id-set is the smallest superset of the visible set.
  - Exact match (id-set == visible set) is the zero-excess case of this search.
  - The bare `__void__` (id-set = all non-virtual layers) is always a valid superset, so it's
    the guaranteed fallback when nothing tighter was precomputed — resolution never fails.
  - This lets `geo-builder` ship partial coverage (e.g. only pairs, not every triple) and
    still get the closest available approximation, rather than jumping straight to "everything"
    whenever the exact combination wasn't generated.
  - Use the resolved layer's own `url` and `name` (the displayed label follows whichever
    variant won the search).
- Rendering is an ordinary GeoJSON polygon layer.
- Style stays manifest-configurable (`style.color` / `style.opacity`) per variant, same as
  today.
- **Faded edge (implemented, 2026-07-12):** the polygon renders into a dedicated Leaflet pane
  (`void-pane`) with a CSS `blur(5px)` applied to the pane's SVG element — a hard edge at
  `opacity: 0.5`+ read poorly in manual testing; the blur softens it into a feathered fade
  instead. Applied directly to the SVG element created by the polygon render, not to the pane
  div itself — Leaflet pane divs are zero-size positioning wrappers, and a filter on a zero-size
  element clips its overflowing (real-sized) SVG child entirely, which silently produced no
  visible fog at all the first time this exact mistake was made (see `tasks/void_layer.md`'s
  history for the earlier canvas-renderer version of this bug). No `geo-builder` contract
  change — the precomputed polygon geometry and `style.opacity` are unchanged; the blur is
  purely presentational on the `geo-browser` side.

## Open questions

1. **Per-layer coverage** — v1 generates one `__void__<id>__` for *every* non-virtual,
   point-bearing layer (`type in ("heatmap", "circle")`), unconditionally. Whether to curate
   this down (e.g. skip a generic "Shops, Services" catch-all) or add curated multi-layer
   combinations (`__void__2_3__`) remains open — no curation logic exists yet.
2. **Rebuild staleness** — resolved: acceptable, same as every other baked layer.
   `VoidWorker` fully regenerates the `__void__*` set on every build (no incremental patching).
3. **Areas with only `__poi__`/no heatmap layers** — resolved: no void layer at all. `VoidWorker`
   skips a variant entirely (bare or per-layer) whenever it has zero contributing points.
