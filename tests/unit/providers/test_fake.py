import pytest

from geo_builder.contracts import AcquisitionTask, BoundingBox
from geo_builder.errors import ProviderError
from geo_builder.protocols import AreaStyle
from geo_builder.providers.fake import FakeProvider

DATA_PATH = "tests/data/providers/fake.json"

TASK = AcquisitionTask(
    areaId="napoli",
    areaName="Napoli",
    provider="fake",
    bbox=BoundingBox(west=14.20, south=40.80, east=14.33, north=40.90),
    filters={"amenity": AreaStyle(values=["restaurant", "cafe", "bar"])},
)


def make_provider(data_path: str = DATA_PATH) -> FakeProvider:
    return FakeProvider({"dataPath": data_path})


class TestFakeProvider:
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

    def test_id_and_url_are_empty_pending_worker_assignment(self):
        layer = make_provider().fetch(TASK)

        assert layer.id == ""
        assert layer.url is None

    def test_missing_data_path_raises(self):
        with pytest.raises(ProviderError, match="dataPath"):
            FakeProvider({})

    def test_missing_data_file_raises(self):
        with pytest.raises(FileNotFoundError):
            make_provider("nonexistent.json").fetch(TASK)
