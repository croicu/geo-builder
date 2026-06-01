from __future__ import annotations

from dataclasses import dataclass

# Shared API definitions — mirrored as TypeScript interfaces in api.ts.
# Only plain dataclasses with primitive / list / dict fields belong here.

# --- Error codes ---

OK = 0
ERR_AREA_NOT_FOUND = 1
ERR_TEMPLATE_NOT_FOUND = 2
ERR_MANIFEST_INVALID = 3
ERR_IO = 4


# --- Ready (connection handshake) ---


@dataclass
class ReadyData:
    pass


READY_ID = "__geo_ready__"


# --- GetAreaBbox ---


@dataclass
class GetAreaBboxInput:
    areaId: str


@dataclass
class GetAreaBboxOutput:
    error: int
    errorDescription: str | None = None
    bbox: list[float] | None = None  # [west, south, east, north]


GET_AREA_BBOX_ID = "__geo_get_area_bbox__"


# --- SetAreaBbox ---


@dataclass
class SetAreaBboxInput:
    areaId: str
    bbox: list[float]  # [west, south, east, north]


@dataclass
class SetAreaBboxOutput:
    error: int
    errorDescription: str | None = None


SET_AREA_BBOX_ID = "__geo_set_area_bbox__"


# --- AddArea ---


@dataclass
class AddAreaInput:
    areaName: str
    bbox: list[float]  # [west, south, east, north]
    template: str = "acquisition"


@dataclass
class AreaSummary:
    id: str
    name: str
    bbox: list[float]  # [west, south, east, north]
    minRadiusPx: int
    maxRadiusPx: int
    liveMapRadiusPx: int
    manifestUrl: str


@dataclass
class AddAreaOutput:
    error: int
    errorDescription: str | None = None
    area: AreaSummary | None = None


ADD_AREA_ID = "__geo_add_area__"


# --- AreaChanged ---


@dataclass
class AreaChangedData:
    area: AreaSummary


AREA_CHANGED_ID = "__geo_area_changed__"


# --- GetAreaJson ---


@dataclass
class GetAreaJsonInput:
    areaId: str


@dataclass
class GetAreaJsonOutput:
    error: int
    errorDescription: str | None = None
    manifest: dict | None = None  # manifest.json-shaped payload; null when error != OK


GET_AREA_JSON_ID = "__geo_get_area_json__"


# --- PutAreaJson ---


@dataclass
class PutAreaJsonInput:
    areaId: str
    manifest: dict  # manifest.json-shaped payload


@dataclass
class PutAreaJsonOutput:
    error: int
    errorDescription: str | None = None


PUT_AREA_JSON_ID = "__geo_put_area_json__"


# --- GetUserPoints ---


@dataclass
class GetUserPointsInput:
    areaId: str


@dataclass
class GetUserPointsOutput:
    error: int
    errorDescription: str | None = None
    geojson: dict | None = None  # GeoJSON FeatureCollection; null when error != OK


GET_USER_POINTS_ID = "__geo_get_user_points__"


# --- AddUserPoint ---


@dataclass
class UserPointData:
    lat: float
    lon: float
    timestamp: str
    pressure: float
    name: str | None = None
    properties: dict | None = None  # optional POI metadata; None when no nearby POI


@dataclass
class AddUserPointInput:
    areaId: str
    point: UserPointData

    def __post_init__(self) -> None:
        if isinstance(self.point, dict):
            self.point = UserPointData(**self.point)


@dataclass
class AddUserPointOutput:
    error: int
    errorDescription: str | None = None


ADD_USER_POINT_ID = "__geo_add_user_point__"


# --- RemoveUserPoint ---


@dataclass
class RemoveUserPointInput:
    areaId: str
    lon: float
    lat: float


@dataclass
class RemoveUserPointOutput:
    error: int
    errorDescription: str | None = None


REMOVE_USER_POINT_ID = "__geo_remove_user_point__"
