import json
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

import pytest

from geo_builder.contracts import AcquisitionTask, BoundingBox
from geo_builder.errors import ProviderError
from geo_builder.protocols import AreaStyle
from geo_builder.providers.overpass import OverpassProvider

TASK = AcquisitionTask(
    areaId="napoli",
    areaName="Napoli",
    provider="overpass",
    bbox=BoundingBox(west=14.20, south=40.80, east=14.33, north=40.90),
    filters={"amenity": AreaStyle(values=["restaurant", "cafe", "bar"])},
)

SURFACE_TASK = AcquisitionTask(
    areaId="napoli",
    areaName="Napoli",
    provider="overpass",
    bbox=BoundingBox(west=14.20, south=40.80, east=14.33, north=40.90),
    filters={"leisure": AreaStyle(values=["park"], surface=True)},
)

# Square 100m × 100m at ~45° lat → area ≈ 10 000 m²
_SQUARE_GEOMETRY = [
    {"lat": 45.0000, "lon": 0.0000},
    {"lat": 45.0009, "lon": 0.0000},
    {"lat": 45.0009, "lon": 0.0013},
    {"lat": 45.0000, "lon": 0.0013},
]

PAYLOAD = {
    "elements": [
        {"type": "node", "id": 1, "lat": 40.8518, "lon": 14.2681, "tags": {"name": "Trattoria da Mario", "amenity": "restaurant"}},
        {"type": "way", "id": 2, "center": {"lat": 40.8491, "lon": 14.2698}, "tags": {"name": "Ristorante Partenope", "amenity": "restaurant"}},
    ]
}


class StubOverpassProvider(OverpassProvider):
    def __init__(self, payload: dict) -> None:
        super().__init__()
        self._payload = payload

    def _execute_query(self, query: str) -> dict:
        return self._payload


def make_response(payload: dict):
    body = json.dumps(payload).encode("utf-8")
    mock = MagicMock()
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    mock.read.return_value = body
    return mock


class TestFetch:
    def test_returns_layer(self):
        layer = StubOverpassProvider(PAYLOAD).fetch(TASK)

        assert layer.geojson is not None
        assert layer.geojson.type == "FeatureCollection"

    def test_feature_count(self):
        layer = StubOverpassProvider(PAYLOAD).fetch(TASK)

        assert len(layer.geojson.features) == 2

    def test_merge_key_format(self):
        layer = StubOverpassProvider(PAYLOAD).fetch(TASK)

        assert layer.mergeKey == "overpass:amenity=bar,cafe,restaurant"

    def test_layer_id_and_url(self):
        layer = StubOverpassProvider(PAYLOAD).fetch(TASK)

        assert layer.id == "overpass_amenity_bar_cafe_restaurant"
        assert layer.url == "./layers/overpass_amenity_bar_cafe_restaurant.geojson"

    def test_default_layer_type_is_heatmap(self):
        layer = StubOverpassProvider(PAYLOAD).fetch(TASK)

        assert layer.type == "heatmap"

    def test_circle_type_propagates_to_layer(self):
        task = AcquisitionTask(
            areaId="x",
            areaName="X",
            provider="overpass",
            bbox=BoundingBox(west=0, south=0, east=1, north=1),
            filters={"leisure": AreaStyle(values=["park"], type="circle")},
        )
        layer = StubOverpassProvider({"elements": []}).fetch(task)

        assert layer.type == "circle"


class TestToGeoJson:
    def setup_method(self):
        self.provider = OverpassProvider()

    def test_node_uses_lon_lat(self):
        payload = {"elements": [{"type": "node", "id": 1, "lat": 40.85, "lon": 14.27, "tags": {}}]}

        geojson = self.provider._to_geojson(payload)

        assert geojson.features[0].geometry.coordinates == [14.27, 40.85]

    def test_way_uses_center(self):
        payload = {"elements": [{"type": "way", "id": 1, "center": {"lat": 40.85, "lon": 14.27}, "tags": {}}]}

        geojson = self.provider._to_geojson(payload)

        assert geojson.features[0].geometry.coordinates == [14.27, 40.85]

    def test_element_without_coordinates_skipped(self):
        payload = {"elements": [{"type": "relation", "id": 1, "tags": {}}]}

        geojson = self.provider._to_geojson(payload)

        assert geojson.features == []

    def test_none_tag_values_excluded_from_properties(self):
        payload = {"elements": [{"type": "node", "id": 1, "lat": 40.85, "lon": 14.27, "tags": {"amenity": "restaurant"}}]}

        geojson = self.provider._to_geojson(payload)

        props = geojson.features[0].properties
        assert "name" not in props
        assert props["amenity"] == "restaurant"

    def test_empty_elements_returns_empty_collection(self):
        geojson = self.provider._to_geojson({"elements": []})

        assert geojson.features == []


