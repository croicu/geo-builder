from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from ..errors import CatalogError
from ..protocols import (
    Acquisition,
    Area,
    AreaStyle,
    Feature,
    GeoJson,
    Geometry,
    Layer,
    Manifest,
    PipelineStep,
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
    return parent / relative_path.removeprefix("./")


# --- GeoJSON loaders ---


def _load_geometry(payload: dict) -> Geometry:
    coordinates = payload["coordinates"]
    if not isinstance(coordinates, list):
        raise CatalogError("geometry coordinates must be an array.")
    return Geometry(
        type=str(payload["type"]),
        coordinates=[float(coordinates[0]), float(coordinates[1])],
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


def _load_stub_layer(payload: dict) -> Layer:
    style = payload.get("style", {})
    if not isinstance(style, dict):
        style = {}
    return Layer(
        id=str(payload["id"]),
        name=str(payload["name"]),
        type=str(payload["type"]),
        visible=bool(payload["visible"]),
        style=style,
        mergeKey=str(payload["mergeKey"]),
    )


def _load_layer(geojson_path: Path, payload: dict) -> Layer:
    geojson_payload = _read_json(geojson_path)
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
        geojson=_load_geojson(geojson_payload),
    )


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
            geo_layers.append(GeoLayer(_load_stub_layer(layer_payload)))
        else:
            geojson_path = _child_path(manifest_dir, str(url))
            geo_layers.append(GeoLayer(_load_layer(geojson_path, layer_payload)))
    return geo_layers


def _load_pipeline_steps(data: object) -> list[PipelineStep]:
    steps: list[PipelineStep] = []
    if not isinstance(data, list):
        return steps
    for item in data:
        if not isinstance(item, dict):
            continue
        step_type = str(item.get("type", ""))
        if step_type == "acquisition":
            filters: dict[str, AreaStyle] = {}
            for key, style_data in dict(item.get("filters", {})).items():
                if not isinstance(style_data, dict):
                    continue
                values: list[str] = []
                for v in style_data.get("values", []):
                    values.append(str(v))
                filters[str(key)] = AreaStyle(
                    values=values,
                    name=str(style_data["name"]) if style_data.get("name") is not None else None,
                    color=str(style_data["color"]) if style_data.get("color") is not None else None,
                    scale=float(style_data["scale"]) if style_data.get("scale") is not None else None,
                    surface=bool(style_data.get("surface", False)),
                    type=str(style_data.get("type", "heatmap")),
                )
            steps.append(
                PipelineStep(
                    type="acquisition",
                    provider=str(item.get("provider", "")),
                    filters=filters,
                )
            )
        elif step_type in ("aggregation", "deduping", "poi"):
            steps.append(PipelineStep(type=step_type))
    return steps


def _build_manifest_dict(detail: Manifest | None, layers: list[GeoLayer]) -> dict:
    manifest_version = detail.version if detail is not None else 1

    tasks_payload: list[dict] = []
    if detail is not None:
        for step in detail.tasks:
            if step.type == "acquisition":
                step_data: dict = {"type": "acquisition"}
                if step.provider is not None:
                    step_data["provider"] = step.provider
                if step.filters is not None:
                    filters_payload: dict = {}
                    for k, v in step.filters.items():
                        filters_payload[k] = asdict(v)
                    step_data["filters"] = filters_payload
                tasks_payload.append(step_data)
            else:
                tasks_payload.append({"type": step.type})

    layers_payload: list[dict] = []
    for geo_layer in layers:
        layer_data = asdict(geo_layer.layer)
        del layer_data["geojson"]
        layers_payload.append(layer_data)

    return {"version": manifest_version, "tasks": tasks_payload, "layers": layers_payload}


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
        self._on_changed: Callable[[GeoArea], None] | None = None

    def subscribe_changed(self, fn: Callable[[GeoArea], None]) -> None:
        self._on_changed = fn

    @classmethod
    def load(cls, manifest_path: Path, area_payload: dict) -> GeoArea:
        manifest_payload = _read_json(manifest_path)
        if not isinstance(manifest_payload, dict):
            raise CatalogError(f"{manifest_path} must contain an object.")

        geo_layers = _load_manifest_layers(manifest_path, manifest_payload)
        pipeline_steps = _load_pipeline_steps(manifest_payload.get("tasks", []))
        manifest_version = int(manifest_payload.get("version", 1))

        bbox = area_payload.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            raise CatalogError("area bbox must be an array of four numbers.")

        summary = Area(
            id=str(area_payload["id"]),
            name=str(area_payload["name"]),
            bbox=[float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])],
            minRadiusPx=int(area_payload["minRadiusPx"]),
            maxRadiusPx=int(area_payload["maxRadiusPx"]),
            liveMapRadiusPx=int(area_payload["liveMapRadiusPx"]),
            manifestUrl=str(area_payload["manifestUrl"]),
        )

        detail = Manifest(version=manifest_version, tasks=pipeline_steps)
        return cls(summary=summary, layers=geo_layers, detail=detail)

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
        return _build_manifest_dict(self.detail, self.layers)

    def apply_manifest(self, payload: dict, output_dir: Path) -> None:
        """Replace this area's layers and pipeline steps from a manifest-shaped dict.

        Saves to disk before updating self — if the save fails self is unchanged.
        Raises CatalogError on invalid payload or missing geojson files, OSError on I/O failure.
        """
        if not isinstance(payload, dict):
            raise CatalogError("manifest must be an object.")

        manifest_path = _child_path(output_dir, self.manifestUrl)

        new_layers = _load_manifest_layers(manifest_path, payload)
        new_steps = _load_pipeline_steps(payload.get("tasks", []))
        new_detail = Manifest(version=int(payload.get("version", 1)), tasks=new_steps)

        _save_json(manifest_path, _build_manifest_dict(new_detail, new_layers))

        self.layers = new_layers
        self.detail = new_detail

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
    def acquisition(self) -> Acquisition | None:
        if self.detail is None:
            return None
        for step in self.detail.tasks:
            if step.type == "acquisition" and step.provider is not None and step.filters is not None:
                return Acquisition(provider=step.provider, filters=step.filters)
        return None

    @acquisition.setter
    def acquisition(self, value: Acquisition | None) -> None:
        if self.detail is None:
            self.detail = Manifest(version=1)
        other_steps = [s for s in self.detail.tasks if s.type != "acquisition"]
        if value is not None:
            self.detail.tasks = [PipelineStep(type="acquisition", provider=value.provider, filters=value.filters)] + other_steps
        else:
            self.detail.tasks = other_steps
