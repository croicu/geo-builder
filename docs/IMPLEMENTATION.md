# IMPLEMENTATION.md

## Suggested Layout

```text
geo_builder/
  cli.py
  tasks.py
  executor.py
  protocols.py
  contracts.py

  workers/
    acquisition_worker.py
    deduping_worker.py
    aggregation_worker.py
    worker_factory.py

  providers/
    provider_factory.py
    overpass_provider.py

tests/
docs/
```

## CLI

```text
geo-builder <task_path> [--in <in_directory>] [--out <out_directory>]
```

## Execution Model

The executor uses a stack (`append` / `pop`) to process tasks depth-first.

## Acquisition

1. Resolve provider
2. `executor.add_area(task)`
3. Fetch layer
4. `executor.add_layer(area, layer)`
5. On provider failure, split bbox into four tasks

## Deduplication

- Scope: one layer
- Distance threshold: 10 meters
- First feature wins
- Alternate names and amenities are accumulated into arrays

## Aggregation

- Scope: one area
- Group by `mergeKey`
- Concatenate features
- Replace source layers with one merged layer

## Designer Handler Pattern

Every return statement in a `host.py` handler function must be wrapped in `MethodResult(...)` — for both error and success (`OK`) cases. `MethodResult` is the single exit path for all handlers; it logs a warning for any non-OK result and is a no-op for OK.

```python
# correct
return MethodResult(SetAreaBboxOutput(error=OK))
return MethodResult(SetAreaBboxOutput(error=ERR_AREA_NOT_FOUND, errorDescription="..."))

# wrong — bare return bypasses the exit-path convention
return SetAreaBboxOutput(error=OK)
```

## Interactive Session — Threading Model

All reads and writes to the model (catalog, areas, layers) must happen on the `run_dispatcher` thread — the thread that runs `Gateway.run()`.

`Gateway` enforces this by routing every inbound message and every outbound call through its internal `Queue`. Both JS→Python events and Python→JS method callbacks are dispatched by that same loop, so handler code is always on the dispatcher thread.

Any model access that bypasses this queue (e.g. reading catalog state from the WinForms UI thread or from a one-off `threading.Thread`) is subject to race conditions and must be avoided.

## Feature Enrichment (Overpass)

During acquisition, `OverpassProvider._to_geojson` extracts additional OSM tags for each element:

- `name`, `cuisine`, `opening_hours` — taken directly from element tags
- `address` — assembled from `addr:street` + `addr:housenumber` + `addr:city`; falls back to `addr:full`
- `phone` — `contact:phone` preferred, falls back to `phone`
- `website` — `contact:website` preferred, falls back to `website`

`hasDetails: true` is set on a feature when at least one of the above fields is present. Features without any detail fields carry only `weight` (and the standard id/name/amenity properties).

Review/search URLs (Foursquare, Google Maps, Yelp) are **not** baked into the GeoJSON; they are computed at render time in the browser from `name` and coordinates.

## POI Layer

`PoiWorker` runs after aggregation and deduping. For each area it:

1. Scans all layers for features with `hasDetails: true`.
2. If any are found, inserts a **stub** `Layer` with `type: "poi"` into the area's layer list. The stub has no `url` and no `geojson`; it is manifest-only metadata.
3. If none are found (or the area was updated and details disappeared), removes any existing stub.

The stub's presence in the manifest is the signal to the browser that POI data exists and the layer should appear in the layer selection widget. Style properties (name, color, radius, opacity) are driven by the `style` block in the `poi` task definition in tasks.json and stored as `PoiStyle` in `protocols.py`.

Persistence skips `save_layer` for stub layers (`url is None`). Loading skips the GeoJSON file read for the same reason.

## Overpass Query Shape

Multi-value filters use a **regex union** instead of one filter line per value:

```
# Before (N values × 3 element types = 3N lines):
node["amenity"="bar"](bbox);
node["amenity"="cafe"](bbox);
...

# After (always 3 lines per key):
node["amenity"~"^(bar|cafe|restaurant|...)$"](bbox);
way["amenity"~"^(bar|cafe|restaurant|...)$"](bbox);
relation["amenity"~"^(bar|cafe|restaurant|...)$"](bbox);
```

Single-value filters still use `=` equality. Wildcards (`*`) use the bare key form `["amenity"]`.

## Overpass Error Handling

HTTP status codes are handled differently:

| Code | Meaning | Action |
|------|---------|--------|
| 400 | Query rejected / data too large | Raise `ProviderError` immediately → AcquisitionWorker splits bbox |
| 429 | Rate limited | Retry with backoff (5 s, 15 s, 45 s); after exhausting retries → raise `ProviderError` |
| 504 | Gateway timeout | Same as 429 |
| other | Unexpected | Re-raise as-is |

Retry delays are defined in `_RETRY_DELAYS = (5, 15, 45)` in `overpass.py`.
