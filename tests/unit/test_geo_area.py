from __future__ import annotations

import json
from pathlib import Path

import pytest

from geo_builder.entities import GeoArea, GeoLayer
from geo_builder.errors import CatalogError
from geo_builder.protocols import Area, AreaStyle, Feature, GeoJson, Geometry, Layer


def _make_area_payload(manifest_url: str = "./areas/rome/manifest.json") -> dict:
    return {
        "id": "rome",
        "name": "Rome",
        "bbox": [12.40, 41.85, 12.55, 41.95],
        "minRadiusPx": 32,
        "maxRadiusPx": 512,
        "liveMapRadiusPx": 640,
        "manifestUrl": manifest_url,
    }


def _make_layer() -> Layer:
    return Layer(
        id="overpass_amenity_cafe",
        name="Cafe",
        type="heatmap",
        url="./layers/overpass_amenity_cafe.geojson",
        visible=True,
        style={"color": "#ff0000"},
        mergeKey="overpass:amenity=cafe",
        geojson=GeoJson(
            type="FeatureCollection",
            features=[
                Feature(
                    type="Feature",
                    properties={"weight": 1.0},
                    geometry=Geometry(type="Point", coordinates=[12.48, 41.90]),
                )
            ],
        ),
    )


def _make_geo_area() -> GeoArea:
    summary = Area(
        id="rome",
        name="Rome",
        bbox=[12.40, 41.85, 12.55, 41.95],
        minRadiusPx=32,
        maxRadiusPx=512,
        liveMapRadiusPx=640,
        manifestUrl="./areas/rome/manifest.json",
    )
    return GeoArea(summary=summary, layers=[GeoLayer(_make_layer())])


def _manifest_path(tmp_path: Path) -> Path:
    """Absolute path where save() will write the manifest given the test area's manifestUrl."""
    return tmp_path / "areas" / "rome" / "manifest.json"


def _write_area_to_disk(tmp_path: Path, area: GeoArea) -> Path:
    """Save manifest.json and layer geojson under tmp_path; return manifest path."""
    area.save(tmp_path)
    return _manifest_path(tmp_path)


class TestGeoAreaLoad:
    def test_loads_summary_fields(self, tmp_path):
        manifest_path = _write_area_to_disk(tmp_path, _make_geo_area())

        loaded = GeoArea.load(manifest_path, _make_area_payload())

        assert loaded.id == "rome"
        assert loaded.name == "Rome"
        assert loaded.bbox == pytest.approx([12.40, 41.85, 12.55, 41.95])
        assert loaded.minRadiusPx == 32
        assert loaded.maxRadiusPx == 512
        assert loaded.liveMapRadiusPx == 640

    def test_loads_layers(self, tmp_path):
        manifest_path = _write_area_to_disk(tmp_path, _make_geo_area())

        loaded = GeoArea.load(manifest_path, _make_area_payload())

        assert len(loaded.layers) == 1
        assert loaded.layers[0].layer.id == "overpass_amenity_cafe"

    def test_loads_layer_geojson(self, tmp_path):
        manifest_path = _write_area_to_disk(tmp_path, _make_geo_area())

        loaded = GeoArea.load(manifest_path, _make_area_payload())

        assert loaded.layers[0].layer.geojson is not None
        assert len(loaded.layers[0].layer.geojson.features) == 1

    def test_loads_layer_coordinates(self, tmp_path):
        manifest_path = _write_area_to_disk(tmp_path, _make_geo_area())

        loaded = GeoArea.load(manifest_path, _make_area_payload())
        coords = loaded.layers[0].layer.geojson.features[0].geometry.coordinates

        assert coords == pytest.approx([12.48, 41.90])

    def test_loads_pipeline_steps(self, tmp_path):
        area = _make_geo_area()
        area.acquisition = None
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "tasks": [
                        {
                            "type": "acquisition",
                            "provider": "overpass",
                            "filters": {
                                "amenity": {
                                    "values": ["cafe"],
                                    "name": "Cafes",
                                    "color": None,
                                    "scale": None,
                                    "surface": False,
                                    "type": "heatmap",
                                }
                            },
                        },
                        {"type": "aggregation"},
                        {"type": "deduping"},
                    ],
                    "layers": [],
                }
            )
        )

        loaded = GeoArea.load(manifest_path, _make_area_payload())

        assert loaded.detail is not None
        assert len(loaded.detail.tasks) == 3
        assert loaded.detail.tasks[0].type == "acquisition"
        assert loaded.detail.tasks[0].provider == "overpass"

    def test_missing_manifest_raises(self, tmp_path):
        with pytest.raises(CatalogError):
            GeoArea.load(tmp_path / "missing.json", _make_area_payload())

    def test_invalid_bbox_raises(self, tmp_path):
        manifest_path = _write_area_to_disk(tmp_path, _make_geo_area())
        bad_payload = _make_area_payload()
        bad_payload["bbox"] = [12.40]

        with pytest.raises(CatalogError, match="bbox"):
            GeoArea.load(manifest_path, bad_payload)

    def test_stub_layer_without_url_loaded(self, tmp_path):
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "tasks": [],
                    "layers": [
                        {
                            "id": "poi",
                            "name": "POI",
                            "type": "poi",
                            "visible": True,
                            "style": {},
                            "mergeKey": "poi",
                        }
                    ],
                }
            )
        )

        loaded = GeoArea.load(manifest_path, _make_area_payload())

        assert len(loaded.layers) == 1
        assert loaded.layers[0].layer.url is None
        assert loaded.layers[0].layer.geojson is None


