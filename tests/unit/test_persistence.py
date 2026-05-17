import csv
import json
from pathlib import Path

import pytest

from geo_builder.errors import CatalogError
from geo_builder.persistence import (
    child_path,
    load_catalog,
    load_feature,
    load_geojson,
    load_geometry,
    read_json,
    save_area_csv,
    save_catalog,
    save_json,
)
from geo_builder.protocols import Area, Catalog, Feature, GeoJson, Geometry, Layer, Manifest


def make_feature() -> Feature:
    return Feature(
        type="Feature",
        properties={"name": "Trattoria da Mario", "amenity": "restaurant"},
        geometry=Geometry(type="Point", coordinates=[14.27, 40.85]),
    )


def make_layer() -> Layer:
    return Layer(
        id="overpass_amenity_restaurant",
        name="Restaurant",
        type="heatmap",
        url="./layers/overpass_amenity_restaurant.geojson",
        visible=True,
        style={"color": "#00ff00"},
        mergeKey="overpass:amenity=restaurant",
        geojson=GeoJson(type="FeatureCollection", features=[make_feature()]),
    )


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
        manifest=Manifest(version=1, layers=[make_layer()]),
    )


def make_catalog() -> Catalog:
    return Catalog(version="1.0", createdAt="2026-01-01T00:00:00+00:00", areas=[make_area()])


class TestChildPath:
    def test_strips_dot_slash_prefix(self):
        assert child_path(Path("/out"), "./layers/foo.geojson") == Path("/out/layers/foo.geojson")

    def test_no_prefix_unchanged(self):
        assert child_path(Path("/out"), "layers/foo.geojson") == Path("/out/layers/foo.geojson")


class TestReadWriteJson:
    def test_round_trip(self, tmp_path):
        payload = {"key": "value", "numbers": [1, 2, 3]}
        path = tmp_path / "data.json"

        save_json(path, payload)
        loaded = read_json(path)

        assert loaded == payload

    def test_save_json_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "deep" / "nested" / "file.json"

        save_json(path, {"x": 1})

        assert path.exists()

    def test_read_missing_file_raises(self, tmp_path):
        with pytest.raises(CatalogError):
            read_json(tmp_path / "missing.json")


class TestLoadGeometry:
    def test_parses_coordinates(self):
        geometry = load_geometry({"type": "Point", "coordinates": [14.27, 40.85]})

        assert geometry.coordinates == pytest.approx([14.27, 40.85])

    def test_coordinates_cast_to_float(self):
        geometry = load_geometry({"type": "Point", "coordinates": [14, 40]})

        assert isinstance(geometry.coordinates[0], float)

    def test_non_list_coordinates_raises(self):
        with pytest.raises(CatalogError, match="coordinates"):
            load_geometry({"type": "Point", "coordinates": "bad"})


class TestLoadFeature:
    def test_parses_feature(self):
        payload = {
            "type": "Feature",
            "properties": {"name": "Cafe"},
            "geometry": {"type": "Point", "coordinates": [14.27, 40.85]},
        }

        feature = load_feature(payload)

        assert feature.type == "Feature"
        assert feature.properties == {"name": "Cafe"}
        assert feature.geometry.coordinates == pytest.approx([14.27, 40.85])

    def test_non_dict_properties_raises(self):
        with pytest.raises(CatalogError, match="properties"):
            load_feature({
                "type": "Feature",
                "properties": "bad",
                "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
            })

    def test_non_dict_geometry_raises(self):
        with pytest.raises(CatalogError, match="geometry"):
            load_feature({"type": "Feature", "properties": {}, "geometry": "bad"})


class TestLoadGeoJson:
    def test_parses_feature_collection(self):
        payload = {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [14.27, 40.85]}},
            ],
        }

        geojson = load_geojson(payload)

        assert geojson.type == "FeatureCollection"
        assert len(geojson.features) == 1

    def test_empty_features(self):
        geojson = load_geojson({"type": "FeatureCollection", "features": []})

        assert geojson.features == []

    def test_non_list_features_raises(self):
        with pytest.raises(CatalogError, match="features"):
            load_geojson({"type": "FeatureCollection", "features": "bad"})


