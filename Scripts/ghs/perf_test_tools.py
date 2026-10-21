"""Pure tests for rejecting invalid performance evidence (no Unreal dependency)."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).with_name('perf_analyze.py')
spec = importlib.util.spec_from_file_location('perf_analyze', MODULE) if MODULE.exists() else None
analyze = importlib.util.module_from_spec(spec) if spec else None
if spec:
    spec.loader.exec_module(analyze)


class EvidenceTests(unittest.TestCase):
    def test_analyzer_available(self):
        self.assertIsNotNone(analyze, 'The performance evidence analyzer must exist')

    @unittest.skipIf(analyze is None, 'Analyzer not implemented yet')
    def test_final_header_and_gpu_validity(self):
        # UE can append GPU columns after its initial header. Never use the first header.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'sample.csv'
            path.write_text('EVENTS,FrameTime\nTwinPerf:overview,10,3,4,5,5\n,20,4,5,6,6\n'
                            'EVENTS,FrameTime,GameThreadTime,RenderThreadTime,GPUTime,GPU/Total\n'
                            '[HasHeaderRowAtEnd],1\n')
            data = analyze.read_csv(path)
            self.assertEqual(data['metrics']['GPUTime']['mean_ms'], 5.5)
            self.assertEqual(data['metrics']['FrameTime']['over_16_67_ms_count'], 1)
            self.assertEqual(data['metrics']['FrameTime']['p99_ms'], 20)
            self.assertEqual(data['segments']['overview']['frames'], 2)

    @unittest.skipIf(analyze is None, 'Analyzer not implemented yet')
    def test_incomplete_or_missing_gpu_cannot_claim_success(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'sample.csv'
            for contents in ['EVENTS,FrameTime\n,10\n',
                             'EVENTS,FrameTime\n,10\nEVENTS,FrameTime\n[HasHeaderRowAtEnd],1\n',
                             'EVENTS,FrameTime,GameThreadTime,RenderThreadTime,GPUTime,GPU/Total\n'
                             ',10,3,4,0,0\nEVENTS,FrameTime,GameThreadTime,RenderThreadTime,GPUTime,GPU/Total\n[HasHeaderRowAtEnd],1\n']:
                path.write_text(contents)
                with self.assertRaises(ValueError):
                    analyze.read_csv(path)

    @unittest.skipIf(analyze is None, 'Analyzer not implemented yet')
    def test_comparison_requires_same_runtime_route_and_quality(self):
        base = {'runtime':'packaged', 'route_version':1, 'viewport':[1920,1080],
                'duration_seconds':90, 'warmup_seconds':15, 'trace_enabled':False,
                'observed_cvars':{'r.ScreenPercentage':'100'}}
        self.assertEqual(analyze.comparison_issues(base, dict(base)), [])
        changed = dict(base, runtime='editor-game')
        self.assertIn('runtime', analyze.comparison_issues(base, changed))
        changed = dict(base, observed_cvars={'r.ScreenPercentage':'70'})
        self.assertIn('observed_cvars', analyze.comparison_issues(base, changed))

    @unittest.skipIf(analyze is None, 'Analyzer not implemented yet')
    def test_route_markers_exclude_setup_and_gpu_drain(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'sample.csv'
            header = 'EVENTS,FrameTime,GameThreadTime,RenderThreadTime,GPUTime,GPU/Total\n'
            path.write_text(header+',1000,1,1,1,1\n'
                            'TwinPerf:capture_begin;TwinPerf:overview,1500,2,3,4,4\n'
                            'TwinPerf:orbit,20,3,4,5,5\n'
                            'TwinPerf:capture_end,500,490,4,5,5\n'
                            ',1000,1,1,1,1\n'+header+'[HasHeaderRowAtEnd],1\n')
            result = analyze.read_csv(path)
            self.assertEqual(result['measured_frames'], 2)
            self.assertEqual(result['metrics']['FrameTime']['mean_ms'], 260)
            self.assertEqual(result['metrics']['FrameTime']['max_ms'], 500)
            self.assertEqual(result['metrics']['FrameTime']['p99_ms'], 500)
            self.assertEqual(result['metrics']['FrameTime']['over_16_67_ms_count'], 2)
            self.assertEqual(result['duration_from_frame_times_seconds'], .52)
            self.assertEqual(result['segments']['orbit']['metrics']['GPUTime']['mean_ms'], 5)
            self.assertTrue(result['route_markers_present'])

    def test_version_one_retains_its_original_marker_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'sample.csv'
            header = 'EVENTS,FrameTime,GameThreadTime,RenderThreadTime,GPUTime,GPU/Total\n'
            path.write_text(header+'TwinPerf:capture_begin,10,2,3,4,4\n'
                            'TwinPerf:orbit,20,3,4,5,5\n'
                            'TwinPerf:capture_end,500,490,4,5,5\n'
                            +header+'[HasHeaderRowAtEnd],1\n')
            result = analyze.read_csv(path, route_version=1)
            self.assertEqual(result['metrics']['FrameTime']['max_ms'], 20)
            self.assertEqual(result['duration_from_frame_times_seconds'], .03)

    def test_comparison_rejects_changed_build_rhi_and_presentation(self):
        base = dict(runtime='packaged', route_version=2, build_configuration='Development',
                    rhi='D3D12', render_offscreen=True, window_mode='windowed')
        self.assertEqual(analyze.comparison_issues(base, dict(base)), [])
        for key, value in [('build_configuration','DebugGame'), ('rhi','D3D11'),
                           ('render_offscreen',False), ('window_mode','fullscreen')]:
            with self.subTest(key=key):
                self.assertIn(key, analyze.comparison_issues(base, dict(base, **{key:value})))

    def test_version_two_rejects_missing_or_invalid_execution_metadata(self):
        base = dict(success=True, status='complete', viewport=[1920,1080], measured_seconds=90,
                    warmup_seconds=15, cargo_clicks=2, runtime='packaged', route_version=2,
                    build_configuration='Development', rhi='D3D12', render_offscreen=True,
                    window_mode='windowed')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'run.json'
            for key in ['build_configuration','rhi','render_offscreen','window_mode']:
                for invalid in [None, '']:
                    bad = dict(base, **{key:invalid})
                    if invalid is None:
                        del bad[key]
                    with self.subTest(key=key, invalid=invalid):
                        self.assertIn(key, analyze.comparison_issues(bad, dict(bad)))
                        path.write_text(json.dumps(bad), encoding='utf-8')
                        with self.assertRaisesRegex(ValueError, 'execution metadata'):
                            analyze.summarize(path)

    @unittest.skipIf(analyze is None, 'Analyzer not implemented yet')
    def test_unfinished_route_and_nan_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'sample.csv'
            header = 'EVENTS,FrameTime,GameThreadTime,RenderThreadTime,GPUTime,GPU/Total\n'
            for body in ['TwinPerf:capture_begin,10,2,3,4,4\n', ',10,2,3,nan,4\n']:
                path.write_text(header+body+header+'[HasHeaderRowAtEnd],1\n')
                with self.assertRaises(ValueError):
                    analyze.read_csv(path)


if __name__ == '__main__':
    unittest.main()
