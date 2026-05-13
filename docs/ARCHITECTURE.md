# ARCHITECTURE.md

## High-Level Architecture

```text
tasks.json
    → Tasks.load()
    → Builder.run()
    → Workers
    → Catalog (mutable)
    → persistence.save_catalog()
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

## Builder

`builder.py` — the `Builder` class owns:

- Current Catalog
- Task stack
- WorkerFactory
- Errors

Workers receive the builder as their `executor: Executor` parameter and mutate shared state directly.

## Error Handling

`errors.py` defines the exception hierarchy:

- `GeoError` — base class for all application errors
- `TaskError` — task file parsing
- `CatalogError` — catalog / manifest / GeoJSON loading
- `ProviderError` — provider network errors and unknown provider names
- `WorkerError` — unknown task type at worker dispatch

In normal mode `Builder` catches `GeoError`, records the message in `Builder.errors`, and stops. The CLI then prints each error and exits without writing output. In `--debug` mode no exceptions are caught.

## Data Contracts

`protocols.py` — pure field-only dataclasses, no methods:

- Result
- Catalog
- Area
- Manifest
- Layer
- GeoJson
- Feature
- Geometry

Field names match JSON exactly.

## Persistence

`persistence.py` — all load/save logic as module-level functions:

- `load_catalog(path)` / `save_catalog(catalog, path)`
- `load_area`, `save_area`, `load_manifest`, `load_layer`, `save_layer`
- `load_geojson`, `load_feature`, `load_geometry`
- `read_json`, `save_json`, `child_path` utilities

## Runtime Contracts

`contracts.py` contains:

- `Map` — protocol for catalog mutation: `add_area`, `add_layer`
- `Executor` — protocol extending `Map`, adds `push_task`, `push_tasks`; passed to all workers
- `Worker` — protocol: `execute(executor: Executor) → WorkerResult`
- `WorkerResult`
- `Provider`

## Design Mode Integration

```text
geo-builder (Python)
    ↕ pywebview bridge
geo-browser (?design=1)
```

Large GeoJSON is written to disk and fetched by URL rather than passed over the bridge.
