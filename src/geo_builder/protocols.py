from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

JsonObject = dict[str, object]

JsonValue = (
    str
    | int
    | float
    | bool
    | None
    | list["JsonValue"]
    | dict[str, "JsonValue"]
)


def read_json(path: Path) -> JsonValue:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, payload: JsonValue) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def child_path(parent: Path, relative_path: str) -> Path:
    return parent / relative_path.removeprefix("./")


@dataclass
class Result:
    catalog: Catalog

    def save(self, output_dir: str | Path) -> None:
        self.catalog.save(Path(output_dir))


@dataclass
class Catalog:
    version: int = "1.0"
    createdAt: str = str(datetime.now(timezone.utc))
    areas: list[Area] = field(default_factory=list)

    @staticmethod
    def load(output_dir: str | Path) -> Catalog | None:

        output_dir = Path(output_dir)
        payload = read_json(output_dir / "catalog.json")

        if not isinstance(payload, dict):
            raise ValueError("catalog.json must contain an object.")

        areas_payload = payload.get("areas", [])

        if not isinstance(areas_payload, list):
            raise ValueError("catalog.json areas must be an array.")

        areas = [
            Area.load(output_dir, area_payload)
            for area_payload in areas_payload
            if isinstance(area_payload, dict)
        ]

        return Catalog(
            version=int(payload["version"]),
            createdAt=str(payload["createdAt"]),
            areas=areas,
        )

    def save(self, output_dir: Path) -> None:
        payload = asdict(self)

        for area_payload in payload["areas"]:
            del area_payload["manifest"]

        Catalog._clean_dir(output_dir)
        save_json(output_dir / "catalog.json", payload)

        for area in self.areas:
            area.save(output_dir)

    @staticmethod
    def _clean_dir(path: str):
        shutil.rmtree(path, ignore_errors=True)
        os.makedirs(path, exist_ok=True)


@dataclass
class Area:
    id: str
    name: str
    center: list[float]
    radiusMeters: int
    minRadiusPx: int
    maxRadiusPx: int
    liveMapRadiusPx: int
    manifestUrl: str
    manifest: Manifest

    @staticmethod
    def load(output_dir: Path, payload: dict[str, JsonValue]) -> Area:
        manifest_path = child_path(output_dir, str(payload["manifestUrl"]))
        manifest_payload = read_json(manifest_path)

        if not isinstance(manifest_payload, dict):
            raise ValueError(f"{manifest_path} must contain an object.")

        manifest = Manifest.load(manifest_path.parent, manifest_payload)

        center = payload["center"]
        if not isinstance(center, list):
            raise ValueError("area center must be an array.")

        return Area(
            id=str(payload["id"]),
            name=str(payload["name"]),
            center=[float(center[0]), float(center[1])],
            radiusMeters=int(payload["radiusMeters"]),
            minRadiusPx=int(payload["minRadiusPx"]),
            maxRadiusPx=int(payload["maxRadiusPx"]),
            liveMapRadiusPx=int(payload["liveMapRadiusPx"]),
            manifestUrl=str(payload["manifestUrl"]),
            manifest=manifest,
        )

    def save(self, output_dir: Path) -> None:
        manifest_path = child_path(output_dir, self.manifestUrl)

        payload = asdict(self.manifest)

        for layer_payload in payload["layers"]:
            del layer_payload["geojson"]

        save_json(manifest_path, payload)

        for layer in self.manifest.layers:
            layer.save(manifest_path.parent)


@dataclass
class Manifest:
    version: int
    layers: list[Layer]

    @staticmethod
    def load(manifest_dir: Path, payload: dict[str, JsonValue]) -> Manifest:
        layers_payload = payload.get("layers", [])

        if not isinstance(layers_payload, list):
            raise ValueError("manifest layers must be an array.")

        layers = [
            Layer.load(manifest_dir, layer_payload)
            for layer_payload in layers_payload
            if isinstance(layer_payload, dict)
        ]

        return Manifest(
            version=int(payload["version"]),
            layers=layers,
        )

    def save(self, output_dir: Path) -> None:
        payload = asdict(self)

        for layer_payload in payload["layers"]:
            del layer_payload["geojson"]

        # Manifest path is owned by the parent Area, so Manifest itself
        # does not know where to save. The parent writes the manifest file.
        # This class exists only as a data container.


@dataclass
class Layer:
    id: str
    name: str
    type: str
    url: str
    visible: bool
    style: dict[str, JsonValue]
    mergeKey: str
    geojson: GeoJson

    @staticmethod
    def load(manifest_dir: Path, payload: dict[str, JsonValue]) -> Layer:
        geojson_path = child_path(manifest_dir, str(payload["url"]))
        geojson_payload = read_json(geojson_path)

        if not isinstance(geojson_payload, dict):
            raise ValueError(f"{geojson_path} must contain an object.")

        style = payload.get("style", {})
        if not isinstance(style, dict):
            raise ValueError("layer style must be an object.")

        return Layer(
            id=str(payload["id"]),
            name=str(payload["name"]),
            type=str(payload["type"]),
            url=str(payload["url"]),
            visible=bool(payload["visible"]),
            style=style,
            mergeKey=str(payload["mergeKey"]),
            geojson=GeoJson.load(geojson_payload),
        )

    def save(self, manifest_dir: Path) -> None:
        save_json(child_path(manifest_dir, self.url), asdict(self.geojson))


@dataclass
class GeoJson:
    type: str
    features: list[Feature]

    @staticmethod
    def load(payload: dict[str, JsonValue]) -> GeoJson:
        features_payload = payload.get("features", [])

        if not isinstance(features_payload, list):
            raise ValueError("GeoJSON features must be an array.")

        features = [
            Feature.load(feature_payload)
            for feature_payload in features_payload
            if isinstance(feature_payload, dict)
        ]

        return GeoJson(
            type=str(payload["type"]),
            features=features,
        )


@dataclass
class Feature:
    type: str
    properties: dict[str, JsonValue]
    geometry: Geometry

    @staticmethod
    def load(payload: dict[str, JsonValue]) -> Feature:
        properties = payload.get("properties", {})
        geometry_payload = payload["geometry"]

        if not isinstance(properties, dict):
            raise ValueError("feature properties must be an object.")

        if not isinstance(geometry_payload, dict):
            raise ValueError("feature geometry must be an object.")

        return Feature(
            type=str(payload["type"]),
            properties=properties,
            geometry=Geometry.load(geometry_payload),
        )


@dataclass
class Geometry:
    type: str
    coordinates: list[float]

    @staticmethod
    def load(payload: dict[str, JsonValue]) -> Geometry:
        coordinates = payload["coordinates"]

        if not isinstance(coordinates, list):
            raise ValueError("geometry coordinates must be an array.")

        return Geometry(
            type=str(payload["type"]),
            coordinates=[float(coordinates[0]), float(coordinates[1])],
        )
    
