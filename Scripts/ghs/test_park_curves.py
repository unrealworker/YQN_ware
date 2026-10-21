"""Geometric regressions for the Blender-independent campus path kernel."""
import math
import unittest

import park_curves as curves


def distance(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


class RoundedRoadTests(unittest.TestCase):
    def test_truck_corner_is_an_exact_tangent_radius_18_arc(self):
        path, info = curves.rounded_path(
            [(0, 0), (60, 0), (60, 60)], radius=18,
            max_step=.5, return_metadata=True)
        corner = info['corners'][0]
        self.assertEqual(path[0], (0, 0))
        self.assertEqual(path[-1], (60, 60))
        self.assertAlmostEqual(info['min_radius'], 18)
        for actual, wanted in zip(corner['tangent_in'], (42, 0)):
            self.assertAlmostEqual(actual, wanted)
        for actual, wanted in zip(corner['tangent_out'], (60, 18)):
            self.assertAlmostEqual(actual, wanted)
        self.assertAlmostEqual(corner['center'][0], 42)
        self.assertAlmostEqual(corner['center'][1], 18)
        for p in path:
            if p[0] > 42 and p[1] < 18:
                self.assertAlmostEqual(distance(p, (42, 18)), 18)
        # Radius perpendicular to each adjoining straight proves analytic C1.
        self.assertAlmostEqual(corner['tangent_in'][0] - corner['center'][0], 0)
        self.assertAlmostEqual(corner['tangent_out'][1] - corner['center'][1], 0)
        self.assertTrue(all(0 < distance(a, b) <= .500001
                            for a, b in zip(path, path[1:])))

    def test_clockwise_corner_bends_to_the_correct_side(self):
        path, info = curves.rounded_path(
            [(0, 0), (60, 0), (60, -60)], radius=18,
            return_metadata=True)
        self.assertAlmostEqual(info['corners'][0]['center'][1], -18)
        self.assertTrue(all(p[1] <= 0 for p in path))
        self.assertLess(info['corners'][0]['turn_angle'], 0)

    def test_short_shared_segment_clamps_both_corners_without_reversing(self):
        path, info = curves.rounded_path(
            [(0, 0), (60, 0), (60, 20), (120, 20)], radius=18,
            max_step=.5, return_metadata=True)
        self.assertAlmostEqual(info['min_radius'], 10)
        self.assertTrue(all(b[0] >= a[0] - 1e-8 and b[1] >= a[1] - 1e-8
                            for a, b in zip(path, path[1:])))
        self.assertEqual(info['clamped_corners'], 2)

    def test_road_edges_preserve_width_without_inverted_quads(self):
        center = curves.rounded_path([(0, 0), (60, 0), (60, 60)], radius=18)
        left = curves.offset_path(center, 4.5)
        right = curves.offset_path(center, -4.5)
        self.assertEqual(len(left), len(center))
        for l, r in zip(left, right):
            self.assertAlmostEqual(distance(l, r), 9, delta=.004)
        for i in range(len(center) - 1):
            edge = (right[i][0] - left[i][0], right[i][1] - left[i][1])
            advance = (left[i + 1][0] - left[i][0], left[i + 1][1] - left[i][1])
            self.assertGreater(cross(edge, advance), 0)

    def test_duplicate_controls_do_not_create_zero_length_segments(self):
        path = curves.rounded_path([(0, 0), (0, 0), (20, 0), (20, 0), (20, 20)], 5)
        self.assertTrue(all(distance(a, b) > 0 for a, b in zip(path, path[1:])))

    def test_hairpin_is_rejected_instead_of_emitting_a_spike(self):
        with self.assertRaises(ValueError):
            curves.rounded_path([(0, 0), (20, 0), (0, 0)], radius=5)

    def test_invalid_sampling_parameters_fail_promptly(self):
        with self.assertRaises(ValueError):
            curves.rounded_path([(0, 0), (20, 0)], max_step=0)
        with self.assertRaises(ValueError):
            curves.sample_along([(0, 0), (20, 0)], spacing=0)
        with self.assertRaises(ValueError):
            curves.dash_segments([(0, 0), (20, 0)], dash_length=0)


class ArcLengthTests(unittest.TestCase):
    def test_sampling_carries_distance_across_polyline_vertices(self):
        samples = curves.sample_along([(0, 0), (5, 0), (5, 10)], 4)
        self.assertEqual([s[0] for s in samples], [(0, 0), (4, 0), (5, 3), (5, 7)])
        self.assertEqual([s[2] for s in samples], [0, 4, 8, 12])
        self.assertEqual(samples[-1][1], (0, 1))
        self.assertEqual(curves.path_length([(0, 0), (5, 0), (5, 10)]), 15)

    def test_slice_preserves_corner_and_interpolates_both_endpoints(self):
        path = curves.slice_path([(0, 0), (5, 0), (5, 10)], 3, 9)
        self.assertEqual(path, [(3, 0), (5, 0), (5, 4)])
        self.assertEqual(curves.point_at_distance([(0, 0), (5, 0), (5, 10)], 9),
                         ((5, 4), (0, 1)))

    def test_dashes_survive_dense_sampling_and_cross_corner(self):
        dense = [(i / 4, 0) for i in range(21)] + [(5, i / 4) for i in range(1, 41)]
        dashes = curves.dash_segments(dense, dash_length=4, gap_length=2)
        self.assertEqual(len(dashes), 3)
        self.assertEqual([(d[0], d[-1]) for d in dashes],
                         [((0, 0), (4, 0)), ((5, 1), (5, 5)), ((5, 7), (5, 10))])
        crossing = curves.dash_segments(dense, dash_length=7, gap_length=2)
        self.assertIn((5, 0), crossing[0])
        self.assertEqual(crossing[0][-1], (5, 2))

    def test_dash_phase_is_global_distance_before_first_dash(self):
        dashes = curves.dash_segments([(0, 0), (20, 0)], 4, 3, phase=2)
        self.assertEqual([(d[0], d[-1]) for d in dashes],
                         [((2, 0), (6, 0)), ((9, 0), (13, 0)), ((16, 0), (20, 0))])


class ClosedFenceTests(unittest.TestCase):
    def setUp(self):
        self.path = curves.rounded_path([(0, 0), (60, 0), (60, 40), (0, 40)],
                                        radius=8, closed=True, max_step=.4)

    def test_closed_fence_has_one_closure_and_consistent_offset_seam(self):
        self.assertEqual(self.path[0], self.path[-1])
        self.assertEqual(sum(p == self.path[0] for p in self.path), 2)
        offset = curves.offset_path(self.path, .4, closed=True)
        self.assertEqual(offset[0], offset[-1])
        self.assertEqual(len(offset), len(self.path))
        self.assertTrue(all(distance(a, b) > 0 for a, b in zip(offset, offset[1:])))

    def test_closed_post_spacing_includes_the_seam_without_duplicate_post(self):
        samples = curves.sample_along(self.path, 3.2, closed=True)
        total = curves.path_length(self.path, closed=True)
        distances = [s[2] for s in samples] + [total]
        spans = [b - a for a, b in zip(distances, distances[1:])]
        self.assertGreater(len(samples), 40)
        self.assertLessEqual(max(spans), 3.2)
        self.assertAlmostEqual(min(spans), max(spans))
        self.assertNotEqual(samples[0][0], samples[-1][0])

    def test_closed_slice_wraps_across_seam(self):
        square = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
        self.assertEqual(curves.slice_path(square, 38, 43, closed=True),
                         [(0, 2), (0, 0), (3, 0)])


if __name__ == '__main__':
    unittest.main()
