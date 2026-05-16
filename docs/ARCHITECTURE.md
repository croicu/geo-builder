# ARCHITECTURE.md

## High-Level Architecture

```text
build.json
    → Settings.load()
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

In normal mode `Builder` catches `GeoError`, records the message in `Builder.errors`, and stops. The CLI then prints each error and exits without writing output. When `settings.debug` is `true` no exceptions are caught.

## Data Contracts

`protocols.py` — dataclasses whose fields match JSON exactly. Static methods that semantically belong to a class live here too.

- Result
- Catalog
- Area
- Manifest
- Layer — includes `Layer.id_from_merge_key(merge_key)` to derive a filesystem-safe layer id
- GeoJson
- Feature
- Geometry

## Settings

`settings.py` — `Settings` singleton, DI root for tests:

- `Settings.load(path)` — parses `build.json`, instantiates tasks, stores the singleton
- `Settings.current()` — returns the active instance (raises if not loaded)
- Fields: `debug: bool`, `tasks: list[Task]`, `providers: dict[str, dict]`
- Tests set up the singleton directly via `Settings._instance = Settings(...)`

## Debug Output

When `settings.debug` is `true`, `Builder.run()` clears `./build/` at the start of the run then, after each worker executes, writes:

```text
./build/{task_type}/{counter:03d}/
    catalog.json       — catalog + areas + layers metadata (geojson stripped)
    {layer_id}.geojson — layers whose feature count changed in this step
    {layer_id}.csv     — matching CSV (lon, lat, + all feature properties)
```

The counter is global across task types so files sort in execution order.

## Data Layer Hierarchy

Data is resolved through four layers, in priority order:

| Priority | Layer | Description |
|----------|-------|-------------|
| 1 | **In-memory** | Live `Catalog` / `Area` / `Layer` objects held by `Builder` |
| 2 | **Out folder** | Previously built artifacts in the `--out` directory |
| 3 | **In folder** | Seeded or cached data in the `--in` directory |
| 4 | **Service** | Remote provider (e.g. Overpass API) |

**Reading** — always starts at layer 1. On a miss, layers 2 → 3 → 4 are queried in order until the data is found.

**Writing** — always targets layer 1 (in-memory). Persistence (`save_catalog` etc.) is responsible for flushing layer 1 to layer 2 after a successful run.

No code should write directly to layers 2–4 outside of persistence, and no code should read from layer 4 without first exhausting layers 1–3.

## Persistence

`persistence.py` — all load/save logic as module-level functions:

- `load_catalog(path)` / `save_catalog(catalog, path)`
- `load_area`, `save_area`, `save_area_csv`, `load_manifest`, `load_layer`, `save_layer`
- `load_geojson`, `load_feature`, `load_geometry`
- `read_json`, `save_json`, `child_path` utilities

`save_area_csv` writes `{areaId}.csv` into each area directory combining all features across all layers. Columns: `lon`, `lat`, `layer_id`, then all unique property keys (sorted). Missing properties are written as empty strings.

## Runtime Contracts

`contracts.py` contains:

- `Task` — base dataclass with `type: str`
- `BoundingBox` — west/south/east/north floats
- `AreaStyle` — per-filter-key style record: `values: list[str]`, `color: str | None`, `scale: float | None`
- `AcquisitionTask` — carries `filters: dict[str, AreaStyle]` (one entry per OSM tag key)
- `AggregationTask`, `DedupingTask`
- `Map` — protocol for catalog mutation: `add_area`, `add_layer`
- `Executor` — protocol extending `Map`, adds `push_task`, `push_tasks`; passed to all workers
- `Worker` — protocol: `execute(executor: Executor) → WorkerResult`
- `WorkerResult`
- `Provider`

## API Message Contract

Every API call (JS → Python or Python → JS) carries three fields:

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Message identifier (e.g. `__geo_get_area_bbox__`) |
| `error` | `int` | `0` = success; non-zero = caller-defined error code |
| payload | additional fields | Domain data (e.g. `bbox`, `areaId`); may be absent on error |

**Error codes are part of the API contract.** Each API declares its own set of error codes (defined in `api.py` as module-level constants, e.g. `ERR_AREA_NOT_FOUND = 1`). The callee must always check `error` on completion — a non-zero value means the payload should not be trusted.

Optional `errorDescription: str | None` may accompany a non-zero `error` for human-readable context, but code must branch on the numeric code, not the string.

`OK = 0` is the only universal constant; all other codes are API-specific.

## Design Mode Integration

```text
geo-builder (Python)
    ↕ pywebview bridge
geo-browser (?design=1)
```

Large GeoJSON is written to disk and fetched by URL rather than passed over the bridge.

### Designer Threading Model

pywebview on Windows uses Python.NET → WinForms → WebView2 (three marshaling layers). This shapes the threading model:

```text
MainThread      — blocked in webview.start() → .NET STA loop; never returns to Python
STA thread      — WinForms/WebView2 UI loop (spawned by pywebview)
Dummy-N         — WebView2 browser thread; fires CoreWebView2 events including WebMessageReceived
Thread-6        — dispatcher; owned by Api.run(), the only thread that processes API work
```

**Rule: all Api work runs on Thread-6.**

- `Api._on_message(raw)` — called from Dummy-N, enqueues `("msg", raw)`; returns immediately
- `Api.invoke(id, payload)` — callable from any thread, enqueues `("invoke", ...)`; returns immediately
- `Api.run()` — dequeues and processes both; the only place handlers execute and `_send` is called

This cannot be enforced at the model layer. Callers must not call `_dispatch` or `_send` directly.
