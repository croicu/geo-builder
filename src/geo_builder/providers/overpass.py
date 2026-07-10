import json
import math
import time
import urllib.parse
import urllib.request

from ..contracts import AcquisitionTask, Provider
from ..diagnostics import Logger
from ..errors import ProviderError
from ..protocols import Feature, GeoJson, Geometry, Layer

_DEFAULT_URL = "https://overpass-api.de/api/interpreter"

# Delays (seconds) between successive retries on HTTP 429 / 504.
# After exhausting these, the error is re-raised as ProviderError.
_RETRY_DELAYS = (5, 15, 45)

FEATURE_META: dict[str, dict[str, list[str]]] = {
    "amenity": {
        "sustenance": ["bar", "biergarten", "cafe", "fast_food", "food_court", "ice_cream", "pub", "restaurant"],
        "education": ["college", "kindergarten", "library", "school", "university"],
        "healthcare": ["clinic", "dentist", "doctors", "hospital", "pharmacy", "veterinary"],
        "financial": ["atm", "bank", "bureau_de_change"],
        "entertainment": ["arts_centre", "casino", "cinema", "nightclub", "theatre"],
        "transportation": ["bicycle_parking", "bicycle_rental", "bus_station", "car_rental", "fuel", "parking", "taxi"],
    },
    "historic": {
        "monuments": ["castle", "fort", "manor", "tower", "gate", "ruins", "archaeological_site", "city_gate"],
        "memorials": ["monument", "memorial", "milestone", "boundary_stone", "wayside_cross", "wayside_shrine"],
    },
}


