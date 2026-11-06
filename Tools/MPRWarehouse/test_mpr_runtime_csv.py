"""Exercise the pure CSV parser without importing Unreal or starting a capture."""
import ast
import csv
import hashlib
import io
import math
from pathlib import Path
import statistics
import tempfile
import unittest


SOURCE = Path(__file__).with_name('profile_mpr_runtime.py')
tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
functions = [node for node in tree.body
             if isinstance(node, ast.FunctionDef) and node.name in ('stats', 'parse_csv')]
assert len(functions) == 2
namespace = dict(csv=csv, hashlib=hashlib, io=io, math=math, statistics=statistics)
exec(compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE), 'exec'), namespace)
parse_csv = namespace['parse_csv']


class NativeCsvTests(unittest.TestCase):
    initial = ['EVENTS', 'FrameTime', 'GameThreadTime', 'RenderThreadTime', 'GPUTime', 'GPU/BasePass']

    def fixture(self, dynamic=False):
        # One retained spike proves that parsing does not drop slow frames.
        frames = [['', '120' if i == 17 else '100', '4', '8', '9', '7'] for i in range(120)]
        final = list(self.initial)
        if dynamic:
            final += ['Scheduler/LateStat', 'GPU/FrameRenderFinish']
            for index, row in enumerate(frames):
                if index >= 30:
                    row.append('0')
                if index >= 70:
                    row.append('0.5')
        return [list(self.initial), *frames, final, ['[HasHeaderRowAtEnd]', '1']]

    def parse(self, rows):
        with tempfile.TemporaryDirectory(prefix='mpr_csv_') as folder:
            path = Path(folder)/'capture.csv'
            with path.open('w', encoding='utf-8', newline='') as stream:
                csv.writer(stream).writerows(rows)
            return parse_csv(path)

    def test_same_width_keeps_all_frames_and_spike(self):
        result = self.parse(self.fixture())
        self.assertEqual(result['frame_count'], 120)
        self.assertEqual(result['metrics']['FrameTime']['max_ms'], 120)
        self.assertEqual(result['metrics']['FrameTime']['over_50ms_count'], 120)
        self.assertAlmostEqual(result['native_frame_time_seconds'], 12.02)
        self.assertEqual(result['gpu_evidence']['unregistered_tail_pass_zero_fill_counts'], {})

    def test_append_only_columns_zero_fill_only_unregistered_tail(self):
        normal = self.parse(self.fixture())
        dynamic = self.parse(self.fixture(dynamic=True))
        self.assertEqual(dynamic['frame_count'], 120)
        self.assertEqual(dynamic['metrics'], normal['metrics'])
        self.assertEqual(dynamic['native_frame_time_seconds'], normal['native_frame_time_seconds'])
        self.assertEqual(dynamic['gpu_evidence']['gpu_pass_positive_frame_ratio'], 1)
        self.assertEqual(dynamic['gpu_evidence']['unregistered_tail_pass_zero_fill_counts'],
                         {'GPU/FrameRenderFinish': 70})

    def test_core_timing_cannot_be_registered_late(self):
        rows = self.fixture()
        for row in rows[:-1]:
            row[4], row[5] = row[5], row[4]
        rows[0] = rows[0][:-1]
        rows[1] = rows[1][:-1]
        with self.assertRaisesRegex(AssertionError, 'initial native timing'):
            self.parse(rows)

    def test_mid_capture_truncation_is_rejected(self):
        rows = self.fixture(dynamic=True)
        rows[90] = rows[90][:-1]
        with self.assertRaisesRegex(AssertionError, 'row width'):
            self.parse(rows)

    def test_blank_frame_is_rejected_instead_of_dropped(self):
        rows = self.fixture()
        rows[18] = []
        with self.assertRaisesRegex(AssertionError, 'row width'):
            self.parse(rows)

    def test_final_header_cannot_reorder_initial_columns(self):
        rows = self.fixture(dynamic=True)
        rows[-2][2], rows[-2][3] = rows[-2][3], rows[-2][2]
        with self.assertRaisesRegex(AssertionError, 'final header'):
            self.parse(rows)

    def test_invalid_present_timing_is_not_replaced_by_zero(self):
        for value in ('nan', 'inf', '-1', ''):
            for column in (1, 5, 7):
                with self.subTest(value=value, column=column):
                    rows = self.fixture(dynamic=True)
                    rows[100][column] = value
                    with self.assertRaises((AssertionError, ValueError)):
                        self.parse(rows)


if __name__ == '__main__':
    unittest.main()
