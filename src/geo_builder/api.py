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
