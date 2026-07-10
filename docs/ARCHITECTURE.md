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
    └── manifest.json        (aggregation + deduping + layers[])
        └── Layer
            └── .geojson
```

### manifest.json schema

```json
{
  "version": 1,
  "layers": [
    {
      "id": "1",
      "name": "Restaurants",
      "type": "heatmap",
      "url": "./layers/1.geojson",
      "visible": true,
      "style": { "opacity": 0.7, "radiusScale": 1.0, "color": "#ff0000" },
      "acquisition": { "provider": "overpass", "filter": "amenity", "values": ["restaurant"] }
    }
  ],
  "aggregation": {},
  "deduping": {}
}
```

`layers[]` is the single source of truth for style, visibility, and acquisition config. Each data layer owns its own `acquisition` record, which the builder uses for catalog-driven incremental re-acquisition. `aggregation` and `deduping` are area-scoped pipeline steps (empty objects, reserved for future config).

## Tasks File Format

`template.json` is a flat manifest-shaped document used as the starting point for new areas created via the `AddArea` designer API. It omits `id` and `url` on data layers — those are assigned at build time.

```json
{
  "layers": [
    {
      "type": "heatmap",
      "visible": true,
      "style": { "opacity": 0.7, "color": "#ff0000" },
      "acquisition": { "provider": "overpass", "filter": "amenity", "values": ["restaurant"] }
    },
    {
      "id": "__poi__",
      "name": "POI",
      "type": "__poi__",
      "visible": true,
      "style": { "opacity": 0.9, "color": "#3f3f3f", "radius": 8 }
    }
  ],
  "aggregation": {},
  "deduping": {}
}
```

The `template` field in `AddAreaInput` is reserved for future multi-template support; currently unused (there is only one `template.json`).

## Builder

`builder.py` — the `Builder` class owns:

- Current Catalog
- Task stack
- WorkerFactory
- Errors

Workers receive the builder as their `executor: Executor` parameter and mutate shared state directly.

### Build modes

`Builder.run()` has two modes, selected by whether an explicit task list is passed:

**Explicit tasks** — `Builder.run(tasks=[...])`: used for a fresh build. The caller supplies the full task list (e.g. from a template or from the designer's `AddArea` handler).

**Catalog-driven** — `Builder.run()` (no argument): used for an incremental build. `_tasks_from_catalog()` scans the loaded catalog and generates an `AcquisitionTask` for every area whose `acquisition` is set but whose `layers` list is empty. Aggregation and deduping tasks are appended once at the end if any acquisition tasks were generated.

## Workers

### AcquisitionWorker

Fetches one task's bbox from the configured provider, creates or updates the area, and inserts the resulting layer. On HTTP 400 (query too large), splits the bbox into four quadrants and pushes child tasks onto the executor stack. HTTP 429 / 504 trigger retry-with-backoff (5 s, 15 s, 45 s) before splitting.

### DedupingWorker

Removes near-duplicate points within each layer (not cross-layer). Two features are duplicates if their Haversine distance is ≤ 10 m and they share the same OSM name.

Algorithm: **O(n log n)** — features are sorted by latitude, then scanned in order. For each candidate, only the trailing suffix of the result list whose latitude is within 10 m / 111 111 ° of the candidate's latitude needs to be checked. The early-exit lat-gap condition makes the inner loop effectively constant-depth in practice.

### AggregationWorker

Merges compatible layers within an area, grouped by `mergeKey`. Layers sharing a mergeKey have their feature lists concatenated into a single layer.

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
- Manifest — `version: int`, `aggregation: dict`, `deduping: dict`, `layers: list[Layer]`; the per-area manifest file
- Layer — `id: str` (numeric string for data layers; `"__poi__"` for the builtin virtual layer), `acquisition: dict | None` (absent on virtual layers)
- GeoJson
- Feature
- Geometry

## Settings

`settings.py` — `Settings` singleton, DI root for tests:

- `Settings.load(path)` — parses `settings.json`, optionally loads the template file, stores the singleton
- `Settings.current()` — returns the active instance (raises if not loaded)
- Fields: `debug: bool`, `template: dict | None`, `providers: dict[str, dict]`
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

`child_path(parent, relative_path)` resolves a URL relative to a parent directory. If `relative_path` contains a scheme (e.g. `https://cdn.example.com/catalog.json`), the scheme and host are stripped and only the path component is used, so the result is always under `parent`. This allows catalog and manifest files to reference layers hosted on a different origin without breaking local resolution.

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

### WebView2 User Data Folder

`host.py` sets `WEBVIEW2_USER_DATA_FOLDER` to `%LOCALAPPDATA%\geo-builder\WebView2` before launch. This folder holds the WebView2 browser profile (cache, cookies, local storage, etc.). It is safe to delete while the designer is closed — WebView2 recreates it on next launch.

### Debugging "catalog changes don't show up in the designer"

`_on_web_resource_requested` intercepts every request the WebView2 page makes (`AddWebResourceRequestedFilter("*", CoreWebView2WebResourceContext.All)`) and `DataPipeline._resolve` logs each one (`memory` / `out path` / `in path` / `network`) at info level. If a catalog rebuild doesn't appear after restarting the designer, check this log first: if there is no log line at all for `catalog.head.json` / `catalog.head.debug.json` / `catalog.json` / `catalog.debug.json`, the geo-browser frontend never issued a request for it in this session — the bug is not in geo-builder's serving path.

One confirmed cause on the geo-browser side: when its dev server statically imports the catalog file (`import catalog from './public/catalog.json'`) instead of fetching it at runtime, the bundler inlines the file's contents at build/transform time, reading from geo-browser's own `public/` folder. No HTTP request is ever made, so geo-builder's `out`/`in` dirs are never consulted — this is independent of dev vs. production and independent of host/port; it depends only on whether geo-browser uses a static import or a runtime `fetch()` for the catalog. The documented contract (`docs/MESSAGING.md`) assumes a runtime fetch of `catalog.head.json`; if a catalog update isn't visible, confirm that assumption holds on the geo-browser side.
