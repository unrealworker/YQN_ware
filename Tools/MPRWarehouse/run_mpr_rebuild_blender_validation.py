"""Run unchanged native validation rules in fresh Blender processes.

Ordinary Python entry point. Each process reads the saved blend and roundtrips
at most 64 FBX files. The final report requires exact, nonoverlapping coverage
of one manifest, stable artifact hashes, and successful native exit codes.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'SourceAssets/MPR/rebuild_b50b57'
OUTPUT = ROOT / 'Saved/MPR/rebuild_20261104'
VERIFIER = ROOT / 'Tools/MPRWarehouse/verify_mpr_rebuild_blender.py'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def aggregate_results(manifest, results, hashes):
    """Never interpret a partial batch or native zero exit as full success."""
    expected_rows = manifest['meshes']
    meshes, stop, reference = [], 0, None
    for result in results:
        assert result['native_exit_code'] == 0, ('Native validation failed', result['native_exit_code'])
        assert result.get('success') is True, ('Native report failed', result.get('error'))
        batch = result['batch']
        assert batch['start'] == stop, ('Missing/duplicate/out-of-order batch', batch, stop)
        assert batch['total_meshes'] == len(expected_rows)
        assert batch['start'] < batch['stop'] <= len(expected_rows)
        expected = expected_rows[batch['start']:batch['stop']]
        rows = result['meshes']
        assert [row['name'] for row in rows] == [row['name'] for row in expected], 'Batch mesh coverage differs'
        assert result['fbx_roundtrip_meshes'] == len(expected)
        assert result['triangles'] == sum(row['triangles'] for row in expected)
        for row, original in zip(rows, expected):
            assert row['triangles'] == original['triangles']
            assert row.get('fbx', {}).get('imported') is True, ('Missing native FBX check', row['name'])
            assert row['fbx']['triangles'] == original['triangles']
            if original.get('vertex_color_fade'):
                assert row.get('fbx_color_roundtrip', {}).get('multiset_equal') is True, ('Missing fade roundtrip', row['name'])
        for key, value in hashes.items():
            assert result[key] == value, ('Artifact changed between batches', key)
        checks = {key: result[key] for key in ('source_validation', 'context_validation', 'relative_textures')}
        if reference is None:
            reference = checks
        else:
            assert reference == checks, 'Source/context evidence changed between batches'
        meshes.extend(rows)
        stop = batch['stop']
    assert stop == len(expected_rows), ('Incomplete native validation', stop, len(expected_rows))
    return dict(success=True, scope='Saved Blender and every native FBX roundtrip in isolated processes',
                meshes=meshes, fbx_roundtrip_meshes=len(meshes),
                triangles=sum(row['triangles'] for row in expected_rows),
                batches=[dict(**result['batch'], native_exit_code=result['native_exit_code'],
                              report=result['batch_report'], log=result['batch_log']) for result in results],
                **hashes, **reference)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--blender', type=Path, required=True)
    parser.add_argument('--batch-size', type=int, default=64)
    args = parser.parse_args()
    assert args.blender.is_file(), 'Blender executable missing'
    assert 1 <= args.batch_size <= 64, 'Batch size must remain between 1 and 64'
    manifest_path = SOURCE / 'manifest.json'
    manifest = read(manifest_path)
    blend = (ROOT / manifest['blend']).resolve()
    assert blend.is_relative_to(SOURCE.resolve()) and blend.is_file()
    hashes = dict(manifest_sha256=sha(manifest_path), blend_sha256=sha(blend))
    verifier_hash = sha(VERIFIER)
    run_dir = OUTPUT / 'native_validation_batches' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    run_dir.mkdir(parents=True, exist_ok=False)
    report_path = OUTPUT / 'blender_validation.json'
    if report_path.is_file():
        shutil.copy2(report_path, run_dir / 'previous_report.json')
    results = []
    final = dict(success=False, scope='Isolated native FBX validation', **hashes)
    try:
        for start in range(0, len(manifest['meshes']), args.batch_size):
            stop = min(start + args.batch_size, len(manifest['meshes']))
            target, log = run_dir / f'batch_{start:04d}_{stop:04d}.json', run_dir / f'batch_{start:04d}_{stop:04d}.log'
            assert sha(VERIFIER) == verifier_hash, 'Verifier changed during native validation'
            command = [str(args.blender.resolve()), '--background', '--factory-startup', '--disable-autoexec',
                       '--debug-memory', '--threads', '1', '--python-exit-code', '1',
                       '--python', str(VERIFIER), '--', '--start', str(start), '--stop', str(stop), '--report', str(target)]
            print(f'MPRR_NATIVE_BATCH {start}:{stop}/{len(manifest["meshes"])}', flush=True)
            with log.open('w', encoding='utf-8') as stream:
                environment = dict(os.environ, PYTHONMALLOC='malloc')
                completed = subprocess.run(command, cwd=ROOT, env=environment, stdout=stream, stderr=subprocess.STDOUT,
                                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            result = read(target) if target.is_file() else dict(success=False, error='Native process produced no report')
            result.update(native_exit_code=completed.returncode, batch_report=str(target), batch_log=str(log))
            results.append(result)
            assert completed.returncode == 0 and result.get('success') is True, (
                f'Native batch {start}:{stop} failed', completed.returncode, result.get('active_check'), result.get('error'), str(log))
        assert sha(manifest_path) == hashes['manifest_sha256'] and sha(blend) == hashes['blend_sha256'], 'Artifacts changed during validation'
        assert sha(VERIFIER) == verifier_hash, 'Verifier changed during native validation'
        final = aggregate_results(manifest, results, hashes)
    except Exception:
        final['error'] = traceback.format_exc()
        final['completed_or_failed_batches'] = [dict(path=r['batch_report'], exit_code=r['native_exit_code'],
                                                    success=r.get('success'), active_check=r.get('active_check')) for r in results]
    final.update(verifier_sha256=verifier_hash, batch_run_directory=str(run_dir), native_processes=len(results))
    report_path.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding='utf-8')
    print('MPRR_BLENDER_VALIDATION', final['success'], str(report_path), flush=True)
    if not final['success']:
        print(final['error'], file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
