from __future__ import annotations

import csv
import json
import os
import shutil
from dataclasses import asdict
from pathlib import Path

from .entities import GeoArea, GeoCatalog, GeoLayer
from .errors import CatalogError
from .protocols import Area, Feature, GeoJson, Geometry, JsonValue, Layer, Manifest


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


def load_catalog(input_dir: str | Path, debug: bool = False) -> GeoCatalog:
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

    return GeoCatalog(
        version=str(payload["version"]),
        created_at=str(payload["createdAt"]),
        areas=areas,
        is_default=False,
    )


def save_catalog(geo_catalog: GeoCatalog, output_dir: str | Path, debug: bool = False) -> None:
    output_dir = Path(output_dir)
    catalog_dir = "debug" if debug else "release"
    head_filename = _CATALOG_HEAD_DEBUG if debug else _CATALOG_HEAD
    catalog_url = f"./{catalog_dir}/{_CATALOG_FILENAME}"

    areas_payload = []
    for geo_area in geo_catalog.areas:
        areas_payload.append(asdict(geo_area.summary))

    catalog_payload = {
        "version": geo_catalog.version,
        "createdAt": geo_catalog.created_at,
        "areas": areas_payload,
    }

    _clean_dir(output_dir)
    save_json(output_dir / head_filename, {"version": 1, "catalogUrl": catalog_url})
    save_json(output_dir / catalog_dir / _CATALOG_FILENAME, catalog_payload)

    catalog_base = output_dir / catalog_dir
    for geo_area in geo_catalog.areas:
        save_area(geo_area, catalog_base)
        save_area_csv(geo_area, catalog_base)


def save_catalog_meta(geo_catalog: GeoCatalog, output_dir: str | Path, debug: bool = False) -> None:
    """Write head + catalog.json only; does not touch area directories."""
    output_dir = Path(output_dir)
    catalog_dir = "debug" if debug else "release"
    head_filename = _CATALOG_HEAD_DEBUG if debug else _CATALOG_HEAD
    catalog_url = f"./{catalog_dir}/{_CATALOG_FILENAME}"

    areas_payload = []
    for geo_area in geo_catalog.areas:
        areas_payload.append(asdict(geo_area.summary))

    catalog_payload = {
        "version": geo_catalog.version,
        "createdAt": geo_catalog.created_at,
        "areas": areas_payload,
    }

    save_json(output_dir / head_filename, {"version": 1, "catalogUrl": catalog_url})
    save_json(output_dir / catalog_dir / _CATALOG_FILENAME, catalog_payload)


def load_area(manifest_path: Path, payload: dict[str, JsonValue]) -> GeoArea:
    manifest_payload = read_json(manifest_path)

    if not isinstance(manifest_payload, dict):
        raise CatalogError(f"{manifest_path} must contain an object.")

    geo_layers = _load_manifest_layers(manifest_path, manifest_payload)
    manifest_version = int(manifest_payload.get("version", 1))

    bbox = payload.get("bbox")
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise CatalogError("area bbox must be an array of four numbers.")

    summary = Area(
        id=str(payload["id"]),
        name=str(payload["name"]),
        bbox=[float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])],
        minRadiusPx=int(payload["minRadiusPx"]),
        maxRadiusPx=int(payload["maxRadiusPx"]),
        liveMapRadiusPx=int(payload["liveMapRadiusPx"]),
        manifestUrl=str(payload["manifestUrl"]),
    )

    detail = Manifest(version=manifest_version, layers=[])
    return GeoArea(summary=summary, layers=geo_layers, detail=detail)


def save_area(geo_area: GeoArea, output_dir: Path) -> None:
    manifest_path = child_path(output_dir, geo_area.manifestUrl)
    manifest_version = geo_area.detail.version if geo_area.detail is not None else 1

    layers_payload = []
    for geo_layer in geo_area.layers:
        layer_data = asdict(geo_layer.layer)
        del layer_data["geojson"]
        layers_payload.append(layer_data)

    save_json(manifest_path, {"version": manifest_version, "layers": layers_payload})

    for geo_layer in geo_area.layers:
        save_layer(geo_layer.layer, manifest_path.parent)


def _load_manifest_layers(manifest_path: Path, payload: dict[str, JsonValue]) -> list[GeoLayer]:
    layers_payload = payload.get("layers", [])

    if not isinstance(layers_payload, list):
        raise CatalogError("manifest layers must be an array.")

    manifest_dir = manifest_path.parent
    geo_layers = []
    for layer_payload in layers_payload:
        if isinstance(layer_payload, dict):
            geojson_path = child_path(manifest_dir, str(layer_payload["url"]))
            geo_layers.append(GeoLayer(load_layer(geojson_path, layer_payload)))

    return geo_layers


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


def save_area_csv(geo_area: GeoArea, output_dir: Path) -> None:
    area_dir = child_path(output_dir, geo_area.manifestUrl).parent
    csv_path = area_dir / f"{geo_area.id}.csv"

    rows: list[tuple[str, object]] = []
    for geo_layer in geo_area.layers:
        for feature in geo_layer.layer.geojson.features:
            rows.append((geo_layer.layer.id, feature))

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
