import pytest

from geo_builder.builder import Builder
from geo_builder.contracts import (
    AcquisitionTask,
    AggregationTask,
    BoundingBox,
    DedupingTask,
    PoiTask,
    SearchTask,
    VoidTask,
    WorkerResult,
)
from geo_builder.entities import GeoArea
from geo_builder.errors import GeoError
from geo_builder.protocols import Area, Feature, GeoJson, Geometry, Layer
from geo_builder.settings import Settings


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


def make_layer(layer_id: str, feature_count: int) -> Layer:
    features = []
    for i in range(feature_count):
        features.append(
            Feature(
                type="Feature",
                properties={"id": i},
                geometry=Geometry(type="Point", coordinates=[14.27, 40.85]),
            )
        )
    return Layer(
        id=layer_id,
        name="Overpass",
        type="heatmap",
        url=f"./layers/{layer_id}.geojson",
        visible=True,
        style={},
        acquisition={"provider": "overpass", "filters": {"amenity": ["restaurant"]}},
        geojson=GeoJson(type="FeatureCollection", features=features),
    )


TASK = AcquisitionTask(
    areaId="napoli",
    areaName="Napoli",
    provider="fake",
    bbox=BoundingBox(west=14.20, south=40.80, east=14.33, north=40.90),
    filters={},
)


class StubWorker:
    def __init__(self, result: WorkerResult | None = None, raises: Exception | None = None) -> None:
        self.executed = False
        self._result = result or WorkerResult()
        self._raises = raises

    def execute(self, executor) -> WorkerResult:
        self.executed = True
        if self._raises:
            raise self._raises
        return self._result


class StubWorkerFactory:
    def __init__(self, workers: list[StubWorker]) -> None:
        self._workers = iter(workers)

    def create(self, task) -> StubWorker:
        return next(self._workers)


@pytest.fixture(autouse=True)
def settings():
    Settings._instance = Settings(debug=False, providers={})
    yield
    Settings._instance = None


class TestAddArea:
    def test_creates_area_with_correct_id_and_name(self):
        area = Builder().add_area(TASK)

        assert area.id == "napoli"
        assert area.name == "Napoli"

    def test_area_added_to_catalog(self):
        builder = Builder()
        builder.add_area(TASK)

        assert len(builder.catalog.areas) == 1

    def test_duplicate_area_id_returns_same_instance(self):
        builder = Builder()

        a1 = builder.add_area(TASK)
        a2 = builder.add_area(TASK)

        assert a1 is a2
        assert len(builder.catalog.areas) == 1

    def test_bbox_matches_task(self):
        area = Builder().add_area(TASK)

        assert area.bbox == pytest.approx([14.20, 40.80, 14.33, 40.90])

    def test_manifest_url_uses_area_id(self):
        area = Builder().add_area(TASK)

        assert area.manifestUrl == "./areas/napoli/manifest.json"


class TestRun:
    def test_processes_all_tasks(self):
        workers = [StubWorker(), StubWorker()]
        builder = Builder()
        builder._worker_factory = StubWorkerFactory(workers)

        builder.run(tasks=[TASK, TASK])

        assert all(w.executed for w in workers)

    def test_fatal_result_stops_processing(self):
        workers = [StubWorker(result=WorkerResult(fatal=True, error="boom")), StubWorker()]
        builder = Builder()
        builder._worker_factory = StubWorkerFactory(workers)

        builder.run(tasks=[TASK, TASK])

        assert workers[0].executed
        assert not workers[1].executed

    def test_fatal_error_message_recorded(self):
        builder = Builder()
        builder._worker_factory = StubWorkerFactory([StubWorker(result=WorkerResult(fatal=True, error="boom"))])

        builder.run(tasks=[TASK])

        assert builder.errors == ["boom"]

    def test_geo_error_caught_in_non_debug_mode(self):
        builder = Builder()
        builder._worker_factory = StubWorkerFactory([StubWorker(raises=GeoError("oops"))])

        builder.run(tasks=[TASK])

        assert builder.errors == ["oops"]

    def test_geo_error_propagates_in_debug_mode(self):
        builder = Builder()
        builder._worker_factory = StubWorkerFactory([StubWorker(raises=GeoError("oops"))])
        Settings._instance = Settings(debug=True, providers={})

        with pytest.raises(GeoError):
            builder.run(tasks=[TASK])

    def test_returns_geo_catalog(self):
        builder = Builder()
        builder._worker_factory = StubWorkerFactory([])

        result = builder.run(tasks=[])

        assert result is builder.catalog


