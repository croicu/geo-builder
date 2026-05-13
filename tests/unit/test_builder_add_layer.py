from geo_builder.builder import Builder
from geo_builder.protocols import Area, Feature, GeoJson, Geometry, Layer, Manifest


def make_area() -> Area:
    return Area(
        id="napoli",
        name="Napoli",
        center=[40.85, 14.27],
        radiusMeters=5000,
        minRadiusPx=32,
        maxRadiusPx=512,
        liveMapRadiusPx=640,
        manifestUrl="./areas/napoli/manifest.json",
        manifest=Manifest(version=1, layers=[]),
    )


def make_layer(merge_key: str, feature_count: int) -> Layer:
    features = [
        Feature(
            type="Feature",
            properties={"id": i},
            geometry=Geometry(type="Point", coordinates=[14.27, 40.85]),
        )
        for i in range(feature_count)
    ]
    return Layer(
        id="overpass",
        name="Overpass",
        type="heatmap",
        url="./layers/overpass.geojson",
        visible=True,
        style={},
        mergeKey=merge_key,
        geojson=GeoJson(type="FeatureCollection", features=features),
    )


class TestBuilderAddLayer:
    def test_first_layer_is_appended(self):
        builder = Builder()
        area = make_area()
        layer = make_layer("overpass:amenity=restaurant", 3)

        builder.add_layer(area, layer)

        assert len(area.manifest.layers) == 1

    def test_same_merge_key_merges_features(self):
        builder = Builder()
        area = make_area()

        builder.add_layer(area, make_layer("overpass:amenity=restaurant", 3))
        builder.add_layer(area, make_layer("overpass:amenity=restaurant", 2))

        assert len(area.manifest.layers) == 1
        assert len(area.manifest.layers[0].geojson.features) == 5

    def test_different_merge_key_appends_new_layer(self):
        builder = Builder()
        area = make_area()

        builder.add_layer(area, make_layer("overpass:amenity=restaurant", 3))
        builder.add_layer(area, make_layer("overpass:amenity=cafe", 2))

        assert len(area.manifest.layers) == 2
