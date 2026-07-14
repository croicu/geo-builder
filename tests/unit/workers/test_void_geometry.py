from geo_builder.workers.void_geometry import SourcePoint, compute_void_feature

# A modest bbox near Naples so grid resolution stays small and tests run fast.
BBOX = [14.20, 40.80, 14.21, 40.81]


def bbox_of_ring(ring: list[list[float]]) -> tuple[float, float, float, float]:
    lons = []
    lats = []
    for coordinate in ring:
        lons.append(coordinate[0])
        lats.append(coordinate[1])
    return (min(lons), min(lats), max(lons), max(lats))


class TestComputeVoidFeature:
    def test_no_points_returns_none(self):
        feature = compute_void_feature(BBOX, [])
        assert feature is None

    def test_label_accepted_and_does_not_affect_result(self):
        center_lon = (BBOX[0] + BBOX[2]) / 2.0
        center_lat = (BBOX[1] + BBOX[3]) / 2.0
        points = [SourcePoint(lon=center_lon, lat=center_lat, radius_m=100.0)]

        unlabeled = compute_void_feature(BBOX, points)
        labeled = compute_void_feature(BBOX, points, label="napoli:__void__")

        assert unlabeled is not None
        assert labeled is not None
        assert unlabeled.geometry.coordinates == labeled.geometry.coordinates

    def test_huge_radius_covering_bbox_returns_none(self):
        center_lon = (BBOX[0] + BBOX[2]) / 2.0
        center_lat = (BBOX[1] + BBOX[3]) / 2.0
        points = [SourcePoint(lon=center_lon, lat=center_lat, radius_m=50_000.0)]
        feature = compute_void_feature(BBOX, points)
        assert feature is None

    def test_single_centered_point_produces_polygon_with_hole(self):
        center_lon = (BBOX[0] + BBOX[2]) / 2.0
        center_lat = (BBOX[1] + BBOX[3]) / 2.0
        # radius_m must clear the morphological closing pass (~2x cell size) or the hole gets
        # smoothed away entirely, which is the closing's intended effect on small slivers.
        points = [SourcePoint(lon=center_lon, lat=center_lat, radius_m=100.0)]

        feature = compute_void_feature(BBOX, points)

        assert feature is not None
        assert feature.geometry.type == "Polygon"
        rings = feature.geometry.coordinates
        assert len(rings) == 2  # exterior + one hole (the excluded circle)

        exterior_bbox = bbox_of_ring(rings[0])
        assert exterior_bbox[0] <= BBOX[0] + 1e-6
        assert exterior_bbox[1] <= BBOX[1] + 1e-6
        assert exterior_bbox[2] >= BBOX[2] - 1e-6
        assert exterior_bbox[3] >= BBOX[3] - 1e-6

        hole_bbox = bbox_of_ring(rings[1])
        hole_center_lon = (hole_bbox[0] + hole_bbox[2]) / 2.0
        hole_center_lat = (hole_bbox[1] + hole_bbox[3]) / 2.0
        assert abs(hole_center_lon - center_lon) < 0.001
        assert abs(hole_center_lat - center_lat) < 0.001

    def test_two_corner_points_do_not_crash_and_produce_geometry(self):
        points = [
            SourcePoint(lon=BBOX[0] + 0.0005, lat=BBOX[1] + 0.0005, radius_m=20.0),
            SourcePoint(lon=BBOX[2] - 0.0005, lat=BBOX[3] - 0.0005, radius_m=20.0),
        ]
        feature = compute_void_feature(BBOX, points)
        assert feature is not None
        assert feature.geometry.type in ("Polygon", "MultiPolygon")
        assert len(feature.geometry.coordinates) > 0

    def test_larger_radius_produces_larger_hole(self):
        center_lon = (BBOX[0] + BBOX[2]) / 2.0
        center_lat = (BBOX[1] + BBOX[3]) / 2.0
        small = [SourcePoint(lon=center_lon, lat=center_lat, radius_m=100.0)]
        large = [SourcePoint(lon=center_lon, lat=center_lat, radius_m=300.0)]

        small_feature = compute_void_feature(BBOX, small)
        large_feature = compute_void_feature(BBOX, large)

        assert small_feature is not None
        assert large_feature is not None
        small_hole_bbox = bbox_of_ring(small_feature.geometry.coordinates[1])
        large_hole_bbox = bbox_of_ring(large_feature.geometry.coordinates[1])
        small_hole_width = small_hole_bbox[2] - small_hole_bbox[0]
        large_hole_width = large_hole_bbox[2] - large_hole_bbox[0]
        assert large_hole_width > small_hole_width
