from __future__ import annotations

from dataclasses import dataclass

from executor import Catalog


@dataclass
class Result:
    catalog: Catalog