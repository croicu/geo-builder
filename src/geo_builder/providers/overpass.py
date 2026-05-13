import json
import urllib.parse
import urllib.request

from ..contracts import Provider
from ..protocols import Feature, GeoJson, Geometry, Layer
from ..tasks import AcquisitionTask


class OverpassProvider(Provider):
    name = "overpass"

    def fetch(self, task: AcquisitionTask) -> Layer:
        query = self._build_query(task)
        payload = self._execute_query(query)
        geojson = self._to_geojson(payload)

        return Layer(
            id="overpass",
            name="Overpass #1 (heatmap)",
            type="heatmap",
            url="./layers/overpass.geojson",
            visible=True,
            style={
                "color": "#00ff00",
                "opacity": 0.7,
                "radiusScale": 1.0,
            },
            mergeKey=self._create_merge_key(task),
            geojson=geojson,
        )

    def _build_query(self, task: AcquisitionTask) -> str:
        filters = self._build_filters(task)

        return f"""
[out:json][timeout:25];
(
{filters}
);
out center;
""".strip()

    def _build_filters(self, task: AcquisitionTask) -> str:
        bbox = task.bbox
        bbox_text = f"{bbox.south},{bbox.west},{bbox.north},{bbox.east}"

        lines: list[str] = []

        for key, values in task.filter.items():
            for value in values:
                lines.append(f'  node["{key}"="{value}"]({bbox_text});')
                lines.append(f'  way["{key}"="{value}"]({bbox_text});')
                lines.append(f'  relation["{key}"="{value}"]({bbox_text});')

        return "\n".join(lines)

    def _execute_query(self, query: str) -> dict:
        data = urllib.parse.urlencode({"data": query}).encode("utf-8")

        request = urllib.request.Request(
            "https://overpass-api.de/api/interpreter",
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
                raise ValueError("Overpass request too large or rate limited.") from error

            raise

    def _to_geojson(self, payload: dict) -> GeoJson:
        features: list[Feature] = []

        for element in payload.get("elements", []):
            coordinates = self._get_coordinates(element)

            if coordinates is None:
                continue

            tags = element.get("tags", {})

            properties = {
                "id": element.get("id"),
                "name": tags.get("name"),
                "amenity": tags.get("amenity"),
                "weight": 1.0,
            }

            properties = {
                key: value
                for key, value in properties.items()
                if value is not None
            }

            features.append(
                Feature(
                    type="Feature",
                    properties=properties,
                    geometry=Geometry(
                        type="Point",
                        coordinates=coordinates,
                    ),
                )
            )

        return GeoJson(
            type="FeatureCollection",
            features=features,
        )

    def _get_coordinates(self, element: dict) -> list[float] | None:
        if "lon" in element and "lat" in element:
            return [
                float(element["lon"]),
                float(element["lat"]),
            ]

        center = element.get("center")
        if center is not None:
            return [
                float(center["lon"]),
                float(center["lat"]),
            ]

        return None

    def _create_merge_key(self, task: AcquisitionTask) -> str:
        parts: list[str] = [task.provider]

        for key in sorted(task.filter.keys()):
            values = sorted(task.filter[key])
            parts.append(f"{key}={','.join(values)}")

        return ":".join(parts)
    