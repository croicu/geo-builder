from __future__ import annotations

import csv
import json
import os
import shutil
from pathlib import Path
from urllib.parse import urlparse

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
_DEFAULT_CATALOG_URL = "./catalog.json"
_DEFAULT_CATALOG_URL_DEBUG = "./catalog.debug.json"


def child_path(parent: Path, relative_path: str) -> Path:
    parsed = urlparse(relative_path)
    if parsed.scheme:
        path = parsed.path.lstrip("/")
    else:
        path = relative_path.removeprefix("./")
    return parent / path


def _default_catalog_url(debug: bool) -> str:
    return _DEFAULT_CATALOG_URL_DEBUG if debug else _DEFAULT_CATALOG_URL


def _resolve_catalog_url(directory: Path, debug: bool) -> str:
    head_name = _CATALOG_HEAD_DEBUG if debug else _CATALOG_HEAD
    head_path = directory / head_name
    if not head_path.exists():
        return _default_catalog_url(debug)
    payload = read_json(head_path)
    if not isinstance(payload, dict):
        raise CatalogError(f"{head_name} must contain an object.")
    url = str(payload.get("catalogUrl", ""))
    if not url:
        raise CatalogError(f"{head_name} must contain a catalogUrl.")
    return url


def load_catalog(input_dir: str | Path, debug: bool = False) -> GeoCatalog:
    input_dir = Path(input_dir)

    catalog_url = _resolve_catalog_url(input_dir, debug)

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


def save_catalog(
    geo_catalog: GeoCatalog,
    output_dir: str | Path,
    debug: bool = False,
    in_dir: str | Path | None = None,
) -> None:
    from dataclasses import asdict

    output_dir = Path(output_dir)
    source_dir = Path(in_dir) if in_dir is not None else None
    catalog_url = _resolve_catalog_url(source_dir, debug) if source_dir is not None else _default_catalog_url(debug)

    areas_payload = []
    for geo_area in geo_catalog.areas:
        areas_payload.append(asdict(geo_area.summary))

    catalog_payload = {
        "version": geo_catalog.version,
        "createdAt": geo_catalog.created_at,
        "areas": areas_payload,
    }

    _clean_dir(output_dir)
    head_payload = {"version": 1, "catalogUrl": catalog_url}
    save_json(output_dir / _CATALOG_HEAD, head_payload)
    save_json(output_dir / _CATALOG_HEAD_DEBUG, head_payload)
    catalog_path = child_path(output_dir, catalog_url)
    save_json(catalog_path, catalog_payload)

    catalog_base = catalog_path.parent
    for geo_area in geo_catalog.areas:
        geo_area.save(catalog_base)
        save_area_csv(geo_area, catalog_base)


def save_area_to_catalog(geo_area: GeoArea, output_dir: str | Path, debug: bool = False) -> None:
    """Write one area's manifest, geojson, and CSV into a catalog directory without touching other areas."""
    output_dir = Path(output_dir)
    catalog_url = _resolve_catalog_url(output_dir, debug)
    catalog_base = child_path(output_dir, catalog_url).parent
    geo_area.save(catalog_base)
    save_area_csv(geo_area, catalog_base)


def save_catalog_meta(geo_catalog: GeoCatalog, output_dir: str | Path, debug: bool = False) -> None:
    """Write head + catalog.json only; does not touch area directories."""
    from dataclasses import asdict

    output_dir = Path(output_dir)
    catalog_url = _resolve_catalog_url(output_dir, debug)

    areas_payload = []
    for geo_area in geo_catalog.areas:
        areas_payload.append(asdict(geo_area.summary))

    catalog_payload = {
        "version": geo_catalog.version,
        "createdAt": geo_catalog.created_at,
        "areas": areas_payload,
    }

    head_payload = {"version": 1, "catalogUrl": catalog_url}
    save_json(output_dir / _CATALOG_HEAD, head_payload)
    save_json(output_dir / _CATALOG_HEAD_DEBUG, head_payload)
    catalog_path = child_path(output_dir, catalog_url)
    save_json(catalog_path, catalog_payload)


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
