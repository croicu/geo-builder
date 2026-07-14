from geo_builder.contracts import VoidTask
from geo_builder.entities import GeoArea, GeoCatalog, GeoLayer
from geo_builder.protocols import Area, Feature, GeoJson, Geometry, Layer
from geo_builder.workers.void import VoidWorker
from tests.shared.stubs import StubExecutor

# A modest bbox near Naples so grid resolution stays small and tests run fast.
BBOX = [14.20, 40.80, 14.21, 40.81]
CENTER_LON = (BBOX[0] + BBOX[2]) / 2.0
CENTER_LAT = (BBOX[1] + BBOX[3]) / 2.0


def make_area(layers: list[Layer]) -> GeoArea:
    summary = Area(
        id="napoli",
        name="Napoli",
        bbox=list(BBOX),
        minRadiusPx=32,
        maxRadiusPx=512,
        liveMapRadiusPx=640,
        manifestUrl="./areas/napoli/manifest.json",
    )
    geo_layers = []
    for layer in layers:
        geo_layers.append(GeoLayer(layer))
    return GeoArea(summary=summary, layers=geo_layers)


def make_point_feature(lon: float, lat: float, radius_m: float | None = None) -> Feature:
    properties: dict = {"weight": 1.0}
    if radius_m is not None:
        properties["radius_m"] = radius_m
    return Feature(type="Feature", properties=properties, geometry=Geometry(type="Point", coordinates=[lon, lat]))


def make_data_layer(layer_id: str, name: str, features: list[Feature]) -> Layer:
    return Layer(
        id=layer_id,
        name=name,
        type="heatmap",
        visible=True,
        style={},
        url=f"./layers/{layer_id}.geojson",
        acquisition={"provider": "stub", "filters": {"amenity": ["restaurant"]}},
        geojson=GeoJson(type="FeatureCollection", features=features),
    )


def make_executor(areas: list[GeoArea]) -> StubExecutor:
    catalog = GeoCatalog(areas=areas)
    area = areas[0] if areas else make_area([])
    return StubExecutor(area=area, catalog=catalog)


def void_layers(area: GeoArea) -> list[Layer]:
    result = []
    for geo_layer in area.layers:
        if geo_layer.layer.type == "__void__":
            result.append(geo_layer.layer)
    return result


def variant_ids(area: GeoArea) -> list[str]:
    ids = []
    for layer in void_layers(area):
        ids.append(layer.id)
    return sorted(ids)


def bare_void_layer(area: GeoArea) -> Layer | None:
    for layer in void_layers(area):
        if layer.id == "__void__":
            return layer
    return None


def run(areas: list[GeoArea]) -> None:
    executor = make_executor(areas)
    VoidWorker(task=None).execute(executor)


