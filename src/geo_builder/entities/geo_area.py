from __future__ import annotations

from ..protocols import Area, Manifest
from .geo_layer import GeoLayer


class GeoArea:
    def __init__(
        self,
        summary: Area,
        layers: list[GeoLayer] | None = None,
        detail: Manifest | None = None,
    ) -> None:
        self._summary = summary
        self.layers: list[GeoLayer] = layers if layers is not None else []
        self.detail = detail

    @property
    def summary(self) -> Area:  # TODO: protocol exposed — revisit
        return self._summary

    @property
    def id(self) -> str:
        return self._summary.id

    @property
    def name(self) -> str:
        return self._summary.name

    @property
    def bbox(self) -> list[float]:
        return self._summary.bbox

    @bbox.setter
    def bbox(self, value: list[float]) -> None:
        self._summary.bbox = value

    @property
    def manifestUrl(self) -> str:
        return self._summary.manifestUrl

    @property
    def minRadiusPx(self) -> int:
        return self._summary.minRadiusPx

    @property
    def maxRadiusPx(self) -> int:
        return self._summary.maxRadiusPx

    @property
    def liveMapRadiusPx(self) -> int:
        return self._summary.liveMapRadiusPx
