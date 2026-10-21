"""Summarize three matching baseline/optimized captures without re-reading CSVs."""
import argparse
import json
import statistics
from pathlib import Path

from perf_analyze import comparison_issues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    runs = {}
    for variant in ('Baseline', 'Optimized'):
        for index in range(1, 4):
            label = f'{variant}{index:02}'
            candidates = sorted(args.root.glob(f'{label}_*/summary.json'))
            if not candidates:
                raise ValueError(f'Missing completed capture: {label}')
            path = candidates[-1]
            data = json.loads(path.read_text(encoding='utf-8'))
            report = data['configuration']
            if report.get('label') != label or not report.get('success'):
                raise ValueError(f'Invalid report: {path}')
            if not data['capture']['route_markers_present']:
                raise ValueError(f'Missing route markers: {path}')
            runs[label] = dict(summary=str(path.resolve()), **data)
    reference = runs['Baseline01']['configuration']
    for label, run in runs.items():
        issues = comparison_issues(reference, run['configuration'])
        if issues:
            raise ValueError(f'Incomparable {label}: {issues}')
    metrics = {}
    for name in ('FrameTime', 'GameThreadTime', 'RenderThreadTime', 'GPUTime', 'GPU/Total'):
        metrics[name] = {}
        for field in ('mean_ms', 'p95_ms', 'p99_ms', 'over_budget_percent',
                      'over_16_67_ms_count', 'over_33_33_ms_count'):
            pair = {}
            for variant in ('Baseline', 'Optimized'):
                values = [runs[f'{variant}{index:02}']['capture']['metrics'][name][field]
                          for index in range(1, 4)]
                pair[variant.lower()] = dict(values=values, median=statistics.median(values),
                                             minimum=min(values), maximum=max(values))
            before = pair['baseline']['median']
            after = pair['optimized']['median']
            pair['median_delta'] = after-before
            pair['median_change_percent'] = (100*(after-before)/before) if before else None
            metrics[name][field] = pair
    result = dict(comparable=True, runs={label: run['summary'] for label, run in runs.items()},
                  aggregation='Median and range of three independent 90-second captures per variant.',
                  metrics=metrics,
                  note='Uncapped 1080p offscreen Development rendering. Not Pixel Streaming or presentation latency.')
    output = args.root/'matrix_summary.json'
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
