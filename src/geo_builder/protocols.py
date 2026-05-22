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
class Acquisition:
    provider: str
    filters: dict[str, AreaStyle] = field(default_factory=dict)


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
class PipelineStep:
    type: str
    provider: str | None = None
    filters: dict[str, AreaStyle] | None = None


@dataclass
class Manifest:
    version: int
    tasks: list[PipelineStep] = field(default_factory=list)
    layers: list[Layer] = field(default_factory=list)


@dataclass
class Layer:
    id: str
    name: str
    type: str
    visible: bool
    style: dict[str, JsonValue]
    mergeKey: str
    url: str | None = None
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
