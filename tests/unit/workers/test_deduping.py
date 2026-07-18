import pytest

from geo_builder.contracts import DedupingTask, WorkerResult
from geo_builder.entities import GeoArea, GeoCatalog, GeoLayer
from geo_builder.protocols import Area, Feature, GeoJson, Geometry, Layer
from geo_builder.workers.deduping import DedupingWorker
from tests.shared.stubs import StubExecutor

# Napoli centre — used as a reference point for distance-based tests
BASE_LON = 14.27
BASE_LAT = 40.85

# ~8 m east of base — within the 10 m dedup threshold
NEAR_LON = 14.270072
NEAR_LAT = 40.85

# ~15 m east of base — outside the threshold
FAR_LON = 14.270135
FAR_LAT = 40.85


def make_feature(lon: float, lat: float, properties: dict | None = None) -> Feature:
    return Feature(
        type="Feature",
        properties=properties or {},
        geometry=Geometry(type="Point", coordinates=[lon, lat]),
    )


def make_layer(features: list[Feature]) -> Layer:
    return Layer(
        id="1",
        name="Restaurant",
        type="heatmap",
        url="./layers/1.geojson",
        visible=True,
        style={},
        acquisition={"provider": "stub", "filters": {"amenity": ["restaurant"]}},
        geojson=GeoJson(type="FeatureCollection", features=features),
    )


def make_area(layers: list[Layer]) -> GeoArea:
    summary = Area(
        id="napoli",
        name="Napoli",
        bbox=[14.20, 40.80, 14.33, 40.90],
        minRadiusPx=32,
        maxRadiusPx=512,
        liveMapRadiusPx=640,
        manifestUrl="./areas/napoli/manifest.json",
    )
    geo_layers = []
    for layer in layers:
        geo_layers.append(GeoLayer(layer))
    return GeoArea(summary=summary, layers=geo_layers)


def make_executor(areas: list[GeoArea]) -> StubExecutor:
    area = areas[0] if areas else make_area([])
    return StubExecutor(area=area, catalog=GeoCatalog(areas=areas))


def run(areas: list[GeoArea]) -> None:
    DedupingWorker(task=None).execute(make_executor(areas))


class TestExecute:
    def test_returns_non_fatal(self):
        executor = make_executor([make_area([])])

        result = DedupingWorker(task=None).execute(executor)

        assert result == WorkerResult()

    def test_no_catalog_returns_non_fatal(self):
        executor = StubExecutor(area=make_area([]), catalog=None)

        result = DedupingWorker(task=None).execute(executor)

        assert result == WorkerResult()

    def test_unique_features_are_kept(self):
        area = make_area(
            [
                make_layer(
                    [
                        make_feature(BASE_LON, BASE_LAT),
                        make_feature(FAR_LON, FAR_LAT),
                    ]
                )
            ]
        )

        run([area])

        assert len(area.layers[0].layer.geojson.features) == 2

    def test_near_duplicate_is_removed(self):
        area = make_area(
            [
                make_layer(
                    [
                        make_feature(BASE_LON, BASE_LAT),
                        make_feature(NEAR_LON, NEAR_LAT),
                    ]
                )
            ]
        )

        run([area])

        assert len(area.layers[0].layer.geojson.features) == 1

    def test_first_feature_is_kept_on_dedup(self):
        area = make_area(
            [
                make_layer(
                    [
                        make_feature(BASE_LON, BASE_LAT, {"name": "A"}),
                        make_feature(NEAR_LON, NEAR_LAT, {"name": "B"}),
                    ]
                )
            ]
        )

        run([area])

        assert area.layers[0].layer.geojson.features[0].geometry.coordinates == [BASE_LON, BASE_LAT]

    def test_empty_layer_stays_empty(self):
        area = make_area([make_layer([])])

        run([area])

        assert area.layers[0].layer.geojson.features == []


