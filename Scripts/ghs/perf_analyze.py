"""Validate native TwinPerf captures and compare like-for-like UE performance.

python perf_analyze.py summarize PATH/TO/run.json
python perf_analyze.py compare BEFORE/run.json AFTER/run.json --output comparison.json
No UE installation or third-party Python packages are required.
"""
import argparse
import csv
import hashlib
import io
import json
import math
import re
import statistics
from pathlib import Path

REQUIRED = ('FrameTime', 'GameThreadTime', 'RenderThreadTime', 'GPUTime', 'GPU/Total')
EVENT = re.compile(r'TwinPerf:([A-Za-z0-9_]+)')
EXECUTION_KEYS = ('build_configuration', 'rhi', 'render_offscreen', 'window_mode')


def stats(values):
    ordered = sorted(values)
    if not ordered:
        raise ValueError('No finite samples')
    return dict(count=len(ordered), mean_ms=statistics.fmean(ordered),
                median_ms=statistics.median(ordered),
                p95_ms=ordered[math.ceil(.95*len(ordered))-1],
                p99_ms=ordered[math.ceil(.99*len(ordered))-1],
                min_ms=ordered[0], max_ms=ordered[-1],
                over_16_67_ms_count=sum(x > 1000/60 for x in ordered),
                over_33_33_ms_count=sum(x > 1000/30 for x in ordered),
                over_budget_percent=100*sum(x > 1000/60 for x in ordered)/len(ordered))


def read_csv(path, route_version=2):
    path = Path(path)
    raw = path.read_bytes()
    text = raw.decode('utf-8-sig')
    if '[HasHeaderRowAtEnd],1' not in text:
        raise ValueError('CSV is incomplete; final metadata marker is missing')
    rows = list(csv.reader(io.StringIO(text)))
    headers = [i for i, row in enumerate(rows) if row and row[0] == 'EVENTS']
    if not headers:
        raise ValueError('Final EVENTS header is missing')
    names = rows[headers[-1]]
    missing = set(REQUIRED)-set(names)
    if missing:
        raise ValueError('Actual CPU/GPU timing columns missing: '+repr(sorted(missing)))
    first = headers[0]+1 if len(headers)>1 else 0
    samples = [row for row in rows[first:headers[-1]] if row and not row[0].startswith('[')]
    # Never substitute wall-clock Python time for GPU measurements.
    selected = {name: names.index(name) for name in names if name in REQUIRED or name.startswith('GPU/')}
    values = {name: [] for name in selected}
    sections = {}
    active = 'unmarked'
    marked_begin = any('TwinPerf:capture_begin' in row[0] for row in samples)
    started = not marked_begin
    end_seen = False
    analyzed = 0
    for row in samples:
        marks = EVENT.findall(row[0])
        ending = 'capture_end' in marks
        if ending and route_version < 2:
            end_seen = True
            break
        for mark in marks:
            if mark == 'capture_begin':
                started = True
            elif mark != 'capture_end':
                active = mark
        # The native core ticker marks boundaries after the frame's scene/Slate
        # work. Version 2 measures complete frames after begin, including end.
        if route_version >= 2 and 'capture_begin' in marks:
            continue
        if not started:
            continue
        section = sections.setdefault(active, {'frames':0, 'values':{name:[] for name in REQUIRED}})
        section['frames'] += 1
        analyzed += 1
        for name, index in selected.items():
            try:
                number = float(row[index])
            except (ValueError, IndexError):
                if name in REQUIRED:
                    raise ValueError(f'Invalid {name} timing at CSV frame {analyzed}')
                continue
            if not math.isfinite(number) or number < 0:
                raise ValueError(f'Non-finite or negative {name} timing')
            values[name].append(number)
            if name in REQUIRED:
                section['values'][name].append(number)
        if ending:
            end_seen = True
            break
    if not analyzed:
        raise ValueError('No measured frames')
    for name in ('GPUTime', 'GPU/Total'):
        if sum(v > 0 for v in values[name]) < analyzed*.95:
            raise ValueError(name+' does not contain valid GPU timestamps for 95% of frames')
    if marked_begin and not end_seen:
        raise ValueError('Measured route started but capture_end is missing')
    metrics = {name:stats(data) for name,data in values.items() if data}
    for section in sections.values():
        section['metrics'] = {name:stats(data) for name,data in section.pop('values').items()}
    return dict(csv=str(path.resolve()), csv_sha256=hashlib.sha256(raw).hexdigest(),
                captured_frames=len(samples), measured_frames=analyzed,
                route_markers_present=marked_begin and end_seen,
                sample_window='after_begin_through_end' if route_version >= 2 else 'begin_through_before_end',
                metrics=metrics, segments=sections,
                duration_from_frame_times_seconds=sum(values['FrameTime'])/1000,
                units='milliseconds', thresholds_ms=[1000/60,1000/30])


