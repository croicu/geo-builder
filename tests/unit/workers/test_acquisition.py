from geo_builder.contracts import AcquisitionTask, AreaStyle, BoundingBox, WorkerResult
from geo_builder.entities import GeoArea
from geo_builder.protocols import Area, Feature, GeoJson, Geometry, Layer
from geo_builder.workers.acquisition import AcquisitionWorker
from tests.shared.stubs import StubExecutor, StubFactory, StubProvider


def make_task(west=0.0, south=0.0, east=2.0, north=2.0) -> AcquisitionTask:
    return AcquisitionTask(
        areaId="napoli",
        areaName="Napoli",
        provider="stub",
        bbox=BoundingBox(west=west, south=south, east=east, north=north),
        filters={"amenity": AreaStyle(values=["restaurant"])},
    )


def make_area() -> GeoArea:
    summary = Area(
        id="napoli",
        name="Napoli",
        bbox=[14.20, 40.80, 14.33, 40.90],
        minRadiusPx=32,
        maxRadiusPx=512,
        liveMapRadiusPx=640,
        manifestUrl="./areas/napoli/manifest.json",
    )
    return GeoArea(summary=summary)


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
            features=[
                Feature(
                    type="Feature",
                    properties={},
                    geometry=Geometry(type="Point", coordinates=[14.27, 40.85]),
                ),
            ],
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
        from geo_builder.errors import ProviderError
        executor = StubExecutor(make_area())
        worker = make_worker(StubProvider(raises=ProviderError("too large")))

        worker.execute(executor)

        assert len(executor.pushed_tasks) == 4

    def test_provider_error_returns_non_fatal(self):
        from geo_builder.errors import ProviderError
        executor = StubExecutor(make_area())
        worker = make_worker(StubProvider(raises=ProviderError("too large")))

        result = worker.execute(executor)

        assert result.fatal is False

    def test_provider_error_does_not_add_layer(self):
        from geo_builder.errors import ProviderError
        executor = StubExecutor(make_area())
        worker = make_worker(StubProvider(raises=ProviderError("too large")))

        worker.execute(executor)

        assert executor.added_layers == []

    def test_provider_error_on_degenerate_bbox_is_fatal(self):
        from geo_builder.errors import ProviderError
        task = make_task(west=1.0, south=1.0, east=1.0, north=1.0)
        executor = StubExecutor(make_area())
        worker = make_worker(StubProvider(raises=ProviderError("too large")), task=task)

        result = worker.execute(executor)

        assert result.fatal is True
        assert result.error is not None


class TestSplitByKey:
    def test_returns_one_task_per_key(self):
        task = AcquisitionTask(
            areaId="napoli", areaName="Napoli", provider="stub",
            bbox=BoundingBox(west=0, south=0, east=1, north=1),
            filters={"amenity": AreaStyle(values=["restaurant"]), "leisure": AreaStyle(values=["park"])},
        )
        worker = AcquisitionWorker(task)

        children = worker._split_by_key(task)

        assert len(children) == 2

    def test_each_child_has_single_key_filter(self):
        task = AcquisitionTask(
            areaId="napoli", areaName="Napoli", provider="stub",
            bbox=BoundingBox(west=0, south=0, east=1, north=1),
            filters={"amenity": AreaStyle(values=["restaurant"]), "leisure": AreaStyle(values=["park"])},
        )
        worker = AcquisitionWorker(task)

        children = worker._split_by_key(task)

        assert all(len(c.filters) == 1 for c in children)
        assert "amenity" in [next(iter(c.filters)) for c in children]
        assert "leisure" in [next(iter(c.filters)) for c in children]

    def test_child_tasks_inherit_bbox_and_area(self):
        task = AcquisitionTask(
            areaId="napoli", areaName="Napoli", provider="stub",
            bbox=BoundingBox(west=1, south=2, east=3, north=4),
            filters={"amenity": AreaStyle(values=["restaurant"]), "leisure": AreaStyle(values=["park"])},
        )
        worker = AcquisitionWorker(task)

        children = worker._split_by_key(task)

        assert all(c.bbox == task.bbox for c in children)
        assert all(c.areaId == "napoli" for c in children)
        assert all(c.areaName == "Napoli" for c in children)


class TestColorOverride:
    def test_filter_color_applied_to_layer(self):
        task = AcquisitionTask(
            areaId="napoli", areaName="Napoli", provider="stub",
            bbox=BoundingBox(west=0, south=0, east=1, north=1),
            filters={"leisure": AreaStyle(values=["park"], color="#00ff00")},
        )
        executor = StubExecutor(make_area())
        worker = make_worker(StubProvider(layer=make_layer()), task=task)

        worker.execute(executor)

        assert executor.added_layers[0].style["color"] == "#00ff00"

    def test_no_override_does_not_set_color_on_layer(self):
        executor = StubExecutor(make_area())
        worker = make_worker(StubProvider(layer=make_layer()))

        worker.execute(executor)

        assert executor.added_layers[0].style.get("color") is None

    def test_color_inherited_by_key_split_children(self):
        task = AcquisitionTask(
            areaId="napoli", areaName="Napoli", provider="stub",
            bbox=BoundingBox(west=0, south=0, east=1, north=1),
            filters={
                "amenity": AreaStyle(values=["restaurant"]),
                "leisure": AreaStyle(values=["park"], color="#00ff00"),
            },
        )
        executor = StubExecutor(make_area())
        worker = make_worker(StubProvider(layer=make_layer()), task=task)

        worker.execute(executor)

        children = executor.pushed_tasks
        leisure_task = next(t for t in children if "leisure" in t.filters)
        assert leisure_task.filters["leisure"].color == "#00ff00"


class TestExecuteMultiKey:
    def test_multi_key_filter_pushes_one_task_per_key(self):
        task = AcquisitionTask(
            areaId="napoli", areaName="Napoli", provider="stub",
            bbox=BoundingBox(west=0, south=0, east=1, north=1),
            filters={"amenity": AreaStyle(values=["restaurant"]), "leisure": AreaStyle(values=["park"])},
        )
        executor = StubExecutor(make_area())
        worker = make_worker(StubProvider(layer=make_layer()), task=task)

        worker.execute(executor)

        assert len(executor.pushed_tasks) == 2

    def test_multi_key_filter_does_not_add_layer(self):
        task = AcquisitionTask(
            areaId="napoli", areaName="Napoli", provider="stub",
            bbox=BoundingBox(west=0, south=0, east=1, north=1),
            filters={"amenity": AreaStyle(values=["restaurant"]), "leisure": AreaStyle(values=["park"])},
        )
        executor = StubExecutor(make_area())
        worker = make_worker(StubProvider(layer=make_layer()), task=task)

        worker.execute(executor)

        assert executor.added_layers == []


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

        assert bboxes == sorted(
            [
                (0.0, 0.0, 1.0, 1.0),
                (1.0, 0.0, 2.0, 1.0),
                (0.0, 1.0, 1.0, 2.0),
                (1.0, 1.0, 2.0, 2.0),
            ]
        )

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
        assert all(c.filters == {"amenity": AreaStyle(values=["restaurant"])} for c in children)

    def test_degenerate_bbox_returns_empty(self):
        task = make_task(west=1.0, south=1.0, east=1.0, north=1.0)
        worker = AcquisitionWorker(task)

        assert worker._split_task(task) == []
