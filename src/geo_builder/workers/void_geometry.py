"""Pure geometry functions for precomputing the "__void__" layer's polygon.

No Worker/Task coupling here — VoidWorker calls compute_void_feature() with a bbox and a list
of source points, and gets back a GeoJSON Feature (Polygon or MultiPolygon) or None if there is
no meaningful void region.

Algorithm: a signed distance-field grid (distance to the nearest excluded circle, positive =
void) is sampled over the area's bbox padded by one extra ring of forced-excluded cells (so
marching squares always closes contours using only the interior case table, never needing
boundary-walking — see geo-builder#54 for the full design rationale). The field
is smoothed with a morphological closing pass (grayscale dilate then erode) to merge nearby void
lobes and kill small slivers before contouring — real point data otherwise produces a boundary
that overfits to individual points rather than reading as a single coherent "far from anything"
region. Contours are extracted with marching squares, linked into rings, classified into
exterior/hole by containment, clipped back down to the true bbox with Sutherland-Hodgman, and
simplified with Douglas-Peucker.

Field construction is point-splatting, not corner-querying: for each source point, only the grid
corners within that point's own exclusion radius (plus a small padding margin) are visited and
updated with the exact distance-minus-radius value; every other corner starts at (and, if never
touched by any point, stays at) a large "definitely void" constant. This is deliberately the
opposite of the earlier "for each corner, find nearby points" approach, which degraded badly on
dense real-world data (a spatial bucket index still means every corner scans every point in its
neighborhood — for a dense urban core this can be thousands of points per corner, over tens of
thousands of corners). Splatting instead does one bounded pass per point over just the corners it
can actually influence, which is the correct complexity for "many points, most of them irrelevant
to any given far-away corner." See geo-builder#48 for the measurements that motivated
this and the reasoning for why it's still exact where it matters (see _splat_point's docstring).
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from ..diagnostics import Logger
from ..protocols import Feature, Geometry

_SLOW_THRESHOLD_S = 0.5

_EARTH_RADIUS_M = 6_371_000.0
_METERS_PER_DEGREE_LAT = 111_111.0
_TARGET_CELL_SIZE_M = 25.0
_MAX_GRID_CELLS_PER_AXIS = 200
_EXCLUDED_SENTINEL = -1.0e9
_SIMPLIFY_TOLERANCE_M = 10.0
_CLOSING_RADIUS_CELLS = 1


@dataclass
class SourcePoint:
    lon: float
    lat: float
    radius_m: float


Point2D = tuple[float, float]


# --- Distance math ---


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return _EARTH_RADIUS_M * c


def _meters_per_degree_lon(center_lat: float) -> float:
    return _METERS_PER_DEGREE_LAT * math.cos(math.radians(center_lat))


# --- Grid ---

_UNTOUCHED_FIELD = 1.0e6
_SPLAT_PADDING_FACTOR = 2.0


class _Grid:
    def __init__(self, bbox: list[float], points: list[SourcePoint]) -> None:
        west, south, east, north = bbox[0], bbox[1], bbox[2], bbox[3]
        center_lat = (south + north) / 2.0
        meters_per_deg_lon = _meters_per_degree_lon(center_lat)

        width_m = (east - west) * meters_per_deg_lon
        height_m = (north - south) * _METERS_PER_DEGREE_LAT

        interior_cols = max(1, int(width_m / _TARGET_CELL_SIZE_M))
        interior_rows = max(1, int(height_m / _TARGET_CELL_SIZE_M))
        if interior_cols > _MAX_GRID_CELLS_PER_AXIS:
            interior_cols = _MAX_GRID_CELLS_PER_AXIS
        if interior_rows > _MAX_GRID_CELLS_PER_AXIS:
            interior_rows = _MAX_GRID_CELLS_PER_AXIS

        self.west = west
        self.south = south
        self.east = east
        self.north = north
        self.cell_lon_deg = (east - west) / interior_cols
        self.cell_lat_deg = (north - south) / interior_rows
        self.interior_cols = interior_cols
        self.interior_rows = interior_rows
        self.padded_cols = interior_cols + 2
        self.padded_rows = interior_rows + 2
        self._meters_per_deg_lon = meters_per_deg_lon

        corner_cols = self.padded_cols + 1
        corner_rows = self.padded_rows + 1
        self._field = []
        for _ in range(corner_cols):
            column = []
            for _ in range(corner_rows):
                column.append(_UNTOUCHED_FIELD)
            self._field.append(column)

        cell_lon_m = self.cell_lon_deg * meters_per_deg_lon
        cell_lat_m = self.cell_lat_deg * _METERS_PER_DEGREE_LAT
        padding_m = max(cell_lon_m, cell_lat_m) * _SPLAT_PADDING_FACTOR

        for point in points:
            self._splat_point(point, padding_m)

        for i in range(corner_cols):
            for j in range(corner_rows):
                if i == 0 or i == self.padded_cols or j == 0 or j == self.padded_rows:
                    self._field[i][j] = _EXCLUDED_SENTINEL
                elif self._field[i][j] == 0.0:
                    self._field[i][j] = -1.0e-9

    def _splat_point(self, point: SourcePoint, padding_m: float) -> None:
        """Update every grid corner within (point.radius_m + padding_m) of this point.

        padding_m is chosen (in __init__) to be at least a couple of grid cells wide, which
        guarantees both corners of any edge that could actually cross zero — i.e. any edge
        marching squares needs an accurate interpolated position for — get their exact,
        individually-computed value from whichever point is responsible for the crossing.
        Corners this never reaches are, by construction, farther than every point's own
        radius+padding, so their true field value is positive by more than padding_m; using the
        flat _UNTOUCHED_FIELD constant there instead of the real (larger) value is safe because
        only the sign matters that far from any boundary, not the magnitude.
        """
        search_m = point.radius_m + padding_m
        lat_span_deg = search_m / _METERS_PER_DEGREE_LAT
        lon_span_deg = search_m / self._meters_per_deg_lon

        i_center = 1.0 + (point.lon - self.west) / self.cell_lon_deg
        j_center = 1.0 + (point.lat - self.south) / self.cell_lat_deg
        i_span = lon_span_deg / self.cell_lon_deg
        j_span = lat_span_deg / self.cell_lat_deg

        i_min = max(0, int(math.floor(i_center - i_span)))
        i_max = min(self.padded_cols, int(math.ceil(i_center + i_span)))
        j_min = max(0, int(math.floor(j_center - j_span)))
        j_max = min(self.padded_rows, int(math.ceil(j_center + j_span)))

        for i in range(i_min, i_max + 1):
            lon = self.lon_of(i)
            for j in range(j_min, j_max + 1):
                lat = self.lat_of(j)
                distance = _distance_m(lat, lon, point.lat, point.lon) - point.radius_m
                if distance < self._field[i][j]:
                    self._field[i][j] = distance

    def lon_of(self, i: int) -> float:
        return self.west + (i - 1) * self.cell_lon_deg

    def lat_of(self, j: int) -> float:
        return self.south + (j - 1) * self.cell_lat_deg

    def value_at(self, i: int, j: int) -> float:
        return self._field[i][j]

    def set_value(self, i: int, j: int, value: float) -> None:
        self._field[i][j] = value


# --- Morphological closing (smooths the field before contouring) ---


def _clamp(value: int, low: int, high: int) -> int:
    if value < low:
        return low
    if value > high:
        return high
    return value


def _apply_morphological_closing(grid: _Grid, radius_cells: int) -> None:
    """Grayscale-dilate then grayscale-erode the interior field values in place.

    Merges nearby void lobes and removes small excluded slivers between close-together points,
    without needing a bigger exclusion radius. Only the real (non-padding) corners are touched;
    neighbor lookups near the interior boundary clamp to the interior range so the always-forced
    padding ring never bleeds into real edge data.
    """
    min_i = 1
    max_i = grid.padded_cols - 1
    min_j = 1
    max_j = grid.padded_rows - 1

    dilated: list[list[float]] = []
    for i in range(min_i, max_i + 1):
        row: list[float] = []
        for j in range(min_j, max_j + 1):
            best: float | None = None
            for di in range(-radius_cells, radius_cells + 1):
                for dj in range(-radius_cells, radius_cells + 1):
                    ni = _clamp(i + di, min_i, max_i)
                    nj = _clamp(j + dj, min_j, max_j)
                    value = grid.value_at(ni, nj)
                    if best is None or value > best:
                        best = value
            row.append(best)
        dilated.append(row)

    eroded: list[list[float]] = []
    for local_i in range(len(dilated)):
        row = []
        for local_j in range(len(dilated[0])):
            i = local_i + min_i
            j = local_j + min_j
            best = None
            for di in range(-radius_cells, radius_cells + 1):
                for dj in range(-radius_cells, radius_cells + 1):
                    ni = _clamp(i + di, min_i, max_i) - min_i
                    nj = _clamp(j + dj, min_j, max_j) - min_j
                    value = dilated[ni][nj]
                    if best is None or value < best:
                        best = value
            row.append(best)
        eroded.append(row)

    for local_i in range(len(eroded)):
        for local_j in range(len(eroded[0])):
            grid.set_value(local_i + min_i, local_j + min_j, eroded[local_i][local_j])


# --- Marching squares ---


def _interp_point(v1: float, v2: float, p1: Point2D, p2: Point2D) -> Point2D:
    if v1 == v2:
        t = 0.5
    else:
        t = v1 / (v1 - v2)
    x = p1[0] + t * (p2[0] - p1[0])
    y = p1[1] + t * (p2[1] - p1[1])
    return (x, y)


def _extract_segments(grid: _Grid) -> list[tuple[Point2D, Point2D]]:
    segments: list[tuple[Point2D, Point2D]] = []
    edge_cache: dict[tuple[int, int, int, int], Point2D | None] = {}

    for i in range(grid.padded_cols):
        for j in range(grid.padded_rows):
            bl_pos = (grid.lon_of(i), grid.lat_of(j))
            br_pos = (grid.lon_of(i + 1), grid.lat_of(j))
            tr_pos = (grid.lon_of(i + 1), grid.lat_of(j + 1))
            tl_pos = (grid.lon_of(i), grid.lat_of(j + 1))

            bl_val = grid.value_at(i, j)
            br_val = grid.value_at(i + 1, j)
            tr_val = grid.value_at(i + 1, j + 1)
            tl_val = grid.value_at(i, j + 1)

            left = _cached_crossing(edge_cache, (i, j, i, j + 1), tl_val, bl_val, tl_pos, bl_pos)
            bottom = _cached_crossing(edge_cache, (i, j, i + 1, j), bl_val, br_val, bl_pos, br_pos)
            right = _cached_crossing(edge_cache, (i + 1, j, i + 1, j + 1), br_val, tr_val, br_pos, tr_pos)
            top = _cached_crossing(edge_cache, (i, j + 1, i + 1, j + 1), tl_val, tr_val, tl_pos, tr_pos)

            crossings = []
            if left is not None:
                crossings.append(("left", left))
            if bottom is not None:
                crossings.append(("bottom", bottom))
            if right is not None:
                crossings.append(("right", right))
            if top is not None:
                crossings.append(("top", top))

            if len(crossings) == 2:
                segments.append((crossings[0][1], crossings[1][1]))
            elif len(crossings) == 4:
                avg = (bl_val + br_val + tr_val + tl_val) / 4.0
                by_name: dict[str, Point2D] = {}
                for name, point in crossings:
                    by_name[name] = point
                if avg <= 0.0:
                    segments.append((by_name["left"], by_name["bottom"]))
                    segments.append((by_name["right"], by_name["top"]))
                else:
                    segments.append((by_name["left"], by_name["top"]))
                    segments.append((by_name["bottom"], by_name["right"]))
    return segments


def _cached_crossing(
    cache: dict[tuple[int, int, int, int], Point2D | None],
    key: tuple[int, int, int, int],
    v1: float,
    v2: float,
    p1: Point2D,
    p2: Point2D,
) -> Point2D | None:
    if key in cache:
        return cache[key]
    if (v1 > 0.0) == (v2 > 0.0):
        cache[key] = None
        return None
    point = _interp_point(v1, v2, p1, p2)
    cache[key] = point
    return point


# --- Ring assembly ---


def _assemble_rings(segments: list[tuple[Point2D, Point2D]]) -> list[list[Point2D]]:
    adjacency: dict[Point2D, list[Point2D]] = {}
    for a, b in segments:
        if a not in adjacency:
            adjacency[a] = []
        if b not in adjacency:
            adjacency[b] = []
        adjacency[a].append(b)
        adjacency[b].append(a)

    visited_edges: set[tuple[Point2D, Point2D]] = set()
    rings: list[list[Point2D]] = []

    for start in list(adjacency.keys()):
        neighbors = adjacency[start]
        for first_neighbor in list(neighbors):
            edge_key = (start, first_neighbor)
            if edge_key in visited_edges:
                continue
            ring = _walk_ring(adjacency, visited_edges, start, first_neighbor)
            if ring is not None and len(ring) >= 3:
                rings.append(ring)
    return rings


def _walk_ring(
    adjacency: dict[Point2D, list[Point2D]],
    visited_edges: set[tuple[Point2D, Point2D]],
    start: Point2D,
    first_neighbor: Point2D,
) -> list[Point2D] | None:
    ring = [start]
    previous = start
    current = first_neighbor
    visited_edges.add((previous, current))
    visited_edges.add((current, previous))

    max_steps = 1_000_000
    steps = 0
    while current != start:
        ring.append(current)
        candidates = adjacency.get(current, [])
        next_point = None
        for candidate in candidates:
            edge_key = (current, candidate)
            if edge_key not in visited_edges:
                next_point = candidate
                break
        if next_point is None:
            return None
        visited_edges.add((current, next_point))
        visited_edges.add((next_point, current))
        previous = current
        current = next_point
        steps += 1
        if steps > max_steps:
            return None
    return ring


# --- Exterior / hole classification ---


def _signed_area(ring: list[Point2D]) -> float:
    area = 0.0
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return area / 2.0


def _point_in_ring(point: Point2D, ring: list[Point2D]) -> bool:
    x, y = point
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y):
            x_intersect = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < x_intersect:
                inside = not inside
        j = i
    return inside


def _classify_rings(rings: list[list[Point2D]]) -> list[dict]:
    n = len(rings)
    contains_count = [0] * n
    for i in range(n):
        test_point = rings[i][0]
        for j in range(n):
            if i == j:
                continue
            if _point_in_ring(test_point, rings[j]):
                contains_count[i] += 1

    exterior_indices = []
    hole_indices = []
    for i in range(n):
        if contains_count[i] % 2 == 0:
            exterior_indices.append(i)
        else:
            hole_indices.append(i)

    polygons = []
    for ext_i in exterior_indices:
        polygons.append({"exterior_index": ext_i, "holes": []})

    for hole_i in hole_indices:
        best_ext = None
        best_area = None
        for ext_i in exterior_indices:
            if _point_in_ring(rings[hole_i][0], rings[ext_i]):
                area = abs(_signed_area(rings[ext_i]))
                if best_area is None or area < best_area:
                    best_area = area
                    best_ext = ext_i
        if best_ext is not None:
            for polygon in polygons:
                if polygon["exterior_index"] == best_ext:
                    polygon["holes"].append(hole_i)
                    break

    return polygons


# --- Sutherland-Hodgman bbox clip ---


def _x_intersect(p1: Point2D, p2: Point2D, x: float) -> Point2D:
    x1, y1 = p1
    x2, y2 = p2
    if x2 == x1:
        t = 0.0
    else:
        t = (x - x1) / (x2 - x1)
    return (x, y1 + t * (y2 - y1))


def _y_intersect(p1: Point2D, p2: Point2D, y: float) -> Point2D:
    x1, y1 = p1
    x2, y2 = p2
    if y2 == y1:
        t = 0.0
    else:
        t = (y - y1) / (y2 - y1)
    return (x1 + t * (x2 - x1), y)


def _clip_west(points: list[Point2D], west: float) -> list[Point2D]:
    result: list[Point2D] = []
    n = len(points)
    for i in range(n):
        current = points[i]
        previous = points[i - 1]
        current_inside = current[0] >= west
        previous_inside = previous[0] >= west
        if current_inside:
            if not previous_inside:
                result.append(_x_intersect(previous, current, west))
            result.append(current)
        elif previous_inside:
            result.append(_x_intersect(previous, current, west))
    return result


def _clip_east(points: list[Point2D], east: float) -> list[Point2D]:
    result: list[Point2D] = []
    n = len(points)
    for i in range(n):
        current = points[i]
        previous = points[i - 1]
        current_inside = current[0] <= east
        previous_inside = previous[0] <= east
        if current_inside:
            if not previous_inside:
                result.append(_x_intersect(previous, current, east))
            result.append(current)
        elif previous_inside:
            result.append(_x_intersect(previous, current, east))
    return result


def _clip_south(points: list[Point2D], south: float) -> list[Point2D]:
    result: list[Point2D] = []
    n = len(points)
    for i in range(n):
        current = points[i]
        previous = points[i - 1]
        current_inside = current[1] >= south
        previous_inside = previous[1] >= south
        if current_inside:
            if not previous_inside:
                result.append(_y_intersect(previous, current, south))
            result.append(current)
        elif previous_inside:
            result.append(_y_intersect(previous, current, south))
    return result


def _clip_north(points: list[Point2D], north: float) -> list[Point2D]:
    result: list[Point2D] = []
    n = len(points)
    for i in range(n):
        current = points[i]
        previous = points[i - 1]
        current_inside = current[1] <= north
        previous_inside = previous[1] <= north
        if current_inside:
            if not previous_inside:
                result.append(_y_intersect(previous, current, north))
            result.append(current)
        elif previous_inside:
            result.append(_y_intersect(previous, current, north))
    return result


def _clip_ring_to_bbox(ring: list[Point2D], bbox: list[float]) -> list[Point2D]:
    west, south, east, north = bbox[0], bbox[1], bbox[2], bbox[3]
    clipped = _clip_west(ring, west)
    clipped = _clip_east(clipped, east)
    clipped = _clip_south(clipped, south)
    clipped = _clip_north(clipped, north)
    return clipped


# --- Douglas-Peucker simplification ---


def _perpendicular_distance(point: Point2D, line_start: Point2D, line_end: Point2D) -> float:
    x0, y0 = point
    x1, y1 = line_start
    x2, y2 = line_end
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0.0 and dy == 0.0:
        return math.hypot(x0 - x1, y0 - y1)
    numerator = abs(dy * x0 - dx * y0 + x2 * y1 - y2 * x1)
    denominator = math.hypot(dx, dy)
    return numerator / denominator


def _douglas_peucker(points: list[Point2D], tolerance: float) -> list[Point2D]:
    if len(points) < 3:
        return list(points)
    start = points[0]
    end = points[-1]
    dmax = 0.0
    index = 0
    for i in range(1, len(points) - 1):
        d = _perpendicular_distance(points[i], start, end)
        if d > dmax:
            index = i
            dmax = d
    if dmax > tolerance:
        left = _douglas_peucker(points[: index + 1], tolerance)
        right = _douglas_peucker(points[index:], tolerance)
        return left[:-1] + right
    return [start, end]


def _simplify_closed_ring(ring: list[Point2D], tolerance_deg: float) -> list[Point2D]:
    closed = ring + [ring[0]]
    simplified = _douglas_peucker(closed, tolerance_deg)
    if len(simplified) < 4:
        return closed
    return simplified


# --- Top-level orchestration ---


def compute_void_feature(bbox: list[float], points: list[SourcePoint], label: str = "") -> Feature | None:
    if len(points) == 0:
        return None

    t_start = time.perf_counter()
    t_prev = t_start
    stage_seconds: dict[str, float] = {}
    stage_counts: dict[str, int] = {}

    def mark(stage: str, count: int | None = None) -> None:
        nonlocal t_prev
        now = time.perf_counter()
        stage_seconds[stage] = now - t_prev
        if count is not None:
            stage_counts[stage] = count
        t_prev = now

    try:
        grid = _Grid(bbox, points)
        mark("grid")

        _apply_morphological_closing(grid, _CLOSING_RADIUS_CELLS)
        mark("closing")

        segments = _extract_segments(grid)
        mark("segments", len(segments))
        if len(segments) == 0:
            return None

        raw_rings = _assemble_rings(segments)
        mark("assemble_rings", len(raw_rings))

        clipped_rings: list[list[Point2D]] = []
        for ring in raw_rings:
            clipped = _clip_ring_to_bbox(ring, bbox)
            if len(clipped) >= 3:
                clipped_rings.append(clipped)
        mark("clip", len(clipped_rings))
        if len(clipped_rings) == 0:
            return None

        polygons = _classify_rings(clipped_rings)
        mark("classify", len(polygons))
        if len(polygons) == 0:
            return None

        tolerance_deg = _SIMPLIFY_TOLERANCE_M / _METERS_PER_DEGREE_LAT

        polygon_coordinates: list[list[list[list[float]]]] = []
        for polygon in polygons:
            exterior = clipped_rings[polygon["exterior_index"]]
            if _signed_area(exterior) < 0.0:
                exterior = list(reversed(exterior))
            exterior_simplified = _simplify_closed_ring(exterior, tolerance_deg)
            rings_out = [_to_coordinate_ring(exterior_simplified)]

            for hole_index in polygon["holes"]:
                hole = clipped_rings[hole_index]
                if _signed_area(hole) > 0.0:
                    hole = list(reversed(hole))
                hole_simplified = _simplify_closed_ring(hole, tolerance_deg)
                rings_out.append(_to_coordinate_ring(hole_simplified))

            polygon_coordinates.append(rings_out)
        mark("simplify")

        if len(polygon_coordinates) == 1:
            geometry = Geometry(type="Polygon", coordinates=polygon_coordinates[0])
        else:
            geometry = Geometry(type="MultiPolygon", coordinates=polygon_coordinates)

        return Feature(type="Feature", properties={}, geometry=geometry)
    finally:
        _log_timing(label, len(points), stage_seconds, stage_counts, time.perf_counter() - t_start)


def _log_timing(label: str, point_count: int, stage_seconds: dict[str, float], stage_counts: dict[str, int], total_s: float) -> None:
    prefix = f"compute_void_feature[{label}]" if label else "compute_void_feature"
    parts: list[str] = []
    for stage in ("grid", "closing", "segments", "assemble_rings", "clip", "classify", "simplify"):
        if stage not in stage_seconds:
            continue
        piece = f"{stage}={stage_seconds[stage]:.3f}s"
        if stage in stage_counts:
            piece += f"({stage_counts[stage]})"
        parts.append(piece)
    detail = ", ".join(parts)
    message = f"{prefix}: {point_count} points, total={total_s:.3f}s [{detail}]"
    if total_s >= _SLOW_THRESHOLD_S:
        Logger.info(f"slow void computation — {message}")
    else:
        Logger.diagnostic(message)


def _to_coordinate_ring(points: list[Point2D]) -> list[list[float]]:
    ring_out: list[list[float]] = []
    for point in points:
        ring_out.append([point[0], point[1]])
    return ring_out