def execution_metadata_issues(report):
    if report.get('route_version', 1) < 2:
        return []
    issues = []
    for key in ('build_configuration', 'rhi'):
        value = report.get(key)
        if not isinstance(value, str) or not value.strip() or value.lower() in ('unknown', 'unavailable'):
            issues.append(key)
    if type(report.get('render_offscreen')) is not bool:
        issues.append('render_offscreen')
    if report.get('window_mode') not in ('windowed', 'fullscreen', 'windowed_fullscreen'):
        issues.append('window_mode')
    return issues


def comparison_issues(before, after):
    keys = ['runtime','route_version','viewport','duration_seconds','warmup_seconds',
            'trace_enabled','observed_cvars','gpu','cpu','engine_version','cargo_fixture', *EXECUTION_KEYS]
    invalid = set(execution_metadata_issues(before) + execution_metadata_issues(after))
    return [key for key in keys if key in invalid or before.get(key) != after.get(key)]


def summarize(run_path):
    path = Path(run_path)
    report = json.loads(path.read_text(encoding='utf-8-sig'))
    if not report.get('success') or report.get('status') != 'complete':
        raise ValueError('Native benchmark did not complete successfully: '+str(report.get('error')))
    if report.get('viewport') != [1920,1080] or report.get('measured_seconds',0) < 90:
        raise ValueError('Requires the complete 1080P route of at least 90 seconds')
    if report.get('warmup_seconds',0) < 15 or not report.get('cargo_clicks'):
        raise ValueError('Missing warmup or actual material-click evidence')
    missing = execution_metadata_issues(report)
    if missing:
        raise ValueError('Missing or invalid execution metadata: '+', '.join(missing))
    csv_path = Path(report['csv'])
    if not csv_path.exists():
        csv_path = path.parent/'frames.csv'
    data = read_csv(csv_path, route_version=report.get('route_version', 1))
    if not data['route_markers_present']:
        raise ValueError('CSV lacks native route markers')
    required = {'overview','orbit','agv','forklift','racks','cargo_click','panel_close','panel_open',
                'page_devices','page_orders','page_inventory','page_alerts','page_trace','page_settings','all_poi'}
    if required-set(data['segments']):
        raise ValueError('Route segments missing: '+repr(sorted(required-set(data['segments']))))
    duration = data['duration_from_frame_times_seconds']
    if abs(duration-report['measured_seconds']) > max(2.,report['measured_seconds']*.05):
        raise ValueError('CSV frame duration does not match the native route duration')
    frame = data['metrics']['FrameTime']
    data['sixty_fps_assessment'] = dict(
        p99_within_budget=frame['p99_ms'] <= 1000/60,
        all_frames_within_budget=frame['over_16_67_ms_count']==0,
        note='Uncapped render headroom only. Not a claim of Pixel Streaming delivery or input latency.')
    result = dict(run=str(path.resolve()), configuration=report, capture=data)
    output = path.parent/'summary.json'
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


def compare(before_path, after_path):
    before, after = summarize(before_path), summarize(after_path)
    issues = comparison_issues(before['configuration'],after['configuration'])
    if issues:
        raise ValueError('Incomparable captures: '+', '.join(issues))
    differences = {}
    for name in REQUIRED:
        a,b = before['capture']['metrics'][name], after['capture']['metrics'][name]
        differences[name] = {key:dict(before=a[key],after=b[key],delta=b[key]-a[key])
                             for key in ['mean_ms','p95_ms','p99_ms','over_budget_percent']}
    return dict(comparable=True,before=before['run'],after=after['run'],differences=differences,
                after_sixty_fps_assessment=after['capture']['sixty_fps_assessment'],
                note='Negative delta indicates reduction; use repeated runs and segment metrics before attributing causality.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['summarize','compare'])
    parser.add_argument('before',type=Path)
    parser.add_argument('after',type=Path,nargs='?')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.action=='compare' and args.after is None:
        parser.error('compare requires a second run.json')
    result=compare(args.before,args.after) if args.action=='compare' else summarize(args.before)
    text=json.dumps(result,ensure_ascii=False,indent=2)
    if args.output:
        args.output.write_text(text,encoding='utf-8')
    if args.action=='summarize':
        print(json.dumps({'run':result['run'],'metrics':{k:result['capture']['metrics'][k] for k in REQUIRED},
                          'assessment':result['capture']['sixty_fps_assessment']},ensure_ascii=False,indent=2))
    else:
        print(text)


if __name__=='__main__':
    main()
