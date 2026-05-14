from geo_builder.contracts import AcquisitionTask
from geo_builder.errors import ProviderError
from geo_builder.protocols import Area, Layer


class StubProvider:
    name = "stub"

    def __init__(self, layer: Layer | None = None, raises: Exception | None = None) -> None:
        self._layer = layer
        self._raises = raises

    def fetch(self, task: AcquisitionTask) -> Layer:
        if self._raises:
            raise self._raises
        return self._layer


class StubFactory:
    def __init__(self, provider: StubProvider) -> None:
        self._provider = provider

    def create(self, name: str) -> StubProvider:
        return self._provider


class StubExecutor:
    def __init__(self, area: Area) -> None:
        self._area = area
        self.added_layers: list[Layer] = []
        self.pushed_tasks: list[AcquisitionTask] = []

    def add_area(self, task: AcquisitionTask) -> Area:
        return self._area

    def add_layer(self, area: Area, layer: Layer) -> None:
        self.added_layers.append(layer)

    def push_task(self, task: AcquisitionTask) -> None:
        self.pushed_tasks.append(task)

    def push_tasks(self, tasks: list[AcquisitionTask]) -> None:
        self.pushed_tasks.extend(tasks)
