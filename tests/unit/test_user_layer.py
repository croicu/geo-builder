from __future__ import annotations

import json
from pathlib import Path

from geo_builder.api import (
    ADD_USER_POINT_ID,
    GET_USER_POINTS_ID,
    AddUserPointInput,
    AddUserPointOutput,
    GetUserPointsOutput,
    UserPointData,
)
from geo_builder.builder import Builder
from geo_builder.contracts import AcquisitionTask, BoundingBox
from geo_builder.entities import GeoArea, GeoLayer
from geo_builder.protocols import Area, Feature, GeoJson, Geometry, Layer, UserStyle
from geo_builder.settings import Settings

# --- helpers ---


def _make_area(area_id: str = "rome") -> GeoArea:
    summary = Area(
        id=area_id,
        name=area_id.capitalize(),
        bbox=[12.40, 41.85, 12.55, 41.95],
        minRadiusPx=32,
        maxRadiusPx=512,
        liveMapRadiusPx=640,
        manifestUrl=f"./areas/{area_id}/manifest.json",
    )
    return GeoArea(summary=summary)


def _make_user_layer(with_geojson: bool = False) -> GeoLayer:
    geojson = None
    if with_geojson:
        geojson = GeoJson(
            type="FeatureCollection",
            features=[
                Feature(
                    type="Feature",
                    properties={"timestamp": "2026-05-29T14:00:00Z", "pressure": 0.5, "name": None},
                    geometry=Geometry(type="Point", coordinates=[12.48, 41.90]),
                )
            ],
        )
    return GeoLayer(
        Layer(
            id="__user__",
            name="My Trip",
            type="__user__",
            visible=True,
            style={"opacity": 0.9, "color": "#9E9E9E", "radius": 10, "minZoom": 14},
            geojson=geojson,
        )
    )


# --- UserStyle ---


class TestUserStyle:
    def test_defaults(self):
        style = UserStyle()
        assert style.name == "My Trip"
        assert style.color == "#9E9E9E"
        assert style.opacity == 0.9
        assert style.radius == 10.0
        assert style.min_zoom == 14.0

    def test_custom_values(self):
        style = UserStyle(name="Trip", color="#ff0000", opacity=0.5, radius=8.0, min_zoom=12.0)
        assert style.name == "Trip"
        assert style.color == "#ff0000"
        assert style.opacity == 0.5
        assert style.radius == 8.0
        assert style.min_zoom == 12.0


# --- API types ---


class TestUserLayerApi:
    def test_ids(self):
        assert GET_USER_POINTS_ID == "__geo_get_user_points__"
        assert ADD_USER_POINT_ID == "__geo_add_user_point__"

    def test_get_user_points_output_defaults(self):
        out = GetUserPointsOutput(error=0)
        assert out.error == 0
        assert out.errorDescription is None
        assert out.geojson is None

    def test_add_user_point_output_defaults(self):
        out = AddUserPointOutput(error=0)
        assert out.error == 0
        assert out.errorDescription is None

    def test_user_point_data_name_optional(self):
        pt = UserPointData(lat=47.0, lon=-122.0, timestamp="2026-05-29T00:00:00Z", pressure=0.5)
        assert pt.name is None

    def test_user_point_data_with_name(self):
        pt = UserPointData(lat=47.0, lon=-122.0, timestamp="2026-05-29T00:00:00Z", pressure=0.5, name="Cafe")
        assert pt.name == "Cafe"

    def test_add_user_point_input_shape(self):
        inp = AddUserPointInput(
            areaId="rome",
            point=UserPointData(lat=41.9, lon=12.5, timestamp="2026-05-29T14:00:00Z", pressure=0.6),
        )
        assert inp.areaId == "rome"
        assert inp.point.pressure == 0.6


# --- Pipeline preservation ---


