import json
import math
import urllib.parse
import urllib.request

from ..contracts import Provider
from ..entities import GeoLayer
from ..errors import ProviderError
from ..protocols import Feature, GeoJson, Geometry, Layer
from ..tasks import AcquisitionTask

_DEFAULT_URL = "https://overpass-api.de/api/interpreter"

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
        if len(task.filters) == 1:
            area_style = next(iter(task.filters.values()))
            if area_style.scale is not None:
                scale = area_style.scale
            layer_type = area_style.type
            layer_name = area_style.name

        query = self._build_query(task)
        payload = self._execute_query(query)
        geojson = self._to_geojson(payload, surface=surface, layer_type=layer_type)
        merge_key = self._create_merge_key(task)
        layer_id = GeoLayer.id_from_merge_key(merge_key)

        style: dict = {"opacity": 0.7, "radiusScale": scale}
        if surface:
            style["surface"] = True

        return Layer(
            id=layer_id,
            name=layer_name or f"Overpass ({layer_type})",
            type=layer_type,
            url=f"./layers/{layer_id}.geojson",
            visible=True,
            style=style,
            mergeKey=merge_key,
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
                for value in values:
                    if value == "*":
                        lines.append(f'  node["{key}"]({bbox_text});')
                        lines.append(f'  way["{key}"]({bbox_text});')
                        lines.append(f'  relation["{key}"]({bbox_text});')
                    else:
                        lines.append(f'  node["{key}"="{value}"]({bbox_text});')
                        lines.append(f'  way["{key}"="{value}"]({bbox_text});')
                        lines.append(f'  relation["{key}"="{value}"]({bbox_text});')

        return "\n".join(lines)

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

        request = urllib.request.Request(
            self._url,
            data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "geo-builder/0.1",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            if error.code in (400, 429, 504):
                raise ProviderError("Overpass request too large or rate limited.") from error

            raise

    def _to_geojson(self, payload: dict, surface: bool = False, layer_type: str = "heatmap") -> GeoJson:
        features: list[Feature] = []
        feature_areas: list[float | None] = []

        for element in payload.get("elements", []):
            coordinates = self._get_coordinates(element)

            if coordinates is None:
                continue

            tags = element.get("tags", {})

            properties: dict = {
                "id": element.get("id"),
                "name": tags.get("name"),
                "amenity": tags.get("amenity"),
                "weight": 1.0,
            }

            area_sqm: float | None = None
            if surface and element.get("type") == "way":
                geometry = element.get("geometry", [])
                if len(geometry) >= 3:
                    area_sqm = self._polygon_area_sqm(geometry)
                    if layer_type == "circle":
                        properties["area_sqm"] = round(area_sqm, 1)
                        properties["radius_m"] = round(math.sqrt(area_sqm / math.pi), 1)

            properties = {key: value for key, value in properties.items() if value is not None}

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

    def _create_merge_key(self, task: AcquisitionTask) -> str:
        parts: list[str] = [task.provider]

        for key in sorted(task.filters.keys()):
            values = sorted(task.filters[key].values)
            parts.append(f"{key}={','.join(values)}")

        return ":".join(parts)