class TestVoidWorker:
    def test_returns_non_fatal(self):
        executor = make_executor([make_area([])])
        result = VoidWorker(task=None).execute(executor)
        assert not result.fatal

    def test_no_catalog_returns_non_fatal(self):
        area = make_area([])
        executor = StubExecutor(area=area, catalog=None)
        result = VoidWorker(task=None).execute(executor)
        assert not result.fatal

    def test_no_source_layers_produces_bare_stub_only(self):
        area = make_area([])
        run([area])
        assert variant_ids(area) == ["__void__"]
        bare = bare_void_layer(area)
        assert bare.url is None
        assert bare.geojson is None

    def test_single_source_layer_produces_bare_and_one_variant(self):
        feature = make_point_feature(CENTER_LON, CENTER_LAT, radius_m=30.0)
        layer = make_data_layer("1", "Restaurants", [feature])
        area = make_area([layer])
        run([area])

        layers = void_layers(area)
        ids = []
        for layer in layers:
            ids.append(layer.id)
        assert sorted(ids) == ["__void__", "__void__1__"]

    def test_bare_variant_has_expected_shape(self):
        feature = make_point_feature(CENTER_LON, CENTER_LAT, radius_m=30.0)
        layer = make_data_layer("1", "Restaurants", [feature])
        area = make_area([layer])
        run([area])

        bare = None
        for candidate in void_layers(area):
            if candidate.id == "__void__":
                bare = candidate
        assert bare is not None
        assert bare.visible is False
        assert bare.url == "./void/void.geojson"
        assert bare.geojson is not None
        assert len(bare.geojson.features) == 1
        assert bare.geojson.features[0].geometry.type == "Polygon"

    def test_per_layer_variant_named_after_source_layer(self):
        feature = make_point_feature(CENTER_LON, CENTER_LAT, radius_m=30.0)
        layer = make_data_layer("1", "Restaurants", [feature])
        area = make_area([layer])
        run([area])

        variant = None
        for candidate in void_layers(area):
            if candidate.id == "__void__1__":
                variant = candidate
        assert variant is not None
        assert variant.name == "No Restaurants"
        assert variant.url == "./void/layer-1.geojson"

    def test_poi_and_user_layers_excluded_from_source(self):
        poi_stub = Layer(id="__poi__", name="POI", type="__poi__", visible=False, style={})
        user_stub = Layer(id="__user__", name="My Trip", type="__user__", visible=True, style={})
        area = make_area([poi_stub, user_stub])
        run([area])
        assert variant_ids(area) == ["__void__"]
        assert bare_void_layer(area).url is None

    def test_layer_with_huge_radius_produces_no_variant(self):
        feature = make_point_feature(CENTER_LON, CENTER_LAT, radius_m=50_000.0)
        layer = make_data_layer("1", "Restaurants", [feature])
        area = make_area([layer])
        run([area])
        assert variant_ids(area) == ["__void__"]
        assert bare_void_layer(area).url is None

    def test_stale_variant_removed_when_source_layer_disappears(self):
        feature = make_point_feature(CENTER_LON, CENTER_LAT, radius_m=30.0)
        layer = make_data_layer("1", "Restaurants", [feature])
        area = make_area([layer])
        run([area])
        assert "__void__1__" in variant_ids(area)

        remaining = []
        for gl in area.layers:
            if gl.layer.type != "heatmap":
                remaining.append(gl)
        area.layers = remaining
        run([area])
        assert variant_ids(area) == ["__void__"]

    def test_regenerated_every_run_not_duplicated(self):
        feature = make_point_feature(CENTER_LON, CENTER_LAT, radius_m=30.0)
        layer = make_data_layer("1", "Restaurants", [feature])
        area = make_area([layer])
        run([area])
        run([area])
        ids = []
        for candidate in void_layers(area):
            ids.append(candidate.id)
        assert sorted(ids) == ["__void__", "__void__1__"]

    def test_default_radius_from_task_applied_when_feature_has_none(self):
        feature = make_point_feature(CENTER_LON, CENTER_LAT)  # no radius_m
        layer = make_data_layer("1", "Restaurants", [feature])
        area = make_area([layer])
        executor = make_executor([area])

        VoidWorker(task=VoidTask(default_radius_m=50_000.0)).execute(executor)
        assert variant_ids(area) == ["__void__"]
        assert bare_void_layer(area).geometry == {"radius": 50_000.0}

    def test_area_geometry_override_takes_priority_over_task_default(self):
        feature = make_point_feature(CENTER_LON, CENTER_LAT)  # no radius_m
        layer = make_data_layer("1", "Restaurants", [feature])
        existing_void = Layer(
            id="__void__",
            name="Mundane",
            type="__void__",
            visible=False,
            style={},
            geometry={"radius": 50_000.0},
        )
        area = make_area([layer, existing_void])
        executor = make_executor([area])

        # Task default (30m) would normally leave plenty of void; the area's own override
        # (50,000m, larger than the bbox) should win instead, suppressing every variant.
        VoidWorker(task=VoidTask(default_radius_m=30.0)).execute(executor)
        assert variant_ids(area) == ["__void__"]
        assert bare_void_layer(area).geometry == {"radius": 50_000.0}

    def test_area_geometry_override_persists_across_reruns(self):
        feature = make_point_feature(CENTER_LON, CENTER_LAT)  # no radius_m
        layer = make_data_layer("1", "Restaurants", [feature])
        existing_void = Layer(
            id="__void__",
            name="Mundane",
            type="__void__",
            visible=False,
            style={},
            geometry={"radius": 50_000.0},
        )
        area = make_area([layer, existing_void])
        run([area])
        run([area])  # second run should still see the override, not the task default

        assert variant_ids(area) == ["__void__"]
        assert bare_void_layer(area).geometry == {"radius": 50_000.0}

    def test_bare_variant_carries_resolved_radius_in_geometry(self):
        feature = make_point_feature(CENTER_LON, CENTER_LAT, radius_m=30.0)
        layer = make_data_layer("1", "Restaurants", [feature])
        area = make_area([layer])
        executor = make_executor([area])

        VoidWorker(task=VoidTask(default_radius_m=42.0)).execute(executor)

        bare = None
        for candidate in void_layers(area):
            if candidate.id == "__void__":
                bare = candidate
        assert bare is not None
        assert bare.geometry == {"radius": 42.0}
