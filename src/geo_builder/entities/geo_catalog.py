from __future__ import annotations

from datetime import datetime, timezone

from .geo_area import GeoArea


class GeoCatalog:
    def __init__(
        self,
        version: str = "1.0",
        created_at: str | None = None,
        areas: list[GeoArea] | None = None,
        is_default: bool = True,
    ) -> None:
        self.version = version
        self.created_at = created_at if created_at is not None else str(datetime.now(timezone.utc))
        self.areas: list[GeoArea] = areas if areas is not None else []
        self.is_default = is_default

    def register_handlers(self, gateway) -> None:
        from ..api import GET_AREA_BBOX_ID, GetAreaBboxInput, GetAreaBboxOutput
        gateway.define_method(GET_AREA_BBOX_ID, GetAreaBboxInput, GetAreaBboxOutput)
        gateway.register(GET_AREA_BBOX_ID, self._get_area_bbox)

    def _get_area_bbox(self, data) -> object:
        from ..api import ERR_AREA_NOT_FOUND, OK, GetAreaBboxOutput
        for area in self.areas:
            if area.id == data.areaId:
                return GetAreaBboxOutput(error=OK, bbox=area.bbox)
        return GetAreaBboxOutput(error=ERR_AREA_NOT_FOUND, errorDescription=f"Area '{data.areaId}' not found")
