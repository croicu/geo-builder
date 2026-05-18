# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Mission

Build a simple, deterministic Python application that creates static geographic datasets for the geo ecosystem.

## Collaboration rules

- Before implementing any feature or non-trivial change, ask clarifying questions until the intent is unambiguous.
- If anything is unclear or could be interpreted multiple ways, ask — do not assume and implement.

## Documentation rule

After any change that affects the public interface, CLI, file formats, or core architecture, update the relevant docs:

- `CLAUDE.md` — commands, pipeline, architecture notes
- `docs/ARCHITECTURE.md` — modules, data flow, contracts
- `docs/PROTOCOL.md` — CLI signature, build file schema
- `docs/MESSAGING.md` — anything that affects browser code (API shapes, wire protocol, error codes, architectural decisions visible to the TypeScript side) must be reflected here; this file is shared with geo-browser to keep contracts in sync. This includes but is not limited to changes to `src/geo_builder/api.py`

## Off-limits directories

Never read, glob, or search inside `./in/` or `./out/`. They contain large volumes of generated data and are not part of the source tree.

## Commands

```bash
# Install (editable, with dev deps)
pip install -e ".[dev]"

# Build
geo-builder tasks_production.json                        # fresh build to ./out
geo-builder tasks_production.json --in ./in --out ./out  # incremental build

# Designer (requires designUrl in build.json)
geo-builder tasks_production.json --edit                        # pull on first run, then open WebView
geo-builder tasks_production.json --in ./in --out ./out --edit  # same with explicit paths

# Lint
ruff check src/ tests/
ruff format src/ tests/

# Test
pytest
pytest tests/test_foo.py::test_bar   # single test
```

## Core Invariants

1. `geo-builder` builds; `geo-browser` displays.
2. Internal processing uses strongly typed dataclasses.
3. `protocols.py` contains persisted/shared data contracts — pure data only, no behavior. Behavior that operates on protocol types belongs in entity classes under `geo_builder/entities/` (e.g. `catalog_entity.py`). *(Entity layer not yet implemented — existing methods on protocol classes are technical debt.)*
4. `contracts.py` contains runtime behavioral interfaces.
5. Execution mutates an in-memory catalog.
6. Persistence occurs only after successful completion.
7. Child paths are relative to their parent files.
8. Prefer explicit, readable Python over clever abstractions.
9. Tests must run offline.
10. Static artifacts are immutable and deterministic.

## Coding Style

- **Protocols are pure data** — `protocols.py` holds dataclasses only. No methods, no logic. Behavior lives in entity classes (`geo_builder/entities/`).
- **Explicit over brief** — if two implementations are equivalent, choose the one that is easier to read and debug, even if it is longer.
- **No list/dict/set comprehensions** — use explicit `for` loops. Comprehensions obscure control flow and make multi-step logic harder to follow.
- **No lambdas** — use named functions or plain `for` loops. Lambdas hide intent and cannot be stepped through in a debugger.

## Processing Pipeline

```text
Task[]
    → Builder (stack-based DFS)
    → WorkerFactory
    → Worker.execute(executor)
    → Catalog mutation
    → persistence.save_catalog()
```

## Task Types

- AcquisitionTask
- DedupingTask
- AggregationTask

## Worker Responsibilities

- AcquisitionWorker: provider fetch + area creation + layer insertion
- DedupingWorker: remove near-duplicates within each layer (10 m Haversine threshold)
- AggregationWorker: merge compatible layers within an area (grouped by `mergeKey`)

## Provider Strategy

Providers are isolated under `providers/`.

Current:
- OverpassProvider — fetches OSM amenity data via Overpass API; supports meta amenity expansion (e.g. `sustenance` → bar, cafe, …)
- FakeProvider — offline stub that reads a local JSON file; used in tests and local dev

Future:
- FlickrProvider
- NominatimProvider

## Key Architecture Notes

**Coordinate conventions** — Area `center` is `[lat, lon]`; GeoJSON `coordinates` are `[lon, lat]`. The conversion happens at provider boundaries (`overpass.py`).

**Bbox decomposition** — When OverpassProvider receives a 400/429/504, AcquisitionWorker splits the bbox into four quadrants and pushes them back onto the executor stack. This is the mechanism for handling "request too large" errors without caller involvement.

**AreaStyle** — Each filter key in an acquisition task carries an `AreaStyle(values, color, scale)` record. `color` overrides the auto-assigned layer color; `scale` overrides `radiusScale` in the heatmap style (useful for sparse layers like historic places). Both are optional.

**MergeKey format** — `"provider:key1=val1,val2"` (e.g., `"overpass:amenity=restaurant,cafe"`). AggregationWorker groups layers within an area by this key and concatenates their features into a single layer.

**Layer id/url derived from mergeKey** — `Layer.id_from_merge_key(merge_key)` sanitizes the mergeKey into a filesystem-safe string used as both the layer `id` and the `.geojson` filename. This ensures two providers covering the same amenity set (e.g. `overpass` vs `fake`) produce distinct files and never overwrite each other on disk.

**Debug output** — When `settings.debug: true`, each worker step writes a snapshot to `./build/{task_type}/{counter:03d}/`: a `catalog.json` (no embedded geojson), plus `.geojson` and `.csv` for any layer that was added or modified.

**Output layout**

```
{out_dir}/
├── catalog.json
└── areas/{areaId}/
    ├── manifest.json
    ├── {areaId}.csv
    └── layers/{layerId}.geojson
```

`manifest` is not embedded in `catalog.json`; `geojson` is not embedded in `manifest.json`. Each is a separate file loaded on demand.