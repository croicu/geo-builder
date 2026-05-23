from __future__ import annotations

import csv
import json
import os
import shutil
from pathlib import Path

from .entities import GeoArea, GeoCatalog
from .errors import CatalogError
from .protocols import Feature, GeoJson, Geometry, JsonValue


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
            areas.append(GeoArea.load(manifest_path, area_payload))

    return GeoCatalog(
        version=str(payload["version"]),
        created_at=str(payload["createdAt"]),
        areas=areas,
        is_default=False,
    )


def save_catalog(geo_catalog: GeoCatalog, output_dir: str | Path, debug: bool = False) -> None:
    from dataclasses import asdict

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
        geo_area.save(catalog_base)
        save_area_csv(geo_area, catalog_base)


def save_catalog_meta(geo_catalog: GeoCatalog, output_dir: str | Path, debug: bool = False) -> None:
    """Write head + catalog.json only; does not touch area directories."""
    from dataclasses import asdict

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
        if geo_layer.layer.geojson is None:
            continue
        for feature in geo_layer.layer.geojson.features:
            rows.append((geo_layer.layer.id, feature))

    if not rows:
        return

    all_keys: set[str] = set()
    for _, feature in rows:
        for key in feature.properties:
            all_keys.add(key)
    property_keys = sorted(all_keys)
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
