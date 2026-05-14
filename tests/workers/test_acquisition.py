import pytest

from geo_builder.contracts import AcquisitionTask, BoundingBox, WorkerResult
from geo_builder.errors import ProviderError
from geo_builder.protocols import Area, Feature, GeoJson, Geometry, Layer, Manifest
from geo_builder.workers.acquisition import AcquisitionWorker
from tests.shared.stubs import StubExecutor, StubFactory, StubProvider


def make_task(west=0.0, south=0.0, east=2.0, north=2.0) -> AcquisitionTask:
    return AcquisitionTask(
        areaId="napoli",
        areaName="Napoli",
        provider="stub",
        bbox=BoundingBox(west=west, south=south, east=east, north=north),
        filter={"amenity": ["restaurant"]},
    )


def make_area() -> Area:
    return Area(
        id="napoli",
        name="Napoli",
        center=[40.85, 14.27],
        radiusMeters=5000,
        minRadiusPx=32,
        maxRadiusPx=512,
        liveMapRadiusPx=640,
        manifestUrl="./areas/napoli/manifest.json",
        manifest=Manifest(version=1, layers=[]),
    )


def make_layer() -> Layer:
    return Layer(
        id="stub_amenity_restaurant",
        name="Restaurant",
        type="heatmap",
        url="./layers/stub_amenity_restaurant.geojson",
        visible=True,
        style={},
        mergeKey="stub:amenity=restaurant",
        geojson=GeoJson(
            type="FeatureCollection",
            features=[Feature(type="Feature", properties={}, geometry=Geometry(type="Point", coordinates=[14.27, 40.85]))],
        ),
    )



def make_worker(provider: StubProvider, task: AcquisitionTask | None = None) -> AcquisitionWorker:
    if task is None:
        task = make_task()
    worker = AcquisitionWorker(task)
    worker._provider_factory = StubFactory(provider)
    return worker


class TestExecute:
    def test_adds_layer_on_success(self):
        executor = StubExecutor(make_area())
        worker = make_worker(StubProvider(layer=make_layer()))

        worker.execute(executor)

        assert len(executor.added_layers) == 1

    def test_returns_non_fatal_on_success(self):
        executor = StubExecutor(make_area())
        worker = make_worker(StubProvider(layer=make_layer()))

        result = worker.execute(executor)

        assert result == WorkerResult()

    def test_provider_error_pushes_four_child_tasks(self):
        executor = StubExecutor(make_area())
        worker = make_worker(StubProvider(raises=ProviderError("too large")))

        worker.execute(executor)

        assert len(executor.pushed_tasks) == 4

    def test_provider_error_returns_non_fatal(self):
        executor = StubExecutor(make_area())
        worker = make_worker(StubProvider(raises=ProviderError("too large")))

        result = worker.execute(executor)

        assert result.fatal is False

    def test_provider_error_does_not_add_layer(self):
        executor = StubExecutor(make_area())
        worker = make_worker(StubProvider(raises=ProviderError("too large")))

        worker.execute(executor)

        assert executor.added_layers == []

    def test_provider_error_on_degenerate_bbox_is_fatal(self):
        task = make_task(west=1.0, south=1.0, east=1.0, north=1.0)
        executor = StubExecutor(make_area())
        worker = make_worker(StubProvider(raises=ProviderError("too large")), task=task)

        result = worker.execute(executor)

        assert result.fatal is True
        assert result.error is not None


class TestSplitTask:
    def test_returns_four_quadrants(self):
        task = make_task(west=0.0, south=0.0, east=2.0, north=2.0)
        worker = AcquisitionWorker(task)

        children = worker._split_task(task)

        assert len(children) == 4

    def test_quadrant_bboxes(self):
        task = make_task(west=0.0, south=0.0, east=2.0, north=2.0)
        worker = AcquisitionWorker(task)

        children = worker._split_task(task)
        bboxes = sorted((c.bbox.west, c.bbox.south, c.bbox.east, c.bbox.north) for c in children)

        assert bboxes == sorted([
            (0.0, 0.0, 1.0, 1.0),
            (1.0, 0.0, 2.0, 1.0),
            (0.0, 1.0, 1.0, 2.0),
            (1.0, 1.0, 2.0, 2.0),
        ])

    def test_child_tasks_inherit_area(self):
        task = make_task()
        worker = AcquisitionWorker(task)

        children = worker._split_task(task)

        assert all(c.areaId == "napoli" for c in children)
        assert all(c.areaName == "Napoli" for c in children)

    def test_child_tasks_inherit_provider_and_filter(self):
        task = make_task()
        worker = AcquisitionWorker(task)

        children = worker._split_task(task)

        assert all(c.provider == "stub" for c in children)
        assert all(c.filter == {"amenity": ["restaurant"]} for c in children)

    def test_degenerate_bbox_returns_empty(self):
        task = make_task(west=1.0, south=1.0, east=1.0, north=1.0)
        worker = AcquisitionWorker(task)

        assert worker._split_task(task) == []
