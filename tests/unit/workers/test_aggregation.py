from geo_builder.contracts import WorkerResult
from geo_builder.entities import GeoArea, GeoCatalog, GeoLayer
from geo_builder.protocols import Area, Feature, GeoJson, Geometry, Layer
from geo_builder.workers.aggregation import AggregationWorker
from tests.shared.stubs import StubExecutor


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


def make_layer(layer_id: str, acquisition: dict, feature_count: int, name: str = "Layer") -> Layer:
    features = []
    for _ in range(feature_count):
        features.append(
            Feature(
                type="Feature",
                properties={},
                geometry=Geometry(type="Point", coordinates=[14.27, 40.85]),
            )
        )
    return Layer(
        id=layer_id,
        name=name,
        type="heatmap",
        url=f"./layers/{layer_id}.geojson",
        visible=True,
        style={},
        acquisition=acquisition,
        geojson=GeoJson(type="FeatureCollection", features=features),
    )


_ACQ_RESTAURANT = {"provider": "overpass", "filter": "amenity", "values": ["restaurant"]}
_ACQ_CAFE = {"provider": "overpass", "filter": "amenity", "values": ["cafe"]}


def make_executor(areas: list[GeoArea]) -> StubExecutor:
    catalog = GeoCatalog(areas=areas)
    area = areas[0] if areas else make_area([])
    return StubExecutor(area=area, catalog=catalog)


def run(areas: list[GeoArea]) -> None:
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
        layer = make_layer("1", _ACQ_RESTAURANT, feature_count=3)
        area = make_area([layer])

        run([area])

        assert len(area.layers) == 1
        assert len(area.layers[0].layer.geojson.features) == 3

    def test_two_layers_same_acquisition_are_merged(self):
        area = make_area(
            [
                make_layer("1", _ACQ_RESTAURANT, feature_count=3),
                make_layer("2", _ACQ_RESTAURANT, feature_count=2),
            ]
        )

        run([area])

        assert len(area.layers) == 1
        assert len(area.layers[0].layer.geojson.features) == 5

    def test_different_acquisitions_stay_separate(self):
        area = make_area(
            [
                make_layer("1", _ACQ_RESTAURANT, feature_count=2),
                make_layer("2", _ACQ_CAFE, feature_count=2),
            ]
        )

        run([area])

        assert len(area.layers) == 2

    def test_merged_layer_keeps_first_id(self):
        area = make_area(
            [
                make_layer("1", _ACQ_RESTAURANT, feature_count=1),
                make_layer("2", _ACQ_RESTAURANT, feature_count=1),
            ]
        )

        run([area])

        assert area.layers[0].layer.id == "1"

    def test_merged_layer_url_derived_from_id(self):
        area = make_area(
            [
                make_layer("1", _ACQ_RESTAURANT, feature_count=1),
                make_layer("2", _ACQ_RESTAURANT, feature_count=1),
            ]
        )

        run([area])

        geo_layer = area.layers[0]
        assert geo_layer.layer.url == f"./layers/{geo_layer.layer.id}.geojson"

    def test_layer_without_acquisition_not_affected(self):
        poi = Layer(id="__poi__", name="POI", type="__poi__", visible=True, style={})
        area = make_area([make_layer("1", _ACQ_RESTAURANT, feature_count=2), poi])

        run([area])

        layer_ids = [gl.layer.id for gl in area.layers]
        assert "__poi__" in layer_ids
