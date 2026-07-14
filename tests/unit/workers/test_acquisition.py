from geo_builder.contracts import AcquisitionTask, BoundingBox, WorkerResult
from geo_builder.entities import GeoArea
from geo_builder.errors import ProviderError, ProviderErrorReason
from geo_builder.protocols import Area, AreaStyle, Feature, GeoJson, Geometry, Layer
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
        id="",  # worker assigns id
        name="Restaurant",
        type="heatmap",
        url=None,
        visible=True,
        style={},
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

    def test_too_large_error_pushes_four_child_tasks(self):
        executor = StubExecutor(make_area())
        worker = make_worker(StubProvider(raises=ProviderError("too large", reason=ProviderErrorReason.TOO_LARGE)))

        worker.execute(executor)

        assert len(executor.pushed_tasks) == 4

    def test_too_large_error_returns_non_fatal(self):
        executor = StubExecutor(make_area())
        worker = make_worker(StubProvider(raises=ProviderError("too large", reason=ProviderErrorReason.TOO_LARGE)))

        result = worker.execute(executor)

        assert result.fatal is False

    def test_too_large_error_does_not_add_layer(self):
        executor = StubExecutor(make_area())
        worker = make_worker(StubProvider(raises=ProviderError("too large", reason=ProviderErrorReason.TOO_LARGE)))

        worker.execute(executor)

        assert executor.added_layers == []

    def test_too_large_error_on_degenerate_bbox_is_fatal(self):
        task = make_task(west=1.0, south=1.0, east=1.0, north=1.0)
        executor = StubExecutor(make_area())
        worker = make_worker(StubProvider(raises=ProviderError("too large", reason=ProviderErrorReason.TOO_LARGE)), task=task)

        result = worker.execute(executor)

        assert result.fatal is True
        assert result.error is not None

    def test_rate_limited_error_defers_task_not_split(self):
        executor = StubExecutor(make_area())
        worker = make_worker(StubProvider(raises=ProviderError("rate limited", reason=ProviderErrorReason.RATE_LIMITED)))

        result = worker.execute(executor)

        assert executor.pushed_tasks == []
        assert len(executor.deferred_tasks) == 1
        assert result.fatal is False

    def test_rate_limited_error_increments_attempts(self):
        task = make_task()
        executor = StubExecutor(make_area())
        worker = make_worker(StubProvider(raises=ProviderError("rate limited", reason=ProviderErrorReason.RATE_LIMITED)), task=task)

        worker.execute(executor)

        assert executor.deferred_tasks[0].rate_limit_attempts == 1

    def test_rate_limited_error_fatal_after_max_requeues(self):
        task = make_task()
        task.rate_limit_attempts = 3
        executor = StubExecutor(make_area())
        worker = make_worker(StubProvider(raises=ProviderError("rate limited", reason=ProviderErrorReason.RATE_LIMITED)), task=task)

        result = worker.execute(executor)

        assert executor.deferred_tasks == []
        assert result.fatal is True

    def test_fatal_error_neither_splits_nor_defers(self):
        executor = StubExecutor(make_area())
        worker = make_worker(StubProvider(raises=ProviderError("unknown provider")))

        result = worker.execute(executor)

        assert executor.pushed_tasks == []
        assert executor.deferred_tasks == []
        assert result.fatal is True