class TestSaveCatalog:
    def test_catalog_head_json_written(self, tmp_path):
        save_catalog(make_catalog(), tmp_path)

        assert (tmp_path / "catalog.head.json").exists()

    def test_catalog_head_json_points_to_catalog(self, tmp_path):
        save_catalog(make_catalog(), tmp_path)

        payload = json.loads((tmp_path / "catalog.head.json").read_text())

        assert payload["catalogUrl"] == "./catalog.json"

    def test_catalog_json_written(self, tmp_path):
        save_catalog(make_catalog(), tmp_path)

        assert (tmp_path / "catalog.json").exists()

    def test_manifest_json_written(self, tmp_path):
        save_catalog(make_catalog(), tmp_path)

        assert (tmp_path / "areas" / "napoli" / "manifest.json").exists()

    def test_layer_geojson_written(self, tmp_path):
        save_catalog(make_catalog(), tmp_path)

        assert (tmp_path / "areas" / "napoli" / "layers" / "overpass_amenity_restaurant.geojson").exists()

    def test_catalog_json_excludes_manifest(self, tmp_path):
        save_catalog(make_catalog(), tmp_path)

        payload = json.loads((tmp_path / "catalog.json").read_text())

        assert "manifest" not in payload["areas"][0]

    def test_manifest_json_excludes_geojson(self, tmp_path):
        save_catalog(make_catalog(), tmp_path)

        payload = json.loads((tmp_path / "areas" / "napoli" / "manifest.json").read_text())

        assert "geojson" not in payload["layers"][0]

    def test_clean_dir_removes_previous_output(self, tmp_path):
        stale = tmp_path / "stale.txt"
        stale.write_text("old")

        save_catalog(make_catalog(), tmp_path)

        assert not stale.exists()


class TestRoundTrip:
    def test_catalog_fields(self, tmp_path):
        original = make_catalog()

        save_catalog(original, tmp_path)
        loaded = load_catalog(tmp_path)

        assert loaded.version == original.version
        assert loaded.createdAt == original.createdAt

    def test_area_fields(self, tmp_path):
        save_catalog(make_catalog(), tmp_path)
        area = load_catalog(tmp_path).areas[0]

        assert area.id == "napoli"
        assert area.name == "Napoli"
        assert area.center == pytest.approx([40.85, 14.27])
        assert area.radiusMeters == 5000

    def test_layer_fields(self, tmp_path):
        save_catalog(make_catalog(), tmp_path)
        layer = load_catalog(tmp_path).areas[0].manifest.layers[0]

        assert layer.id == "overpass_amenity_restaurant"
        assert layer.mergeKey == "overpass:amenity=restaurant"
        assert layer.style == {"color": "#00ff00"}

    def test_feature_coordinates(self, tmp_path):
        save_catalog(make_catalog(), tmp_path)
        feature = load_catalog(tmp_path).areas[0].manifest.layers[0].geojson.features[0]

        assert feature.geometry.coordinates == pytest.approx([14.27, 40.85])

    def test_feature_properties(self, tmp_path):
        save_catalog(make_catalog(), tmp_path)
        feature = load_catalog(tmp_path).areas[0].manifest.layers[0].geojson.features[0]

        assert feature.properties["name"] == "Trattoria da Mario"
        assert feature.properties["amenity"] == "restaurant"


