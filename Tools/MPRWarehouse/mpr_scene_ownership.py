"""Durable, file-level ownership checks for the generated MPR scene.

This module imports no Unreal API and never modifies scene packages. Only the
explicit bootstrap command may establish ownership of already-existing files.
Normal rebuilds verify every recorded package before the caller mutates UE.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

DEFAULT_OWNER = 'mpr-cad-scene-v1'
DEFAULT_MAP = '/Game/Maps/MPR_CAD_Warehouse'
MANIFEST = Path('SourceAssets/MPR/scene_ownership.json')
ASSET_PREFIX = '/Game/MPRWarehouse/'
COMPANIONS = ('.uexp', '.ubulk', '.uptnl')


class OwnershipError(RuntimeError):
    """The caller must preserve existing packages and stop rebuilding."""


def _sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _package_file(root, package, map_path=DEFAULT_MAP):
    if not isinstance(package, str) or not re.fullmatch(r'/Game/[A-Za-z0-9_/]+', package):
        raise OwnershipError('Invalid generated package path: ' + repr(package))
    if package != map_path and not package.startswith(ASSET_PREFIX):
        raise OwnershipError('Package is outside the MPR ownership scope: ' + package)
    if map_path != DEFAULT_MAP:
        raise OwnershipError('Unexpected map identity: ' + map_path)
    suffix = '.umap' if package == map_path else '.uasset'
    path = root / ('Content/' + package.removeprefix('/Game/') + suffix)
    if not path.resolve().is_relative_to(root.resolve()):
        raise OwnershipError('Package resolves outside project: ' + package)
    return path


def _package_records(root, package, map_path):
    path = _package_file(root, package, map_path)
    if not path.is_file():
        raise OwnershipError('Owned package is missing: ' + str(path))
    files = [path] + [path.with_suffix(s) for s in COMPANIONS if path.with_suffix(s).is_file()]
    return {'package': package, 'files': {
        p.relative_to(root).as_posix(): _sha(p) for p in files}}


def _read(root, owner, map_path):
    path = root / MANIFEST
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise OwnershipError('Missing or invalid durable MPR ownership manifest: ' + str(path)) from error
    if data.get('schema_version') != 1 or data.get('owner') != owner or data.get('map') != map_path:
        raise OwnershipError('MPR ownership identity does not match this generator')
    records = data.get('packages')
    if not isinstance(records, list) or not records:
        raise OwnershipError('Ownership package list is empty or malformed')
    names = [r.get('package') for r in records]
    if len(set(names)) != len(names) or names.count(map_path) != 1:
        raise OwnershipError('Duplicate packages or missing owned map')
    for row in records:
        primary = _package_file(root, row['package'], map_path)
        allowed = {p.relative_to(root).as_posix() for p in [primary] + [primary.with_suffix(s) for s in COMPANIONS]}
        files = row.get('files')
        if not isinstance(files, dict) or primary.relative_to(root).as_posix() not in files:
            raise OwnershipError('Primary package hash is missing: ' + row['package'])
        if not set(files).issubset(allowed) or any(not re.fullmatch(r'[0-9a-f]{64}', str(v)) for v in files.values()):
            raise OwnershipError('Invalid package file/hash record: ' + row['package'])
    return data


def _verify_records(root, data, skip_map=False):
    for row in data['packages']:
        if skip_map and row['package'] == data['map']:
            continue
        current = _package_records(root, row['package'], data['map'])
        if current['files'] != row['files']:
            raise OwnershipError('Package changed since generation; preserve manual edits: ' + row['package'])


def verify_owned_scene(project_root, *, owner=DEFAULT_OWNER, map_path=DEFAULT_MAP,
                       planned_assets=(), allow_new=False):
    """Verify all owned files and reject existing unowned planned destinations.

    No Saved/ file is consulted. With allow_new=True a first build is allowed
    only when the map and every planned destination are absent. Return the
    verification token for record_successful_build() or refresh_map_hash().
    """
    root = Path(project_root).resolve()
    planned = sorted(set(planned_assets))
    targets = [_package_file(root, p, map_path) for p in [map_path] + planned]
    path = root / MANIFEST
    if not path.exists():
        if not allow_new or any(p.exists() or any(p.with_suffix(s).exists() for s in COMPANIONS) for p in targets):
            raise OwnershipError('Existing target or rebuild has no durable ownership manifest; refusing overwrite')
        return {'manifest_sha256': None, 'owner': owner, 'map': map_path, 'planned_assets': planned, 'new_scene': True}
    data = _read(root, owner, map_path)
    _verify_records(root, data)
    tracked = {r['package'] for r in data['packages']}
    for package, path in zip([map_path] + planned, targets):
        if package not in tracked and (path.exists() or any(path.with_suffix(s).exists() for s in COMPANIONS)):
            raise OwnershipError('Planned destination already exists but is not owned: ' + package)
    return {'manifest_sha256': _sha(root / MANIFEST), 'owner': owner, 'map': map_path,
            'planned_assets': planned, 'new_scene': False}


def _write(root, data):
    path = root / MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.scene_ownership-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
    return data


def _unchanged_manifest(root, verification):
    current = _sha(root / MANIFEST) if (root / MANIFEST).exists() else None
    if current != verification['manifest_sha256']:
        raise OwnershipError('Ownership manifest changed after verification; refusing to replace it')


def _report_packages(report, owner, map_path):
    if report.get('success') is not True or report.get('owner') != owner or report.get('map') != map_path:
        raise OwnershipError('A successful matching generation report is required')
    packages = [row['path'] for row in report.get('meshes', [])]
    packages += [row['path'] for row in report.get('materials_created', [])]
    if not packages or len(packages) != len(set(packages)):
        raise OwnershipError('Generation report must list unique generated mesh/material packages')
    if any(not p.startswith(ASSET_PREFIX) for p in packages):
        raise OwnershipError('Generation report contains assets outside MPR')
    return sorted(packages)


def record_successful_build(project_root, report, verification):
    """Record only the saved map, report meshes and materials_created packages.

    materials_created is optional so existing mesh-only reports remain valid.
    Shared/reused source materials must never be included in materials_created.
    """
    root = Path(project_root).resolve()
    _unchanged_manifest(root, verification)
    owner, map_path = verification['owner'], verification['map']
    packages = _report_packages(report, owner, map_path)
    if set(packages) != set(verification['planned_assets']):
        raise OwnershipError('Saved asset list differs from the destinations checked before rebuilding')
    data = {'schema_version': 1, 'owner': owner, 'map': map_path,
            'packages': [_package_records(root, p, map_path) for p in [map_path] + packages]}
    return _write(root, data)


def bootstrap_from_report(project_root, report_path=None, *, owner=DEFAULT_OWNER, map_path=DEFAULT_MAP):
    """Explicit one-time migration for the scene already generated by this task.

    This is the sole function allowed to adopt existing files without an earlier
    ownership manifest. It refuses to replace a manifest and includes only the
    successful report's meshes/materials_created, never unknown extra packages.
    """
    root = Path(project_root).resolve()
    if (root / MANIFEST).exists():
        raise OwnershipError('Ownership already exists; bootstrap may only run once')
    source = Path(report_path) if report_path else root / 'Saved/MPR/scene_build.json'
    report = json.loads(source.read_text(encoding='utf-8-sig'))
    packages = _report_packages(report, owner, map_path)
    token = {'manifest_sha256': None, 'owner': owner, 'map': map_path, 'planned_assets': packages}
    return record_successful_build(root, report, token)


def refresh_map_hash(project_root, verification):
    """After an authorized capture restores/saves the map, update only its hashes.

    Call verify_owned_scene() before capture and retain its return value. Every
    mesh and generated material must still match; unknown packages are neither
    included nor modified.
    """
    root = Path(project_root).resolve()
    _unchanged_manifest(root, verification)
    data = _read(root, verification['owner'], verification['map'])
    _verify_records(root, data, skip_map=True)
    data['packages'] = [_package_records(root, r['package'], data['map'])
                        if r['package'] == data['map'] else r for r in data['packages']]
    return _write(root, data)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['verify', 'bootstrap-from-report'])
    parser.add_argument('--project-root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.command == 'bootstrap-from-report':
        answer = bootstrap_from_report(args.project_root, args.report)
        print('MPR_OWNERSHIP_BOOTSTRAPPED', len(answer['packages']), str(args.project_root / MANIFEST))
    else:
        verify_owned_scene(args.project_root)
        print('MPR_OWNERSHIP_VERIFIED')
