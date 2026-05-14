from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict
from pathlib import Path

from .errors import CatalogError
from .protocols import Area, Catalog, Feature, GeoJson, Geometry, JsonValue, Layer, Manifest


def read_json(path: Path) -> JsonValue:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, payload: JsonValue) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def child_path(parent: Path, relative_path: str) -> Path:
    return parent / relative_path.removeprefix("./")


def load_catalog(output_dir: str | Path) -> Catalog:
    output_dir = Path(output_dir)
    payload = read_json(output_dir / "catalog.json")

    if not isinstance(payload, dict):
        raise CatalogError("catalog.json must contain an object.")

    areas_payload = payload.get("areas", [])

    if not isinstance(areas_payload, list):
        raise CatalogError("catalog.json areas must be an array.")

    areas = [load_area(output_dir, area_payload) for area_payload in areas_payload if isinstance(area_payload, dict)]

    return Catalog(
        version=str(payload["version"]),
        createdAt=str(payload["createdAt"]),
        areas=areas,
    )


def save_catalog(catalog: Catalog, output_dir: str | Path) -> None:
    output_dir = Path(output_dir)
    payload = asdict(catalog)

    for area_payload in payload["areas"]:
        del area_payload["manifest"]

    _clean_dir(output_dir)
    save_json(output_dir / "catalog.json", payload)

    for area in catalog.areas:
        save_area(area, output_dir)


def load_area(output_dir: Path, payload: dict[str, JsonValue]) -> Area:
    manifest_path = child_path(output_dir, str(payload["manifestUrl"]))
    manifest_payload = read_json(manifest_path)

    if not isinstance(manifest_payload, dict):
        raise CatalogError(f"{manifest_path} must contain an object.")

    manifest = load_manifest(manifest_path.parent, manifest_payload)

    center = payload["center"]
    if not isinstance(center, list):
        raise CatalogError("area center must be an array.")

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


def save_area(area: Area, output_dir: Path) -> None:
    manifest_path = child_path(output_dir, area.manifestUrl)
    payload = asdict(area.manifest)

    for layer_payload in payload["layers"]:
        del layer_payload["geojson"]

    save_json(manifest_path, payload)

    for layer in area.manifest.layers:
        save_layer(layer, manifest_path.parent)


def load_manifest(manifest_dir: Path, payload: dict[str, JsonValue]) -> Manifest:
    layers_payload = payload.get("layers", [])

    if not isinstance(layers_payload, list):
        raise CatalogError("manifest layers must be an array.")

    layers = [load_layer(manifest_dir, layer_payload) for layer_payload in layers_payload if isinstance(layer_payload, dict)]

    return Manifest(
        version=int(payload["version"]),
        layers=layers,
    )


def load_layer(manifest_dir: Path, payload: dict[str, JsonValue]) -> Layer:
    geojson_path = child_path(manifest_dir, str(payload["url"]))
    geojson_payload = read_json(geojson_path)

    if not isinstance(geojson_payload, dict):
        raise CatalogError(f"{geojson_path} must contain an object.")

    style = payload.get("style", {})
    if not isinstance(style, dict):
        raise CatalogError("layer style must be an object.")

    return Layer(
        id=str(payload["id"]),
        name=str(payload["name"]),
        type=str(payload["type"]),
        url=str(payload["url"]),
        visible=bool(payload["visible"]),
        style=style,
        mergeKey=str(payload["mergeKey"]),
        geojson=load_geojson(geojson_payload),
    )


def save_layer(layer: Layer, manifest_dir: Path) -> None:
    save_json(child_path(manifest_dir, layer.url), asdict(layer.geojson))


def load_geojson(payload: dict[str, JsonValue]) -> GeoJson:
    features_payload = payload.get("features", [])

    if not isinstance(features_payload, list):
        raise CatalogError("GeoJSON features must be an array.")

    features = [load_feature(feature_payload) for feature_payload in features_payload if isinstance(feature_payload, dict)]

    return GeoJson(
        type=str(payload["type"]),
        features=features,
    )


def load_feature(payload: dict[str, JsonValue]) -> Feature:
    properties = payload.get("properties", {})
    geometry_payload = payload["geometry"]

    if not isinstance(properties, dict):
        raise CatalogError("feature properties must be an object.")

    if not isinstance(geometry_payload, dict):
        raise CatalogError("feature geometry must be an object.")

    return Feature(
        type=str(payload["type"]),
        properties=properties,
        geometry=load_geometry(geometry_payload),
    )


def load_geometry(payload: dict[str, JsonValue]) -> Geometry:
    coordinates = payload["coordinates"]

    if not isinstance(coordinates, list):
        raise CatalogError("geometry coordinates must be an array.")

    return Geometry(
        type=str(payload["type"]),
        coordinates=[float(coordinates[0]), float(coordinates[1])],
    )


def _clean_dir(path: str | Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
    os.makedirs(path, exist_ok=True)
