# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Mission

Build a simple, deterministic Python application that creates static geographic datasets for the geo ecosystem.

## Documentation rule

After any change that affects the public interface, CLI, file formats, or core architecture, update the relevant docs:

- `CLAUDE.md` — commands, pipeline, architecture notes
- `docs/ARCHITECTURE.md` — modules, data flow, contracts
- `docs/PROTOCOL.md` — CLI signature, build file schema

## Off-limits directories

Never read, glob, or search inside `./in/` or `./out/`. They contain large volumes of generated data and are not part of the source tree.

## Commands

```bash
# Install (editable, with dev deps)
pip install -e ".[dev]"

# Run
geo-builder build.json --out ./output
geo-builder build.json --in ./existing --out ./output   # incremental

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
3. `protocols.py` contains persisted/shared data contracts. Static methods that semantically belong to a class live inside the class, even if they don't use `self`.
4. `contracts.py` contains runtime behavioral interfaces.
5. Execution mutates an in-memory catalog.
6. Persistence occurs only after successful completion.
7. Child paths are relative to their parent files.
8. Prefer explicit, readable Python over clever abstractions.
9. Tests must run offline.
10. Static artifacts are immutable and deterministic.

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
- OverpassProvider

Future:
- FlickrProvider
- NominatimProvider

## Key Architecture Notes

**Coordinate conventions** — Area `center` is `[lat, lon]`; GeoJSON `coordinates` are `[lon, lat]`. The conversion happens at provider boundaries (`overpass.py`).

**Bbox decomposition** — When OverpassProvider receives a 400/429/504, AcquisitionWorker splits the bbox into four quadrants and pushes them back onto the executor stack. This is the mechanism for handling "request too large" errors without caller involvement.

**MergeKey format** — `"provider:key1=val1,val2"` (e.g., `"overpass:amenity=restaurant,cafe"`). AggregationWorker groups layers within an area by this key and concatenates their features into a single layer.

**Output layout**

```
{out_dir}/
├── catalog.json
└── areas/{areaId}/
    ├── manifest.json
    └── layers/{layerId}.geojson
```

`manifest` is not embedded in `catalog.json`; `geojson` is not embedded in `manifest.json`. Each is a separate file loaded on demand.