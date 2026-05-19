from __future__ import annotations

import re

from ..protocols import Layer


class GeoLayer:
    def __init__(self, layer: Layer) -> None:
        self._layer = layer

    @property
    def layer(self) -> Layer:  # TODO: protocol exposed — revisit
        return self._layer

    @staticmethod
    def id_from_merge_key(merge_key: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", merge_key.lower()).strip("_")
