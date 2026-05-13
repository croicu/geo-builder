# providers/factory.py

from ..contracts import Provider
from .overpass import OverpassProvider


class ProviderFactory:
    def create(self, name: str) -> Provider:
        if name == "overpass":
            return OverpassProvider()

        raise ValueError(f"Unknown provider: {name}")