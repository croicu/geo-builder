# POI Layer — Plan of Record

## Goal

Surface point-of-interest details (name, hours, cuisine, etc.) for relevant map points without any runtime API calls, so the feature works fully offline.

## Build-time (geo-builder)

- Query Overpass API for all POIs in the area.
- For each POI, extract: `name`, `amenity`, `cuisine`, `address`, `website`, `opening_hours`.
- `address` is assembled from Overpass address tags in order of preference: `addr:full` → `addr:housenumber` + `addr:street` + `addr:city` → `addr:city` alone. Omit if none are present.
- Bake `hasDetails: true` plus the detail fields into the **existing heatmap layer GeoJSON** alongside the regular weight-only points.
- Regular (non-enriched) points carry only `weight`; enriched points carry `weight` + details.

### GeoJSON shape (embedded in existing layer)

Enriched feature:

```json
{
  "type": "Feature",
  "properties": {
    "id": 293835813,
    "weight": 1.0,
    "hasDetails": true,
    "name": "Bar Ristorante Gaetano",
    "amenity": "restaurant",
    "cuisine": "italian;pizza",
    "address": "Via Roma 42, Naples",
    "website": "https://example.com",
    "opening_hours": "Mo-Su 12:00-23:00"
  },
  "geometry": { "type": "Point", "coordinates": [14.267789, 40.853179] }
}
```

Regular point (no details):

```json
{
  "type": "Feature",
  "properties": { "weight": 1.0 },
  "geometry": { "type": "Point", "coordinates": [14.267789, 40.853179] }
}
```

**Not** baked: review/search links (Google Maps, Yelp, Foursquare). Computed at render time from `name`, `address`, and coordinates to avoid GeoJSON bloat and insulate against URL schema changes.

### Conditional manifest entry

The `__poi__` layer has `url: null` — it is a reserved builtin virtual layer derived at runtime from the existing layers. The `__poi__` entry is always present in the manifest after the first build. `visible` encodes whether real data exists:

- `visible: true` — enriched POIs were found; the browser shows the layer.
- `visible: false` — no enriched POIs; the browser shows nothing, but the entry is retained to preserve style across rebuilds.

```json
{
  "id": "__poi__",
  "name": "POI",
  "type": "__poi__",
  "url": null,
  "visible": true,
  "style": { "opacity": 0.7, "color": "#7b241c", "strokeWidth": 0 }
}
```

## Runtime (geo-browser)

### Layer type

`__poi__` is a reserved builtin virtual layer type with no associated GeoJSON URL. When the browser encounters it in the manifest, it:

1. Waits for the other layers in the area to finish loading.
2. Scans all loaded features across those layers for `hasDetails: true`.
3. Renders those features as interactive circle markers on top of the existing heat.

The heatmap layer already renders all points as heat — including the enriched ones. The `__poi__` layer adds only the interactive marker pass on top. No data is fetched twice, no file is duplicated.

### Interaction

- Only `hasDetails` markers are tappable.
- Tap → popup showing: name, amenity, cuisine, address, website, opening hours.
- Popup includes search links computed lazily when the popup opens (not at layer render time):

```typescript
const googleUrl = `https://www.google.com/maps/search/${encodeURIComponent(name)}/@${lat},${lng},15z`;
const yelpUrl   = `https://www.yelp.com/search?find_desc=${encodeURIComponent(name)}&find_loc=${encodeURIComponent(address)}`;
const fsqUrl    = `https://foursquare.com/search?query=${encodeURIComponent(name)}&near=${lat},${lng}`;
// Yelp link is omitted when address is not present — raw coordinates are not reliable for find_loc.
```

### Protocol change

`protocols.ts` `Layer` type needs to accommodate a URL-less `__poi__` entry. The feature properties shape (`hasDetails`, `name`, `cuisine`, etc.) lives in the existing layer's GeoJSON — no new payload type needed, but the browser's GeoJSON parsing must tolerate and forward these extra fields. Agree the shape between geo-builder and geo-browser before the builder emits it.

---

# User Layer

## Goal

Let the end user record points of personal interest during a trip — "I've been here" markers — that persist across catalog reloads and pipeline rebuilds without touching OSM data.

## Build-time (geo-builder)

- The `__user__` layer stub is injected into every area at creation time (alongside `__poi__`).
- `url` is always `null` — the browser never fetches user points via HTTP. Points are accessed exclusively through `__geo_get_user_points__`.
- Points are stored at `{in_dir}/areas/{areaId}/user.geojson` — alongside the catalog source data, not inside `layers/` and not URL-served. `in_dir` holds both service-pulled catalog data and user-generated points; when a Cloudflare Worker is introduced, `pull` will sync user points from the service and the folder stays semantically consistent.
- Points are written by `__geo_add_user_point__` — no pipeline re-run occurs. The file is never written to `out_dir`.
- Default style comes from the `__user__` entry in `template.json`. Defaults: color `#9E9E9E`, opacity `0.9`, radius `10`, minZoom `14`.

