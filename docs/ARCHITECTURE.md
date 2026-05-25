# ARCHITECTURE.md

## High-Level Architecture

```text
settings.json
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
    └── manifest.json        (tasks[] + layers[])
        └── Layer
            └── .geojson
```

### manifest.json schema

```json
{
  "version": 1,
  "tasks": [
    {
      "type": "acquisition",
      "provider": "overpass",
      "filters": {
        "amenity": { "values": ["restaurant"], "name": "Restaurants", "type": "heatmap", "color": null, "scale": null, "surface": false }
      }
    },
    { "type": "deduping" },
    { "type": "aggregation" }
  ],
  "layers": [ ... ]
}
```

`tasks` records the acquisition config that produced the area's layers — it is the source of truth used by `GeoArea.acquisition` and drives catalog-driven incremental builds.

## Tasks File Format

Entries in the tasks file (e.g. `template.json`) are keyed by an arbitrary name and distinguished by the presence of `bbox`:

**Concrete task** (`"type": "acquisition"` with `bbox`) — parsed into an `AcquisitionTask` and added to `settings.tasks`. Drives a full fresh build when passed to `Builder.run()`.

**Template** (`"type": "acquisition"` without `bbox`) — parsed into an `Acquisition` and stored in `settings.templates` by name. Templates are never executed directly; they are applied to new areas at design time via the `AddArea` designer API.

```json
{
  "napoli": {
    "type": "acquisition",
    "provider": "overpass",
    "bbox": { "west": 14.1, "south": 40.8, "east": 14.4, "north": 40.9 },
    "filters": { ... }
  },
  "acquisition": {
    "type": "acquisition",
    "provider": "overpass",
    "filters": { ... }
  }
}
```

## Builder

`builder.py` — the `Builder` class owns:

- Current Catalog
- Task stack
- WorkerFactory
- Errors

Workers receive the builder as their `executor: Executor` parameter and mutate shared state directly.

### Build modes

`Builder.run()` has two modes, selected by whether an explicit task list is passed:

**Explicit tasks** — `Builder.run(tasks=settings.tasks)`: used for a fresh build driven by a tasks file (entries with a `bbox` field). The caller supplies the full task list.

**Catalog-driven** — `Builder.run()` (no argument): used for an incremental build. `_tasks_from_catalog()` scans the loaded catalog and generates an `AcquisitionTask` for every area whose `acquisition` is set but whose `layers` list is empty. Aggregation and deduping tasks are appended once at the end if any acquisition tasks were generated.

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
- Acquisition — `provider: str`, `filters: dict[str, AreaStyle]`; the acquisition config stored on each area (via `manifest.tasks`) to drive incremental re-acquisition
- Manifest — `version: int`, `tasks: list[PipelineStep]`, `layers: list[Layer]`; the per-area manifest file
- PipelineStep — `type: str`, `provider: str | None`, `filters: dict[str, AreaStyle] | None`; one recorded pipeline step in the manifest
- Layer — includes `Layer.id_from_merge_key(merge_key)` to derive a filesystem-safe layer id
- GeoJson
- Feature
- Geometry

## Settings

`settings.py` — `Settings` singleton, DI root for tests:

- `Settings.load(path)` — parses `settings.json`, instantiates tasks, stores the singleton
- `Settings.current()` — returns the active instance (raises if not loaded)
- Fields: `debug: bool`, `tasks: list[Task]`, `templates: dict[str, Acquisition]`, `providers: dict[str, dict]`
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

### Build mode

| Priority | Layer | Description |
|----------|-------|-------------|
| 1 | **Memory** | Live `Catalog` / `Area` / `Layer` objects mutated by workers |
| 2 | **Out folder** | Built artifacts written by `persistence.save_catalog()` |
| 3 | **In folder** | Seed data for incremental builds |
| 4 | **Service** | Remote provider (e.g. Overpass API) |

Workers read from layer 1 and write to layer 1. Persistence flushes layer 1 to layer 2 after a successful run. No worker reads from layer 4 without first exhausting layers 1–3.

### Designer mode

The `DataPipeline` (`designer/data_pipeline.py`) intercepts every WebView HTTP request and resolves it through four layers:

| Priority | Layer | Description |
|----------|-------|-------------|
| 1 | **Memory** | `dict[str, bytes]` — in-session edits (color changes, dimension tweaks); lost on close |
| 2 | **Out folder** | Built artifacts — the next version to push to the service |
| 3 | **In folder** | Working area — pre-fetched from the service by `pull`; mutable by design actions |
| 4 | **Network** | Pass-through to the live service; no write-back |

**Pull** (`designer/pull.py`) — fetches all artifacts from the service into `--in` before the WebView starts (first launch or explicit refresh). Follows relative URLs from the HEAD file through catalog → manifests → layers. Safe to run against an empty or unreachable service.

**In folder is the working area** — analogous to a Git working tree. Pull is `git pull`; build produces `--out` (the proposed next version); push sends `--out` to the service at the end of a session.

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
