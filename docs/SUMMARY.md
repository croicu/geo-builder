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
