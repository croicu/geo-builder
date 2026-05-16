from __future__ import annotations

import math
import re
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

    def register_handlers(self, gateway) -> None:
        from .api import GET_AREA_BBOX_ID, GetAreaBboxInput, GetAreaBboxOutput
        gateway.define_method(GET_AREA_BBOX_ID, GetAreaBboxInput, GetAreaBboxOutput)
        gateway.register(GET_AREA_BBOX_ID, self._get_area_bbox)

    def _get_area_bbox(self, data) -> object:
        from .api import ERR_AREA_NOT_FOUND, OK, GetAreaBboxOutput
        area = next((a for a in self.areas if a.id == data.areaId), None)
        if area is None:
            return GetAreaBboxOutput(error=ERR_AREA_NOT_FOUND, errorDescription=f"Area '{data.areaId}' not found")
        return GetAreaBboxOutput(error=OK, bbox=area.bbox())


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

    def bbox(self) -> list[float]:
        lat, lon = self.center
        lat_delta = self.radiusMeters / 111_320.0
        lon_delta = self.radiusMeters / (111_320.0 * math.cos(math.radians(lat)))
        return [lon - lon_delta, lat - lat_delta, lon + lon_delta, lat + lat_delta]


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

    @staticmethod
    def id_from_merge_key(merge_key: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", merge_key.lower()).strip("_")


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
