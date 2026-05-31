# Manifest Schema

`manifest.json` lives at `{out_dir}/areas/{areaId}/manifest.json` and describes a single geographic area and its layers.

## Top level

```json
{
  "version": 1,
  "layers": [...],
  "aggregation": {},
  "deduping": {}
}
```

| Field | Type | Description |
|---|---|---|
| `version` | `number` | Schema version. Currently always `1`. |
| `layers` | `Layer[]` | Ordered list of layers. |
| `aggregation` | `object` | Reserved. Always `{}`. |
| `deduping` | `object` | Reserved. Always `{}`. |

---

## Layer types

### Data layer (`type: "heatmap"` or `type: "circle"`)

```json
{
  "id": "1",
  "name": "Parks",
  "type": "circle",
  "visible": true,
  "style": {
    "color": "#007f00",
    "opacity": 0.3,
    "radiusScale": 1,
    "surface": true
  },
  "url": "./layers/1.geojson",
  "acquisition": {
    "provider": "overpass",
    "filters": {
      "leisure": ["park"]
    }
  }
}
```

| Field | Type | Description |
|---|---|---|
| `id` | `string` | Unique layer id within the area. Numeric string (e.g. `"1"`). |
| `name` | `string` | Display name. |
| `type` | `"heatmap"` \| `"circle"` | Render mode. |
| `visible` | `boolean` | Whether the layer is shown on load. |
| `style` | `DataStyle` | See below. |
| `url` | `string` | Relative path to the `.geojson` file. |
| `acquisition` | `Acquisition` | See below. |

#### DataStyle

| Field | Type | Default | Description |
|---|---|---|---|
| `color` | `string` | — | CSS hex color. |
| `opacity` | `number` | `0.7` | Layer opacity, 0–1. |
| `radiusScale` | `number` | `1` | Scales the rendered point radius / heat weight. |
| `surface` | `boolean` | `false` | `circle` only. When `true`, renders polygons as filled surfaces rather than centroid circles. |

#### Acquisition

| Field | Type | Description |
|---|---|---|
| `provider` | `string` | Provider id (e.g. `"overpass"`). |
| `filters` | `{ [key: string]: string[] }` | Map of OSM tag key → allowed values. Multiple keys are ANDed; multiple values per key are ORed. Use `["*"]` to match any value. |

---

### POI layer (`type: "__poi__"`, `id: "__poi__"`)

Virtual layer — `url` is absent. The browser derives POI markers at runtime from `hasDetails: true` features embedded in the data layers.

```json
{
  "id": "__poi__",
  "name": "POI",
  "type": "__poi__",
  "visible": true,
  "style": {
    "color": "#7f0000",
    "opacity": 0.9,
    "radius": 8,
    "minZoom": 18
  }
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `color` | `string` | `"#7f0000"` | Marker color. |
| `opacity` | `number` | `0.9` | Marker opacity. |
| `radius` | `number` | `8` | Marker radius in pixels. |
| `minZoom` | `number` | `18` | Zoom level below which markers are hidden. |

`visible: true` means enriched POIs exist in the data layers. `visible: false` means none were found but the entry is retained to preserve style across rebuilds.

---

### User layer (`type: "__user__"`, `id: "__user__"`)

Virtual layer — `url` is absent. Points are loaded via the `GetUserPoints` API, not HTTP. Stored in `{in_dir}/areas/{areaId}/user.geojson`.

```json
{
  "id": "__user__",
  "name": "My Trip",
  "type": "__user__",
  "visible": true,
  "style": {
    "color": "#5f5f5f",
    "opacity": 0.7,
    "radius": 40,
    "minZoom": 12
  }
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `color` | `string` | `"#9E9E9E"` | Marker color. |
| `opacity` | `number` | `0.9` | Marker opacity. |
| `radius` | `number` | `10` | Marker radius in pixels. |
| `minZoom` | `number` | `14` | Zoom level below which markers are hidden. |

#### User point GeoJSON shape

```json
{
  "type": "Feature",
  "geometry": { "type": "Point", "coordinates": [14.42, 50.08] },
  "properties": {
    "timestamp": "2026-05-29T14:00:00Z",
    "pressure": 0.6,
    "name": null
  }
}
```

`coordinates` are `[longitude, latitude]` (GeoJSON convention).

| Property | Type | Description |
|---|---|---|
| `timestamp` | `string` | ISO 8601 UTC timestamp of when the point was added. |
| `pressure` | `number` | Touch force at add time, 0.0–1.0. Browser decides visual encoding. |
| `name` | `string \| null` | Optional label. `null` = unnamed. |

---

## POI enrichment in data layer GeoJSON

Enriched features (those with detail data baked in at build time) carry additional properties alongside the standard `weight`:

```json
{
  "type": "Feature",
  "properties": {
    "weight": 1.0,
    "hasDetails": true,
    "id": 293835813,
    "name": "Bar Gaetano",
    "amenity": "restaurant",
    "cuisine": "italian;pizza",
    "address": "Via Roma 42, Naples",
    "website": "https://example.com",
    "opening_hours": "Mo-Su 12:00-23:00"
  },
  "geometry": { "type": "Point", "coordinates": [14.267789, 40.853179] }
}
```

Plain features carry only `weight`. The browser scans all loaded features for `hasDetails: true` to build the `__poi__` layer at runtime.
