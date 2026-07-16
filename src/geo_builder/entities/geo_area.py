from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict
from enum import Enum
from pathlib import Path
from urllib.parse import urlparse

from ..errors import CatalogError
from ..protocols import (
    Area,
    Feature,
    GeoJson,
    Geometry,
    Layer,
    Manifest,
)
from .geo_layer import GeoLayer

# --- File I/O helpers (private to this module) ---


def _read_json(path: Path) -> object:
    if not path.exists():
        raise CatalogError(f"{path} not found.")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def _child_path(parent: Path, relative_path: str) -> Path:
    parsed = urlparse(relative_path)
    if parsed.scheme:
        path = parsed.path.lstrip("/")
    else:
        path = relative_path.removeprefix("./")
    return parent / path


# --- GeoJSON loaders ---


def _normalize_coordinates(coordinates: object) -> object:
    """Recursively cast every leaf number in a GeoJSON coordinates array to float.

    Handles Point ([lon, lat]), Polygon (list of rings), and MultiPolygon (list of Polygons)
    shapes uniformly, since they only differ in nesting depth.
    """
    if not isinstance(coordinates, list):
        raise CatalogError("geometry coordinates must be an array.")
    if len(coordinates) == 0:
        return []
    if isinstance(coordinates[0], list):
        normalized = []
        for item in coordinates:
            normalized.append(_normalize_coordinates(item))
        return normalized
    return [float(coordinates[0]), float(coordinates[1])]


def _load_geometry(payload: dict) -> Geometry:
    coordinates = payload["coordinates"]
    return Geometry(
        type=str(payload["type"]),
        coordinates=_normalize_coordinates(coordinates),
    )


def _load_feature(payload: dict) -> Feature:
    properties = payload.get("properties", {})
    geometry_payload = payload["geometry"]
    if not isinstance(properties, dict):
        raise CatalogError("feature properties must be an object.")
    if not isinstance(geometry_payload, dict):
        raise CatalogError("feature geometry must be an object.")
    return Feature(
        type=str(payload["type"]),
        properties=properties,
        geometry=_load_geometry(geometry_payload),
    )


def _load_geojson(payload: dict) -> GeoJson:
    features_payload = payload.get("features", [])
    if not isinstance(features_payload, list):
        raise CatalogError("GeoJSON features must be an array.")
    features: list[Feature] = []
    for feature_payload in features_payload:
        if isinstance(feature_payload, dict):
            features.append(_load_feature(feature_payload))
    return GeoJson(type=str(payload["type"]), features=features)


# --- Layer loaders ---


def _load_layer_geometry(payload: dict) -> dict | None:
    geometry = payload.get("geometry")
    if geometry is not None and not isinstance(geometry, dict):
        geometry = None
    return geometry


def _load_stub_layer(payload: dict) -> Layer:
    style = payload.get("style", {})
    if not isinstance(style, dict):
        style = {}
    acquisition = payload.get("acquisition")
    if acquisition is not None and not isinstance(acquisition, dict):
        acquisition = None
    return Layer(
        id=str(payload["id"]),
        name=str(payload["name"]),
        type=str(payload["type"]),
        visible=bool(payload["visible"]),
        style=style,
        acquisition=acquisition,
        geometry=_load_layer_geometry(payload),
    )


def _load_layer(geojson_path: Path, payload: dict) -> Layer:
    geojson_payload = _read_json(geojson_path)
    if not isinstance(geojson_payload, dict):
        raise CatalogError(f"{geojson_path} must contain an object.")
    style = payload.get("style", {})
    if not isinstance(style, dict):
        raise CatalogError("layer style must be an object.")
    acquisition = payload.get("acquisition")
    if acquisition is not None and not isinstance(acquisition, dict):
        acquisition = None
    return Layer(
        id=str(payload["id"]),
        name=str(payload["name"]),
        type=str(payload["type"]),
        url=str(payload["url"]),
        visible=bool(payload["visible"]),
        style=style,
        acquisition=acquisition,
        geojson=_load_geojson(geojson_payload),
        geometry=_load_layer_geometry(payload),
    )


_KNOWN_MANIFEST_KEYS = {"version", "layers", "aggregation", "deduping"}
_KNOWN_LAYER_KEYS = {"id", "name", "type", "url", "visible", "style", "acquisition", "geojson", "geometry"}


