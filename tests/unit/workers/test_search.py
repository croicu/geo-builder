from geo_builder.contracts import SearchTask
from geo_builder.entities import GeoArea, GeoCatalog, GeoLayer
from geo_builder.protocols import Area, Layer, SearchStyle
from geo_builder.workers.search import SearchWorker
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


def make_executor(areas: list[GeoArea]) -> StubExecutor:
    catalog = GeoCatalog(areas=areas)
    area = areas[0] if areas else make_area([])
    return StubExecutor(area=area, catalog=catalog)


def search_layers(area: GeoArea) -> list[Layer]:
    result = []
    for geo_layer in area.layers:
        if geo_layer.layer.id == "__search__":
            result.append(geo_layer.layer)
    return result


def run(areas: list[GeoArea], task=None) -> None:
    executor = make_executor(areas)
    SearchWorker(task=task).execute(executor)


class TestSearchWorker:
    def test_returns_non_fatal(self):
        executor = make_executor([make_area([])])
        result = SearchWorker(task=None).execute(executor)
        assert not result.fatal

    def test_no_catalog_returns_non_fatal(self):
        area = make_area([])
        executor = StubExecutor(area=area, catalog=None)
        result = SearchWorker(task=None).execute(executor)
        assert not result.fatal

    def test_stub_added_when_missing(self):
        area = make_area([])
        run([area])
        layers = search_layers(area)
        assert len(layers) == 1
        assert layers[0].type == "__search__"
        assert layers[0].visible is False
        assert layers[0].url is None
        assert layers[0].geojson is None

    def test_default_style_matches_browser_fallback(self):
        area = make_area([])
        run([area])
        layer = search_layers(area)[0]
        assert layer.name == "Search Results"
        assert layer.style == {"opacity": 0.3, "color": "#00007f"}

    def test_style_from_task_applied(self):
        area = make_area([])
        style = SearchStyle(name="Find Stuff", color="#123456", opacity=0.5)
        run([area], task=SearchTask(style=style))
        layer = search_layers(area)[0]
        assert layer.name == "Find Stuff"
        assert layer.style == {"opacity": 0.5, "color": "#123456"}

    def test_stub_not_duplicated_on_repeated_run(self):
        area = make_area([])
        run([area])
        run([area])
        assert len(search_layers(area)) == 1

    def test_existing_stub_left_untouched(self):
        existing = Layer(
            id="__search__",
            name="Custom Name",
            type="__search__",
            visible=True,
            style={"opacity": 0.9, "color": "#ffffff"},
        )
        area = make_area([existing])
        run([area])
        layers = search_layers(area)
        assert len(layers) == 1
        assert layers[0].name == "Custom Name"
        assert layers[0].visible is True
        assert layers[0].style == {"opacity": 0.9, "color": "#ffffff"}