class TestSaveAreaCsv:
    def _area_dir(self, tmp_path: Path) -> Path:
        return tmp_path / "areas" / "napoli"

    def _save(self, area: Area, tmp_path: Path) -> Path:
        area_dir = self._area_dir(tmp_path)
        area_dir.mkdir(parents=True)
        save_area_csv(area, tmp_path)
        return area_dir / "napoli.csv"

    def _read_csv(self, path: Path) -> list[dict]:
        with open(path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def test_csv_written(self, tmp_path):
        csv_path = self._save(make_area(), tmp_path)

        assert csv_path.exists()

    def test_header_contains_lon_lat_layer_id(self, tmp_path):
        csv_path = self._save(make_area(), tmp_path)
        rows = self._read_csv(csv_path)

        assert "lon" in rows[0]
        assert "lat" in rows[0]
        assert "layer_id" in rows[0]

    def test_feature_coordinates(self, tmp_path):
        csv_path = self._save(make_area(), tmp_path)
        row = self._read_csv(csv_path)[0]

        assert float(row["lon"]) == pytest.approx(14.27)
        assert float(row["lat"]) == pytest.approx(40.85)

    def test_layer_id_column(self, tmp_path):
        csv_path = self._save(make_area(), tmp_path)
        row = self._read_csv(csv_path)[0]

        assert row["layer_id"] == "overpass_amenity_restaurant"

    def test_property_columns(self, tmp_path):
        csv_path = self._save(make_area(), tmp_path)
        row = self._read_csv(csv_path)[0]

        assert row["name"] == "Trattoria da Mario"
        assert row["amenity"] == "restaurant"

    def test_missing_property_is_empty_string(self, tmp_path):
        layer_a = Layer(
            id="a", name="A", type="heatmap", url="./layers/a.geojson",
            visible=True, style={}, mergeKey="k:a",
            geojson=GeoJson(type="FeatureCollection", features=[
                Feature(type="Feature", properties={"name": "X"}, geometry=Geometry(type="Point", coordinates=[14.27, 40.85])),
            ]),
        )
        layer_b = Layer(
            id="b", name="B", type="heatmap", url="./layers/b.geojson",
            visible=True, style={}, mergeKey="k:b",
            geojson=GeoJson(type="FeatureCollection", features=[
                Feature(type="Feature", properties={"amenity": "cafe"}, geometry=Geometry(type="Point", coordinates=[14.28, 40.86])),
            ]),
        )
        area = Area(
            id="napoli", name="Napoli", center=[40.85, 14.27],
            radiusMeters=5000, minRadiusPx=32, maxRadiusPx=512, liveMapRadiusPx=640,
            manifestUrl="./areas/napoli/manifest.json",
            manifest=Manifest(version=1, layers=[layer_a, layer_b]),
        )
        csv_path = self._save(area, tmp_path)
        rows = self._read_csv(csv_path)

        assert rows[0]["amenity"] == ""
        assert rows[1]["name"] == ""

    def test_all_features_from_all_layers(self, tmp_path):
        layer_a = Layer(
            id="a", name="A", type="heatmap", url="./layers/a.geojson",
            visible=True, style={}, mergeKey="k:a",
            geojson=GeoJson(type="FeatureCollection", features=[
                Feature(type="Feature", properties={}, geometry=Geometry(type="Point", coordinates=[14.27, 40.85])),
                Feature(type="Feature", properties={}, geometry=Geometry(type="Point", coordinates=[14.28, 40.86])),
            ]),
        )
        layer_b = Layer(
            id="b", name="B", type="heatmap", url="./layers/b.geojson",
            visible=True, style={}, mergeKey="k:b",
            geojson=GeoJson(type="FeatureCollection", features=[
                Feature(type="Feature", properties={}, geometry=Geometry(type="Point", coordinates=[14.29, 40.87])),
            ]),
        )
        area = Area(
            id="napoli", name="Napoli", center=[40.85, 14.27],
            radiusMeters=5000, minRadiusPx=32, maxRadiusPx=512, liveMapRadiusPx=640,
            manifestUrl="./areas/napoli/manifest.json",
            manifest=Manifest(version=1, layers=[layer_a, layer_b]),
        )
        csv_path = self._save(area, tmp_path)

        assert len(self._read_csv(csv_path)) == 3

    def test_no_features_writes_no_csv(self, tmp_path):
        area = Area(
            id="napoli", name="Napoli", center=[40.85, 14.27],
            radiusMeters=5000, minRadiusPx=32, maxRadiusPx=512, liveMapRadiusPx=640,
            manifestUrl="./areas/napoli/manifest.json",
            manifest=Manifest(version=1, layers=[]),
        )
        csv_path = self._save(area, tmp_path)

        assert not csv_path.exists()

    def test_csv_written_by_save_catalog(self, tmp_path):
        save_catalog(make_catalog(), tmp_path)

        assert (tmp_path / "areas" / "napoli" / "napoli.csv").exists()


class TestLoadCatalogErrors:
    def test_missing_catalog_head_raises(self, tmp_path):
        with pytest.raises(CatalogError):
            load_catalog(tmp_path)

    def test_non_object_catalog_head_raises(self, tmp_path):
        (tmp_path / "catalog.head.json").write_text('"not an object"')

        with pytest.raises(CatalogError, match="object"):
            load_catalog(tmp_path)

    def test_missing_catalog_url_in_head_raises(self, tmp_path):
        (tmp_path / "catalog.head.json").write_text('{"version": 1}')

        with pytest.raises(CatalogError, match="catalogUrl"):
            load_catalog(tmp_path)

    def test_non_object_catalog_raises(self, tmp_path):
        (tmp_path / "catalog.head.json").write_text('{"version": 1, "catalogUrl": "./catalog.json"}')
        (tmp_path / "catalog.json").write_text('["not", "an", "object"]')

        with pytest.raises(CatalogError, match="object"):
            load_catalog(tmp_path)

    def test_non_list_areas_raises(self, tmp_path):
        (tmp_path / "catalog.head.json").write_text('{"version": 1, "catalogUrl": "./catalog.json"}')
        (tmp_path / "catalog.json").write_text('{"version": "1.0", "areas": "bad"}')

        with pytest.raises(CatalogError, match="areas"):
            load_catalog(tmp_path)
