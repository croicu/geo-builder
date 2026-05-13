# geo-builder

Static GeoJSON generation pipeline for the geo ecosystem.

---

## Purpose

`geo-builder` is the offline/static data-generation pipeline for the geo ecosystem.

Its responsibility is to generate GeoJSON layer files and related static assets consumed by:

- `geo-browser`
- `geo-ios` (future)
- `geo-desktop` (future)

`geo-builder` does NOT:

- render maps
- host APIs
- run backend services

`geo-builder` is a pure preprocessing/export pipeline.

---

# Architecture

Pipeline:

```text
raw photo metadata
→ filtering / clustering / weighting
→ GeoJSON generation
→ static layer files
```

Output is fully static and immutable.

Generated artifacts are committed/published as static files.

---

# Relationship to geo-browser

`geo-browser` is the renderer.

`geo-builder` is the producer.

## geo-builder owns

- GeoJSON generation
- weighting logic
- clustering logic
- export pipeline

## geo-browser owns

- rendering
- interaction
- state
- viewport
- UI

---

# Shared Contract Philosophy

`geo-builder` must generate payloads compatible with the existing `geo-browser` protocols.

Current layer contract:

```json
{
  "id": "debug-heat",
  "name": "Debug Heat",
  "type": "heatmap",
  "url": "/areas/napoli/layers/flickr.geojson",
  "visible": true
}
```

Current GeoJSON shape:

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": {
        "weight": 0.9
      },
      "geometry": {
        "type": "Point",
        "coordinates": [14.2681, 40.8518]
      }
    }
  ]
}
```

Important architectural invariant:

`geo-browser` treats payloads as open/unknown JSON.

Validation is capability-based, not schema-heavy.

Therefore `geo-builder` should:

- emit stable/simple GeoJSON
- avoid overengineering schemas
- preserve forward compatibility

---

# Initial V1 Goal

Minimal pipeline:

## Input

- directory of photos
OR
- metadata json/csv

## Output

GeoJSON `FeatureCollection` containing `Point` features.

Each feature may contain:

- coordinates
- optional weight

Nothing else yet.

---

# Initial Area Example

Napoli:

```json
{
  "id": "napoli",
  "name": "Napoli",
  "center": [40.8518, 14.2681],
  "radiusMeters": 12000,

  "minRadiusPx": 32,
  "maxRadiusPx": 512,
  "liveMapRadiusPx": 640
}
```

Important:

Area center uses:

```text
[latitude, longitude]
```

GeoJSON coordinates use:

```text
[longitude, latitude]
```

Example:

```text
Area center: [40.8518, 14.2681]
GeoJSON point: [14.2681, 40.8518]
```

---

# Repository Structure

```text
geo-builder/
  pyproject.toml

  geo_photo/
    __init__.py

    protocols.py
    area.py
    loader.py
    weighting.py
    geojson_writer.py
    pipeline.py
    cli.py

    sources/
      flickr.py

  tests/
```

---

# Design Principles

- static-first
- deterministic output
- explicit/simple code
- minimal dependencies
- readable Python over clever Python
- no database
- no backend
- no framework

---

# Ecosystem Conventions

Across the geo ecosystem:

- `protocols` = data contracts
- `contracts` = behavioral/runtime boundaries
- explicit lifecycle preferred
- avoid terse clever idioms
- dependency injection preferred over mocks
- tests should avoid network access
- immutable/static artifacts preferred

---

# Current Ecosystem

- `geo-browser` → TypeScript renderer
- `geo-builder` → Python data generator
- `geo-ios` → future native renderer
- `geo-desktop` → future desktop renderer
- `geo-schema` → optional future shared contracts repo

---

# Initial Flickr Pipeline

```text
AreaSpec
→ FlickrPhotoRecord[]
→ PhotoPoint[]
→ WeightedPoint[]
→ FeatureCollection
→ flickr.geojson
```

Initial flow:

```text
load AreaSpec
→ query Flickr around center
→ normalize metadata
→ filter to radiusMeters
→ compute optional weight
→ generate GeoJSON
→ export static file
```

Initial output target:

```text
public/areas/napoli/layers/flickr.geojson
```

---

# V1 Constraints

V1 intentionally avoids:

- live APIs in production
- databases
- server-side rendering
- schema-heavy validation
- clustering engines
- advanced GIS dependencies

The goal is to prove the static geometry pipeline first.
