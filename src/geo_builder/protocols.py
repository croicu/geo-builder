from __future__ import annotations

from dataclasses import dataclass

JsonObject = dict[str, object]

JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass
class Area:
    id: str
    name: str
    bbox: list[float]  # [west, south, east, north]
    minRadiusPx: int
    maxRadiusPx: int
    liveMapRadiusPx: int
    manifestUrl: str


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
