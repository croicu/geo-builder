# PROTOCOL.md

## Command Line

```text
geo-builder <tasks_path> [--in <dir>] [--out <dir>] [--edit] [--rebuild <id>]
```

| Argument | Default | Description |
|---|---|---|
| `tasks_path` | required | Tasks JSON file. Always required. |
| `--in <dir>` | `./in` | Working directory for service artifacts. Auto-created if absent. |
| `--out <dir>` | `./out` | Output directory for built artifacts. |
| `--edit` | off | Open the designer WebView instead of running a build (requires `designUrl` in `settings.json`). |
| `--rebuild <id>` | off | Force re-acquisition of this area id regardless of existing `--in` data. Repeatable; build mode only. `all` forces every loaded area. See `docs/CLI.md` for full semantics. |

**Build mode** (no `--edit`) — runs the processing pipeline and writes artifacts to `--out`. Output is never written when errors are present. `--in` seeds the catalog for incremental builds; a missing or empty `--in` starts from scratch. `--rebuild` overrides the default implicit (data-presence-based) acquisition skip logic with an explicit, validated area list.

**Designer mode** (`--edit`) — opens the geo-browser WebView. On first launch (empty `--in`) pulls all artifacts from the service into `--in` before the WebView starts. Subsequent launches serve directly from `--in`; use the refresh action in the UI to re-pull. The tasks file is used by `SetAreaBbox` to rebuild `--out` after a bbox change.

## File Schema

Configuration is split across two files:

**`settings.json`** — stable settings, auto-loaded from `./settings.json` if it exists. Contains `settings` and `providers`.

```json
{
  "settings": {
    "debug": false,
    "logging": "error",
    "designUrl": "http://localhost:5173/?design=1",
    "map": {
      "center": "47.726,-122.106",
      "zoom": 10
    }
  },
  "providers": {
    "overpass": {
      "url": "https://overpass-api.de/api/interpreter"
    }
  }
}
```

At designer launch, `settings.py` appends query parameters to `designUrl` in this order:
- `debug=1` — when `debug` is `true`
- `center=<value>` — from `map.center` if present
- `zoom=<value>` — from `map.zoom` if present

**`settings.local.json`** — local overrides, gitignored. Loaded after `settings.json`; any key present here wins. Used to persist window geometry across designer sessions.

```json
{
  "settings": {
    "window": {
      "left": 100,
      "top": 50,
      "width": 1400,
      "height": 900
    }
  }
}
```

**Tasks file** (e.g. `template.json`) — passed as the CLI positional argument. Contains a named dictionary of tasks processed in declaration order.

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

| Field     | Type                      | Required | Description |
|-----------|---------------------------|----------|-------------|
| `values`  | `list[str]`               | yes      | OSM tag values (literals, meta names, or `["*"]` wildcard) |
| `name`    | `str`                     | no       | Display name for the layer in the manifest |
| `type`    | `"heatmap" \| "circle"`   | no       | Render mode (default `"heatmap"`) |
| `color`   | `str`                     | no       | Hex color override for this layer (e.g. `"#ffff00"`) |
| `scale`   | `float`                   | no       | `radiusScale` override for the heatmap layer (default `1.0`) |
| `surface` | `bool`                    | no       | `circle` only — treat feature as an area rather than a point (default `false`) |

### Templates

A `"type": "acquisition"` entry without a `bbox` field is a **template** — it defines an acquisition config (provider + filters) that the designer can apply to new areas at design time. Templates are stored in `Settings.templates` and never executed directly by the build pipeline.

```json
{
  "acquisition": {
    "type": "acquisition",
    "provider": "overpass",
    "filters": {
      "amenity": { "name": "Restaurants", "values": ["sustenance"], "type": "heatmap" }
    }
  }
}
```

The `"acquisition"` key is the default template name referenced by the `AddArea` designer API. Any number of named templates may coexist with concrete (bbox-bearing) tasks in the same file.

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