class TestGeoAreaSave:
    def test_manifest_json_written(self, tmp_path):
        manifest_path = _write_area_to_disk(tmp_path, _make_geo_area())

        assert manifest_path.exists()

    def test_layer_geojson_written(self, tmp_path):
        manifest_path = _write_area_to_disk(tmp_path, _make_geo_area())

        assert (manifest_path.parent / "layers" / "overpass_amenity_cafe.geojson").exists()

    def test_manifest_excludes_geojson(self, tmp_path):
        manifest_path = _write_area_to_disk(tmp_path, _make_geo_area())

        payload = json.loads(manifest_path.read_text())

        assert "geojson" not in payload["layers"][0]

    def test_stub_layer_not_saved_as_geojson(self, tmp_path):
        summary = Area(
            id="rome",
            name="Rome",
            bbox=[12.40, 41.85, 12.55, 41.95],
            minRadiusPx=32,
            maxRadiusPx=512,
            liveMapRadiusPx=640,
            manifestUrl="./areas/rome/manifest.json",
        )
        stub = Layer(
            id="poi",
            name="POI",
            type="poi",
            visible=True,
            style={},
            mergeKey="poi",
        )
        area = GeoArea(summary=summary, layers=[GeoLayer(stub)])

        area.save(tmp_path)

        assert not (tmp_path / "layers").exists()

    def test_round_trip_layer_style(self, tmp_path):
        manifest_path = _write_area_to_disk(tmp_path, _make_geo_area())

        loaded = GeoArea.load(manifest_path, _make_area_payload())

        assert loaded.layers[0].layer.style == {"color": "#ff0000"}


class TestGeoAreaToManifestDict:
    def test_contains_version(self):
        area = _make_geo_area()
        result = area.to_manifest_dict()

        assert result["version"] == 1

    def test_contains_tasks_list(self):
        area = _make_geo_area()
        result = area.to_manifest_dict()

        assert "tasks" in result
        assert isinstance(result["tasks"], list)

    def test_contains_layers_list(self):
        area = _make_geo_area()
        result = area.to_manifest_dict()

        assert "layers" in result
        assert isinstance(result["layers"], list)

    def test_layer_excludes_geojson(self):
        area = _make_geo_area()
        result = area.to_manifest_dict()

        assert "geojson" not in result["layers"][0]

    def test_acquisition_task_serialized(self):
        from geo_builder.protocols import Acquisition

        area = _make_geo_area()
        area.acquisition = Acquisition(
            provider="overpass",
            filters={"amenity": AreaStyle(values=["cafe"], name="Cafes")},
        )

        result = area.to_manifest_dict()
        tasks = result["tasks"]

        assert any(t["type"] == "acquisition" for t in tasks)
        acq = next(t for t in tasks if t["type"] == "acquisition")
        assert acq["provider"] == "overpass"
        assert "amenity" in acq["filters"]


class TestGeoAreaApplyManifest:
    def _save_and_load(self, tmp_path: Path, area: GeoArea) -> tuple[GeoArea, Path]:
        manifest_path = _write_area_to_disk(tmp_path, area)
        loaded = GeoArea.load(manifest_path, _make_area_payload())
        return loaded, tmp_path

    def test_replaces_layers(self, tmp_path):
        area, out_dir = self._save_and_load(tmp_path, _make_geo_area())

        new_manifest = {
            "version": 1,
            "tasks": [],
            "layers": [
                {
                    "id": "poi",
                    "name": "POI",
                    "type": "poi",
                    "visible": True,
                    "style": {},
                    "mergeKey": "poi",
                }
            ],
        }
        area.apply_manifest(new_manifest, out_dir)

        assert len(area.layers) == 1
        assert area.layers[0].layer.id == "poi"

    def test_manifest_written_to_disk(self, tmp_path):
        area, out_dir = self._save_and_load(tmp_path, _make_geo_area())
        new_manifest = {"version": 2, "tasks": [], "layers": []}

        area.apply_manifest(new_manifest, out_dir)

        payload = json.loads(_manifest_path(tmp_path).read_text())
        assert payload["version"] == 2

    def test_self_not_mutated_on_missing_geojson(self, tmp_path):
        area, out_dir = self._save_and_load(tmp_path, _make_geo_area())
        original_layers = list(area.layers)

        bad_manifest = {
            "version": 1,
            "tasks": [],
            "layers": [
                {
                    "id": "overpass_amenity_restaurant",
                    "name": "Restaurant",
                    "type": "heatmap",
                    "url": "./layers/overpass_amenity_restaurant.geojson",
                    "visible": True,
                    "style": {},
                    "mergeKey": "overpass:amenity=restaurant",
                }
            ],
        }

        with pytest.raises(CatalogError):
            area.apply_manifest(bad_manifest, out_dir)

        assert len(area.layers) == len(original_layers)

    def test_replaces_pipeline_steps(self, tmp_path):
        area, out_dir = self._save_and_load(tmp_path, _make_geo_area())

        new_manifest = {
            "version": 1,
            "tasks": [
                {
                    "type": "acquisition",
                    "provider": "overpass",
                    "filters": {
                        "amenity": {
                            "values": ["bar"],
                            "name": None,
                            "color": None,
                            "scale": None,
                            "surface": False,
                            "type": "heatmap",
                        }
                    },
                }
            ],
            "layers": [],
        }

        area.apply_manifest(new_manifest, out_dir)

        assert area.detail is not None
        assert area.detail.tasks[0].type == "acquisition"
        assert area.detail.tasks[0].filters["amenity"].values == ["bar"]

    def test_non_dict_manifest_raises(self, tmp_path):
        area, out_dir = self._save_and_load(tmp_path, _make_geo_area())

        with pytest.raises(CatalogError):
            area.apply_manifest("not a dict", out_dir)  # type: ignore[arg-type]
