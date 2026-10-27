"""Summarize completed native TwinPerf runs without starting UE or changing captures.

Usage: python perf_report_20261028.py [--root Saved/Performance20261028]
        [--output Saved/Performance20261028/report.json] [--self-test]

All timings are milliseconds. Group statistics describe per-run statistics;
they are not pooled percentiles. No FPS gain or causal attribution is inferred.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import sys

REPO = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = REPO / 'Saved' / 'Performance20261028'
REQUIRED = ('FrameTime', 'GPUTime', 'GameThreadTime', 'RenderThreadTime', 'GPU/Total')
STAT_FIELDS = ('mean_ms', 'median_ms', 'p95_ms', 'p99_ms')
CONFIG_FIELDS = (
    'runtime', 'build_configuration', 'rhi', 'render_offscreen', 'window_mode',
    'map', 'viewport', 'gpu', 'cpu', 'engine_version', 'route_version',
    'duration_seconds', 'warmup_seconds', 'route_cycle_seconds', 'trace_enabled',
    'cargo_fixture', 'cargo_fixture_version', 'cargo_fixture_metadata',
    'cargo_fixture_instance_count', 'cargo_fixture_slot_count',
    'cargo_fixture_visible_candidates', 'equipment_count', 'facility_count',
    'observed_cvars', 'input_scope', 'poi_mode',
)
CAPACITY_FIELDS = ('rack_capacity', 'floor_capacity', 'rack_total_slots',
                   'floor_total_slots', 'rack_visible_slots', 'floor_visible_groups',
                   'registered_components', 'shared_materials', 'storage_visible')
FAMILIES = (
    ('Baseline', r'^(?:Current)?Baseline'),
    ('ShadowAuto', r'^ShadowAuto'), ('ShadowOff', r'^ShadowOff'), ('TAA', r'^TAA'),
    ('TrafficOff', r'^TrafficOff'), ('TrafficHidden', r'^TrafficHidden'),
)
EXPECTED_VARIANT = {'Baseline': 'baseline', 'TAA': 'baseline',
                    'ShadowAuto': 'shadow-auto', 'ShadowOff': 'shadow-off',
                    'TrafficOff': 'traffic-off', 'TrafficHidden': 'traffic-hidden'}


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def family_for(label, trace):
    for family, pattern in FAMILIES:
        if re.match(pattern, label, re.I):
            return family
    return 'OtherTrace' if trace else None


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_metric(name, metric, frames):
    if not isinstance(metric, dict):
        raise ValueError('Metric is not an object: ' + name)
    count = metric.get('count')
    if not isinstance(count, int) or isinstance(count, bool) or not 0 < count <= frames:
        raise ValueError('Invalid sample count: ' + name)
    if name in REQUIRED and count != frames:
        raise ValueError('Required metric does not cover all frames: ' + name)
    for key in STAT_FIELDS:
        if not finite(metric.get(key)) or metric[key] < 0:
            raise ValueError('Invalid metric statistic: ' + name + '.' + key)
    if not metric['median_ms'] <= metric['p95_ms'] <= metric['p99_ms']:
        raise ValueError('Non-monotonic metric percentiles: ' + name)


def variant_evidence(run_path, run, family):
    """A label alone never proves a non-baseline intervention was applied."""
    expected = EXPECTED_VARIANT.get(family)
    native = run.get('variant_setup')
    if native is not None:
        if not isinstance(native, dict) or native.get('success') is not True:
            raise ValueError('Native variant_setup did not succeed')
        name = native.get('name')
        if expected and name != expected:
            raise ValueError('Variant does not match label family: ' + str(name))
        if run.get('variant') != name:
            raise ValueError('Native variant and setup name disagree')
        if run.get('variant_restored') is False:
            raise ValueError('Native variant restoration failed')
        implementation = native.get('implementation')
        if not isinstance(implementation, str) or not implementation.strip():
            raise ValueError('Native variant implementation is not recorded')
        if native.get('applied_before_warmup') is not True:
            raise ValueError('Native variant was not verified before warmup')
        return {'source': 'native variant_setup', 'name': name, 'success': True,
                'implementation': implementation}
    pid = run.get('process_id')
    candidate = run_path.parent.parent / ('variant-' + str(run.get('label')) + '-' + str(pid) + '.json')
    if candidate.exists():
        evidence = load(candidate)
        if evidence.get('success') is not True or evidence.get('status') != 'applied':
            raise ValueError('Python variant manifest failed or was not applied')
        if evidence.get('pid') != pid or evidence.get('label') != run.get('label'):
            raise ValueError('Python variant manifest identity mismatch')
        if expected and evidence.get('variant') != expected:
            raise ValueError('Python variant does not match label family')
        if evidence.get('native_status_at_setup') not in ('discovering', 'warmup'):
            raise ValueError('Variant setup was not before capture')
        if Path(evidence.get('native_report', '')).resolve() != run_path.resolve():
            raise ValueError('Python variant manifest belongs to another native report')
        if evidence.get('map_unchanged') is not True:
            raise ValueError('Variant did not verify unchanged map')
        return {'source': str(candidate), 'name': evidence.get('variant'), 'success': True,
                'sha256': sha(candidate), 'map_sha256': evidence.get('map_sha256'),
                'metadata_sha256': evidence.get('metadata_sha256'),
                'implementation': 'python-setup-manifest',
                'setup_script_sha256': evidence.get('setup_script_sha256')}
    if expected not in (None, 'baseline'):
        raise ValueError('Non-baseline label lacks verified variant evidence')
    return {'source': 'completed native route only', 'name': run.get('variant', 'baseline'),
            'success': None, 'implementation': 'legacy-unrecorded',
            'warning': 'No separate variant setup record; do not infer an intervention.'}


def validate_launch(manifest, run, evidence, family):
    if manifest.get('label') != run.get('label') or manifest.get('pid') != run.get('process_id'):
        raise ValueError('Launch manifest label/PID does not match native run')
    if type(manifest.get('trace')) is not bool or manifest['trace'] != run['trace_enabled']:
        raise ValueError('Launch trace setting does not match native run')
    if manifest.get('variant') != evidence['name'] or run.get('variant', evidence['name']) != manifest['variant']:
        raise ValueError('Launch variant does not match applied variant')
    if type(manifest.get('diagnosticTAA')) is not bool:
        raise ValueError('Launch manifest lacks diagnosticTAA flag')
    if family == 'TAA' and not manifest['diagnosticTAA']:
        raise ValueError('TAA label lacks explicit diagnosticTAA launch flag')
    if manifest['diagnosticTAA'] and str(run.get('observed_cvars', {}).get('r.AntiAliasingMethod')) != '2':
        raise ValueError('Diagnostic TAA was requested but native AA readback is not 2')
    for key in ('project', 'processStartUtc'):
        if not isinstance(manifest.get(key), str) or not manifest[key].strip():
            raise ValueError('Launch manifest lacks ' + key)
    for key in ('testModuleSha256', 'sourceMapSha256'):
        if not isinstance(manifest.get(key), str) or not re.fullmatch(r'[0-9a-fA-F]{64}', manifest[key]):
            raise ValueError('Launch manifest lacks valid ' + key)
    declared_map = evidence.get('map_sha256') or run.get('map_sha256')
    if declared_map and declared_map.lower() != manifest['sourceMapSha256'].lower():
        raise ValueError('Launch and variant map hashes disagree')
    return {'status': 'verified-owned-launch', 'project': str(Path(manifest['project']).resolve()),
            'test_module_sha256': manifest['testModuleSha256'].lower(),
            'source_map_sha256': manifest['sourceMapSha256'].lower(),
            'background_condition': (manifest.get('backgroundCondition') or 'unknown-background'),
            'diagnostic_taa': manifest['diagnosticTAA'],
            'process_start_utc': manifest['processStartUtc'],
            'source_commit': manifest.get('sourceCommit'),
            'variant_implementation': evidence['implementation']}


def launch_evidence(run_path, run, evidence, family):
    candidate = run_path.parent.parent / ('launch-' + run['label'] + '.json')
    if not candidate.exists():
        return {'status': 'legacy-provisional', 'project': None, 'test_module_sha256': None,
                'source_map_sha256': evidence.get('map_sha256') or run.get('map_sha256'),
                'background_condition': 'unknown-background',
                'diagnostic_taa': None, 'variant_implementation': evidence['implementation'],
                'warning': 'No owned launch manifest; kept in a separate provisional configuration group.'}
    result = validate_launch(load(candidate), run, evidence, family)
    result.update(path=str(candidate.resolve()), sha256=sha(candidate))
    return result


def trace_evidence(run_path, run):
    if not run['trace_enabled']:
        return {'enabled': False, 'validated': False}
    for key in ('trace_start_succeeded', 'trace_connected', 'trace_connected_before_stop',
                'trace_stop_succeeded', 'trace_file_exists'):
        if run.get(key) is not True:
            raise ValueError('Trace run lacks successful recording evidence: ' + key)
    size = run.get('trace_file_bytes')
    if not finite(size) or size <= 0 or int(size) != size:
        raise ValueError('Trace run has no recorded nonempty file size')
    trace_name, destination = run.get('trace_path'), run.get('trace_destination')
    if not isinstance(trace_name, str) or not trace_name or not isinstance(destination, str) or not destination:
        raise ValueError('Trace path/destination not recorded')
    original, target = Path(trace_name), Path(destination)
    if original.resolve() != target.resolve():
        raise ValueError('Trace recording destination differs from expected file')
    actual = original if original.is_file() else run_path.with_name(original.name)
    if not actual.is_file() or actual.stat().st_size != int(size):
        raise ValueError('Trace file is missing, empty or differs from recorded size')
    return {'enabled': True, 'validated': True, 'path': str(actual.resolve()), 'bytes': int(size),
            'verification': 'native start/connection/stop flags and physical nonzero file size; trace not parsed here'}


def read_run(run_path):
    run = load(run_path)
    if run.get('success') is not True or run.get('status') != 'complete':
        raise ValueError('Native run is failed or not complete: ' + str(run.get('status')))
    if type(run.get('trace_enabled')) is not bool:
        raise ValueError('Missing explicit trace_enabled flag')
    trace = trace_evidence(run_path, run)
    label = run.get('label')
    if not isinstance(label, str) or not label:
        raise ValueError('Missing label')
    family = family_for(label, run['trace_enabled'])
    if family is None:
        raise ValueError('Label is outside the configured families: ' + label)
    for key in ('runtime', 'rhi', 'map', 'cargo_fixture', 'build_configuration', 'gpu', 'cpu', 'engine_version'):
        if not isinstance(run.get(key), str) or not run[key] or run[key].lower() in ('unknown', 'unavailable'):
            raise ValueError('Missing comparison metadata: ' + key)
    summary_path = run_path.with_name('summary.json')
    if not summary_path.exists():
        raise ValueError('Completed run has no summary.json yet')
    summary = load(summary_path)
    if summary.get('configuration') != run:
        raise ValueError('summary.configuration does not match current run.json')
    capture = summary.get('capture', {})
    if capture.get('units') != 'milliseconds' or capture.get('route_markers_present') is not True:
        raise ValueError('Summary lacks milliseconds/native route-marker evidence')
    if capture.get('sample_window') != 'after_begin_through_end' or run.get('route_version', 0) < 2:
        raise ValueError('Unsupported or mismatched route/sample-window version')
    frames = capture.get('measured_frames')
    if not isinstance(frames, int) or isinstance(frames, bool) or frames <= 0:
        raise ValueError('Invalid measured frame count')
    if not finite(run.get('measured_seconds')) or run['measured_seconds'] < 90 or run.get('warmup_seconds', 0) < 15:
        raise ValueError('Run lacks full duration and warmup')
    if not run.get('cargo_clicks'):
        raise ValueError('Run lacks successful material-click evidence')
    metrics = capture.get('metrics')
    if not isinstance(metrics, dict) or any(key not in metrics for key in REQUIRED):
        raise ValueError('Summary lacks required Frame/GPU/GT/RT timing metrics')
    selected = {key: value for key, value in metrics.items() if key in REQUIRED or key.startswith('GPU/')}
    for name, metric in selected.items():
        validate_metric(name, metric, frames)
    csv_path = Path(capture.get('csv', ''))
    if not csv_path.is_file():
        csv_path = run_path.with_name('frames.csv')
    if not csv_path.is_file() or sha(csv_path) != capture.get('csv_sha256'):
        raise ValueError('Source CSV is missing or hash differs from summary')
    evidence = variant_evidence(run_path, run, family)
    launch = launch_evidence(run_path, run, evidence, family)
    config = {key: run.get(key) for key in CONFIG_FIELDS}
    capacity = run.get('cargo_fixture_capacity', {})
    config['capacity_state'] = {key: capacity.get(key) for key in CAPACITY_FIELDS}
    config['variant'] = evidence['name']
    config['provenance_status'] = launch['status']
    config['project'] = launch['project']
    config['test_module_sha256'] = launch['test_module_sha256']
    config['source_map_sha256'] = launch['source_map_sha256']
    config['background_condition'] = launch['background_condition']
    config['diagnostic_taa'] = launch['diagnostic_taa']
    config['variant_implementation'] = evidence['implementation']
    config['variant_setup_script_sha256'] = evidence.get('setup_script_sha256')
    for key in ('map_sha256', 'metadata_sha256'):
        config[key] = evidence.get(key) or run.get(key)
    return {'label': label, 'family': family, 'trace_enabled': run['trace_enabled'],
            'run': str(run_path.resolve()), 'run_sha256': sha(run_path),
            'summary': str(summary_path.resolve()), 'summary_sha256': sha(summary_path),
            'csv_sha256': capture['csv_sha256'], 'process_id': run.get('process_id'),
            'measured_frames': frames, 'measured_seconds': run['measured_seconds'],
            'variant_evidence': evidence, 'launch_evidence': launch,
            'trace_evidence': trace, 'configuration': config, 'metrics': selected}


def distribution(values):
    return {'run_count': len(values), 'median': statistics.median(values),
            'min': min(values), 'max': max(values), 'range': max(values) - min(values)}


def aggregate(runs):
    result = {}
    names = sorted(set().union(*(run['metrics'].keys() for run in runs)))
    for name in names:
        present = [run for run in runs if name in run['metrics']]
        result[name] = {
            'runs_with_metric': len(present), 'runs_missing_metric': len(runs) - len(present),
            'missing_labels': [run['label'] for run in runs if name not in run['metrics']],
            'per_run': [{'label': run['label'], 'run': run['run'],
                         'sample_count': run['metrics'][name]['count'],
                         **{key: run['metrics'][name][key] for key in STAT_FIELDS}}
                        for run in present],
            'across_runs': {key: distribution([run['metrics'][name][key] for run in present])
                            for key in STAT_FIELDS},
        }
    return result


def build_report(root):
    accepted, excluded = [], []
    # Only direct native run folders; never recurse into IsolatedProject/caches.
    for run_path in sorted(root.glob('*/run.json')):
        try:
            accepted.append(read_run(run_path))
        except (ValueError, TypeError, KeyError, OSError) as error:
            excluded.append({'run': str(run_path.resolve()), 'reason': str(error)})
    buckets = {}
    for run in accepted:
        fingerprint = hashlib.sha256(canonical(run['configuration']).encode()).hexdigest()
        key = (run['family'], run['trace_enabled'], fingerprint)
        buckets.setdefault(key, []).append(run)
    groups = []
    for (family, trace, fingerprint), runs in sorted(buckets.items()):
        groups.append({'family': family, 'trace_enabled': trace, 'configuration_id': fingerprint,
                       'run_count': len(runs), 'configuration': runs[0]['configuration'],
                       'runs': [{key: value for key, value in run.items() if key != 'metrics'} for run in runs],
                       'metrics': aggregate(runs),
                       'repeatability_warning': 'One run only; no repeatability range established.' if len(runs) < 2 else None})
    comparisons = []
    for index, left in enumerate(groups):
        for right in groups[index + 1:]:
            keys = sorted(set(left['configuration']) | set(right['configuration']))
            differences = {key: {'left': left['configuration'].get(key), 'right': right['configuration'].get(key)}
                           for key in keys if left['configuration'].get(key) != right['configuration'].get(key)}
            comparisons.append({'left_family': left['family'], 'left_configuration_id': left['configuration_id'],
                                'right_family': right['family'], 'right_configuration_id': right['configuration_id'],
                                'exact_configuration_match': not differences,
                                'trace_comparison_allowed': left['trace_enabled'] == right['trace_enabled'],
                                'differences': differences,
                                'causality_assessed': False})
    return {'schema_version': 1, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
            'root': str(root.resolve()), 'units': 'milliseconds',
            'accepted_runs': len(accepted), 'excluded_runs': excluded,
            'non_trace_groups': [group for group in groups if not group['trace_enabled']],
            'trace_groups': [group for group in groups if group['trace_enabled']],
            'configuration_comparisons': comparisons,
            'method': {'aggregation': 'Median/min/max/range of each run mean, median, P95 and P99; runs equally weighted.',
                       'pooled_percentiles': False, 'missing_gpu_passes': 'Reported as missing, never filled with zero.',
                       'source_integrity': 'run success, exact summary configuration, CSV SHA-256, applied variant and owned launch identity/hashes checked when present.',
                       'label_alias': 'CurrentBaseline* is included in Baseline; unknown non-trace labels excluded.',
                       'trace_policy': 'Trace runs require native start/connection/stop and a physical nonempty file; never pooled with non-trace runs.',
                       'legacy_policy': 'Missing launch manifests remain separate legacy-provisional groups; never pooled with verified owned launches.',
                       'causal_claims': False, 'fps_gain_claims': False},
            'limitations': ['GPU passes may be nested/overlapping; do not sum them as independent costs.',
                            'Traffic-off changes simulation, instance updates and dynamic render/shadow work together.',
                            'Random traffic and startup phase can differ; use repeated comparable runs.',
                            'These uncapped local render timings do not measure Pixel Streaming latency or remote FPS.']}


def self_test():
    assert family_for('CurrentBaseline01', False) == 'Baseline'
    assert family_for('ShadowAuto03', False) == 'ShadowAuto'
    assert family_for('ClickTrace01', True) == 'OtherTrace'
    assert family_for('Unrelated', False) is None
    metric = {'count': 10, 'mean_ms': 4., 'median_ms': 3., 'p95_ms': 8., 'p99_ms': 9.}
    validate_metric('FrameTime', metric, 10)
    try:
        validate_metric('FrameTime', {**metric, 'mean_ms': float('nan')}, 10)
        raise AssertionError('NaN accepted')
    except ValueError:
        pass
    a = {'label': 'a', 'run': 'a/run.json', 'metrics': {'FrameTime': metric, 'GPU/Example': metric}}
    b = {'label': 'b', 'run': 'b/run.json', 'metrics': {'FrameTime': {**metric, 'mean_ms': 6.}}}
    result = aggregate([a, b])
    assert result['FrameTime']['across_runs']['mean_ms'] == {'run_count': 2, 'median': 5., 'min': 4., 'max': 6., 'range': 2.}
    assert result['GPU/Example']['runs_missing_metric'] == 1
    assert result['GPU/Example']['across_runs']['mean_ms']['median'] == 4.
    try:
        variant_evidence(Path('unused/run.json'), {'variant': 'shadow-auto',
                         'variant_setup': {'name': 'shadow-auto', 'success': False}}, 'ShadowAuto')
        raise AssertionError('Failed variant accepted')
    except ValueError:
        pass
    assert variant_evidence(Path('unused/run.json'), {'variant': 'shadow-auto',
                            'variant_setup': {'name': 'shadow-auto', 'success': True,
                                              'implementation': 'native-runtime-v1', 'applied_before_warmup': True}},
                            'ShadowAuto')['success'] is True
    sample_run = {'label': 'Baseline01', 'process_id': 17, 'trace_enabled': False,
                  'variant': 'baseline', 'observed_cvars': {'r.AntiAliasingMethod': '4'}}
    sample_launch = {'label': 'Baseline01', 'pid': 17, 'trace': False, 'diagnosticTAA': False,
                     'variant': 'baseline', 'project': 'Test.uproject', 'processStartUtc': '2026-10-28T00:00:00Z',
                     'testModuleSha256': 'a' * 64, 'sourceMapSha256': 'b' * 64}
    applied = {'name': 'baseline', 'implementation': 'native-runtime-v1'}
    assert validate_launch(sample_launch, sample_run, applied, 'Baseline')['test_module_sha256'] == 'a' * 64
    assert validate_launch(sample_launch, sample_run, applied, 'Baseline')['background_condition'] == 'unknown-background'
    assert validate_launch({**sample_launch, 'backgroundCondition': 'user-editor-minimized-figma-static'},
                           sample_run, applied, 'Baseline')['background_condition'] == 'user-editor-minimized-figma-static'
    try:
        validate_launch({**sample_launch, 'pid': 18}, sample_run, applied, 'Baseline')
        raise AssertionError('Mismatched launch PID accepted')
    except ValueError:
        pass
    try:
        trace_evidence(Path('unused/run.json'), {'trace_enabled': True, 'success': True})
        raise AssertionError('Trace with no start/file evidence accepted')
    except ValueError:
        pass
    class FakeRoot:
        def glob(self, _):
            return [Path(name + '/run.json') for name in ('baseline', 'trace', 'other-map', 'other-dll', 'legacy', 'unknown-background', 'failed')]
        def resolve(self):
            return Path('self-test-no-files')
    def fake_read_run(path):
        label = path.parent.name
        if label == 'failed':
            raise ValueError('injected failed run')
        trace = label == 'trace'
        return {'label': label, 'run': str(path), 'family': 'Baseline',
                'trace_enabled': trace,
                'configuration': {'trace_enabled': trace, 'map': 'B' if label == 'other-map' else 'A',
                                  'test_module_sha256': 'b' * 64 if label == 'other-dll' else 'a' * 64,
                                  'background_condition': 'unknown-background' if label == 'unknown-background' else 'user-editor-minimized-figma-static',
                                  'provenance_status': 'legacy-provisional' if label == 'legacy' else 'verified-owned-launch'},
                'metrics': a['metrics']}
    original_reader = globals()['read_run']
    try:
        globals()['read_run'] = fake_read_run
        grouped = build_report(FakeRoot())
    finally:
        globals()['read_run'] = original_reader
    assert len(grouped['non_trace_groups']) == 5, 'Different maps, DLLs, background conditions and legacy provenance must not be pooled'
    assert len(grouped['trace_groups']) == 1, 'Trace must remain separate'
    assert len(grouped['excluded_runs']) == 1, 'Failed run must be excluded'
    assert any('map' in row['differences'] for row in grouped['configuration_comparisons'])
    print(json.dumps({'self_test': 'passed', 'UE_started': False, 'capture_files_changed': False}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    parser.add_argument('--output', type=Path, help='Defaults to ROOT/performance-report-20261028.json')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    root = args.root.resolve()
    if not root.is_dir():
        parser.error('Input root does not exist')
    output = (args.output or root / 'performance-report-20261028.json').resolve()
    if output.name in ('run.json', 'summary.json') or output.suffix.lower() != '.json':
        parser.error('Output must be a separate JSON report, not run.json/summary.json')
    report = build_report(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps({'output': str(output), 'accepted_runs': report['accepted_runs'],
                      'excluded_runs': len(report['excluded_runs']),
                      'non_trace_groups': len(report['non_trace_groups']),
                      'trace_groups': len(report['trace_groups']),
                      'causal_claims': False, 'fps_gain_claims': False}, ensure_ascii=False))
    if not report['accepted_runs']:
        sys.exit(2)


if __name__ == '__main__':
    main()
