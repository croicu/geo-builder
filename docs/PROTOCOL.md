# PROTOCOL.md

## Command Line

```text
geo-builder <settings_path> [--in <in_directory>] [--out <out_directory>]
```

Output is never written when errors are present.

## Build File Schema

The build file (e.g. `build.json`) contains a `settings` object and a named `tasks` dictionary. Tasks are processed in declaration order.

```json
{
  "settings": {
    "debug": false
  },
  "tasks": {
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
      "filter": {
        "amenity": ["restaurant", "cafe", "bar"]
      }
    },
    "aggregate": { "type": "aggregation" },
    "dedupe":    { "type": "deduping" }
  }
}
```

`settings.debug: true` disables all `GeoError` catch blocks so exceptions propagate with full tracebacks.

## Layer Merge Rule

Layers are mergeable if they share the same `mergeKey`.
