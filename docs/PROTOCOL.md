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

## Overpass Filter and Meta Amenities

The `filter` object maps OSM tag keys to lists of values. Values may be literal OSM amenity strings or meta category names defined in `AMENITY_META`:

| Meta name       | Expands to                                                               |
|-----------------|--------------------------------------------------------------------------|
| `sustenance`    | bar, biergarten, cafe, fast_food, food_court, ice_cream, pub, restaurant |
| `education`     | college, kindergarten, library, school, university                       |
| `healthcare`    | clinic, dentist, doctors, hospital, pharmacy, veterinary                 |
| `financial`     | atm, bank, bureau_de_change                                              |
| `entertainment` | arts_centre, casino, cinema, nightclub, theatre                          |
| `transportation`| bicycle_parking, bicycle_rental, bus_station, car_rental, fuel, parking, taxi |

Meta names are expanded in the Overpass query but preserved verbatim in the `mergeKey` (and therefore the layer `id`). Mixed lists (meta + literal) are deduplicated.
