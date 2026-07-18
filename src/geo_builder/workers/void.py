from ..contracts import Executor, Task, VoidTask, Worker, WorkerResult
from ..diagnostics import Logger
from ..entities import GeoArea, GeoLayer
from ..protocols import GeoJson, Layer, VoidStyle
from .void_geometry import SourcePoint, compute_void_feature

_VOID_TYPE = "__void__"
_VOID_ID = "__void__"
_SOURCE_LAYER_TYPES = ("heatmap", "circle")


class VoidWorker(Worker):
    def __init__(self, task: Task) -> None:
        super().__init__()
        self._task = task

    def execute(self, executor: Executor) -> WorkerResult:
        Logger.info("VoidWorker: execute.")

        catalog = executor.catalog
        if catalog is None:
            Logger.warning("VoidWorker: no catalog, skipping.")
            return WorkerResult()

        if isinstance(self._task, VoidTask):
            style = self._task.style
            default_radius_m = self._task.default_radius_m
        else:
            default_task = VoidTask()
            style = default_task.style
            default_radius_m = default_task.default_radius_m

        area_ids = self._task.area_ids if isinstance(self._task, VoidTask) else None

        variant_count = 0
        for area in list(catalog.areas):
            if area_ids is not None and area.id not in area_ids:
                continue
            variant_count += self._process_area(area, style, default_radius_m)

        Logger.info(f"VoidWorker: completed. {variant_count} void variant(s) computed across {len(catalog.areas)} area(s).")
        return WorkerResult()

    def _process_area(self, area: GeoArea, style: VoidStyle, default_radius_m: float) -> int:
        source_layers = self._source_layers(area)
        area_radius_m = self._resolve_area_radius_m(area, default_radius_m)

        filtered = []
        for geo_layer in area.layers:
            if geo_layer.layer.type != _VOID_TYPE:
                filtered.append(geo_layer)
        area.layers = filtered

        variant_count = 0

        bare_points = self._collect_points(source_layers, area_radius_m)
        bare_geometry = {"radius": area_radius_m}
        bare_layer = self._build_variant(area, bare_points, _VOID_ID, style.name, "void", style, bare_geometry)
        if bare_layer is not None:
            area.layers.append(bare_layer)
            variant_count += 1
        else:
            # No void anywhere for this area right now — still keep a stub so the bare __void__
            # entry always exists (per docs/LAYERS.md) and the resolved radius override survives
            # into the next run instead of silently reverting to the template/task default.
            area.layers.append(self._build_stub(style, bare_geometry))

        for source_layer in source_layers:
            points = self._collect_points([source_layer], area_radius_m)
            variant_id = f"__void__{source_layer.layer.id}__"
            variant_name = f"No {source_layer.layer.name}"
            file_stem = f"layer-{source_layer.layer.id}"
            variant_layer = self._build_variant(area, points, variant_id, variant_name, file_stem, style, None)
            if variant_layer is not None:
                area.layers.append(variant_layer)
                variant_count += 1

        Logger.info(f"VoidWorker: {area.name}: {variant_count} void variant(s).")
        return variant_count

    def _build_stub(self, style: VoidStyle, geometry: dict) -> GeoLayer:
        layer = Layer(
            id=_VOID_ID,
            name=style.name,
            type=_VOID_TYPE,
            visible=False,
            style={
                "opacity": style.opacity,
                "color": style.color,
            },
            geometry=geometry,
        )
        return GeoLayer(layer)

    def _resolve_area_radius_m(self, area: GeoArea, fallback: float) -> float:
        """An area's own __void__ layer may carry a per-area override in geometry.radius.

        Read it before this run's stub-clearing step discards the old layer, so a value set
        once through the designer keeps being honored on every subsequent rebuild (VoidWorker
        writes it back into the new bare __void__ layer's geometry every time it runs).
        """
        for geo_layer in area.layers:
            if geo_layer.layer.id != _VOID_ID:
                continue
            geometry = geo_layer.layer.geometry
            if geometry is None:
                continue
            radius = geometry.get("radius")
            if radius is not None:
                return float(radius)
        return fallback

    def _source_layers(self, area: GeoArea) -> list[GeoLayer]:
        result = []
        for geo_layer in area.layers:
            if geo_layer.layer.type not in _SOURCE_LAYER_TYPES:
                continue
            if geo_layer.layer.geojson is None:
                continue
            result.append(geo_layer)
        return result

    def _collect_points(self, layers: list[GeoLayer], default_radius_m: float) -> list[SourcePoint]:
        points: list[SourcePoint] = []
        for geo_layer in layers:
            if geo_layer.layer.geojson is None:
                continue
            for feature in geo_layer.layer.geojson.features:
                if feature.geometry.type != "Point":
                    continue
                lon = float(feature.geometry.coordinates[0])
                lat = float(feature.geometry.coordinates[1])
                radius_m = feature.properties.get("radius_m", default_radius_m)
                points.append(SourcePoint(lon=lon, lat=lat, radius_m=float(radius_m)))
        return points

    def _build_variant(
        self,
        area: GeoArea,
        points: list[SourcePoint],
        variant_id: str,
        variant_name: str,
        file_stem: str,
        style: VoidStyle,
        geometry: dict | None,
    ) -> GeoLayer | None:
        feature = compute_void_feature(area.bbox, points, label=f"{area.id}:{variant_id}")
        if feature is None:
            return None

        url = f"./void/{file_stem}.geojson"

        layer = Layer(
            id=variant_id,
            name=variant_name,
            type=_VOID_TYPE,
            visible=False,
            style={
                "opacity": style.opacity,
                "color": style.color,
            },
            url=url,
            geojson=GeoJson(type="FeatureCollection", features=[feature]),
            geometry=geometry,
        )
        return GeoLayer(layer)