def _load_manifest_layers(manifest_path: Path, payload: dict) -> list[GeoLayer]:
    layers_payload = payload.get("layers", [])
    if not isinstance(layers_payload, list):
        raise CatalogError("manifest layers must be an array.")
    manifest_dir = manifest_path.parent
    geo_layers: list[GeoLayer] = []
    for layer_payload in layers_payload:
        if not isinstance(layer_payload, dict):
            continue
        url = layer_payload.get("url")
        if url is None:
            geo_layers.append(GeoLayer(_load_stub_layer(layer_payload), raw=layer_payload))
        else:
            geojson_path = _child_path(manifest_dir, str(url))
            geo_layers.append(GeoLayer(_load_layer(geojson_path, layer_payload), raw=layer_payload))
    return geo_layers


def _build_manifest_dict(detail: Manifest | None, layers: list[GeoLayer], extras: dict | None = None) -> dict:
    manifest_version = detail.version if detail is not None else 1
    aggregation = detail.aggregation if detail is not None else {}
    deduping = detail.deduping if detail is not None else {}

    layers_payload: list[dict] = []
    for geo_layer in layers:
        layer = geo_layer.layer
        # Start from raw payload so unknown fields are preserved, then overwrite known fields.
        entry: dict = {}
        for k, v in geo_layer.raw.items():
            if k not in _KNOWN_LAYER_KEYS:
                entry[k] = v
        entry["id"] = layer.id
        entry["name"] = layer.name
        entry["type"] = layer.type
        entry["visible"] = layer.visible
        entry["style"] = dict(layer.style)
        if layer.url is not None:
            entry["url"] = layer.url
        if layer.acquisition is not None:
            entry["acquisition"] = layer.acquisition
        if layer.geometry is not None:
            entry["geometry"] = layer.geometry
        layers_payload.append(entry)

    result: dict = {}
    if extras:
        for k, v in extras.items():
            result[k] = v
    result["version"] = manifest_version
    result["layers"] = layers_payload
    result["aggregation"] = aggregation
    result["deduping"] = deduping
    return result


class ManifestChange(Enum):
    """What a manifest edit requires the pipeline to do."""

    NONE = "none"  # only presentational fields changed (style, visibility, name, ...)
    REPROCESS = "reprocess"  # __void__ geometry changed — rerun Agg/Dedup/Poi/Void/Search only
    REACQUIRE = "reacquire"  # a layer's acquisition block changed — full rebuild needed


def _classify_manifest_change(old_layers: list[GeoLayer], new_layers: list[GeoLayer]) -> ManifestChange:
    """Classify what the new layer set requires relative to the old one.

    REACQUIRE takes priority over REPROCESS: layers added/removed or any acquisition block
    changed means a full rebuild is needed regardless of any geometry change elsewhere.
    """
    if len(old_layers) != len(new_layers):
        return ManifestChange.REACQUIRE

    old_by_id: dict[str, GeoLayer] = {}
    for gl in old_layers:
        old_by_id[gl.layer.id] = gl

    reprocess = False
    for gl in new_layers:
        old_gl = old_by_id.get(gl.layer.id)
        if old_gl is None:
            return ManifestChange.REACQUIRE
        if gl.layer.acquisition != old_gl.layer.acquisition:
            return ManifestChange.REACQUIRE
        if gl.layer.type == "__void__" and gl.layer.geometry != old_gl.layer.geometry:
            reprocess = True

    if reprocess:
        return ManifestChange.REPROCESS
    return ManifestChange.NONE


