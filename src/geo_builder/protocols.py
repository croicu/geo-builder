from __future__ import annotations

from dataclasses import dataclass, field

JsonObject = dict[str, object]

JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass
class AreaStyle:
    values: list[str]
    name: str | None = None
    color: str | None = None
    scale: float | None = None
    surface: bool = False
    type: str = "heatmap"


@dataclass
class PoiStyle:
    name: str = "POI"
    type: str = "circle"
    color: str | None = None
    opacity: float = 0.7
    radius: float | None = None
    surface: bool = False


@dataclass
class UserStyle:
    name: str = "My Trip"
    color: str = "#9E9E9E"
    opacity: float = 0.9
    radius: float = 10.0
    min_zoom: float = 14.0


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
    aggregation: dict = field(default_factory=dict)
    deduping: dict = field(default_factory=dict)
    layers: list[Layer] = field(default_factory=list)


@dataclass
class Layer:
    id: str
    name: str
    type: str
    visible: bool
    style: dict[str, JsonValue]
    url: str | None = None
    acquisition: dict | None = None
    geojson: GeoJson | None = None


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
