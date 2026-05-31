from geo_builder.entities import GeoArea, GeoCatalog, GeoLayer
from geo_builder.protocols import Area, Feature, GeoJson, Geometry, Layer
from geo_builder.workers.poi import PoiWorker
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


def make_layer(layer_id: str, features: list[Feature]) -> Layer:
    return Layer(
        id=layer_id,
        name="Test Layer",
        type="heatmap",
        visible=True,
        style={},
        url=f"./layers/{layer_id}.geojson",
        geojson=GeoJson(type="FeatureCollection", features=features),
    )


def make_feature(has_details: bool = False) -> Feature:
    properties: dict = {"weight": 1.0}
    if has_details:
        properties["hasDetails"] = True
        properties["name"] = "Bar Gaetano"
    return Feature(
        type="Feature",
        properties=properties,
        geometry=Geometry(type="Point", coordinates=[14.27, 40.85]),
    )


def make_executor(areas: list[GeoArea]) -> StubExecutor:
    catalog = GeoCatalog(areas=areas)
    area = areas[0] if areas else make_area([])
    return StubExecutor(area=area, catalog=catalog)


def run(areas: list[GeoArea]) -> None:
    executor = make_executor(areas)
    PoiWorker(task=None).execute(executor)


class TestPoiWorker:
    def test_returns_non_fatal(self):
        executor = make_executor([make_area([])])
        result = PoiWorker(task=None).execute(executor)
        assert not result.fatal

    def test_stub_not_visible_when_no_details(self):
        layer = make_layer("1", [make_feature(has_details=False)])
        area = make_area([layer])
        run([area])
        poi_layers = [gl.layer for gl in area.layers if gl.layer.id == "__poi__"]
        assert len(poi_layers) == 1
        assert poi_layers[0].visible is False

    def test_stub_visible_when_details_present(self):
        layer = make_layer("1", [make_feature(has_details=True)])
        area = make_area([layer])
        run([area])
        poi_layers = [gl.layer for gl in area.layers if gl.layer.id == "__poi__"]
        assert len(poi_layers) == 1
        assert poi_layers[0].visible is True

    def test_stub_has_correct_type(self):
        layer = make_layer("1", [make_feature(has_details=True)])
        area = make_area([layer])
        run([area])
        poi_layers = [gl.layer for gl in area.layers if gl.layer.id == "__poi__"]
        assert len(poi_layers) == 1
        assert poi_layers[0].type == "__poi__"

    def test_stub_has_no_geojson(self):
        layer = make_layer("1", [make_feature(has_details=True)])
        area = make_area([layer])
        run([area])
        poi_layers = [gl.layer for gl in area.layers if gl.layer.id == "__poi__"]
        assert poi_layers[0].geojson is None
        assert poi_layers[0].url is None

    def test_existing_stub_not_visible_when_no_details(self):
        stub = Layer(
            id="__poi__",
            name="POI Details",
            type="__poi__",
            visible=True,
            style={"opacity": 0.7},
        )
        layer = make_layer("1", [make_feature(has_details=False)])
        area = make_area([layer, stub])
        run([area])
        poi_layers = [gl.layer for gl in area.layers if gl.layer.id == "__poi__"]
        assert len(poi_layers) == 1
        assert poi_layers[0].visible is False

    def test_stub_not_duplicated_on_repeated_run(self):
        layer = make_layer("1", [make_feature(has_details=True)])
        area = make_area([layer])
        run([area])
        run([area])
        poi_layers = [gl for gl in area.layers if gl.layer.id == "__poi__"]
        assert len(poi_layers) == 1

    def test_details_in_any_layer_triggers_visible_stub(self):
        layer_a = make_layer("1", [make_feature(has_details=False)])
        layer_b = make_layer("2", [make_feature(has_details=True)])
        area = make_area([layer_a, layer_b])
        run([area])
        poi_layers = [gl.layer for gl in area.layers if gl.layer.id == "__poi__"]
        assert len(poi_layers) == 1
        assert poi_layers[0].visible is True

    def test_existing_stub_style_preserved_on_rebuild(self):
        existing_stub = Layer(
            id="__poi__",
            name="POI",
            type="__poi__",
            visible=True,
            style={"opacity": 0.5, "color": "#aabbcc"},
        )
        layer = make_layer("1", [make_feature(has_details=True)])
        area = make_area([layer, existing_stub])
        run([area])
        poi_layers = [gl.layer for gl in area.layers if gl.layer.id == "__poi__"]
        assert len(poi_layers) == 1
        assert poi_layers[0].style == {"opacity": 0.5, "color": "#aabbcc"}

    def test_no_catalog_returns_non_fatal(self):
        area = make_area([])
        executor = StubExecutor(area=area, catalog=None)
        result = PoiWorker(task=None).execute(executor)
        assert not result.fatal