class TestBuildQuery:
    def setup_method(self):
        self.provider = OverpassProvider()

    def test_contains_bbox(self):
        query = self.provider._build_query(TASK)

        assert "40.8,14.2,40.9,14.33" in query

    def test_contains_filter_key_and_value(self):
        query = self.provider._build_query(TASK)

        assert '"amenity"="restaurant"' in query
        assert '"amenity"="cafe"' in query
        assert '"amenity"="bar"' in query

    def test_emits_node_way_relation_per_value(self):
        task = AcquisitionTask(
            areaId="x",
            areaName="X",
            provider="overpass",
            bbox=BoundingBox(west=0, south=0, east=1, north=1),
            filters={"amenity": AreaStyle(values=["restaurant"])},
        )
        query = self.provider._build_query(task)

        assert "node" in query
        assert "way" in query
        assert "relation" in query

    def test_non_surface_uses_out_center(self):
        query = self.provider._build_query(TASK)

        assert "out center" in query
        assert "out geom" not in query

    def test_surface_uses_out_geom(self):
        query = self.provider._build_query(SURFACE_TASK)

        assert "out geom" in query
        assert "out center" not in query


class TestWildcard:
    def setup_method(self):
        self.provider = OverpassProvider()

    def test_wildcard_emits_key_only_filter(self):
        task = AcquisitionTask(
            areaId="x",
            areaName="X",
            provider="overpass",
            bbox=BoundingBox(west=0, south=0, east=1, north=1),
            filters={"historic": AreaStyle(values=["*"])},
        )
        query = self.provider._build_query(task)

        assert '"historic"' in query
        assert '"historic"="*"' not in query

    def test_wildcard_emits_node_way_relation(self):
        task = AcquisitionTask(
            areaId="x",
            areaName="X",
            provider="overpass",
            bbox=BoundingBox(west=0, south=0, east=1, north=1),
            filters={"historic": AreaStyle(values=["*"])},
        )
        query = self.provider._build_query(task)

        assert 'node["historic"]' in query
        assert 'way["historic"]' in query
        assert 'relation["historic"]' in query

    def test_wildcard_merge_key_uses_asterisk(self):
        task = AcquisitionTask(
            areaId="x",
            areaName="X",
            provider="overpass",
            bbox=BoundingBox(west=0, south=0, east=1, north=1),
            filters={"historic": AreaStyle(values=["*"])},
        )
        assert self.provider._create_merge_key(task) == "overpass:historic=*"

    def test_wildcard_layer_id_is_clean(self):
        from geo_builder.entities import GeoLayer

        assert GeoLayer.id_from_merge_key("overpass:historic=*") == "overpass_historic"

    def test_wildcard_mixed_with_specific_value(self):
        task = AcquisitionTask(
            areaId="x",
            areaName="X",
            provider="overpass",
            bbox=BoundingBox(west=0, south=0, east=1, north=1),
            filters={"historic": AreaStyle(values=["*"]), "amenity": AreaStyle(values=["restaurant"])},
        )
        query = self.provider._build_query(task)

        assert 'node["historic"]' in query
        assert '"amenity"="restaurant"' in query


class TestCreateMergeKey:
    def setup_method(self):
        self.provider = OverpassProvider()

    def test_single_filter(self):
        task = AcquisitionTask(
            areaId="x",
            areaName="X",
            provider="overpass",
            bbox=BoundingBox(west=0, south=0, east=1, north=1),
            filters={"amenity": AreaStyle(values=["restaurant"])},
        )

        assert self.provider._create_merge_key(task) == "overpass:amenity=restaurant"

    def test_multiple_values_sorted(self):
        assert self.provider._create_merge_key(TASK) == "overpass:amenity=bar,cafe,restaurant"

    def test_multiple_keys_sorted(self):
        task = AcquisitionTask(
            areaId="x",
            areaName="X",
            provider="overpass",
            bbox=BoundingBox(west=0, south=0, east=1, north=1),
            filters={"leisure": AreaStyle(values=["park"]), "amenity": AreaStyle(values=["cafe"])},
        )

        assert self.provider._create_merge_key(task) == "overpass:amenity=cafe:leisure=park"


