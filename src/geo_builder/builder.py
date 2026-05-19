from __future__ import annotations

import csv
import json
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .colors import layer_color
from .contracts import AcquisitionTask, Task
from .entities import GeoCatalog, GeoArea, GeoLayer
from .errors import GeoError
from .protocols import Area, JsonObject, Layer
from .workers.factory import WorkerFactory


@dataclass
class Builder:
    catalog: GeoCatalog = field(default_factory=GeoCatalog)
    errors: list[str] = field(default_factory=list)

    _stack: list[JsonObject] = field(default_factory=list)
    _worker_factory: WorkerFactory = field(default_factory=WorkerFactory)

    def run(self, tasks: list[Task] | None = None) -> GeoCatalog:
        from .settings import Settings

        settings = Settings.current()
        debug = settings.debug

        self.errors.clear()
        if tasks is not None:
            self._stack = list(reversed(tasks))
        else:
            self._stack = list(reversed(settings.tasks))

        if debug:
            build_dir = Path("./build")
            shutil.rmtree(build_dir, ignore_errors=True)
            build_dir.mkdir(parents=True, exist_ok=True)

        counter = 0

        while self._stack:
            task = self._stack.pop()
            counter += 1

            if debug:
                worker = self._worker_factory.create(task)
                pre_snapshot = self._layer_snapshot()
                result = worker.execute(self)
                self._save_debug_snapshot(task, counter, pre_snapshot)
            else:
                try:
                    worker = self._worker_factory.create(task)
                    result = worker.execute(self)
                except GeoError as error:
                    self.errors.append(str(error))
                    break

            if result.fatal:
                if result.error is not None:
                    self.errors.append(result.error)
                break

        return self.catalog

    def push_task(self, task: JsonObject) -> None:
        self._stack.append(task)

    def push_tasks(self, tasks: list[JsonObject]) -> None:
        self._stack.extend(tasks)

    def add_area(self, task: AcquisitionTask) -> GeoArea:
        area_id = task.areaId

        for area in self.catalog.areas:
            if area.id == area_id:
                return area

        bbox = task.bbox

        summary = Area(
            id=area_id,
            name=task.areaName,
            bbox=[bbox.west, bbox.south, bbox.east, bbox.north],
            minRadiusPx=32,
            maxRadiusPx=512,
            liveMapRadiusPx=640,
            manifestUrl=f"./areas/{area_id}/manifest.json",
        )

        geo_area = GeoArea(summary=summary)
        self.catalog.areas.append(geo_area)
        return geo_area

    def add_layer(self, area: GeoArea, layer: Layer) -> None:
        for existing in area.layers:
            if existing.layer.mergeKey == layer.mergeKey:
                existing.layer.geojson.features.extend(layer.geojson.features)
                return
        layer.style["color"] = layer_color(len(area.layers))
        area.layers.append(GeoLayer(layer))

    def _layer_snapshot(self) -> dict[tuple[str, str], int]:
        snapshot = {}
        for area in self.catalog.areas:
            for geo_layer in area.layers:
                snapshot[(area.id, geo_layer.layer.id)] = len(geo_layer.layer.geojson.features)
        return snapshot

    def _save_debug_snapshot(self, task: Task, counter: int, pre_snapshot: dict[tuple[str, str], int]) -> None:
        task_dir = Path("./build") / task.type / f"{counter:03d}"
        task_dir.mkdir(parents=True, exist_ok=True)

        areas_payload = []
        for geo_area in self.catalog.areas:
            layers_payload = []
            for geo_layer in geo_area.layers:
                layer_data = asdict(geo_layer.layer)
                del layer_data["geojson"]
                layers_payload.append(layer_data)
            area_data = asdict(geo_area.summary)
            area_data["layers"] = layers_payload
            areas_payload.append(area_data)

        payload = {
            "version": self.catalog.version,
            "createdAt": self.catalog.created_at,
            "areas": areas_payload,
        }

        with open(task_dir / "catalog.json", "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        for geo_area in self.catalog.areas:
            for geo_layer in geo_area.layers:
                pre_count = pre_snapshot.get((geo_area.id, geo_layer.layer.id))
                if pre_count is None or pre_count != len(geo_layer.layer.geojson.features):
                    self._save_debug_layer(geo_layer.layer, task_dir)

    def _save_debug_layer(self, layer: Layer, task_dir: Path) -> None:
        geojson_path = task_dir / f"{layer.id}.geojson"
        with open(geojson_path, "w", encoding="utf-8") as f:
            json.dump(asdict(layer.geojson), f, indent=2)

        csv_path = task_dir / f"{layer.id}.csv"
        features = layer.geojson.features
        if not features:
            return
        property_keys = sorted({key for feat in features for key in feat.properties})
        fieldnames = ["lon", "lat"] + property_keys
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for feat in features:
                row: dict[str, object] = {
                    "lon": feat.geometry.coordinates[0],
                    "lat": feat.geometry.coordinates[1],
                }
                for key in property_keys:
                    row[key] = feat.properties.get(key, "")
                writer.writerow(row)
