import json
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

import pytest

from geo_builder.contracts import AcquisitionTask, BoundingBox
from geo_builder.errors import ProviderError
from geo_builder.providers.overpass import OverpassProvider

TASK = AcquisitionTask(
    areaId="napoli",
    areaName="Napoli",
    provider="overpass",
    bbox=BoundingBox(west=14.20, south=40.80, east=14.33, north=40.90),
    filter={"amenity": ["restaurant", "cafe", "bar"]},
)

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
            areaId="x", areaName="X", provider="overpass",
            bbox=BoundingBox(west=0, south=0, east=1, north=1),
            filter={"amenity": ["restaurant"]},
        )
        query = self.provider._build_query(task)

        assert "node" in query
        assert "way" in query
        assert "relation" in query


class TestCreateMergeKey:
    def setup_method(self):
        self.provider = OverpassProvider()

    def test_single_filter(self):
        task = AcquisitionTask(
            areaId="x", areaName="X", provider="overpass",
            bbox=BoundingBox(west=0, south=0, east=1, north=1),
            filter={"amenity": ["restaurant"]},
        )

        assert self.provider._create_merge_key(task) == "overpass:amenity=restaurant"

    def test_multiple_values_sorted(self):
        assert self.provider._create_merge_key(TASK) == "overpass:amenity=bar,cafe,restaurant"

    def test_multiple_keys_sorted(self):
        task = AcquisitionTask(
            areaId="x", areaName="X", provider="overpass",
            bbox=BoundingBox(west=0, south=0, east=1, north=1),
            filter={"leisure": ["park"], "amenity": ["cafe"]},
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

    def test_meta_name_preserved_in_merge_key(self):
        task = AcquisitionTask(
            areaId="x", areaName="X", provider="overpass",
            bbox=BoundingBox(west=0, south=0, east=1, north=1),
            filter={"amenity": ["sustenance"]},
        )
        key = self.provider._create_merge_key(task)

        assert key == "overpass:amenity=sustenance"

    def test_query_contains_expanded_values_not_meta_name(self):
        task = AcquisitionTask(
            areaId="x", areaName="X", provider="overpass",
            bbox=BoundingBox(west=0, south=0, east=1, north=1),
            filter={"amenity": ["sustenance"]},
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
