# SUMMARY.md

Running log of decisions, bugs fixed, and patterns established. Trim or ask Claude to compact as needed.

---

## Provider config (2026-05-13)

`build.json` has a top-level `"providers"` dict alongside `"settings"` and `"tasks"`. Each entry is the provider's own static config — no provider-specific data in tasks.

```json
"providers": {
  "overpass": { "url": "https://overpass-api.de/api/interpreter" },
  "fake":     { "dataPath": "tests/data/providers/fake.json" }
}
```

`ProviderFactory` reads `Settings.current().providers.get(name, {})` and passes the slice to the provider constructor.

## FakeProvider (2026-05-13)

Registered as `"fake"`. Set `"provider": "fake"` in a task to skip network calls during local development. Subclasses `OverpassProvider`, overrides only `_execute_query` to load from the configured `dataPath`. All conversion logic (`_to_geojson`, `_create_merge_key`) is inherited and exercised identically to the real provider. Test data: `tests/data/providers/fake.json`.

## Layer id/url collision fix (2026-05-13)

`Builder.add_layer` merges features into an existing layer when `mergeKey` matches, rather than appending a duplicate entry. Layer `id` and `url` are derived from `mergeKey` via `Layer.id_from_merge_key()` (sanitizes to lowercase alphanumeric + underscores). This prevents two providers covering the same amenity set from writing to the same `.geojson` file on disk.

## Static methods on dataclasses (2026-05-13)

User preference: static methods that semantically belong to a class live inside the class, even if they don't use `self`. Example: `Layer.id_from_merge_key` lives on `Layer` in `protocols.py`, not as a module-level helper in the provider. Captured in CLAUDE.md invariant #3.

## add_layer merge behaviour (2026-05-13)

When `Builder.add_layer` is called with a layer whose `mergeKey` already exists on the area, it extends the existing layer's features rather than appending a new layer. This handles bbox decomposition (quadrant sub-tasks) transparently — all quadrant results fold into one layer.

---

## Meta amenity expansion / FEATURE_META (2026-05-14)

`FEATURE_META: dict[str, dict[str, list[str]]]` in `overpass.py` maps OSM tag keys → meta group names → individual OSM values. `_expand_filter` uses the per-key meta to expand values before building the Overpass query, while `_create_merge_key` uses the original (unexpanded) filter so the layer id is human-readable (`overpass_amenity_sustenance`, not `overpass_amenity_bar_cafe_...`).

Defined groups:

- `amenity`: sustenance, education, healthcare, financial, entertainment, transportation
- `historic`: monuments (castle, fort, ruins, …), memorials (monument, memorial, …)

Keys with no groups (e.g. `leisure`) pass values straight through. `["*"]` is a wildcard that generates the key-only Overpass form (`node["historic"](bbox)`), useful for broad sweeps but picks up everything including cemeteries — use named groups to be selective.

## Per-key filter splitting (2026-05-14)

`AcquisitionWorker` detects multi-key filters (`len(filter) > 1`) and pushes one single-key `AcquisitionTask` per key before returning. Each child task is an independent Overpass fetch that produces its own layer. This keeps each layer semantically homogeneous and enables per-layer color and mergeKey identity.

## Per-layer color assignment (2026-05-14)

`colors.py` generates a maximally-spread hue sequence starting at 240° (blue): step 120°, then interleaved at 60°, 30°, 15°, … offsets. `Builder.add_layer` always auto-assigns a color from the sequence (index = current layer count in the area). The provider no longer sets a default color — builder owns all color assignment.

First six colors: blue (#0000ff), red (#ff0000), green (#00ff00), magenta (#ff00ff), yellow (#ffff00), cyan (#00ffff).

## filterColors override (2026-05-14)

`AcquisitionTask.filterColors: dict[str, str]` carries per-key hex color overrides, parsed from `build.json`:

```json
"filterColors": { "leisure": "#00ff00" }
```

`_split_by_key` and `_split_task` both propagate `filterColors` to child tasks. `AcquisitionWorker` applies the override **after** `executor.add_layer` (so the builder's auto-color always runs first, then the override wins on the same mutable layer object). Merged layers (bbox retry, same mergeKey) keep the color assigned when first added.

## Deduping threshold fix (2026-05-14)

`DedupingWorker._is_duplicate` threshold corrected from 1 m to 10 m. CLAUDE.md and the test comments documented 10 m; the code had 1 m, causing near-duplicates (~8 m apart) to be kept.

## Per-area CSV output (2026-05-14)

`persistence.save_area_csv` writes `{areaId}.csv` into each area directory, combining all layer features. Columns: `lon`, `lat`, `layer_id`, then all unique property keys (sorted). Missing properties → empty string. Called automatically by `save_catalog`.

## OSM key handling (2026-05-14)

OSM tag keys are arbitrary strings — there is no fixed canonical list. The filter dict accepts any key (`amenity`, `leisure`, `historic`, `tourism`, …). An enum would be too restrictive.