class OverpassProvider(Provider):
    name = "overpass"

    def __init__(self, config: dict[str, object] | None = None) -> None:
        self._url = str((config or {}).get("url", _DEFAULT_URL))

    def fetch(self, task: AcquisitionTask) -> Layer:
        surface = self._is_surface(task)

        scale = 1.0
        layer_type = "heatmap"
        layer_name: str | None = None
        if task.filters:
            area_style = next(iter(task.filters.values()))
            if area_style.scale is not None:
                scale = area_style.scale
            layer_type = area_style.type
            layer_name = area_style.name

        query = self._build_query(task)
        payload = self._execute_query(query)
        geojson = self._to_geojson(payload, surface=surface, layer_type=layer_type)

        style: dict = {"opacity": 0.7, "radiusScale": scale}
        if surface:
            style["surface"] = True

        # id and url are assigned by AcquisitionWorker after stable-id lookup.
        return Layer(
            id="",
            name=layer_name or f"Overpass ({layer_type})",
            type=layer_type,
            url=None,
            visible=True,
            style=style,
            geojson=geojson,
        )

    def _is_surface(self, task: AcquisitionTask) -> bool:
        return any(style.surface for style in task.filters.values())

    def _build_query(self, task: AcquisitionTask) -> str:
        filters = self._build_filters(task)
        out_mode = "geom" if self._is_surface(task) else "center"

        return f"""
[out:json][timeout:25];
(
{filters}
);
out {out_mode};
""".strip()

    def _build_filters(self, task: AcquisitionTask) -> str:
        bbox = task.bbox
        bbox_text = f"{bbox.south},{bbox.west},{bbox.north},{bbox.east}"

        lines: list[str] = []

        if not task.filters:
            lines.append(f'  node["amenity"]({bbox_text});')
            lines.append(f'  way["amenity"]({bbox_text});')
            lines.append(f'  relation["amenity"]({bbox_text});')
        else:
            raw = {key: style.values for key, style in task.filters.items()}
            for key, values in self._expand_filter(raw).items():
                filter_expr = self._build_filter_expr(key, values)
                lines.append(f"  node{filter_expr}({bbox_text});")
                lines.append(f"  way{filter_expr}({bbox_text});")
                lines.append(f"  relation{filter_expr}({bbox_text});")

        return "\n".join(lines)

    def _build_filter_expr(self, key: str, values: list[str]) -> str:
        if "*" in values:
            return f'["{key}"]'
        if len(values) == 1:
            return f'["{key}"="{values[0]}"]'
        joined = "|".join(sorted(values))
        return f'["{key}"~"^({joined})$"]'

    def _expand_filter(self, filter: dict[str, list[str]]) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for key, values in filter.items():
            meta = FEATURE_META.get(key, {})
            expanded: list[str] = []
            for value in values:
                for v in meta.get(value, [value]):
                    if v not in expanded:
                        expanded.append(v)
            result[key] = expanded
        return result

    def _execute_query(self, query: str) -> dict:
        data = urllib.parse.urlencode({"data": query}).encode("utf-8")
        Logger.info(f"OverpassProvider: POST {len(data)} bytes → {self._url}")

        request = urllib.request.Request(
            self._url,
            data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "geo-builder/0.1",
            },
            method="POST",
        )

        for attempt in range(len(_RETRY_DELAYS) + 1):
            try:
                t0 = time.perf_counter()
                with urllib.request.urlopen(request, timeout=60) as response:
                    body = response.read()
                elapsed = time.perf_counter() - t0
                Logger.info(f"OverpassProvider: {len(body)} bytes received in {elapsed:.1f}s")
                return json.loads(body.decode("utf-8"))
            except urllib.error.HTTPError as error:
                if error.code == 400:
                    Logger.warning("OverpassProvider: HTTP 400 — query rejected, will split bbox")
                    raise ProviderError("Overpass query rejected (HTTP 400).") from error
                if error.code in (429, 504):
                    if attempt < len(_RETRY_DELAYS):
                        delay = _RETRY_DELAYS[attempt]
                        Logger.warning(f"OverpassProvider: HTTP {error.code} — retry {attempt + 1}/{len(_RETRY_DELAYS)} in {delay}s")
                        time.sleep(delay)
                        continue
                    Logger.warning(f"OverpassProvider: HTTP {error.code} — retries exhausted, treating as split trigger")
                    raise ProviderError(f"Overpass rate limited (HTTP {error.code}) after {len(_RETRY_DELAYS)} retries.") from error
                Logger.warning(f"OverpassProvider: HTTP {error.code} — unexpected, re-raising")
                raise

        raise ProviderError("Overpass query failed after all retries.")

    def _to_geojson(self, payload: dict, surface: bool = False, layer_type: str = "heatmap") -> GeoJson:
        features: list[Feature] = []
        feature_areas: list[float | None] = []

        for element in payload.get("elements", []):
            coordinates = self._get_coordinates(element)

            if coordinates is None:
                continue

            tags = element.get("tags", {})

            cuisine = tags.get("cuisine")
            address = self._build_address(tags)
            website = tags.get("contact:website") or tags.get("website")
            opening_hours = tags.get("opening_hours")
            wikidata = tags.get("wikidata")
            wikipedia = tags.get("wikipedia")
            stars = tags.get("stars")
            outdoor_seating = tags.get("outdoor_seating")
            has_details = bool(cuisine or address or website or opening_hours or wikidata or wikipedia or stars or outdoor_seating)

            properties: dict = {"weight": 1.0}

            area_sqm: float | None = None
            if surface and element.get("type") == "way":
                geometry = element.get("geometry", [])
                if len(geometry) >= 3:
                    area_sqm = self._polygon_area_sqm(geometry)
                    if layer_type == "circle":
                        properties["area_sqm"] = round(area_sqm, 1)
                        properties["radius_m"] = round(math.sqrt(area_sqm / math.pi), 1)

            if has_details:
                element_id = element.get("id")
                name = tags.get("name")
                amenity = tags.get("amenity")
                if element_id is not None:
                    properties["id"] = element_id
                properties["hasDetails"] = True
                if name is not None:
                    properties["name"] = name
                if amenity is not None:
                    properties["amenity"] = amenity
                if cuisine:
                    properties["cuisine"] = cuisine
                if address:
                    properties["address"] = address
                if website:
                    properties["website"] = website
                if opening_hours:
                    properties["opening_hours"] = opening_hours
                if wikidata:
                    properties["wikidata"] = wikidata
                if wikipedia:
                    properties["wikipedia"] = wikipedia
                if stars:
                    properties["stars"] = stars
                if outdoor_seating:
                    properties["outdoor_seating"] = outdoor_seating

            features.append(
                Feature(
                    type="Feature",
                    properties=properties,
                    geometry=Geometry(type="Point", coordinates=coordinates),
                )
            )
            feature_areas.append(area_sqm)

        if surface and layer_type == "heatmap":
            valid = [a for a in feature_areas if a is not None]
            max_area = max(valid) if valid else 0.0
            if max_area > 0:
                for feature, area in zip(features, feature_areas):
                    if area is not None:
                        feature.properties["weight"] = round(area / max_area, 4)

        return GeoJson(
            type="FeatureCollection",
            features=features,
        )

    def _get_coordinates(self, element: dict) -> list[float] | None:
        if "lon" in element and "lat" in element:
            return [float(element["lon"]), float(element["lat"])]

        center = element.get("center")
        if center is not None:
            return [float(center["lon"]), float(center["lat"])]

        geometry = element.get("geometry")
        if geometry:
            lons = [float(p["lon"]) for p in geometry]
            lats = [float(p["lat"]) for p in geometry]
            return [sum(lons) / len(lons), sum(lats) / len(lats)]

        return None

    def _polygon_area_sqm(self, geometry: list[dict]) -> float:
        n = len(geometry)
        area_deg2 = 0.0
        for i in range(n):
            j = (i + 1) % n
            area_deg2 += geometry[i]["lon"] * geometry[j]["lat"]
            area_deg2 -= geometry[j]["lon"] * geometry[i]["lat"]
        area_deg2 = abs(area_deg2) / 2.0

        center_lat = sum(p["lat"] for p in geometry) / n
        meters_per_deg = 111_000.0
        return area_deg2 * meters_per_deg**2 * math.cos(math.radians(center_lat))

    def _build_address(self, tags: dict) -> str | None:
        full = tags.get("addr:full")
        if full:
            return full

        street = tags.get("addr:street")
        number = tags.get("addr:housenumber")
        city = tags.get("addr:city")

        parts: list[str] = []
        street_parts: list[str] = []
        if street:
            street_parts.append(street)
        if number:
            street_parts.append(number)
        if street_parts:
            parts.append(" ".join(street_parts))
        if city:
            parts.append(city)

        if parts:
            return ", ".join(parts)

        return None
