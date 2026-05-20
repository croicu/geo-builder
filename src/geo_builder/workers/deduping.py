from __future__ import annotations

import math
from copy import deepcopy

from ..contracts import Executor, Task, Worker, WorkerResult


class DedupingWorker(Worker):
    _task: Task

    def __init__(self, task: Task) -> None:
        super().__init__()

        self._task = task

    def execute(self, executor: Executor) -> WorkerResult:
        print("DedupingWorker: execute.")

        if executor.catalog is None:
            return WorkerResult()

        for area in executor.catalog.areas:
            for geo_layer in area.layers:
                if geo_layer.layer.geojson is None:
                    continue

                geo_layer.layer.geojson.features = self._dedupe_features(geo_layer.layer.geojson.features)

        print("DedupingWorker: completed.")
        return WorkerResult()

    def _dedupe_features(self, features: list) -> list:
        result = []

        for feature in features:
            merged = False

            for existing in result:
                if self._is_duplicate(existing, feature):
                    self._merge_features(existing, feature)
                    merged = True
                    break

            if not merged:
                result.append(deepcopy(feature))

        return result

    def _is_duplicate(self, a, b) -> bool:
        a_coordinates = a.geometry.coordinates
        b_coordinates = b.geometry.coordinates

        a_lon = float(a_coordinates[0])
        a_lat = float(a_coordinates[1])

        b_lon = float(b_coordinates[0])
        b_lat = float(b_coordinates[1])

        distance = self._distance_meters(
            a_lat,
            a_lon,
            b_lat,
            b_lon,
        )

        return distance < 10.0

    def _merge_features(self, winner, other) -> None:
        winner_properties = winner.properties
        other_properties = other.properties

        self._merge_property(
            winner_properties,
            other_properties,
            "name",
            "names",
        )

        self._merge_property(
            winner_properties,
            other_properties,
            "amenity",
            "amenities",
        )

    def _merge_property(
        self,
        winner_properties,
        other_properties,
        singular_key: str,
        plural_key: str,
    ) -> None:
        winner_value = winner_properties.get(singular_key)
        other_value = other_properties.get(singular_key)

        if not isinstance(winner_value, str):
            return

        if not isinstance(other_value, str):
            return

        if winner_value == other_value:
            return

        values = []

        if plural_key in winner_properties:
            existing_values = winner_properties[plural_key]

            if isinstance(existing_values, list):
                for value in existing_values:
                    if isinstance(value, str) and value not in values:
                        values.append(value)
        else:
            values.append(winner_value)

        if other_value not in values:
            values.append(other_value)

        if len(values) > 1:
            winner_properties[plural_key] = values

    def _distance_meters(
        self,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> float:
        radius = 6_371_000.0

        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)

        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2

        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

        return radius * c