class GeoArea:
    def __init__(
        self,
        summary: Area,
        layers: list[GeoLayer] | None = None,
        detail: Manifest | None = None,
    ) -> None:
        self._summary = summary
        self.layers: list[GeoLayer] = layers if layers is not None else []
        self.detail = detail
        self._manifest_extras: dict = {}
        self._on_changed: Callable[[GeoArea], None] | None = None

    def subscribe_changed(self, fn: Callable[[GeoArea], None]) -> None:
        self._on_changed = fn

    @classmethod
    def load(cls, manifest_path: Path, area_payload: dict) -> GeoArea:
        manifest_payload = _read_json(manifest_path)
        if not isinstance(manifest_payload, dict):
            raise CatalogError(f"{manifest_path} must contain an object.")

        geo_layers = _load_manifest_layers(manifest_path, manifest_payload)
        manifest_version = int(manifest_payload.get("version", 1))

        aggregation = manifest_payload.get("aggregation", {})
        if not isinstance(aggregation, dict):
            aggregation = {}
        deduping = manifest_payload.get("deduping", {})
        if not isinstance(deduping, dict):
            deduping = {}

        bbox = area_payload.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            raise CatalogError("area bbox must be an array of four numbers.")

        group_payload = area_payload.get("group", [])
        if not isinstance(group_payload, list):
            group_payload = []
        group = []
        for group_name in group_payload:
            group.append(str(group_name))

        summary = Area(
            id=str(area_payload["id"]),
            name=str(area_payload["name"]),
            bbox=[float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])],
            minRadiusPx=int(area_payload["minRadiusPx"]),
            maxRadiusPx=int(area_payload["maxRadiusPx"]),
            liveMapRadiusPx=int(area_payload["liveMapRadiusPx"]),
            manifestUrl=str(area_payload["manifestUrl"]),
            group=group,
        )

        detail = Manifest(version=manifest_version, aggregation=aggregation, deduping=deduping)
        area = cls(summary=summary, layers=geo_layers, detail=detail)
        for k, v in manifest_payload.items():
            if k not in _KNOWN_MANIFEST_KEYS:
                area._manifest_extras[k] = v
        return area

    def save(self, output_dir: Path) -> None:
        manifest_path = _child_path(output_dir, self.manifestUrl)
        _save_json(manifest_path, self.to_manifest_dict())
        for geo_layer in self.layers:
            if geo_layer.layer.url is not None and geo_layer.layer.geojson is not None:
                _save_json(
                    _child_path(manifest_path.parent, geo_layer.layer.url),
                    asdict(geo_layer.layer.geojson),
                )

    def to_manifest_dict(self) -> dict:
        return _build_manifest_dict(self.detail, self.layers, self._manifest_extras)

    def apply_manifest(self, payload: dict, output_dir: Path) -> ManifestChange:
        """Replace this area's layers from a manifest-shaped dict.

        Returns REACQUIRE if any layer's acquisition block changed (a full rebuild — re-fetch
        from the provider — is required), REPROCESS if only the __void__ layer's geometry
        changed (Aggregation/Deduping/Poi/Void/Search need to rerun against existing data, no
        provider fetch needed), or NONE if only presentational fields (style, visibility,
        name, …) changed.
        Saves to disk before updating self — if the save fails self is unchanged.
        Raises CatalogError on invalid payload or missing geojson files, OSError on I/O failure.
        """
        if not isinstance(payload, dict):
            raise CatalogError("manifest must be an object.")

        manifest_path = _child_path(output_dir, self.manifestUrl)

        new_layers = _load_manifest_layers(manifest_path, payload)

        aggregation = payload.get("aggregation", {})
        if not isinstance(aggregation, dict):
            aggregation = {}
        deduping = payload.get("deduping", {})
        if not isinstance(deduping, dict):
            deduping = {}
        new_detail = Manifest(version=int(payload.get("version", 1)), aggregation=aggregation, deduping=deduping)

        new_extras: dict = {}
        for k, v in payload.items():
            if k not in _KNOWN_MANIFEST_KEYS:
                new_extras[k] = v

        change = _classify_manifest_change(self.layers, new_layers)

        _save_json(manifest_path, _build_manifest_dict(new_detail, new_layers, new_extras))

        self.layers = new_layers
        self.detail = new_detail
        self._manifest_extras = new_extras

        return change

    @property
    def summary(self) -> Area:  # TODO: protocol exposed — revisit
        return self._summary

    @property
    def id(self) -> str:
        return self._summary.id

    @property
    def name(self) -> str:
        return self._summary.name

    @property
    def bbox(self) -> list[float]:
        return self._summary.bbox

    @bbox.setter
    def bbox(self, value: list[float]) -> None:
        self._summary.bbox = value

    @property
    def manifestUrl(self) -> str:
        return self._summary.manifestUrl

    @property
    def minRadiusPx(self) -> int:
        return self._summary.minRadiusPx

    @property
    def maxRadiusPx(self) -> int:
        return self._summary.maxRadiusPx

    @property
    def liveMapRadiusPx(self) -> int:
        return self._summary.liveMapRadiusPx

    @property
    def group(self) -> list[str]:
        return self._summary.group
