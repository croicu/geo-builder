# geo-builder

Deterministic static-geodata pipeline and WebView design host for the geo ecosystem.

---

## Purpose

`geo-builder` has two roles today:

1. **Static data pipeline** — generates GeoJSON layer files and related static assets (catalog, manifests, CSV exports) consumed by `geo-browser` (and future `geo-ios`/`geo-desktop` clients).
2. **Design-mode host** — via `geo-builder <tasks> --edit`, it opens a native WebView2 window, loads `geo-browser` inside it in `?design=1` mode, and exposes a small bidirectional message API (`src/geo_builder/api.py`, `designer/gateway.py`) so the embedded browser can add/edit areas, change a bbox, add user points, and forward its own telemetry back into geo-builder's logs. See `docs/PROTOCOL.md`, `docs/MESSAGING.md`, and `docs/ARCHITECTURE.md`'s "Design Mode Integration" section for the full contract.

`geo-builder` does NOT:

- render maps itself — rendering, interaction, and viewport state live entirely in the embedded `geo-browser` instance, even in design mode
- run a network-facing backend or listening service — the WebView host is a local desktop process; `designer/data_pipeline.py` intercepts the WebView's own HTTP requests in-process (memory → `--out` → `--in` → network) rather than exposing anything for other processes to call
- use a database — all state is static JSON/GeoJSON files on disk

`geo-builder` is a static-first pipeline that, in design mode, also drives a local editing UI for the data it produces — it is not a server.

---

## Architecture

Build pipeline (`docs/ARCHITECTURE.md` has the full breakdown):

```text
Task[]
    → Builder (stack-based DFS)
    → WorkerFactory
    → Worker.execute(executor)
    → Catalog mutation (in-memory)
    → persistence.save_catalog()
    → static files (catalog.json, manifests, .geojson, .csv)
```

Design mode adds a second loop around the same `Builder`/`Catalog` machinery:

```text
geo-builder (Python, pywebview/WebView2 host)
    ↕ bidirectional message API (docs/MESSAGING.md)
geo-browser (?design=1, running inside the WebView)
```

Designer actions (`AddArea`, `SetAreaBbox`, manifest edits, …) call back into the same `Builder`/`persistence` layer used by a plain build — there is no separate code path for interactive vs. batch processing.

Output is fully static, deterministic, and immutable once written.

---

## Relationship to geo-browser

`geo-browser` is the renderer. `geo-builder` is the producer — and, in design mode, the host that embeds a `geo-browser` instance for interactive editing.

### geo-builder owns

- GeoJSON generation (acquisition, aggregation, deduping, void/POI/search derivation)
- the catalog/manifest/layer file format and persistence
- the design-mode WebView host and its message API

### geo-browser owns

- rendering
- interaction
- UI state, viewport
- (in design mode) issuing API calls back into geo-builder and rendering geo-builder's responses

---

## Shared Contract Philosophy

`geo-builder` must generate payloads compatible with `geo-browser`'s protocols. Current manifest layer entry (see `docs/ARCHITECTURE.md` for the full `manifest.json` schema):

```json
{
  "id": "1",
  "name": "Restaurants",
  "type": "heatmap",
  "url": "./layers/1.geojson",
  "visible": true,
  "style": { "opacity": 0.7, "radiusScale": 1.0, "color": "#ff0000" },
  "acquisition": { "provider": "overpass", "filter": "amenity", "values": ["restaurant"] }
}
```

Current GeoJSON shape:

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": {},
      "geometry": {
        "type": "Point",
        "coordinates": [14.2681, 40.8518]
      }
    }
  ]
}
```

Important architectural invariant:

`geo-browser` treats payloads as open/unknown JSON. Validation is capability-based, not schema-heavy.

Therefore `geo-builder` should:

- emit stable/simple GeoJSON
- avoid overengineering schemas
- preserve forward compatibility

---

## Coordinate Conventions

Area `center` uses `[latitude, longitude]`. GeoJSON `coordinates` use `[longitude, latitude]`. The conversion happens at provider boundaries (`providers/overpass.py`).

```json
{
  "id": "napoli",
  "name": "Napoli",
  "center": [40.8518, 14.2681]
}
```

```text
Area center:  [40.8518, 14.2681]   (lat, lon)
GeoJSON point: [14.2681, 40.8518]  (lon, lat)
```

---

## Providers

Providers are isolated under `src/geo_builder/providers/`.

**Current:**

- `OverpassProvider` — fetches OSM amenity data via the Overpass API; supports meta-amenity expansion (e.g. `sustenance` → bar, cafe, …)
- `FakeProvider` — offline stub that reads a local JSON file; used in tests and local dev, keeps the test suite network-free

**Future (see `docs/ROADMAP.md`):**

- `FlickrProvider` — geotagged-photo acquisition, revisiting the project's original photo-metadata pipeline concept as one provider among several rather than the whole system
- `NominatimProvider`

---

## Commands

```bash
# Install (editable, with dev deps)
pip install -e ".[dev]"

# Build
geo-builder template.json                        # fresh build to ./out
geo-builder template.json --in ./in --out ./out  # incremental build

# Designer (requires designUrl in settings.json)
geo-builder template.json --edit                        # pull on first run, then open WebView
geo-builder template.json --in ./in --out ./out --edit  # same with explicit paths

# Lint
ruff check src/ tests/
ruff format src/ tests/

# Test
pytest
```

---

## Repository Structure

```text
geo-builder/
  pyproject.toml
  settings.json
  template.json

  src/geo_builder/
    cli.py
    builder.py
    contracts.py
    protocols.py
    persistence.py
    settings.py
    diagnostics.py
    api.py

    entities/   # behavior over protocol types (GeoCatalog, GeoArea, GeoLayer)
    workers/    # AcquisitionWorker, AggregationWorker, DedupingWorker, PoiWorker, VoidWorker, SearchWorker
    providers/  # OverpassProvider, FakeProvider, WorkerFactory
    designer/   # WebView host, message gateway, data pipeline, pull

  tests/
  docs/         # ARCHITECTURE, PROTOCOL, MESSAGING, CLI, LAYERS, MANIFEST, ROADMAP
```

---

## Design Principles

- static-first
- deterministic output
- explicit/simple code (see `CLAUDE.md`'s Coding Style — no comprehensions, no lambdas)
- minimal dependencies
- readable Python over clever Python
- no database
- no network-facing backend
- no framework

---

## Ecosystem Conventions

Across the geo ecosystem:

- `protocols.py` = pure data contracts (dataclasses only, no behavior)
- `contracts.py` = behavioral/runtime boundaries
- explicit lifecycle preferred
- avoid terse clever idioms
- tests should avoid network access
- immutable/static artifacts preferred

---

## Current Ecosystem

- `geo-browser` → TypeScript renderer, embedded by geo-builder in design mode
- `geo-builder` → Python data generator + design-mode WebView host
- `geo-ios` → future native renderer
- `geo-desktop` → future desktop renderer
- `geo-schema` → optional future shared contracts repo

---

## Further Documentation

- `CLAUDE.md` — mission, invariants, coding style, task workflow
- `docs/ARCHITECTURE.md` — modules, data flow, contracts, design-mode threading model
- `docs/PROTOCOL.md` — CLI signature, `settings.json`/`template.json` schema
- `docs/MESSAGING.md` — the geo-builder ↔ geo-browser message API (shared with geo-browser to keep contracts in sync)
- `docs/CLI.md`, `docs/LAYERS.md`, `docs/MANIFEST.md` — command reference, layer types, manifest format
- `docs/ROADMAP.md` — completed / near-term / long-term plans