class TestExpandFilter:
    def setup_method(self):
        self.provider = OverpassProvider()

    def test_meta_value_expands_to_individual_values(self):
        result = self.provider._expand_filter({"amenity": ["sustenance"]})

        assert result["amenity"] == ["bar", "biergarten", "cafe", "fast_food", "food_court", "ice_cream", "pub", "restaurant"]

    def test_non_meta_value_passes_through(self):
        result = self.provider._expand_filter({"amenity": ["restaurant"]})

        assert result["amenity"] == ["restaurant"]

    def test_mix_of_meta_and_individual_values(self):
        result = self.provider._expand_filter({"amenity": ["financial", "restaurant"]})

        assert "atm" in result["amenity"]
        assert "bank" in result["amenity"]
        assert "restaurant" in result["amenity"]

    def test_deduplication_within_expansion(self):
        result = self.provider._expand_filter({"amenity": ["sustenance", "cafe"]})

        assert result["amenity"].count("cafe") == 1

    def test_multiple_keys_expanded_independently(self):
        result = self.provider._expand_filter({"amenity": ["financial"], "leisure": ["park"]})

        assert "atm" in result["amenity"]
        assert result["leisure"] == ["park"]

    def test_unknown_key_values_pass_through_unchanged(self):
        result = self.provider._expand_filter({"leisure": ["park", "garden"]})

        assert result["leisure"] == ["park", "garden"]

    def test_query_uses_correct_key_for_non_amenity_filter(self):
        task = AcquisitionTask(
            areaId="x",
            areaName="X",
            provider="overpass",
            bbox=BoundingBox(west=0, south=0, east=1, north=1),
            filters={"leisure": AreaStyle(values=["park"])},
        )
        query = self.provider._build_query(task)

        assert '"leisure"="park"' in query
        assert '"amenity"' not in query

    def test_meta_name_preserved_in_merge_key(self):
        task = AcquisitionTask(
            areaId="x",
            areaName="X",
            provider="overpass",
            bbox=BoundingBox(west=0, south=0, east=1, north=1),
            filters={"amenity": AreaStyle(values=["sustenance"])},
        )
        key = self.provider._create_merge_key(task)

        assert key == "overpass:amenity=sustenance"

    def test_query_contains_expanded_values_not_meta_name(self):
        task = AcquisitionTask(
            areaId="x",
            areaName="X",
            provider="overpass",
            bbox=BoundingBox(west=0, south=0, east=1, north=1),
            filters={"amenity": AreaStyle(values=["sustenance"])},
        )
        query = self.provider._build_query(task)

        assert '"amenity"="sustenance"' not in query
        assert '"amenity"="restaurant"' in query
        assert '"amenity"="cafe"' in query


class TestExecuteQuery:
    def test_success_returns_parsed_json(self):
        provider = OverpassProvider({"url": "http://fake"})

        with patch("urllib.request.urlopen", return_value=make_response(PAYLOAD)):
            result = provider._execute_query("query")

        assert result == PAYLOAD

    @pytest.mark.parametrize("code", [400, 429, 504])
    def test_rate_limit_codes_raise_provider_error(self, code):
        provider = OverpassProvider({"url": "http://fake"})
        error = urllib.error.HTTPError(url="", code=code, msg="", hdrs=None, fp=None)

        with patch("urllib.request.urlopen", side_effect=error):
            with pytest.raises(ProviderError):
                provider._execute_query("query")

    def test_other_http_error_reraises(self):
        provider = OverpassProvider({"url": "http://fake"})
        error = urllib.error.HTTPError(url="", code=500, msg="", hdrs=None, fp=None)

        with patch("urllib.request.urlopen", side_effect=error):
            with pytest.raises(urllib.error.HTTPError):
                provider._execute_query("query")