class TestAreaScoping:
    def test_area_not_in_area_ids_is_skipped(self):
        napoli = make_area([make_layer([make_feature(BASE_LON, BASE_LAT), make_feature(NEAR_LON, NEAR_LAT)])])
        roma = make_area([make_layer([make_feature(BASE_LON, BASE_LAT), make_feature(NEAR_LON, NEAR_LAT)])])
        roma.summary.id = "roma"

        executor = make_executor([napoli, roma])
        DedupingWorker(task=DedupingTask(area_ids=["napoli"])).execute(executor)

        assert len(napoli.layers[0].layer.geojson.features) == 1
        assert len(roma.layers[0].layer.geojson.features) == 2

    def test_none_area_ids_processes_every_area(self):
        napoli = make_area([make_layer([make_feature(BASE_LON, BASE_LAT), make_feature(NEAR_LON, NEAR_LAT)])])
        roma = make_area([make_layer([make_feature(BASE_LON, BASE_LAT), make_feature(NEAR_LON, NEAR_LAT)])])
        roma.summary.id = "roma"

        executor = make_executor([napoli, roma])
        DedupingWorker(task=DedupingTask(area_ids=None)).execute(executor)

        assert len(napoli.layers[0].layer.geojson.features) == 1
        assert len(roma.layers[0].layer.geojson.features) == 1


class TestDedupeFeatures:
    def setup_method(self):
        self.worker = DedupingWorker(task=None)

    def test_single_feature_unchanged(self):
        features = [make_feature(BASE_LON, BASE_LAT)]

        result = self.worker._dedupe_features(features)

        assert len(result) == 1

    def test_identical_coordinates_deduped(self):
        features = [
            make_feature(BASE_LON, BASE_LAT),
            make_feature(BASE_LON, BASE_LAT),
        ]

        result = self.worker._dedupe_features(features)

        assert len(result) == 1

    def test_output_is_independent_copy(self):
        feature = make_feature(BASE_LON, BASE_LAT, {"name": "Original"})
        result = self.worker._dedupe_features([feature])

        result[0].properties["name"] = "Modified"

        assert feature.properties["name"] == "Original"


class TestMergeProperty:
    def setup_method(self):
        self.worker = DedupingWorker(task=None)

    def test_same_value_no_change(self):
        winner = {"name": "Cafe"}
        other = {"name": "Cafe"}

        self.worker._merge_property(winner, other, "name", "names")

        assert "names" not in winner

    def test_different_values_creates_plural(self):
        winner = {"name": "Cafe"}
        other = {"name": "Bar"}

        self.worker._merge_property(winner, other, "name", "names")

        assert winner["names"] == ["Cafe", "Bar"]

    def test_existing_plural_extended(self):
        winner = {"name": "Cafe", "names": ["Cafe", "Bar"]}
        other = {"name": "Pizza"}

        self.worker._merge_property(winner, other, "name", "names")

        assert winner["names"] == ["Cafe", "Bar", "Pizza"]

    def test_duplicate_value_not_added(self):
        winner = {"name": "Cafe", "names": ["Cafe", "Bar"]}
        other = {"name": "Bar"}

        self.worker._merge_property(winner, other, "name", "names")

        assert winner["names"] == ["Cafe", "Bar"]

    def test_non_string_winner_skipped(self):
        winner = {"name": 42}
        other = {"name": "Bar"}

        self.worker._merge_property(winner, other, "name", "names")

        assert "names" not in winner

    def test_missing_key_skipped(self):
        winner = {}
        other = {"name": "Bar"}

        self.worker._merge_property(winner, other, "name", "names")

        assert "names" not in winner


class TestDistanceMeters:
    def setup_method(self):
        self.worker = DedupingWorker(task=None)

    def test_same_point_is_zero(self):
        assert self.worker._distance_meters(40.85, 14.27, 40.85, 14.27) == pytest.approx(0.0)

    def test_near_points_under_threshold(self):
        assert self.worker._distance_meters(BASE_LAT, BASE_LON, NEAR_LAT, NEAR_LON) < 10.0

    def test_far_points_over_threshold(self):
        assert self.worker._distance_meters(BASE_LAT, BASE_LON, FAR_LAT, FAR_LON) >= 10.0
