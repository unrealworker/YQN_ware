"""Geometry and constrained placement checks for the independent V2 planner."""
import unittest
from prepare_rack_spacing_v2 import forbidden_x_shift, solve_rows


class SpacingTests(unittest.TestCase):
    def test_forbidden_interval_uses_full_load_depth(self):
        rack = dict(position_m=[0, 0], size_m=[1.2, 3.7], rotation_deg=0)
        column = dict(position_m=[.4, 0], size_m=[.6, .6], rotation_deg=0)
        lo, hi = forbidden_x_shift(rack, column)
        self.assertAlmostEqual(lo, -.5)
        self.assertAlmostEqual(hi, 1.3)

    def test_separate_y_cannot_block_x_motion(self):
        rack = dict(position_m=[0, 0], size_m=[1.2, 3.7], rotation_deg=0)
        column = dict(position_m=[.4, 5], size_m=[.6, .6], rotation_deg=0)
        self.assertIsNone(forbidden_x_shift(rack, column))

    def test_neighbor_pushed_without_crossing(self):
        shifts = solve_rows([0, 1.5], [[], [(-.3, .7)]], [1.5], step=.01)
        self.assertAlmostEqual(shifts[0], -.3)
        self.assertAlmostEqual(shifts[1], -.3)
        self.assertGreaterEqual(1.5 + shifts[1] - shifts[0], 1.5 - 1e-9)

    def test_column_between_pair_widens_gap(self):
        shifts = solve_rows([0, 1.5], [[(-.1, 1.5)], [(-1.5, .2)]], [1.5], step=.01)
        self.assertAlmostEqual(shifts[0], -.1)
        self.assertAlmostEqual(shifts[1], .2)


if __name__ == '__main__':
    unittest.main()
