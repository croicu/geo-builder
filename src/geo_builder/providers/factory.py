from ..contracts import Provider
from ..errors import ProviderError
from .fake_overpass import FakeOverpassProvider
from .overpass import OverpassProvider


class ProviderFactory:
    def create(self, name: str) -> Provider:
        from ..settings import Settings

        config = Settings.current().providers.get(name, {})

        if name == "overpass":
            return OverpassProvider(config)

        if name == "fake_overpass":
            return FakeOverpassProvider(config)

        raise ProviderError(f"Unknown provider: {name}")
