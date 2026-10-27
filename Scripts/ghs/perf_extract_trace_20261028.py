"""Summarize the official Insights CPU event export for one verified TwinPerf trace."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run', type=Path)
    args = parser.parse_args()
    run = json.loads(args.run.read_text(encoding='utf-8-sig'))
    assert run['success'] and run['trace_enabled'] and run['trace_stop_succeeded']
    trace = Path(run['trace_path'])
    assert trace.stat().st_size == run['trace_file_bytes'] > 0
    source = args.run.with_name('cpu-events.csv')
    rows = list(csv.DictReader(source.open(encoding='utf-8-sig')))
    actions = sorted((r for r in rows if r['TimerName'] == 'GHSTwinPerfAction'), key=lambda r: float(r['StartTime']))
    segments = [s for s in run['segments'] if s['name'] not in ('capture_begin', 'capture_end')]
    assert len(actions) == len(segments) == run['completed_actions'] == 38
    offsets = [float(a['StartTime']) - s['actual_seconds'] for a, s in zip(actions, segments)]
    # Native route timestamps and trace timestamps use the same monotonic clock.
    # The small difference is the time from ticker entry to the action scope.
    assert max(offsets) - min(offsets) < .02, 'Trace actions do not match the native route'
    begin = statistics.median(offsets)
    end = begin + run['measured_seconds']
    selected = [r for r in rows if begin <= float(r['StartTime']) and float(r['EndTime']) <= end]
    groups = {}
    for row in selected:
        groups.setdefault(row['TimerName'], []).append(float(row['Duration']) * 1000)
    def stats(values):
        v = sorted(values)
        return dict(count=len(v), total_ms=sum(v), mean_ms=statistics.fmean(v),
                    p95_ms=v[math.ceil(.95 * len(v))-1], p99_ms=v[math.ceil(.99 * len(v))-1], max_ms=v[-1])
    result = dict(run=str(args.run.resolve()), source=str(source.resolve()),
                  source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  units='milliseconds', window_seconds=[begin, end],
                  window_alignment='median of 38 native action offsets; excludes pre-capture trace tail history',
                  alignment_spread_ms=(max(offsets)-min(offsets))*1000,
                  scopes={k:stats(v) for k,v in sorted(groups.items())},
                  material_clicks=[dict(start=float(r['StartTime']), duration_ms=float(r['Duration'])*1000) for r in selected if r['TimerName']=='GHSTwinScene_PickRay'],
                  actions=[dict(name=s['name'], planned=s['planned_seconds'], duration_ms=float(a['Duration'])*1000) for a,s in zip(actions,segments)],
                  limitations=['Inclusive CPU scopes can overlap; do not sum nested scopes.',
                               'Two deterministic material clicks are not all possible user selections.',
                               'CEF child-process work, input delivery and network latency are not measured here.'])
    assert len(result['material_clicks']) == run['cargo_clicks'] == 2
    target = args.run.with_name('cpu-scope-summary.json')
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(output=str(target), alignment_spread_ms=result['alignment_spread_ms'], material_clicks=result['material_clicks'], scopes=result['scopes']), ensure_ascii=False))


if __name__ == '__main__':
    main()