### Manifest entry

```json
{
  "id": "__user__",
  "name": "My Trip",
  "type": "__user__",
  "url": null,
  "visible": true,
  "style": {
    "opacity": 0.7,
    "color": "#5f5f5f",
    "radius": 40,
    "minZoom": 12
  }
}
```

`url` is always `null`. The browser uses `__geo_get_user_points__` to load points, not URL fetch.

### GeoJSON point shape

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": { "type": "Point", "coordinates": [-122.12, 47.67] },
      "properties": {
        "timestamp": "2026-05-29T14:00:00Z",
        "pressure": 0.6,
        "name": null
      }
    }
  ]
}
```

`coordinates` are `[longitude, latitude]` — GeoJSON convention.

| Property | Type | Description |
|---|---|---|
| `timestamp` | `string` | ISO 8601 UTC string of when the point was added |
| `pressure` | `number` | Force at time of tap, 0.0 (light) – 1.0 (maximum). Stored verbatim; browser decides rendering |
| `name` | `string \| null` | Optional label. `null` = unnamed. Browser may populate via reverse geocode or nearest-layer name |

## Runtime (geo-browser)

- When the browser encounters a `__user__` layer it calls `__geo_get_user_points__` (not a URL fetch) to load the GeoJSON. This call is made on initial area load and again when `AreaChanged` fires.
- `__user__` is rendered as a circle layer using `style.color`, `style.radius`, and `style.opacity` from the manifest.
- `pressure` can be used to modulate visual weight — e.g. a heavier press yields a slightly larger or darker circle. Keep subtle; avoid visual overwhelm.
- Points are visible at zoom ≥ `style.minZoom` (default 14 — city-district level, not landmark detail).
- Tapping a point may show a detail popup with `timestamp` and `name` (if present).
- `GetUserPoints` returns an empty `FeatureCollection` when no points exist — the browser never needs to special-case a missing or null url.

## Decisions log

| Decision | Rationale |
|---|---|
| No per-point id | Not needed until delete/edit is implemented; keeps the schema minimal |
| `pressure` stored verbatim | Builder has no rendering context — all visual decisions belong in the browser |
| `name` optional, accepted as-is | Reverse geocode / nearest-label population is a future browser feature; builder just persists what it receives |
| Direct file write, no pipeline rebuild | User points are independent of OSM acquisition — no reason to re-fetch data |
| Stub always present, `url` lazy | Avoids creating an empty file for every area; file is created on first actual point |
| `minZoom: 14` | "I've been here" markers are meaningful at city-district zoom, not the POI detail zoom of 18 |

---

## Decisions log

| Decision | Rationale |
|---|---|
| Build-time baking | Zero runtime latency; works offline; no API keys in the PWA |
| `hasDetails` embedded in existing layer GeoJSON | No separate file, no data duplication — enriched points already contribute to the heatmap |
| `poi` is a virtual layer (no URL) | Derived at runtime by filtering loaded features; manifest entry is the only signal needed |
| No review links in GeoJSON | Computed lazily when popup opens — smaller files, no rebuild needed on URL schema changes |
| `address` baked from Overpass addr tags | Needed for Yelp `find_loc`; raw coordinates are not reliable. Assembled as: `addr:full` → housenumber+street+city → city alone |
| Yelp link shown only when `address` present | Yelp `find_loc` does not accept raw coordinates reliably; omit rather than show a broken search |
| Builder emits manifest entry conditionally | Only when enriched POIs exist — presence signals browser to show the layer widget |
