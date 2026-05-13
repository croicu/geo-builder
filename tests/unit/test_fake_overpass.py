import pytest

from geo_builder.contracts import BoundingBox
from geo_builder.errors import ProviderError
from geo_builder.providers.fake_overpass import FakeOverpassProvider
from geo_builder.tasks import AcquisitionTask

DATA_PATH = "tests/data/providers/overpass.json"

TASK = AcquisitionTask(
    areaId="napoli",
    areaName="Napoli",
    provider="fake_overpass",
    bbox=BoundingBox(west=14.20, south=40.80, east=14.33, north=40.90),
    filter={"amenity": ["restaurant", "cafe", "bar"]},
)


def make_provider(data_path: str = DATA_PATH) -> FakeOverpassProvider:
    return FakeOverpassProvider({"dataPath": data_path})


class TestFakeOverpassProvider:
    def test_returns_layer(self):
        layer = make_provider().fetch(TASK)

        assert layer.geojson is not None
        assert layer.geojson.type == "FeatureCollection"

    def test_features_loaded(self):
        layer = make_provider().fetch(TASK)

        assert len(layer.geojson.features) == 4

    def test_node_coordinates_are_lon_lat(self):
        layer = make_provider().fetch(TASK)

        lon, lat = layer.geojson.features[0].geometry.coordinates
        assert lon == pytest.approx(14.2681)
        assert lat == pytest.approx(40.8518)

    def test_way_center_coordinates(self):
        layer = make_provider().fetch(TASK)

        lon, lat = layer.geojson.features[3].geometry.coordinates
        assert lon == pytest.approx(14.2698)
        assert lat == pytest.approx(40.8491)

    def test_merge_key_format(self):
        layer = make_provider().fetch(TASK)

        assert layer.mergeKey == "fake_overpass:amenity=bar,cafe,restaurant"

    def test_missing_data_path_raises(self):
        with pytest.raises(ProviderError, match="dataPath"):
            FakeOverpassProvider({})

    def test_missing_data_file_raises(self):
        with pytest.raises(FileNotFoundError):
            make_provider("nonexistent.json").fetch(TASK)
