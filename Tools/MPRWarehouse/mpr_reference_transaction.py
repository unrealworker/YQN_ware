"""File-level rollback for an isolated MPR exterior import; no Unreal API.

begin_transaction(root, planned_assets=paths) precedes every asset/map write.
record_failure(token, error) snapshots outputs after an unsuccessful import.
record_success(token) closes a successful import without deleting its backup.

Restore is explicitly offline and refuses any post-failure file changes. It
restores existing packages, map and ownership bytes and removes only declared
new files whose hashes still match the failed run. Unknown files are untouched.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import uuid

MAP = '/Game/Maps/MPR_CAD_Warehouse'
OWNERSHIP = 'SourceAssets/MPR/scene_ownership.json'
BUILD_REPORT = 'Saved/MPR/reference_v3_build.json'
TRANSACTIONS = 'Saved/MPR/reference_transactions'
SCHEMA = 1
SIDECARS = ('.uexp', '.ubulk', '.uptnl')


class TransactionError(RuntimeError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat()


def _hash(path):
    if not path.exists():
        return None
    if not path.is_file() or path.is_symlink():
        raise TransactionError('Expected a regular file: ' + str(path))
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _safe(root, relative):
    if not isinstance(relative, str) or Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise TransactionError('Unsafe relative path: ' + repr(relative))
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
        raise TransactionError('Path escapes its declared root: ' + relative)
    return path


def _package_paths(package):
    if package == MAP:
        primary = Path('Content/Maps/MPR_CAD_Warehouse.umap')
    elif isinstance(package, str) and re.fullmatch(r'/Game/MPRWarehouse/[A-Za-z0-9_/-]+', package):
        primary = Path('Content/' + package[len('/Game/'):] + '.uasset')
    else:
        raise TransactionError('Package is outside the MPR transaction scope: ' + repr(package))
    return [primary.as_posix()] + [primary.with_suffix(s).as_posix() for s in SIDECARS]


def _report_path(value):
    if not isinstance(value, str) or not re.fullmatch(r'Saved/MPR/[A-Za-z0-9_-]+\.json', value):
        raise TransactionError('Build report must be an explicit JSON file in Saved/MPR: ' + repr(value))
    return value


def _atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', prefix='.mpr-tx-', suffix='.tmp',
                                         dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def _manifest_path(token):
    return Path(token['manifest']) if isinstance(token, dict) else Path(token) / 'transaction.json'


def _load(token):
    path = _manifest_path(token).resolve()
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise TransactionError('Cannot read transaction manifest: ' + str(path)) from error
    if data.get('schema_version') != SCHEMA or data.get('map') != MAP:
        raise TransactionError('Unsupported transaction identity')
    root = Path(data['project_root']).resolve()
    directory = _safe(root, TRANSACTIONS) / data['id']
    if not re.fullmatch(r'[0-9TZ_\-]+[0-9a-f]{12}', data['id']) or path != (directory/'transaction.json').resolve():
        raise TransactionError('Transaction location does not match its declared project')
    expected = {OWNERSHIP, _report_path(data.get('build_report', BUILD_REPORT))}
    for package in [MAP, *data['planned_assets']]:
        expected.update(_package_paths(package))
    if set(data['files']) != expected:
        raise TransactionError('Transaction file list differs from its declared packages')
    for relative, row in data['files'].items():
        _safe(root, relative)
        before = row.get('before_sha256')
        if before is not None and not re.fullmatch(r'[0-9a-f]{64}', before):
            raise TransactionError('Invalid backup digest: ' + relative)
        if row.get('backup') != ('backup/' + relative if before else None):
            raise TransactionError('Backup path does not match source: ' + relative)
        if row['backup']:
            _safe(directory, row['backup'])
    return path, root, directory, data


def begin_transaction(project_root, *, planned_assets, map_path=MAP, build_report=BUILD_REPORT):
    if map_path != MAP:
        raise TransactionError('Unexpected map identity')
    root = Path(project_root).resolve()
    planned = sorted(set(planned_assets))
    if not planned:
        raise TransactionError('An explicit non-empty output package list is required')
    relative_files = {OWNERSHIP, _report_path(build_report)}
    for package in [MAP, *planned]:
        relative_files.update(_package_paths(package))
    paths = {relative: _safe(root, relative) for relative in sorted(relative_files)}
    if not paths['Content/Maps/MPR_CAD_Warehouse.umap'].is_file() or not paths[OWNERSHIP].is_file():
        raise TransactionError('An existing MPR map and ownership manifest are required')
    identity = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ_') + uuid.uuid4().hex[:12]
    directory = _safe(root, TRANSACTIONS) / identity
    directory.mkdir(parents=True, exist_ok=False)
    records = {}
    for relative, source in paths.items():
        before = _hash(source)
        backup = 'backup/' + relative if before else None
        if backup:
            target = _safe(directory, backup)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            if _hash(target) != before or _hash(source) != before:
                raise TransactionError('File changed while backing it up: ' + relative)
        records[relative] = {'before_sha256': before, 'backup': backup}
    data = {'schema_version': SCHEMA, 'id': identity, 'created_utc': _now(), 'status': 'prepared',
            'project_root': str(root), 'map': MAP, 'build_report': build_report, 'planned_assets': planned, 'files': records}
    manifest = directory / 'transaction.json'
    _atomic_json(manifest, data)
    return {'id': identity, 'directory': str(directory), 'manifest': str(manifest)}


def _current(root, data):
    return {relative: _hash(_safe(root, relative)) for relative in data['files']}


def record_failure(token, error):
    path, root, directory, data = _load(token)
    if data['status'] != 'prepared':
        raise TransactionError('Only a prepared run may be recorded as failed')
    data.update(status='failed', failed_utc=_now(), error=str(error), failed_files=_current(root, data))
    _atomic_json(path, data)
    return {'directory': str(directory), 'manifest': str(path), 'files': len(data['files']),
            'changed_files': sum(data['failed_files'][p] != r['before_sha256'] for p, r in data['files'].items())}


def record_success(token):
    path, root, directory, data = _load(token)
    if data['status'] != 'prepared':
        raise TransactionError('Only a prepared run may be recorded as successful')
    data.update(status='succeeded', completed_utc=_now(), output_files=_current(root, data))
    _atomic_json(path, data)
    return {'directory': str(directory), 'manifest': str(path), 'status': 'succeeded'}


def editor_process_ids():
    """Fail closed if process inspection is unavailable; do not inspect secrets."""
    try:
        if os.name == 'nt':
            command = "@(Get-Process -ErrorAction Stop | Where-Object {$_.ProcessName -match '^UnrealEditor(?:-Cmd)?$'} | Select-Object -ExpandProperty Id) | ConvertTo-Json -Compress"
            done = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                                  capture_output=True, text=True, check=True, timeout=15,
                                  creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            value = json.loads(done.stdout.strip() or '[]')
            return value if isinstance(value, list) else [value]
        done = subprocess.run(['ps', '-A', '-o', 'pid=,comm='], capture_output=True,
                              text=True, check=True, timeout=15)
        return [int(line.split()[0]) for line in done.stdout.splitlines()
                if len(line.split()) > 1 and Path(line.split()[1]).name.startswith('UnrealEditor')]
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        raise TransactionError('Cannot confirm Unreal Editor is closed') from error


def _assert_editors_closed():
    pids = editor_process_ids()
    if pids:
        raise TransactionError('Close Unreal Editor before restoring; active PID(s): ' + ', '.join(map(str, pids)))


def _atomic_restore(backup, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile('wb', prefix='.mpr-restore-', suffix='.tmp', dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name)
        shutil.copy2(backup, temporary)
        os.replace(temporary, target)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def restore_transaction(token):
    path, root, directory, data = _load(token)
    if data['status'] not in ('failed', 'restoring'):
        raise TransactionError('Restore requires a recorded failed transaction')
    _assert_editors_closed()
    if set(data.get('failed_files', {})) != set(data['files']):
        raise TransactionError('The failure output inventory is incomplete')
    # Check EVERY backup and output before the first write. The restoring state
    # permits retry after an interrupted file-atomic restore; only known before
    # or failed bytes are accepted, never arbitrary intervening changes.
    current = _current(root, data)
    for relative, row in data['files'].items():
        if row['backup'] and _hash(_safe(directory, row['backup'])) != row['before_sha256']:
            raise TransactionError('Backup is missing or corrupt: ' + relative)
        allowed = {data['failed_files'][relative]}
        if data['status'] == 'restoring':
            allowed.add(row['before_sha256'])
        if current[relative] not in allowed:
            raise TransactionError('File changed after the failed run; preserving user edits: ' + relative)
    data.update(status='restoring', restore_started_utc=_now())
    _atomic_json(path, data)
    restored, removed = [], []
    _assert_editors_closed()
    last_process_check = time.monotonic()
    for relative, row in data['files'].items():
        target = _safe(root, relative)
        present = _hash(target)
        if present == row['before_sha256']:
            continue
        if time.monotonic() - last_process_check >= 1:
            _assert_editors_closed()
            last_process_check = time.monotonic()
        if present != data['failed_files'][relative]:
            raise TransactionError('File changed during restoration; stopped: ' + relative)
        if row['backup']:
            _atomic_restore(_safe(directory, row['backup']), target)
            restored.append(relative)
        else:
            # This is a declared new output with an exact matching failure hash.
            target.unlink()
            removed.append(relative)
    if _current(root, data) != {p: row['before_sha256'] for p, row in data['files'].items()}:
        raise TransactionError('Restoration verification failed')
    data.update(status='restored', restored_utc=_now(), restored_files=restored, removed_new_files=removed)
    _atomic_json(path, data)
    return {'success': True, 'restored_files': restored, 'removed_new_files': removed, 'transaction': str(directory)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['restore'])
    parser.add_argument('--transaction-dir', required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(restore_transaction(args.transaction_dir), ensure_ascii=False, indent=2))
    except TransactionError as error:
        parser.exit(2, str(error) + '\n')
