from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

JsonObject = dict[str, object]

JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass
class Result:
    catalog: Catalog


@dataclass
class Catalog:
    version: str = "1.0"
    createdAt: str = field(default_factory=lambda: str(datetime.now(timezone.utc)))
    areas: list[Area] = field(default_factory=list)


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


@dataclass
class Manifest:
    version: int
    layers: list[Layer]


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


@dataclass
class GeoJson:
    type: str
    features: list[Feature]


@dataclass
class Feature:
    type: str
    properties: dict[str, JsonValue]
    geometry: Geometry


@dataclass
class Geometry:
    type: str
    coordinates: list[float]
