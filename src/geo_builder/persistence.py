from __future__ import annotations

import csv
import json
import os
import shutil
from dataclasses import asdict
from pathlib import Path

from .errors import CatalogError
from .protocols import Area, Catalog, Feature, GeoJson, Geometry, JsonValue, Layer, Manifest


def read_json(path: Path) -> JsonValue:
    if not path.exists():
        raise CatalogError(f"{path} not found.")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, payload: JsonValue) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


_CATALOG_HEAD = "catalog.head.json"
_CATALOG_HEAD_DEBUG = "catalog.head.debug.json"
_CATALOG_FILENAME = "catalog.json"


def child_path(parent: Path, relative_path: str) -> Path:
    return parent / relative_path.removeprefix("./")


def load_catalog(input_dir: str | Path, debug: bool = False) -> Catalog:
    input_dir = Path(input_dir)

    catalog_head_path = _CATALOG_HEAD_DEBUG if debug else _CATALOG_HEAD
    head_payload = read_json(input_dir / catalog_head_path)

    if not isinstance(head_payload, dict):
        raise CatalogError(f"{_CATALOG_HEAD} must contain an object.")

    catalog_url = str(head_payload.get("catalogUrl", ""))
    if not catalog_url:
        raise CatalogError(f"{_CATALOG_HEAD} must contain a catalogUrl.")

    catalog_path = child_path(input_dir, catalog_url)
    payload = read_json(catalog_path)

    if not isinstance(payload, dict):
        raise CatalogError("catalog must contain an object.")

    areas_payload = payload.get("areas", [])

    if not isinstance(areas_payload, list):
        raise CatalogError("catalog areas must be an array.")

    areas = []
    for area_payload in areas_payload:
        if isinstance(area_payload, dict):
            manifest_path = child_path(catalog_path.parent, str(area_payload["manifestUrl"]))
            areas.append(load_area(manifest_path, area_payload))

    return Catalog(
        version=str(payload["version"]),
        createdAt=str(payload["createdAt"]),
        areas=areas,
        is_default=False,
    )


def save_catalog(catalog: Catalog, output_dir: str | Path) -> None:
    output_dir = Path(output_dir)
    payload = asdict(catalog)
    del payload["is_default"]

    for area_payload in payload["areas"]:
        del area_payload["manifest"]

    _clean_dir(output_dir)
    save_json(output_dir / _CATALOG_HEAD, {"version": 1, "catalogUrl": f"./{_CATALOG_FILENAME}"})
    save_json(output_dir / _CATALOG_FILENAME, payload)

    for area in catalog.areas:
        save_area(area, output_dir)
        save_area_csv(area, output_dir)


def load_area(manifest_path: Path, payload: dict[str, JsonValue]) -> Area:
    manifest_payload = read_json(manifest_path)

    if not isinstance(manifest_payload, dict):
        raise CatalogError(f"{manifest_path} must contain an object.")

    manifest = load_manifest(manifest_path, manifest_payload)

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


def load_manifest(manifest_path: Path, payload: dict[str, JsonValue]) -> Manifest:
    layers_payload = payload.get("layers", [])

    if not isinstance(layers_payload, list):
        raise CatalogError("manifest layers must be an array.")

    manifest_dir = manifest_path.parent
    layers = []
    for layer_payload in layers_payload:
        if isinstance(layer_payload, dict):
            geojson_path = child_path(manifest_dir, str(layer_payload["url"]))
            layers.append(load_layer(geojson_path, layer_payload))

    return Manifest(
        version=int(payload["version"]),
        layers=layers,
    )


def load_layer(geojson_path: Path, payload: dict[str, JsonValue]) -> Layer:
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

    features = []
    for feature_payload in features_payload:
        if isinstance(feature_payload, dict):
            features.append(load_feature(feature_payload))

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


def save_area_csv(area: Area, output_dir: Path) -> None:
    area_dir = child_path(output_dir, area.manifestUrl).parent
    csv_path = area_dir / f"{area.id}.csv"

    rows: list[tuple[str, object]] = []
    for layer in area.manifest.layers:
        for feature in layer.geojson.features:
            rows.append((layer.id, feature))

    if not rows:
        return

    property_keys = sorted({key for _, feature in rows for key in feature.properties})
    fieldnames = ["lon", "lat", "layer_id"] + property_keys

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for layer_id, feature in rows:
            row: dict[str, object] = {
                "lon": feature.geometry.coordinates[0],
                "lat": feature.geometry.coordinates[1],
                "layer_id": layer_id,
            }
            for key in property_keys:
                row[key] = feature.properties.get(key, "")
            writer.writerow(row)


def _clean_dir(path: str | Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
    os.makedirs(path, exist_ok=True)