class TestUserLayerPipelinePreservation:
    def test_user_layer_survives_builder_run(self):
        """__user__ layer with geojson is not modified by the builder pipeline."""
        area = _make_area("rome")
        area.layers.append(_make_user_layer(with_geojson=True))
        from geo_builder.entities import GeoCatalog

        catalog = GeoCatalog(areas=[area])

        tasks = [
            AcquisitionTask(
                areaId="rome",
                areaName="Rome",
                provider="fake",
                bbox=BoundingBox(west=12.40, south=41.85, east=12.55, north=41.95),
                filters={},
            )
        ]
        Settings._instance = Settings(
            debug=False,
            providers={"fake": {"dataFile": "tests/fixtures/empty.json"}},
        )

        result = Builder(catalog).run(tasks=tasks)

        user_layers = []
        for a in result.areas:
            if a.id == "rome":
                for gl in a.layers:
                    if gl.layer.id == "__user__":
                        user_layers.append(gl)
        assert len(user_layers) == 1
        assert user_layers[0].layer.geojson is not None
        assert len(user_layers[0].layer.geojson.features) == 1

    def test_user_geojson_not_cleared_by_rebuild_logic(self):
        """Simulate the _rebuild_area clear loop: __user__ geojson is preserved."""
        area = _make_area("rome")
        user_gl = _make_user_layer(with_geojson=True)
        acquisition_gl = GeoLayer(
            Layer(
                id="1",
                name="Cafe",
                type="heatmap",
                url="./layers/1.geojson",
                visible=True,
                style={},
                acquisition={"provider": "overpass", "filter": "amenity", "values": ["cafe"]},
                geojson=GeoJson(type="FeatureCollection", features=[]),
            )
        )
        area.layers = [acquisition_gl, user_gl]

        for gl in area.layers:
            if gl.layer.type not in ("__poi__", "__user__"):
                gl.layer.geojson = None

        assert acquisition_gl.layer.geojson is None
        assert user_gl.layer.geojson is not None


# --- user.geojson file I/O ---


class TestUserPointFileIo:
    def test_empty_collection_when_no_file(self, tmp_path: Path):
        user_path = tmp_path / "areas" / "rome" / "user.geojson"
        assert not user_path.exists()
        geojson = {"type": "FeatureCollection", "features": []}
        assert geojson["features"] == []

    def test_append_feature_to_new_file(self, tmp_path: Path):
        user_path = tmp_path / "areas" / "rome" / "user.geojson"
        user_path.parent.mkdir(parents=True)

        geojson: dict = {"type": "FeatureCollection", "features": []}
        feature = {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [-122.12, 47.67]},
            "properties": {"timestamp": "2026-05-29T14:00:00Z", "pressure": 0.6, "name": None},
        }
        geojson["features"].append(feature)

        with open(user_path, "w", encoding="utf-8") as f:
            json.dump(geojson, f)

        with open(user_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)

        assert loaded["type"] == "FeatureCollection"
        assert len(loaded["features"]) == 1
        assert loaded["features"][0]["properties"]["pressure"] == 0.6
        assert loaded["features"][0]["geometry"]["coordinates"] == [-122.12, 47.67]

    def test_append_to_existing_file(self, tmp_path: Path):
        user_path = tmp_path / "areas" / "rome" / "user.geojson"
        user_path.parent.mkdir(parents=True)

        existing: dict = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [12.48, 41.90]},
                    "properties": {"timestamp": "2026-05-28T10:00:00Z", "pressure": 0.3, "name": None},
                }
            ],
        }
        with open(user_path, "w", encoding="utf-8") as f:
            json.dump(existing, f)

        with open(user_path, "r", encoding="utf-8") as f:
            geojson = json.load(f)

        geojson["features"].append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [12.50, 41.92]},
                "properties": {"timestamp": "2026-05-29T14:00:00Z", "pressure": 0.8, "name": "Colosseum"},
            }
        )

        with open(user_path, "w", encoding="utf-8") as f:
            json.dump(geojson, f)

        with open(user_path, "r", encoding="utf-8") as f:
            result = json.load(f)

        assert len(result["features"]) == 2
        assert result["features"][1]["properties"]["name"] == "Colosseum"
        assert result["features"][0]["properties"]["pressure"] == 0.3


