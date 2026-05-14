from geo_builder.contracts import WorkerResult
from geo_builder.protocols import Area, Catalog, Feature, GeoJson, Geometry, Layer, Manifest
from geo_builder.workers.aggregation import AggregationWorker
from tests.shared.stubs import StubExecutor


def make_area(layers: list[Layer]) -> Area:
    return Area(
        id="napoli",
        name="Napoli",
        center=[40.85, 14.27],
        radiusMeters=5000,
        minRadiusPx=32,
        maxRadiusPx=512,
        liveMapRadiusPx=640,
        manifestUrl="./areas/napoli/manifest.json",
        manifest=Manifest(version=1, layers=layers),
    )


def make_layer(merge_key: str, feature_count: int, name: str = "Layer") -> Layer:
    features = [
        Feature(
            type="Feature",
            properties={},
            geometry=Geometry(type="Point", coordinates=[14.27, 40.85]),
        )
        for _ in range(feature_count)
    ]
    layer_id = Layer.id_from_merge_key(merge_key)
    return Layer(
        id=layer_id,
        name=name,
        type="heatmap",
        url=f"./layers/{layer_id}.geojson",
        visible=True,
        style={},
        mergeKey=merge_key,
        geojson=GeoJson(type="FeatureCollection", features=features),
    )


def make_executor(areas: list[Area]) -> StubExecutor:
    catalog = Catalog(areas=areas)
    area = areas[0] if areas else make_area([])
    return StubExecutor(area=area, catalog=catalog)


def run(areas: list[Area]) -> None:
    executor = make_executor(areas)
    AggregationWorker(task=None).execute(executor)


class TestExecute:
    def test_returns_non_fatal(self):
        executor = make_executor([make_area([])])

        result = AggregationWorker(task=None).execute(executor)

        assert result == WorkerResult()

    def test_no_catalog_returns_non_fatal(self):
        executor = StubExecutor(area=make_area([]), catalog=None)

        result = AggregationWorker(task=None).execute(executor)

        assert result == WorkerResult()

    def test_single_layer_unchanged(self):
        layer = make_layer("overpass:amenity=restaurant", feature_count=3)
        area = make_area([layer])

        run([area])

        assert len(area.manifest.layers) == 1
        assert len(area.manifest.layers[0].geojson.features) == 3

    def test_two_layers_same_merge_key_are_merged(self):
        area = make_area(
            [
                make_layer("overpass:amenity=restaurant", feature_count=3),
                make_layer("overpass:amenity=restaurant", feature_count=2),
            ]
        )

        run([area])

        assert len(area.manifest.layers) == 1
        assert len(area.manifest.layers[0].geojson.features) == 5

    def test_different_merge_keys_stay_separate(self):
        area = make_area(
            [
                make_layer("overpass:amenity=restaurant", feature_count=2),
                make_layer("overpass:amenity=cafe", feature_count=2),
            ]
        )

        run([area])

        assert len(area.manifest.layers) == 2

    def test_merged_layer_id_derived_from_merge_key(self):
        area = make_area(
            [
                make_layer("overpass:amenity=restaurant", feature_count=1),
                make_layer("overpass:amenity=restaurant", feature_count=1),
            ]
        )

        run([area])

        assert area.manifest.layers[0].id == "overpass_amenity_restaurant"

    def test_merged_layer_url_derived_from_id(self):
        area = make_area(
            [
                make_layer("overpass:amenity=restaurant", feature_count=1),
                make_layer("overpass:amenity=restaurant", feature_count=1),
            ]
        )

        run([area])

        layer = area.manifest.layers[0]
        assert layer.url == f"./layers/{layer.id}.geojson"


class TestCreateLayerId:
    def setup_method(self):
        self.worker = AggregationWorker(task=None)

    def test_colon_becomes_underscore(self):
        assert self.worker._create_layer_id("overpass:amenity") == "overpass_amenity"

    def test_equals_becomes_underscore(self):
        assert self.worker._create_layer_id("amenity=restaurant") == "amenity_restaurant"

    def test_comma_becomes_underscore(self):
        assert self.worker._create_layer_id("restaurant,cafe") == "restaurant_cafe"

    def test_collapses_consecutive_underscores(self):
        result = self.worker._create_layer_id("overpass:amenity=restaurant,cafe")
        assert result == "overpass_amenity_restaurant_cafe"

    def test_strips_leading_trailing_underscores(self):
        assert self.worker._create_layer_id(":amenity:") == "amenity"