class TestSurface:
    def setup_method(self):
        self.provider = OverpassProvider()

    def test_surface_flag_appears_in_layer_style(self):
        payload = {"elements": []}
        layer = StubOverpassProvider(payload).fetch(SURFACE_TASK)

        assert layer.style.get("surface") is True

    def test_non_surface_flag_absent_from_layer_style(self):
        layer = StubOverpassProvider(PAYLOAD).fetch(TASK)

        assert "surface" not in layer.style

    def test_circle_way_gets_area_and_radius(self):
        payload = {
            "elements": [
                {"type": "way", "id": 1, "geometry": _SQUARE_GEOMETRY, "tags": {}},
            ]
        }
        geojson = self.provider._to_geojson(payload, surface=True, layer_type="circle")

        props = geojson.features[0].properties
        assert "area_sqm" in props
        assert "radius_m" in props
        assert props["area_sqm"] > 0
        assert props["radius_m"] == pytest.approx((props["area_sqm"] / 3.14159) ** 0.5, rel=0.01)

    def test_heatmap_way_has_no_area_or_radius_properties(self):
        payload = {
            "elements": [
                {"type": "way", "id": 1, "geometry": _SQUARE_GEOMETRY, "tags": {}},
            ]
        }
        geojson = self.provider._to_geojson(payload, surface=True, layer_type="heatmap")

        props = geojson.features[0].properties
        assert "area_sqm" not in props
        assert "radius_m" not in props

    def test_heatmap_surface_normalises_weight(self):
        large = _SQUARE_GEOMETRY
        small = [
            {"lat": 45.0000, "lon": 0.0000},
            {"lat": 45.0004, "lon": 0.0000},
            {"lat": 45.0004, "lon": 0.0006},
            {"lat": 45.0000, "lon": 0.0006},
        ]
        payload = {
            "elements": [
                {"type": "way", "id": 1, "geometry": large, "tags": {}},
                {"type": "way", "id": 2, "geometry": small, "tags": {}},
            ]
        }
        geojson = self.provider._to_geojson(payload, surface=True, layer_type="heatmap")

        weights = [f.properties["weight"] for f in geojson.features]
        assert max(weights) == pytest.approx(1.0)
        assert min(weights) < 1.0
        assert all(0.0 <= w <= 1.0 for w in weights)

    def test_heatmap_surface_node_keeps_default_weight(self):
        payload = {
            "elements": [
                {"type": "node", "id": 1, "lat": 45.0, "lon": 0.0, "tags": {}},
            ]
        }
        geojson = self.provider._to_geojson(payload, surface=True, layer_type="heatmap")

        assert geojson.features[0].properties["weight"] == 1.0

    def test_node_in_surface_mode_has_no_area_properties(self):
        payload = {
            "elements": [
                {"type": "node", "id": 1, "lat": 45.0, "lon": 0.0, "tags": {}},
            ]
        }
        geojson = self.provider._to_geojson(payload, surface=True, layer_type="circle")

        props = geojson.features[0].properties
        assert "area_sqm" not in props
        assert "radius_m" not in props

    def test_way_without_geometry_has_no_area_properties(self):
        payload = {
            "elements": [
                {"type": "way", "id": 1, "center": {"lat": 45.0, "lon": 0.0}, "tags": {}},
            ]
        }
        geojson = self.provider._to_geojson(payload, surface=True, layer_type="circle")

        props = geojson.features[0].properties
        assert "area_sqm" not in props
        assert "radius_m" not in props


class TestGetCoordinates:
    def setup_method(self):
        self.provider = OverpassProvider()

    def test_node_returns_lon_lat(self):
        element = {"type": "node", "lat": 40.85, "lon": 14.27}
        assert self.provider._get_coordinates(element) == [14.27, 40.85]

    def test_way_center_returns_lon_lat(self):
        element = {"type": "way", "center": {"lat": 40.85, "lon": 14.27}}
        assert self.provider._get_coordinates(element) == [14.27, 40.85]

    def test_way_geometry_returns_centroid(self):
        element = {
            "type": "way",
            "geometry": [
                {"lat": 0.0, "lon": 0.0},
                {"lat": 0.0, "lon": 2.0},
                {"lat": 2.0, "lon": 2.0},
                {"lat": 2.0, "lon": 0.0},
            ],
        }
        coords = self.provider._get_coordinates(element)
        assert coords == pytest.approx([1.0, 1.0])

    def test_element_with_no_location_returns_none(self):
        assert self.provider._get_coordinates({"type": "relation", "id": 1}) is None


class TestPolygonAreaSqm:
    def setup_method(self):
        self.provider = OverpassProvider()

    def test_unit_square_at_equator(self):
        # 1° × 1° square at equator ≈ 111_000² m²
        geom = [
            {"lat": 0.0, "lon": 0.0},
            {"lat": 1.0, "lon": 0.0},
            {"lat": 1.0, "lon": 1.0},
            {"lat": 0.0, "lon": 1.0},
        ]
        area = self.provider._polygon_area_sqm(geom)
        assert area == pytest.approx(111_000.0**2, rel=0.01)

    def test_winding_order_does_not_matter(self):
        cw = [
            {"lat": 0.0, "lon": 0.0},
            {"lat": 1.0, "lon": 0.0},
            {"lat": 1.0, "lon": 1.0},
            {"lat": 0.0, "lon": 1.0},
        ]
        ccw = list(reversed(cw))
        assert self.provider._polygon_area_sqm(cw) == pytest.approx(self.provider._polygon_area_sqm(ccw), rel=1e-9)

    def test_area_shrinks_toward_pole(self):
        def square_at(lat):
            return [
                {"lat": lat, "lon": 0.0},
                {"lat": lat + 1.0, "lon": 0.0},
                {"lat": lat + 1.0, "lon": 1.0},
                {"lat": lat, "lon": 1.0},
            ]

        assert self.provider._polygon_area_sqm(square_at(60.0)) < self.provider._polygon_area_sqm(square_at(0.0))