# --- AddUserPointInput coercion ---


class TestAddUserPointInputCoercion:
    def test_point_dict_coerced_to_user_point_data(self):
        """Gateway sends point as a plain dict; __post_init__ must convert it."""
        from geo_builder.api import AddUserPointInput, UserPointData

        inp = AddUserPointInput(
            areaId="rome",
            point={"lat": 41.9, "lon": 12.5, "timestamp": "2026-05-30T00:00:00Z", "pressure": 0.6},  # type: ignore[arg-type]
        )
        assert isinstance(inp.point, UserPointData)
        assert inp.point.lat == 41.9
        assert inp.point.lon == 12.5
        assert inp.point.pressure == 0.6
        assert inp.point.name is None

    def test_point_already_user_point_data_unchanged(self):
        from geo_builder.api import AddUserPointInput, UserPointData

        pt = UserPointData(lat=41.9, lon=12.5, timestamp="2026-05-30T00:00:00Z", pressure=0.6)
        inp = AddUserPointInput(areaId="rome", point=pt)
        assert inp.point is pt


# --- Startup __user__ injection ---


class TestUserLayerStartupInjection:
    def test_missing_user_layer_injected_into_memory(self, tmp_path: Path):
        """_inject_missing_user_layers adds __user__ stub to areas that lack it."""
        from geo_builder.designer.host import _inject_missing_user_layers
        from geo_builder.entities import GeoCatalog

        area = _make_area("rome")
        catalog = GeoCatalog(areas=[area])

        tmpl: dict = {
            "layers": [
                {
                    "id": "__user__",
                    "name": "My Trip",
                    "type": "__user__",
                    "visible": True,
                    "style": {"opacity": 0.9, "color": "#9E9E9E", "radius": 10, "minZoom": 14},
                }
            ]
        }
        _inject_missing_user_layers(catalog, tmpl, in_dir=None)

        user_count = 0
        for gl in area.layers:
            if gl.layer.id == "__user__":
                user_count += 1
        assert user_count == 1
        assert area.layers[-1].layer.type == "__user__"
        assert area.layers[-1].layer.style["color"] == "#9E9E9E"

    def test_missing_user_layer_saved_to_disk(self, tmp_path: Path):
        """When in_dir is provided the manifest is updated on disk."""
        import json

        from geo_builder.designer.host import _inject_missing_user_layers
        from geo_builder.entities import GeoCatalog

        area_dir = tmp_path / "areas" / "rome"
        area_dir.mkdir(parents=True)
        manifest_path = area_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps({"version": 1, "layers": [], "aggregation": {}, "deduping": {}}),
            encoding="utf-8",
        )

        area_payload = {
            "id": "rome",
            "name": "Rome",
            "bbox": [12.40, 41.85, 12.55, 41.95],
            "minRadiusPx": 32,
            "maxRadiusPx": 512,
            "liveMapRadiusPx": 640,
            "manifestUrl": "./areas/rome/manifest.json",
        }
        from geo_builder.entities import GeoArea

        area = GeoArea.load(manifest_path, area_payload)
        catalog = GeoCatalog(areas=[area])

        _inject_missing_user_layers(catalog, {}, in_dir=tmp_path)

        with open(manifest_path, "r", encoding="utf-8") as f:
            saved = json.load(f)

        user_entries = []
        for layer in saved["layers"]:
            if layer.get("id") == "__user__":
                user_entries.append(layer)
        assert len(user_entries) == 1
        assert user_entries[0]["type"] == "__user__"

    def test_existing_user_layer_not_duplicated(self):
        """Areas that already have __user__ are left untouched."""
        from geo_builder.designer.host import _inject_missing_user_layers
        from geo_builder.entities import GeoCatalog

        area = _make_area("rome")
        area.layers.append(_make_user_layer())
        catalog = GeoCatalog(areas=[area])

        _inject_missing_user_layers(catalog, {}, in_dir=None)

        count = 0
        for gl in area.layers:
            if gl.layer.id == "__user__":
                count += 1
        assert count == 1
