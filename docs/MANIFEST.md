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

### Void layer (`type: "__void__"`)

Reserved type for the "Mundane" fog-of-war layer. An area's manifest may contain **multiple**
`__void__`-type entries, distinguished by an `id` naming convention — one per precomputed
source-layer combination:

```text
__void__               void relative to the union of ALL non-virtual layers in the area.
__void__2__             void relative to just layer id "2".
__void__2_3__           void relative to the union of layer ids "2" and "3".
```

Ids are sorted ascending and joined with `_`. The bare `__void__` must always be present — it's
the guaranteed fallback the browser resolves to when no closer combination exists. Beyond that,
the builder may generate as many or as few combinations as it wants; see
`docs/LAYERS.md` for the full contract (why, resolution algorithm, migration
status).

```json
{
  "id": "__void__2__",
  "name": "No Restaurants, Food",
  "type": "__void__",
  "visible": false,
  "url": "./void/layer-2.geojson",
  "style": {
    "color": "#4a5568",
    "opacity": 0.80
  }
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `url` | `string` | — | Precomputed void `Polygon`/`MultiPolygon` GeoJSON for this combination. |
| `color` | `string` | `"#4a5568"` | Fill color. |
| `opacity` | `number` | `0.80` | Fill opacity, 0–1. |

#### `geometry` (bare `__void__` entry only)

The bare `__void__` entry (never the `__void__<id>__` variants) may also carry a top-level
`geometry` object, a sibling of `style` — deliberately **not** inside `style`, since it affects
the computed shape, not presentation:

```json
{
  "id": "__void__",
  "name": "Mundane",
  "type": "__void__",
  "visible": false,
  "url": "./void/void.geojson",
  "style": { "color": "#3f3f3f", "opacity": 0.5 },
  "geometry": { "radius": 150 }
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `radius` | `number` | from `template.json`'s `__void__.style.radius`, else `50` | Exclusion radius, in meters, for source points without their own `radius_m`. Applies to every variant computed for this area, not just the bare one. |

`radius` is read back by `VoidWorker` on every run: an area that has never had one explicitly set
uses `template.json`'s `__void__.style.radius` (also just `radius`, meters implicit); once a
value is written into an area's own `geometry.radius` (by hand, or via the designer), it
overrides the template value for that area on every subsequent build, including when the
computed void ends up empty (e.g. a radius larger than the bbox) — `VoidWorker` always keeps a
stub `__void__` entry (`url`/`geojson` absent) carrying the resolved `geometry.radius` so the
override is never silently lost on the next run.

Editing `geometry.radius` alone (no `acquisition` change on any layer) does **not** trigger a
full rebuild — `GeoArea.apply_manifest` classifies it as `REPROCESS`: the designer reruns
`Aggregation → Deduping → Poi → Void → Search` against already-acquired data, skipping the
provider fetch entirely. See `ManifestChange` (`entities/geo_area.py`).

`visible` is always `false` as written by the builder — the browser decides which single
`__void__*` variant to show (and its displayed name follows that variant's own `name`) based on
its own runtime state. The user only ever sees one "Mundane" toggle, regardless of how many
variants exist in the manifest.

**Current status:** shipped on both sides. `geo-builder` precomputes `__void__` (this section's
schema is live — `VoidWorker` regenerates the full `__void__*` set on every build). v1 coverage:
the bare `__void__` (union of all non-virtual, point-bearing layers) plus one `__void__<id>__`
per such layer — no curated multi-layer combinations yet. `geo-browser` resolves which variant to
show via minimal-superset resolution (`VoidVariantResolver`) — see `docs/LAYERS.md` for the full
runtime contract.

---

### Search layer (`type: "__search__"`, `id: "__search__"`)

Virtual layer — `url` is always `null`. Holds ephemeral search results (Nominatim) rendered as
temporary markers by the browser at runtime; geo-builder never populates any geometry for it.

```json
{
  "id": "__search__",
  "name": "Search Results",
  "type": "__search__",
  "visible": false,
  "style": {
    "opacity": 0.3,
    "color": "#00007f"
  }
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `color` | `string` | `"#00007f"` | Marker color. |
| `opacity` | `number` | `0.3` | Marker opacity. |

`SearchWorker` writes this stub once per area (copied verbatim from the `__search__` entry in
`template.json`) and never touches it again if already present — unlike `__poi__`/`__void__`,
there is no recomputation; style edits made through the designer persist across rebuilds. The
browser synthesizes the same default if the layer is absent from the manifest entirely (see
`docs/MESSAGING.md`).

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
    "name": null,
    "stars": 4,
    "bookmarked": true
  }
}
```

`coordinates` are `[longitude, latitude]` (GeoJSON convention).

| Property | Type | Description |
|---|---|---|
| `timestamp` | `string` | ISO 8601 UTC timestamp of when the point was added. |
| `pressure` | `number` | Touch force at add time, 0.0–1.0. Browser decides visual encoding. |
| `name` | `string \| null` | Optional label. `null` = unnamed. |
| `stars` | `number` (1–5) | Optional. User star rating; renders as a colored ring around the point. Absent = unrated. |
| `bookmarked` | `boolean` | Optional. `true` = bookmarked (blue ring, takes visual priority over the star ring). Absent/`false` = not bookmarked. |

A point may carry a POI's baked metadata as well (name, amenity, cuisine, address, etc. — the same
fields as "POI enrichment" below) when it was created by tapping an enriched POI marker; see
`docs/MESSAGING.md`'s `AddUserPoint` for the full property bag passed at creation time.

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
    "opening_hours": "Mo-Su 12:00-23:00",
    "wikidata": "Q12345",
    "wikipedia": "en:Bar_Gaetano",
    "stars": "4",
    "outdoor_seating": "yes"
  },
  "geometry": { "type": "Point", "coordinates": [14.267789, 40.853179] }
}
```

All detail properties are optional and present only when the OSM element carries the corresponding tag. Any single one of them (or any combination) causes `hasDetails: true` to be set. Plain features carry only `weight`.

| Property | Type | Description |
|---|---|---|
| `weight` | `number` | Heat contribution (always present, default `1.0`) |
| `hasDetails` | `boolean` | `true` = feature is tappable as a POI marker |
| `id` | `number` | OSM element ID |
| `name` | `string` | Venue name |
| `amenity` | `string` | OSM amenity tag value (e.g. `"restaurant"`) |
| `cuisine` | `string` | Semicolon-separated cuisine tags (e.g. `"italian;pizza"`) |
| `address` | `string` | Constructed from `addr:street`, `addr:housenumber`, `addr:city` (or `addr:full`) |
| `website` | `string` | Venue website URL (`contact:website` preferred over `website`) |
| `opening_hours` | `string` | OSM opening hours string (e.g. `"Mo-Su 12:00-23:00"`) |
| `wikidata` | `string` | Wikidata entity ID (e.g. `"Q12345"`) — use to fetch descriptions, images, and Wikipedia links |
| `wikipedia` | `string` | Wikipedia article in `lang:Title` format (e.g. `"en:Colosseum"`) |
| `stars` | `string` | Star rating from OSM (e.g. `"4"`) — common on hotels |
| `outdoor_seating` | `string` | OSM `outdoor_seating` value (e.g. `"yes"`, `"no"`) |

The browser scans all loaded features for `hasDetails: true` to build the `__poi__` layer at runtime.