class TestBuilderAddLayer:
    def test_first_layer_is_appended(self):
        builder = Builder()
        area = make_area()
        layer = make_layer("1", 3)

        builder.add_layer(area, layer)

        assert len(area.layers) == 1

    def test_same_id_merges_features(self):
        builder = Builder()
        area = make_area()

        builder.add_layer(area, make_layer("1", 3))
        builder.add_layer(area, make_layer("1", 2))

        assert len(area.layers) == 1
        assert len(area.layers[0].layer.geojson.features) == 5

    def test_different_id_appends_new_layer(self):
        builder = Builder()
        area = make_area()

        builder.add_layer(area, make_layer("1", 3))
        builder.add_layer(area, make_layer("2", 2))

        assert len(area.layers) == 2

    def test_first_layer_gets_blue(self):
        builder = Builder()
        area = make_area()

        builder.add_layer(area, make_layer("1", 1))

        assert area.layers[0].layer.style["color"] == "#0000ff"

    def test_second_layer_gets_different_color(self):
        builder = Builder()
        area = make_area()

        builder.add_layer(area, make_layer("1", 1))
        builder.add_layer(area, make_layer("2", 1))

        assert area.layers[0].layer.style["color"] != area.layers[1].layer.style["color"]

    def test_merged_layer_keeps_original_color(self):
        builder = Builder()
        area = make_area()

        builder.add_layer(area, make_layer("1", 1))
        color_before = area.layers[0].layer.style["color"]
        builder.add_layer(area, make_layer("1", 1))

        assert area.layers[0].layer.style["color"] == color_before


def _pop_all_types(builder: Builder) -> list[str]:
    order = []
    while builder._stack:
        order.append(builder._stack.pop().type)
    return order


class TestDeferTask:
    def test_deferred_task_runs_before_fixed_tail_not_after(self):
        # Mirrors a real mid-build stack: two acquisitions still pending (popped first),
        # then the fixed tail queued at the very start of the build (popped last).
        builder = Builder()
        pending_acq_1 = AcquisitionTask(areaId="a", areaName="A", provider="fake", bbox=BoundingBox(0, 0, 1, 1), filters={})
        pending_acq_2 = AcquisitionTask(areaId="a", areaName="A", provider="fake", bbox=BoundingBox(0, 0, 1, 1), filters={})
        deferred = AcquisitionTask(areaId="a", areaName="A", provider="fake", bbox=BoundingBox(0, 0, 1, 1), filters={})
        builder._stack = [SearchTask(), VoidTask(), PoiTask(), DedupingTask(), AggregationTask(), pending_acq_2, pending_acq_1]

        builder.defer_task(deferred)
        order = _pop_all_types(builder)

        assert order == ["acquisition", "acquisition", "acquisition", "aggregation", "deduping", "poi", "void", "search"]
        assert builder._stack == []

    def test_deferred_task_runs_after_other_pending_acquisitions(self):
        builder = Builder()
        pending_acq = AcquisitionTask(areaId="a", areaName="A", provider="fake", bbox=BoundingBox(0, 0, 1, 1), filters={})
        deferred = AcquisitionTask(areaId="a", areaName="A", provider="fake", bbox=BoundingBox(0, 0, 1, 1), filters={})
        builder._stack = [AggregationTask(), pending_acq]

        builder.defer_task(deferred)

        assert builder._stack.pop() is pending_acq
        assert builder._stack.pop() is deferred
        assert builder._stack.pop().type == "aggregation"

    def test_defer_with_only_fixed_tail_pending_runs_before_it(self):
        builder = Builder()
        deferred = AcquisitionTask(areaId="a", areaName="A", provider="fake", bbox=BoundingBox(0, 0, 1, 1), filters={})
        builder._stack = [SearchTask(), VoidTask(), PoiTask(), DedupingTask(), AggregationTask()]

        builder.defer_task(deferred)
        order = _pop_all_types(builder)

        assert order == ["acquisition", "aggregation", "deduping", "poi", "void", "search"]

    def test_defer_on_empty_stack(self):
        builder = Builder()
        deferred = AcquisitionTask(areaId="a", areaName="A", provider="fake", bbox=BoundingBox(0, 0, 1, 1), filters={})
        builder._stack = []

        builder.defer_task(deferred)

        assert builder._stack == [deferred]
