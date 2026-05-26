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
