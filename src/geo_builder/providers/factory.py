from ..contracts import Provider
from ..errors import ProviderError
from .fake import FakeProvider
from .overpass import OverpassProvider


class ProviderFactory:
    def create(self, name: str) -> Provider:
        from ..settings import Settings

        config = Settings.current().providers.get(name, {})

        if name == "overpass":
            return OverpassProvider(config)

        if name == "fake":
            return FakeProvider(config)

        raise ProviderError(f"Unknown provider: {name}")