class TestLayerIdAssignment:
    def test_new_area_gets_id_one(self):
        area = make_area()
        executor = StubExecutor(area)
        worker = make_worker(StubProvider(layer=make_layer()))

        worker.execute(executor)

        assert executor.added_layers[0].id == "1"

    def test_second_layer_gets_next_id(self):
        from geo_builder.entities import GeoLayer

        area = make_area()
        existing = Layer(
            id="1",
            name="Parks",
            type="circle",
            visible=True,
            style={},
            acquisition={"provider": "overpass", "filters": {"leisure": ["park"]}},
        )
        area.layers.append(GeoLayer(existing))

        task = AcquisitionTask(
            areaId="napoli",
            areaName="Napoli",
            provider="stub",
            bbox=BoundingBox(west=0, south=0, east=1, north=1),
            filters={"amenity": AreaStyle(values=["restaurant"])},
        )
        executor = StubExecutor(area)
        worker = make_worker(StubProvider(layer=make_layer()), task=task)

        worker.execute(executor)

        assert executor.added_layers[0].id == "2"

    def test_existing_layer_id_reused(self):
        from geo_builder.entities import GeoLayer

        area = make_area()
        existing_acq = {"provider": "stub", "filters": {"amenity": ["restaurant"]}}
        existing = Layer(
            id="5",
            name="Restaurant",
            type="heatmap",
            visible=True,
            style={"color": "#ff0000"},
            acquisition=existing_acq,
        )
        area.layers.append(GeoLayer(existing))

        executor = StubExecutor(area)
        worker = make_worker(StubProvider(layer=make_layer()))

        worker.execute(executor)

        assert executor.added_layers[0].id == "5"

    def test_existing_layer_style_preserved(self):
        from geo_builder.entities import GeoLayer

        area = make_area()
        existing_acq = {"provider": "stub", "filters": {"amenity": ["restaurant"]}}
        existing = Layer(
            id="5",
            name="Restaurant",
            type="heatmap",
            visible=True,
            style={"color": "#ff0000"},
            acquisition=existing_acq,
        )
        area.layers.append(GeoLayer(existing))

        executor = StubExecutor(area)
        worker = make_worker(StubProvider(layer=make_layer()))

        worker.execute(executor)

        assert executor.added_layers[0].style["color"] == "#ff0000"

    def test_layer_gets_acquisition_dict(self):
        executor = StubExecutor(make_area())
        worker = make_worker(StubProvider(layer=make_layer()))

        worker.execute(executor)

        acq = executor.added_layers[0].acquisition
        assert acq is not None
        assert acq["provider"] == "stub"
        assert acq["filters"] == {"amenity": ["restaurant"]}

    def test_layer_url_set_from_id(self):
        executor = StubExecutor(make_area())
        worker = make_worker(StubProvider(layer=make_layer()))

        worker.execute(executor)

        layer = executor.added_layers[0]
        assert layer.url == f"./layers/{layer.id}.geojson"


class TestColorOverride:
    def test_filter_color_applied_to_new_layer(self):
        task = AcquisitionTask(
            areaId="napoli",
            areaName="Napoli",
            provider="stub",
            bbox=BoundingBox(west=0, south=0, east=1, north=1),
            filters={"leisure": AreaStyle(values=["park"], color="#00ff00")},
        )
        executor = StubExecutor(make_area())
        worker = make_worker(StubProvider(layer=make_layer()), task=task)

        worker.execute(executor)

        assert executor.added_layers[0].style["color"] == "#00ff00"


class TestExecuteMultiFilter:
    def test_multi_filter_adds_one_layer(self):
        task = AcquisitionTask(
            areaId="napoli",
            areaName="Napoli",
            provider="stub",
            bbox=BoundingBox(west=0, south=0, east=1, north=1),
            filters={"tourism": AreaStyle(values=["museum"]), "historic": AreaStyle(values=["castle"])},
        )
        executor = StubExecutor(make_area())
        worker = make_worker(StubProvider(layer=make_layer()), task=task)

        worker.execute(executor)

        assert len(executor.added_layers) == 1
        assert executor.pushed_tasks == []

    def test_multi_filter_acquisition_contains_all_keys(self):
        task = AcquisitionTask(
            areaId="napoli",
            areaName="Napoli",
            provider="stub",
            bbox=BoundingBox(west=0, south=0, east=1, north=1),
            filters={"tourism": AreaStyle(values=["museum"]), "historic": AreaStyle(values=["castle"])},
        )
        executor = StubExecutor(make_area())
        worker = make_worker(StubProvider(layer=make_layer()), task=task)

        worker.execute(executor)

        acq = executor.added_layers[0].acquisition
        assert acq is not None
        assert set(acq["filters"].keys()) == {"tourism", "historic"}


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
        for c in children:
            assert c.filters == {"amenity": AreaStyle(values=["restaurant"])}

    def test_degenerate_bbox_returns_empty(self):
        task = make_task(west=1.0, south=1.0, east=1.0, north=1.0)
        worker = AcquisitionWorker(task)

        assert worker._split_task(task) == []
