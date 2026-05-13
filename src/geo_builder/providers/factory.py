# providers/factory.py

from ..contracts import Provider
from ..errors import ProviderError
from .overpass import OverpassProvider


class ProviderFactory:
    def create(self, name: str) -> Provider:
        if name == "overpass":
            return OverpassProvider()

        raise ProviderError(f"Unknown provider: {name}")