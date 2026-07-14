# Void Grid Field Construction: Point-Splatting Instead of Corner-Querying

## Status: Ready to Submit

## Problem statement

`VoidWorker`'s new duration logging (see `tasks/void_layer_precompute.md`) revealed that
`compute_void_feature`'s `grid` stage — building the signed distance field the whole algorithm is
based on — dominates total runtime by 90–99%, regardless of area or radius. Real measurements
(`tasks/radius_200_baseline.txt`, `radius_100_perf.txt`, `radius_200_perf.txt`): Berlin's bare
`__void__` (35,642 points) took **145–277s** just for `grid`, out of ~147–280s total. Across all
6 areas in a single build, `VoidWorker` alone took 9–13 minutes.

Root cause: `_BucketIndex.field_at` was called once per grid corner (up to ~40,000 of them per
variant), and for each call scanned every point in the surrounding 3×3 bucket neighborhood,
computing a real haversine distance to each. Bucket size was sized for correctness (guaranteed to
find every point within the cutoff radius), not for bounding worst-case density — for a dense
urban core with hundreds of points within a few hundred meters of each other, "9 buckets" can
still mean scanning thousands of points per corner. Total work was effectively
`corners × points-in-neighborhood`, which explodes for real city-scale data.

## Decision

Invert the loop: for each *point*, update only the grid corners within that point's own
`radius_m + padding` — not for each *corner*, query nearby points. A point with a 100–200m radius
only influences a few hundred nearby corners, not the full ~40,000-corner grid, so total work
becomes `points × corners-near-that-point`, the right shape for "many points, most of them
irrelevant to any given far-away corner."

**Correctness argument** (why splatting doesn't sacrifice accuracy, just re-orders the same
work): the field's magnitude only matters for edges where two adjacent corners have opposite
signs (marching squares needs an accurate interpolated crossing position there); everywhere else
only the *sign* matters. `padding_m` is chosen per-grid as `max(cell_lon_m, cell_lat_m) * 2` —
at least two grid cells wide — which guarantees both corners of any edge that could actually
cross zero fall within the responsible point's splat range and get their exact, individually
computed value. Corners no point ever reaches are, by construction, farther than every point's
own `radius + padding`, so their true value exceeds `padding_m` — definitely void, and the flat
`_UNTOUCHED_FIELD = 1.0e6` sentinel used there is a safe stand-in since only its sign is ever
consulted.

## Fix

`void_geometry.py`:
- Removed `_BucketIndex` and `_center_lat` entirely.
- `_Grid.__init__` now initializes the whole field to `_UNTOUCHED_FIELD`, then calls a new
  `_splat_point()` per point (computes the point's corner-index bounding box from
  `radius_m + padding_m` converted through the grid's own cell-size-in-meters, then updates only
  those corners via `min()`), then forces the padding ring to `_EXCLUDED_SENTINEL` and nudges any
  exact-zero values, same as before.
- `_Grid`'s public interface (`lon_of`/`lat_of`/`value_at`/`set_value`/`padded_cols`/
  `padded_rows`) is unchanged, so marching squares, closing, ring assembly, classification, clip,
  and simplify are all untouched.

## Test results

- `ruff format`/`ruff check` — clean.
- `pytest` — 387 passed, no count change (existing tests assert exact hole shapes/exterior
  boundaries/hole-vs-no-hole outcomes at specific radii, which still pass unchanged — strong
  evidence the new field construction produces equivalent results to the old one, not just
  "doesn't crash").
- Synthetic benchmark (35,642 uniformly-random points over a Berlin-sized bbox, radius=200):
  **7.3s** total, vs. the real Berlin baseline's **146.7s** (99% of which was `grid`) — ~20x
  speedup on a synthetic case that doesn't even benefit from splatting as much as real clustered
  urban data should (uniform random points don't create the dense per-corner bucket overload that
  motivated this fix in the first place).
- **Real re-measurement, same baseline parameters** (new Napoli area, radius 200, same 6-area
  catalog — `tasks/radius_200_baseline.txt` vs. `tasks/radius_200_improvements.txt`):
  - Berlin bare `__void__` (35,642 points): `grid` 145.4s → 3.9s (**37x**).
  - Prague bare (10,667 pts): 68.8s → 3.2s (**21x**).
  - Stockholm bare (5,614 pts): 46.4s → 3.1s (**15x**).
  - Napoli bare (2,843 pts): 44.1s → 1.9s (**23x**).
  - Summed `total=` across every `compute_void_feature` call, all 6 areas: **~565s (9.4 min) →
    ~48s (0.8 min)**, ~12x end-to-end for the whole `VoidWorker` pass (an undercount — several of
    the smallest variants dropped under the 0.5s slow-logging threshold entirely in the new run
    and stopped appearing in the log).
  - `classify` times essentially unchanged (Berlin: 0.643s → 0.572s) — confirms the fix targeted
    the actual bottleneck without touching (or regressing) anything else.
- **`default_radius_m` is not a perf lever.** Re-ran the same Napoli/6-area scenario with
  `VoidTask.default_radius_m` at 100 instead of 200 (`tasks/radius_100_improvements.txt` vs.
  `tasks/radius_200_improvements.txt`): `grid` times are unchanged within noise (Berlin bare
  `__void__` 3.987s @ r100 vs 3.908s @ r200; Prague bare 3.138s vs 3.225s). Cause: grid resolution
  is capped at `_MAX_GRID_CELLS_PER_AXIS = 200` cells/axis (`void_geometry.py:95-98`), so for a
  city-sized bbox cell size is set by the cap, not the 25m target — and `_splat_point`'s search
  span is `radius_m + padding_m` where `padding_m = max(cell_lon_m, cell_lat_m) * 2` grows with
  cell size. With capped (large) cells, `padding_m` dominates the search span and the 100m
  difference in `radius_m` barely moves it. `default_radius_m` was still changed to 100
  (`contracts.py:78`) as a deliberate value for void-circle sizing, independent of this perf work.
