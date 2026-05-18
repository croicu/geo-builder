# PROTOCOL.md

## Command Line

```text
geo-builder <tasks_path> [--in <dir>] [--out <dir>] [--edit]
```

| Argument | Default | Description |
|---|---|---|
| `tasks_path` | required | Tasks JSON file. Always required. |
| `--in <dir>` | `./in` | Working directory for service artifacts. Auto-created if absent. |
| `--out <dir>` | `./out` | Output directory for built artifacts. |
| `--edit` | off | Open the designer WebView instead of running a build (requires `designUrl` in `build.json`). |

**Build mode** (no `--edit`) — runs the processing pipeline and writes artifacts to `--out`. Output is never written when errors are present. `--in` seeds the catalog for incremental builds; a missing or empty `--in` starts from scratch.

**Designer mode** (`--edit`) — opens the geo-browser WebView. On first launch (empty `--in`) pulls all artifacts from the service into `--in` before the WebView starts. Subsequent launches serve directly from `--in`; use the refresh action in the UI to re-pull. The tasks file is used by `SetAreaBbox` to rebuild `--out` after a bbox change.

## File Schema

Configuration is split across two files:

**`build.json`** — stable settings, auto-loaded from `./build.json` if it exists. Contains `settings` and `providers`.

```json
{
  "settings": {
    "debug": false,
    "logging": "error"
  },
  "providers": {
    "overpass": {
      "url": "https://overpass-api.de/api/interpreter"
    }
  }
}
```

**Tasks file** (e.g. `tasks.json`) — passed as the CLI positional argument. Contains a named dictionary of tasks processed in declaration order.

```json
{
  "fetch_napoli": {
    "type": "acquisition",
    "areaId": "napoli",
    "areaName": "Napoli",
    "provider": "overpass",
    "bbox": {
      "west": 14.20,
      "south": 40.80,
      "east": 14.33,
      "north": 40.90
    },
    "filters": {
      "amenity":  { "values": ["restaurant", "cafe", "bar"] },
      "historic": { "values": ["monuments", "memorials"], "scale": 3.0, "color": "#ffff00" }
    }
  },
  "aggregate": { "type": "aggregation" },
  "dedupe":    { "type": "deduping" }
}
```

Each entry in `filters` is an `AreaStyle` record:

| Field    | Type            | Required | Description |
|----------|-----------------|----------|-------------|
| `values` | `list[str]`     | yes      | OSM tag values (literals, meta names, or `["*"]` wildcard) |
| `color`  | `str`           | no       | Hex color override for this layer (e.g. `"#ffff00"`) |
| `scale`  | `float`         | no       | `radiusScale` override for the heatmap layer (default `1.0`) |

`settings.debug: true` disables all `GeoError` catch blocks so exceptions propagate with full tracebacks. It also writes per-task snapshots to `./build/{task_type}/{counter:03d}/` (see **Debug Output** below).

`settings.logging` controls the minimum log level printed to stdout during a designer session. Accepted values: `verbose`, `info`, `warning`, `error`, `critical`. Default: `error`.

## Debug Output

When `debug: true`, after each worker executes `Builder` writes:

```text
./build/{task_type}/{counter:03d}/
    catalog.json          — full catalog + areas + layers (no embedded geojson)
    {layer_id}.geojson    — only layers added or modified by this task
    {layer_id}.csv        — lon/lat + all feature properties for each geojson
```

The counter is global across all task types so folder numbers reflect execution order. A layer only appears as a geojson/csv file if it was new or had its feature count change.

## Layer Merge Rule

Layers are mergeable if they share the same `mergeKey`.

## Overpass Filters and Meta Features

The `filters` object maps arbitrary OSM tag keys to `AreaStyle` records. The `values` list may contain literal OSM tag values or meta category names defined in `FEATURE_META` for that key.

Currently defined meta groups (under the `amenity` key):

| Meta name       | Expands to                                                               |
|-----------------|--------------------------------------------------------------------------|
| `sustenance`    | bar, biergarten, cafe, fast_food, food_court, ice_cream, pub, restaurant |
| `education`     | college, kindergarten, library, school, university                       |
| `healthcare`    | clinic, dentist, doctors, hospital, pharmacy, veterinary                 |
| `financial`     | atm, bank, bureau_de_change                                              |
| `entertainment` | arts_centre, casino, cinema, nightclub, theatre                          |
| `transportation`| bicycle_parking, bicycle_rental, bus_station, car_rental, fuel, parking, taxi |

Currently defined meta groups (under the `historic` key):

| Meta name   | Expands to                                                                      |
|-------------|---------------------------------------------------------------------------------|
| `monuments` | castle, fort, manor, tower, gate, ruins, archaeological_site, city_gate        |
| `memorials` | monument, memorial, milestone, boundary_stone, wayside_cross, wayside_shrine   |

Keys with no meta groups defined (e.g. `leisure`, `tourism`) pass values through unchanged. Use `["*"]` for a key-only wildcard match (e.g. `"historic": ["*"]` → `node["historic"](bbox)`). Meta names are expanded in the Overpass query but preserved verbatim in the `mergeKey` (and therefore the layer `id`). Mixed lists (meta + literal) are deduplicated.
