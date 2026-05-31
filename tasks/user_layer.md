# User Layer

## Status: Done

## Problem statement

End users add points during a trip from the browser. Those points need to be persisted in a dedicated layer that survives catalog reloads and pipeline rebuilds. The builder's role is to own the on-disk representation and expose an API the browser can call.

---

## Design decisions

### Layer identity
- Type: `__user__`
- Layer id: `__user__`
- Storage file: `{in_dir}/areas/{areaId}/user.geojson` — lives in `in_dir` alongside the catalog source data, never inside `layers/` and never URL-served
- `url` in manifest: always `null` — browser loads points via `GetUserPoints` API only
- Note: `in_dir` evolves from a pure "service copy" to also holding user-generated data; this is intentional — when a Cloudflare Worker replaces local storage, `pull` will sync user points from the service and the folder stays semantically consistent

### Layer presence
Always present — injected directly into the area at creation time (in the `AddArea` handler), not via a worker. `PoiWorker` exists because `__poi__` visibility is data-derived (`hasDetails` from acquisition); `__user__` has no such pipeline dependency. `url` is always `null`; the geojson file is created on the first `add_user_point` call. `in_dir` always exists because `pull` creates it; the area always exists because the browser must create it before adding a point.

### Point schema
No per-point id. Properties:
```json
{
  "type": "Feature",
  "geometry": { "type": "Point", "coordinates": [lon, lat] },
  "properties": {
    "timestamp": "<ISO 8601 string>",
    "pressure": 0.6,
    "name": "optional label or null"
  }
}
```
`pressure` is a float 0.0–1.0 (0 = light tap, 1 = maximum force). Geo-builder stores it verbatim; rendering decisions are entirely the browser's concern. `name` is optional — stored as-is; null means unnamed.

### New API endpoints

#### `__geo_get_user_points__`
Input: `{ areaId }`
Output: `{ error, errorDescription, geojson: GeoJSON.FeatureCollection | null }`
Returns all points for the area as a GeoJSON FeatureCollection. Returns an empty FeatureCollection (not null/error) when no points exist yet. This is the **only** path the browser uses to load user points.

#### `__geo_add_user_point__`
Input:
```json
{
  "areaId": "redmond",
  "point": {
    "lat": 47.67,
    "lon": -122.12,
    "timestamp": "2026-05-29T14:00:00Z",
    "pressure": 0.6,
    "name": null
  }
}
```
Output: `{ "error": 0, "errorDescription": "" }`

### AddUserPoint write path (no pipeline rebuild)
1. Find area in `catalog.areas`.
2. Find `__user__` layer; if missing, re-create stub with defaults read from template.
3. Resolve storage path: `{in_dir}/areas/{areaId}/user.geojson`.
4. Read existing file if it exists; otherwise start with empty FeatureCollection.
5. Append new GeoJSON Feature and write back to the same path.
6. Fire `AreaChanged` directly (manifest is never updated — `url` stays null; no pipeline rebuild).

### GetUserPoints read path
1. Find area in `catalog.areas`.
2. Resolve storage path: `{in_dir}/areas/{areaId}/user.geojson`.
3. If file exists, read and return it.
4. If not, return empty FeatureCollection `{ type: "FeatureCollection", features: [] }`.

### Rebuild preservation
`_rebuild_area` clears geojson for non-`__poi__` layers. Extend the preserve list to include `__user__`:
```python
if geo_layer.layer.type not in ("__poi__", "__user__"):
    geo_layer.layer.geojson = None
```
`__user__` is always a stub (no in-memory geojson), so this is a no-op in practice but makes the intent explicit.

### New protocols
- `protocols.py`: add `UserStyle` dataclass (name, color, opacity, radius, minZoom)
- No `UserTask` or `UserWorker` needed.

### Template entry (template.json)
```json
{
  "id": "__user__",
  "name": "My Trip",
  "type": "__user__",
  "visible": true,
  "style": {
    "opacity": 0.9,
    "color": "#9E9E9E",
    "radius": 10,
    "minZoom": 14
  }
}
```
The `AddArea` handler reads this entry (like it does for `__poi__`), builds a `UserStyle` from it (or uses `UserStyle()` defaults if absent), and injects the `__user__` stub `GeoLayer` directly into the new area's layers before calling `_rebuild_area`.

### Re-create if `__user__` layer is missing
If `add_user_point` is called and the area has no `__user__` layer (e.g. removed via `put_area_json`), re-create the stub with defaults from the template.

---

## Implementation order
1. `protocols.py` — `UserStyle`
2. `api.py` — `GET_USER_POINTS_ID`, `ADD_USER_POINT_ID` and their input/output dataclasses
3. `host.py` — `__user__` stub injection in `AddArea`; `_rebuild_area` preserve list; `on_get_user_points` + `on_add_user_point` handlers
4. `template.json` — add `__user__` entry
5. Tests
6. Docs (`MESSAGING.md`, `MANIFEST.md`) — done
