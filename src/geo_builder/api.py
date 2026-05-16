from __future__ import annotations

from dataclasses import dataclass

# Shared API definitions — mirrored as TypeScript interfaces in api.ts.
# Only plain dataclasses with primitive / list / dict fields belong here.


@dataclass
class PingData:
    token: str


PING_ID = "__geo_ping__"
