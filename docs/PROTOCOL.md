# PROTOCOL.md

## Command Line

```text
geo-builder <task_path> [--in <in_directory>] [--out <out_directory>] [--debug]
```

`--debug` disables all `GeoError` catch blocks so exceptions propagate with full tracebacks. Output is never written when errors are present.

## Task Schema

```json
{
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
}
```

## Layer Merge Rule

Layers are mergeable if they share the same `mergeKey`.
