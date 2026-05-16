from __future__ import annotations

from dataclasses import dataclass

# Shared API definitions — mirrored as TypeScript interfaces in api.ts.
# Only plain dataclasses with primitive / list / dict fields belong here.

# --- Error codes ---

OK = 0
ERR_AREA_NOT_FOUND = 1


# --- Ping / Pong ---

@dataclass
class PingData:
    token: str


@dataclass
class PongData:
    token: str


PING_ID = "__geo_ping__"
PONG_ID = "__geo_pong__"


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
