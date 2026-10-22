"""Behavior tests for the integer slot ordering shared by CPU and material."""
import importlib.util
import math
from pathlib import Path
import unittest

MODULE = Path(__file__).with_name('storage_capacity_rules.py')


class StorageCapacityRulesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if MODULE.exists():
            spec = importlib.util.spec_from_file_location('capacity_rules', MODULE)
            cls.rules = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.rules)
        else:
            cls.rules = None

    def test_full_slot_permutation_has_exact_counts_and_monotone_recovery(self):
        self.assertIsNotNone(self.rules, 'Stable complete-slot capacity rules have not been implemented')
        for count, default, expected in [(25056, .8, 20045), (7530, 1., 7530)]:
            slots = list(range(count))
            ranks = [self.rules.slot_rank(i, count) for i in slots]
            self.assertEqual(sorted(ranks), slots)
            visible = lambda c: {i for i in slots if self.rules.is_visible(i, count, c)}
            self.assertEqual(visible(0.), set())
            self.assertEqual(visible(1.), set(slots))
            self.assertEqual(len(visible(default)), expected)
            self.assertTrue(visible(.15).issubset(visible(.8)))
            # A 1% change controls complete slots with no partial-stack state.
            self.assertEqual(len(visible(.01)), 251 if count == 25056 else 75)

    def test_invalid_and_out_of_range_values_do_not_poison_visibility(self):
        self.assertIsNotNone(self.rules, 'Capacity input normalization has not been implemented')
        self.assertEqual(self.rules.clamp_capacity(-4., .8), 0.)
        self.assertEqual(self.rules.clamp_capacity(4., .8), 1.)
        self.assertEqual(self.rules.clamp_capacity(float('nan'), .8), .8)
        self.assertEqual(self.rules.clamp_capacity(float('inf'), 1.), 1.)
        self.assertEqual(self.rules.slot_rank(0, 25056), 17)
        self.assertEqual(self.rules.slot_rank(1, 25056), 114)
        self.assertFalse(self.rules.is_visible(-1, 7530, 1.))

    def test_box_mapping_preserves_separate_levels_and_frame(self):
        self.assertIsNotNone(self.rules, 'Local slot mapping has not been implemented')
        stacks = [dict(level=1, column=1, base_z_m=0., stack_top_z_m=1.2, pallet_center_x_m=-.6),
                  dict(level=2, column=1, base_z_m=2., stack_top_z_m=3.2, pallet_center_x_m=-.6)]
        boxes = self.rules.slot_boxes(stacks, 1., 1.2)
        for actual, expected in zip(boxes[0]['min_cm'], [-110., -60., 0.]):
            self.assertAlmostEqual(actual, expected)
        for actual, expected in zip(boxes[1]['max_cm'], [-10., 60., 320.]):
            self.assertAlmostEqual(actual, expected)
        self.assertEqual(self.rules.find_slot(boxes, [-60., 0., 40.]), 0)
        self.assertEqual(self.rules.find_slot(boxes, [-60., 0., 240.]), 1)
        self.assertIsNone(self.rules.find_slot(boxes, [-60., 0., 170.]))


if __name__ == '__main__':
    unittest.main()
