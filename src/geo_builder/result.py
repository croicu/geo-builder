from __future__ import annotations

from dataclasses import dataclass

from .protocols import Catalog


@dataclass
class Result:
    catalog: Catalog
