"""Road union, hole-preserving triangulation and open-ended curb regressions."""
import unittest

import shapely
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

import park_surfaces as surfaces


class MeshCapture:
    def __init__(self):
        self.calls = []

    def mesh(self, role, vertices, faces):
        self.calls.append((role, vertices, faces))

    def top_triangles(self, z):
        triangles = []
        for _, vertices, faces in self.calls:
            for face in faces:
                if len(face) == 3 and all(abs(vertices[i][2] - z) < 1e-9 for i in face):
                    xy = [(vertices[i][0], vertices[i][1]) for i in face]
                    triangles.append(Polygon(xy))
        return triangles


class RoadUnionTests(unittest.TestCase):
    def test_junction_is_rounded_without_filling_the_whole_convex_hull(self):
        specs = [dict(path=[(-20, 0), (20, 0)], width=8),
                 dict(path=[(0, -20), (0, 20)], width=8)]
        geometry, info = surfaces.road_union(specs, 4, return_metadata=True)
        self.assertGreater(geometry.area, 576)
        self.assertLess(geometry.area, 650)
        self.assertTrue(geometry.covers(Point(4.5, 4.5)))
        self.assertFalse(geometry.covers(Point(12, 12)))
        self.assertEqual(len(info['openings']), 4)
        self.assertTrue(geometry.is_valid)

    def test_disconnected_parallel_roads_do_not_bridge_the_gap(self):
        geometry = surfaces.road_union(
            [dict(path=[(0, 0), (40, 0)], width=4),
             dict(path=[(0, 6), (40, 6)], width=4)], junction_radius=4)
        self.assertEqual(geometry.geom_type, 'MultiPolygon')
        self.assertFalse(geometry.covers(Point(20, 3)))

    def test_endpoint_extension_is_explicit_and_default_is_zero(self):
        plain = surfaces.road_union([dict(path=[(0, 0), (10, 0)], width=4)], 0)
        extended = surfaces.road_union(
            [dict(path=[(0, 0), (10, 0)], width=4, extend_end=3)], 0)
        self.assertEqual(plain.bounds, (0, -2, 10, 2))
        self.assertEqual(extended.bounds, (0, -2, 13, 2))

    def test_closed_loop_has_no_cap_openings_and_retains_courtyard(self):
        geometry, info = surfaces.road_union(
            [dict(path=[(0, 0), (40, 0), (40, 40), (0, 40), (0, 0)], width=6)],
            return_metadata=True)
        self.assertEqual(info['openings'], [])
        self.assertFalse(geometry.covers(Point(20, 20)))

    def test_joined_endpoint_does_not_remove_an_internal_junction_curb(self):
        geometry, info = surfaces.road_union(
            [dict(path=[(-20, 0), (20, 0)], width=8),
             dict(path=[(0, -20), (0, 0)], width=8)], return_metadata=True)
        self.assertEqual(len(info['openings']), 3)
        self.assertTrue(geometry.covers(Point(0, 0)))


class SurfaceEmissionTests(unittest.TestCase):
    def test_constrained_triangles_preserve_hole_area_and_winding(self):
        geometry = Polygon([(0, 0), (20, 0), (20, 20), (0, 20)],
                           [[(8, 8), (12, 8), (12, 12), (8, 12)]])
        capture = MeshCapture()
        stats = surfaces.emit_surface({'mesh': capture.mesh}, geometry, 'Roads', .02)
        triangles = capture.top_triangles(.02)
        self.assertEqual(stats['triangles'], len(triangles))
        self.assertAlmostEqual(sum(t.area for t in triangles), 384)
        self.assertAlmostEqual(unary_union(triangles).area, 384)
        self.assertFalse(unary_union(triangles).covers(Point(10, 10)))
        for triangle in triangles:
            self.assertTrue(shapely.is_ccw(triangle.exterior))
            self.assertTrue(geometry.covers(triangle))

    def test_surface_emits_all_disconnected_components(self):
        geometry = unary_union([box(0, 0, 2, 2), box(5, 0, 8, 3)])
        capture = MeshCapture()
        stats = surfaces.emit_surface(capture, geometry, 'Roads', 0)
        self.assertAlmostEqual(stats['area'], 13)
        self.assertAlmostEqual(unary_union(capture.top_triangles(0)).area, 13)

    def test_curbs_follow_external_edges_and_leave_caps_open(self):
        geometry, info = surfaces.road_union(
            [dict(path=[(0, 0), (40, 0)], width=8)], 0, return_metadata=True)
        capture = MeshCapture()
        stats = surfaces.emit_curb(capture, geometry, width=.35, z=.12,
                                   openings=info['openings'], base_z=0)
        top = unary_union(capture.top_triangles(.12))
        self.assertGreater(top.area, 20)
        self.assertAlmostEqual(top.intersection(geometry).area, 0)
        self.assertAlmostEqual(top.intersection(box(-.35, -4, 0, 4)).area, 0)
        self.assertAlmostEqual(top.intersection(box(40, -4, 40.35, 4)).area, 0)
        self.assertGreater(stats['side_faces'], 0)
        for _, vertices, faces in capture.calls:
            for face in faces:
                if len(face) == 4:
                    self.assertEqual({vertices[i][2] for i in face}, {0, .12})

    def test_merged_junction_has_no_curb_crossing_either_carriageway(self):
        geometry, info = surfaces.road_union(
            [dict(path=[(-20, 0), (20, 0)], width=8),
             dict(path=[(0, -20), (0, 20)], width=8)], return_metadata=True)
        capture = MeshCapture()
        surfaces.emit_curb(capture, geometry, openings=info['openings'])
        top = unary_union(capture.top_triangles(.12))
        self.assertAlmostEqual(top.intersection(box(-10, -4, 10, 4)).area, 0)
        self.assertAlmostEqual(top.intersection(box(-4, -10, 4, 10)).area, 0)


if __name__ == '__main__':
    unittest.main()
