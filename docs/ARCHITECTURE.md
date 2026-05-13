# ARCHITECTURE.md

## High-Level Architecture

```text
tasks.json
    → Tasks.load()
    → Executor.execute()
    → Workers
    → Catalog (mutable)
    → Result.save()
    → Static files
```

## Repositories

- geo-browser: static renderer
- geo-builder: authoring + processing + publishing
- geo-ios: future renderer
- geo-desktop: future renderer

## Artifact Hierarchy

```text
catalog.json
└── Area
    └── manifest.json
        └── Layer
            └── .geojson
```

## Executor

The Executor owns:

- Current Catalog
- Task stack
- WorkerFactory
- Errors

Workers receive the executor and mutate shared state directly.

## Data Contracts

`protocols.py` contains:

- Result
- Catalog
- Area
- Manifest
- Layer
- GeoJson
- Feature
- Geometry

Field names match JSON exactly.

## Runtime Contracts

`contracts.py` contains:

- Worker
- WorkerResult
- ExecutorContract
- Provider

## Design Mode Integration

```text
geo-builder (Python)
    ↕ pywebview bridge
geo-browser (?design=1)
```

Large GeoJSON is written to disk and fetched by URL rather than passed over the bridge.
