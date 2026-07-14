from __future__ import annotations

from ..protocols import Layer


class GeoLayer:
    def __init__(self, layer: Layer, raw: dict | None = None) -> None:
        self._layer = layer
        self._raw: dict = dict(raw) if raw is not None else {}

    @property
    def layer(self) -> Layer:  # TODO: protocol exposed — revisit
        return self._layer

    @property
    def raw(self) -> dict:
        """Raw JSON payload this layer was loaded from; empty for programmatically-created layers."""
        return self._raw

    def seed_raw(self, payload: dict) -> None:
        """Copy unknown fields from payload into this layer's raw store.

        Known layer fields are skipped — they are always written from the Layer dataclass on save.
        """
        _known = {"id", "name", "type", "url", "visible", "style", "acquisition", "geojson", "geometry"}
        for k, v in payload.items():
            if k not in _known:
                self._raw[k] = v
