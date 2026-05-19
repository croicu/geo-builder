from __future__ import annotations

from dataclasses import dataclass

# Shared API definitions — mirrored as TypeScript interfaces in api.ts.
# Only plain dataclasses with primitive / list / dict fields belong here.

# --- Error codes ---

OK = 0
ERR_AREA_NOT_FOUND = 1
ERR_TEMPLATE_NOT_FOUND = 2


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
    template: str = "*"


@dataclass
class AddAreaOutput:
    error: int
    errorDescription: str | None = None


ADD_AREA_ID = "__geo_add_area__"
