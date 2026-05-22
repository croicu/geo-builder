# POI Layer — Plan of Record

## Goal

Surface point-of-interest details (name, hours, cuisine, etc.) for relevant map points without any runtime API calls, so the feature works fully offline.

## Build-time (geo-builder)

- Query Overpass API for all POIs in the area.
- For each POI, extract: `name`, `cuisine`, `address`, `phone`, `website`, `opening_hours`.
- Set `hasDetails: true` on enriched features.
- Bake everything into the area's GeoJSON alongside the regular weight-only points.
- Regular (non-enriched) points carry only `weight`; enriched points carry `weight` + details.

### Conditional emission

The builder only emits the `poi-heat` GeoJSON file and its manifest entry when at least one enriched POI was found. The presence of the layer in the manifest is the signal to the browser that POI data exists — the layer then appears in the layer selection widget, can be toggled, etc.

If the Overpass query returns no enrichable POIs, the builder skips the file and the manifest entry entirely. The browser sees no `poi-heat` layer and shows nothing — no empty widget, no error.

### GeoJSON shape

```json
{
  "type": "Feature",
  "properties": {
    "weight": 1.0,
    "hasDetails": true,
    "name": "Bar Ristorante Gaetano",
    "cuisine": "italian",
    "address": "Via Roma 42, Naples",
    "phone": "+39 081 234 5678",
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

**Not** baked into GeoJSON: review/search links (Foursquare, Google Maps, Yelp). These are computed at render time from `name` + coordinates to avoid GeoJSON bloat and insulate against upstream URL schema changes.

## Runtime (geo-browser)

### Layer type

A new layer type `poi-heat` replaces separate `heatmap` + `poi` layers. A single GeoJSON file feeds a single `LayerView` that does two rendering passes:

1. **All points** → heat layer (density visualization).
2. **`hasDetails: true` points only** → interactive circle markers rendered on top, visually more prominent than background heat.

This avoids data duplication: enriched points contribute to the heatmap heat **and** appear as tappable markers without being stored twice.

### Interaction

- Only `hasDetails` markers are tappable.
- Tap → popup showing: name, cuisine, address, phone, website, opening hours.
- Popup includes search links computed at render time:

```typescript
const foursquareUrl = `https://foursquare.com/search?query=${encodeURIComponent(name)}&near=${lat},${lng}`;
const googleUrl = `https://www.google.com/maps/search/${encodeURIComponent(name)}/@${lat},${lng},15z`;
// Yelp requires a text location — use address city, not coordinates.
```

### Protocol change

`protocols.ts` will need an extended feature properties shape for the `poi-heat` layer payload. This must be agreed between geo-builder and geo-browser before the builder emits it, as a schema change requires a data rebuild.

## Decisions log

| Decision | Rationale |
|---|---|
| Build-time baking | Zero runtime latency; works offline; no API keys in the PWA |
| Single `poi-heat` layer | Avoids double-rendering enriched points; one GeoJSON file per area |
| No `reviews` in GeoJSON | Computed at render time — smaller files, no rebuild needed on URL schema changes |
| Yelp uses text location | Yelp `find_loc` does not accept raw coordinates reliably |
| Builder emits conditionally | File and manifest entry only created when enriched POIs exist — presence in manifest signals browser to show the layer |
