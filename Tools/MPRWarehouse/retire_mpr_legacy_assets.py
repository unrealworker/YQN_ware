"""Audit legacy MPR packages; retire only an explicitly reviewed closed set.

Run in the editor with the new B50B57 map active. The default entry point only
writes audit evidence to Saved/MPR/cleanup_20261105; it never loads another
map, saves an asset, deletes a package, or quits the user's editor. The source
Blender/FBX/JSON files remain outside the deletion candidate scope.

The registry records saved references. Dirty packages make an audit ineligible
for deletion; source/config dynamic paths need the caller's separate review.
"""
from collections import Counter, deque
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import traceback

OLD_MAP = '/Game/Maps/MPR_CAD_Warehouse'
NEW_MAP = '/Game/Maps/MPR_CAD_Warehouse_B50B57'
LEGACY_ROOT = '/Game/MPRWarehouse/'
NEW_ROOT = '/Game/MPRWarehouse/RebuildB50B57/'
PACKAGE_SUFFIXES = {'.uasset', '.umap', '.uexp', '.ubulk', '.uptnl'}
PRIMARY_SUFFIXES = {'.uasset', '.umap'}
OUT_REL = 'Saved/MPR/cleanup_20261105'
# Exact orphaned environment packages recorded by the original scene's catalog.
# All five current bytes were verified against this immutable Git revision;
# the modern environment manifest has since replaced their names/geometry.
HISTORIC_OWNER = 'git:be1a58cbde24c7fd038c76228b6001001fa6350e:SourceAssets/MPR/scene_ownership.json'
HISTORIC_ENV_HASHES = {
    'Far_S_Hardstand': 'c76c150d98ffbaef2d2ec96a3f89c0e2ce23104b601cc5033b5908325efbc67d',
    'Far_W_Hardstand': '4ebacb884f3982d2a37864ab047104b1d53710fca7a289855b7546fe2275d11c',
    'Near_Hardstand': '1365da0b6801c8e5c9e7a3f9f7c0fd57637ca868e8f8505e188ac71aed4feb0c',
    'Near_Islands': '612f9809fb54f0185330c50a74ae9e53d416f491b7e63ac308be597710f8b7a8',
    'Near_Parking': '1c4b5e93d6d0a6197e1867a30263a8ebd46f6e3806768a085af07b4ff2ecd42a',
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode('utf8')).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name + '.tmp')
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')
    pending.replace(path)


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def candidate(package):
    return package == OLD_MAP or (package.startswith(LEGACY_ROOT) and not package.startswith(NEW_ROOT))


def inventory(root):
    """Resolve and check every Content path before recording any future deletion."""
    content = (root / 'Content').resolve()
    files, packages = {}, {}
    for path in sorted(content.rglob('*')):
        if not path.is_file():
            continue
        resolved = path.resolve()
        require(resolved.is_relative_to(content), 'Content path escapes project: ' + str(path))
        relative = path.relative_to(root).as_posix()
        files[relative] = dict(sha256=sha(path), bytes=path.stat().st_size)
        if path.suffix.lower() in PRIMARY_SUFFIXES:
            package = '/Game/' + path.relative_to(content).with_suffix('').as_posix()
            require(package not in packages, 'Two primary files for a package: ' + package)
            packages[package] = [relative]
    for package, rows in packages.items():
        primary = root / rows[0]
        for suffix in sorted(PACKAGE_SUFFIXES - PRIMARY_SUFFIXES):
            sidecar = primary.with_suffix(suffix)
            name = sidecar.relative_to(root).as_posix()
            if name in files:
                rows.append(name)
    return files, packages


def protected_closure(candidates, dependencies, referencers, explicit_protected=()):
    """Largest deletable set closed to incoming saved references, including cycles."""
    candidates = set(candidates)
    seeds = {p for p in candidates if set(referencers.get(p, ())) - candidates}
    seeds.update(set(explicit_protected) & candidates)
    protected, reasons = set(seeds), {}
    for package in sorted(seeds):
        reasons[package] = dict(external_referencers=sorted(set(referencers.get(package, ())) - candidates),
                                explicit=package in explicit_protected)
    pending = deque(sorted(seeds))
    while pending:
        package = pending.popleft()
        for dependency in sorted(set(dependencies.get(package, ())) & candidates):
            if dependency not in protected:
                protected.add(dependency)
                reasons[dependency] = dict(required_by_protected=package)
                pending.append(dependency)
    deletable = candidates - protected
    for package in deletable:
        require(not (set(referencers.get(package, ())) - deletable),
                'Deletion closure has an external referencer: ' + package)
    return protected, deletable, reasons


def deletion_order(deletable, dependencies):
    """Referrers first. Cycles are reported instead of being force-broken."""
    remaining = set(deletable)
    edges = {p: set(dependencies.get(p, ())) & remaining - {p} for p in remaining}
    incoming = Counter(q for row in edges.values() for q in row)
    ready = deque(sorted(p for p in remaining if incoming[p] == 0))
    order = []
    while ready:
        package = ready.popleft()
        order.append(package)
        remaining.remove(package)
        for dependency in sorted(edges[package]):
            incoming[dependency] -= 1
            if incoming[dependency] == 0:
                ready.append(dependency)
    return order, sorted(remaining)


def provenance(root, candidates, files):
    """Explain task ownership; these records do not substitute for references."""
    sources = [
        ('SourceAssets/MPR/scene_ownership.json', 'packages'),
        ('SourceAssets/MPR/extension_b50b57/scene_ownership.json', 'packages'),
        ('Saved/MPR/reference_v3_retired_ownership.json', 'retired'),
    ]
    evidence, by_package = {}, {}
    for name, key in sources:
        path = root / name
        if not path.is_file():
            continue
        record = read(path)
        evidence[name] = sha(path)
        for row in record[key]:
            package = row['package']
            if package not in candidates:
                continue
            expected = row['files']
            matches = all(files.get(p, {}).get('sha256') == h for p, h in expected.items())
            by_package.setdefault(package, []).append(dict(record=name, expected_hashes_match=matches))
    env_file = root / 'SourceAssets/MPR/environment/environment_manifest.json'
    if env_file.is_file():
        evidence[env_file.relative_to(root).as_posix()] = sha(env_file)
        for row in read(env_file)['meshes']:
            package = '/Game/MPRWarehouse/Environment/Meshes/' + row['name']
            if package in candidates:
                by_package.setdefault(package, []).append(dict(record=env_file.relative_to(root).as_posix(),
                                                                 expected_hashes_match=None))
    for name, expected in HISTORIC_ENV_HASHES.items():
        package = '/Game/MPRWarehouse/Environment/Meshes/SM_MPR_Env_' + name
        filename = 'Content/MPRWarehouse/Environment/Meshes/SM_MPR_Env_' + name + '.uasset'
        if package in candidates:
            require(files.get(filename, {}).get('sha256') == expected,
                    'Historical orphan was modified and requires review: ' + package)
            by_package.setdefault(package, []).append(dict(record=HISTORIC_OWNER,
                expected_hashes_match=True, expected_files={filename: expected}))
            evidence[HISTORIC_OWNER] = '0efdfc5dde42d61fc6c0d4db3db9c17a4fbb28869ba15142f5837b02ec43a4a6'
    return evidence, by_package


def audit(u, *, explicit_protected=(), output_name='legacy_audit.json'):
    root = Path(u.Paths.convert_relative_path_to_full(u.Paths.project_dir())).resolve()
    require((root / 'Test.uproject').is_file(), 'Expected the Test UE project')
    sys.path.insert(0, str(root / 'Tools/MPRWarehouse'))
    import rebuild_preservation as guard
    out = root / OUT_REL
    require(Path(output_name).name == output_name and output_name.endswith('.json'), 'Invalid output name')
    before = guard.capture(u, root, NEW_MAP)
    files, packages = inventory(root)
    candidates = {p for p in packages if candidate(p)}
    require(OLD_MAP in candidates, 'The legacy map is absent; use cleanup verification after retirement')
    require(NEW_MAP in packages and not candidate(NEW_MAP), 'New map missing or in deletion scope')
    registry = u.AssetRegistryHelpers.get_asset_registry()
    registry.search_all_assets(synchronous_search=True)
    registry.scan_paths_synchronous(['/Game'], True)
    registry.wait_for_completion()
    options = u.AssetRegistryDependencyOptions(include_soft_package_references=True,
        include_hard_package_references=True, include_searchable_names=False,
        include_soft_management_references=True, include_hard_management_references=True)
    dependencies = {}
    for package in sorted(packages):
        assets = registry.get_assets_by_package_name(package, True)
        require(assets is not None and len(assets) > 0, 'Package absent in synchronized registry: ' + package)
        refs = registry.get_dependencies(package, options)
        require(refs is not None, 'Dependency query failed: ' + package)
        dependencies[package] = sorted(set(str(p) for p in refs))
    referencers = {}
    for package in sorted(candidates):
        refs = registry.get_referencers(package, options)
        require(refs is not None, 'Referencer query failed: ' + package)
        referencers[package] = sorted(set(str(p) for p in refs))
    # Cross-check both query directions so stale/partial graph reads fail closed.
    for package, deps in dependencies.items():
        for dependency in set(deps) & candidates:
            require(package in referencers[dependency], 'Dependency/referencer disagreement: ' + package + ' -> ' + dependency)
    for package, refs in referencers.items():
        for referrer in set(refs) & set(packages):
            require(package in dependencies[referrer], 'Referencer/dependency disagreement: ' + referrer + ' -> ' + package)
    protected, deletable, reasons = protected_closure(candidates, dependencies, referencers, explicit_protected)
    order, cyclic = deletion_order(deletable, dependencies)
    source_evidence, package_evidence = provenance(root, candidates, files)
    unknown = sorted(candidates - set(package_evidence))
    after = guard.capture(u, root, NEW_MAP)
    require(digest(before) == digest(after), 'Live scene/dirty package state changed during audit')
    files_after, packages_after = inventory(root)
    require(files == files_after and packages == packages_after, 'Content files changed during audit')
    snapshot_name = Path(output_name).stem + '_scene_snapshot.json'
    write(out / snapshot_name, before)
    def rows(names):
        return [dict(package=p, files={name: files[name] for name in packages[p]},
                     dependencies=dependencies[p], referencers=referencers[p],
                     provenance=package_evidence.get(p, []), protection_reason=reasons.get(p)) for p in sorted(names)]
    result = dict(schema_version=1, success=True, mode='audit',
        created_utc=datetime.now(timezone.utc).isoformat(), root=str(root),
        current_map=before['map'], old_map=OLD_MAP, new_map=NEW_MAP,
        map_sha256=before['map_file_sha256'], dirty_maps=before['dirty_maps'], dirty_content=before['dirty_content'],
        source_tools_sha256=sha(root / 'Tools/MPRWarehouse/retire_mpr_legacy_assets.py'),
        scope='Only legacy MPR Content packages and the original MPR map; source models and GHS are excluded.',
        registry_options=dict(hard_package=True, soft_package=True, hard_management=True, soft_management=True,
                              searchable_names=False, synchronous_scan=True),
        candidate_count=len(candidates), delete_count=len(deletable), retained_count=len(protected),
        deletable=rows(deletable), retained=rows(protected), unknown_provenance=unknown,
        explicit_protected=sorted(explicit_protected), source_evidence=source_evidence,
        deletion_order=order, cyclic_or_cycle_dependent_packages=cyclic,
        project_package_count=len(packages), project_dependencies=dependencies,
        all_content_files=files, all_content_files_digest=digest(files),
        scene_snapshot=snapshot_name, scene_snapshot_sha256=sha(out / snapshot_name),
        scene_actor_digest=digest([guard.canonical_actor(row) for row in before['actors']]),
        scene_guids=sorted(row['guid'] for row in before['actors']),
        live_scene_unchanged=True, content_files_unchanged=True, assets_saved=False, assets_deleted=False,
        eligible_for_review=not (before['dirty_maps'] or before['dirty_content'] or unknown),
        limitation='Registry queries cover saved package/management references. Dynamic source/config paths require independent review before deletion.')
    write(out / output_name, result)
    print('MPR_LEGACY_AUDIT ' + json.dumps({k: result[k] for k in
        ['success', 'candidate_count', 'delete_count', 'retained_count', 'dirty_maps', 'dirty_content', 'eligible_for_review']}, ensure_ascii=False))
    return result


def apply(u):
    """Delete only the reviewed closed set, retaining current user scene changes.

    No filesystem removal fallback is permitted. The UE API handles package
    unload/delete. This implementation deliberately rejects cycles; the current
    reviewed set is acyclic and can be deleted referrer-before-dependency.
    """
    root = Path(u.Paths.convert_relative_path_to_full(u.Paths.project_dir())).resolve()
    sys.path.insert(0, str(root / 'Tools/MPRWarehouse'))
    import rebuild_preservation as guard
    out = root / OUT_REL
    baseline_file = out / 'legacy_audit.json'
    baseline = read(baseline_file)
    require(baseline.get('success') is True and baseline['mode'] == 'audit', 'Missing successful reviewed audit')
    require(baseline['root'] == str(root) and baseline['current_map'] == NEW_MAP, 'Audit identity mismatch')
    snapshot_path = out / baseline['scene_snapshot']
    require(snapshot_path.parent.resolve() == out.resolve() and sha(snapshot_path) == baseline['scene_snapshot_sha256'],
            'Reviewed scene snapshot changed or escaped audit folder')
    original_scene = read(snapshot_path)
    require(not original_scene['dirty_maps'] and not original_scene['dirty_content'], 'Reviewed scene has unsaved packages')
    progress_path = out / 'legacy_delete_progress.json'
    result_path = out / 'legacy_delete.json'
    require(not progress_path.exists() and not result_path.exists(),
            'Prior cleanup attempt exists; inspect its exact state before continuing')
    current = audit(u, explicit_protected=baseline['explicit_protected'], output_name='legacy_predelete.json')
    require(current['eligible_for_review'], 'Fresh predelete audit has dirty packages or unknown source ownership')
    require(current['all_content_files'] == baseline['all_content_files'], 'Content changed since the reviewed audit')
    require(current['map_sha256'] == baseline['map_sha256'], 'Current user-saved map changed since review')
    current_scene = read(out / current['scene_snapshot'])
    require(digest(current_scene) == digest(original_scene), 'Live user scene changed since the reviewed audit')
    rows = {row['package']: row for row in current['deletable']}
    reviewed = {row['package']: row for row in baseline['deletable']}
    require(set(rows) == set(reviewed), 'Fresh graph changed the reviewed deletion set')
    require(all(rows[p]['files'] == reviewed[p]['files'] for p in rows), 'Reviewed deletion bytes changed')
    require(not current['cyclic_or_cycle_dependent_packages'], 'Cycle requires a separately reviewed batch strategy')
    order = current['deletion_order']
    require(len(order) == len(rows) and set(order) == set(rows), 'Incomplete deletion order')
    require(OLD_MAP in rows and NEW_MAP not in rows and all(candidate(p) for p in rows), 'Deletion scope mismatch')
    removed_files = {name: spec for row in rows.values() for name, spec in row['files'].items()}
    require(sum(len(row['files']) for row in rows.values()) == len(removed_files), 'Duplicate deletion file')
    retained = {name: spec for name, spec in baseline['all_content_files'].items() if name not in removed_files}
    backup = (out / 'backup').resolve()
    require(backup.is_relative_to(out.resolve()), 'Backup root escapes audit folder')
    for name, spec in removed_files.items():
        source = (root / name).resolve()
        target = (backup / name).resolve()
        require(source.is_relative_to((root / 'Content').resolve()) and target.is_relative_to(backup), 'Unsafe package backup path')
        require(source.is_file() and sha(source) == spec['sha256'], 'Package changed before backup: ' + name)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            require(sha(target) == spec['sha256'], 'Conflicting existing backup: ' + str(target))
        else:
            shutil.copy2(source, target)
        require(sha(target) == spec['sha256'] and target.stat().st_size == spec['bytes'], 'Backup verification failed: ' + name)
    write(out / 'backup_manifest.json', dict(audit_sha256=sha(baseline_file),
        predelete_sha256=sha(out / 'legacy_predelete.json'), files=removed_files, backup_root=str(backup)))
    # Backups are complete before the first mutation. Every package remains
    # individually constrained by its reviewed graph, filesystem bytes and API.
    progress = dict(success=False, phase='backups_verified', old_map=OLD_MAP, current_map=NEW_MAP,
        map_sha256=baseline['map_sha256'], reviewed_audit_sha256=sha(baseline_file),
        predelete_audit_sha256=sha(out / 'legacy_predelete.json'),
        backup_manifest_sha256=sha(out / 'backup_manifest.json'),
        planned_packages=order, deleted_packages=[], deleted_files=[], in_progress_package=None)
    write(progress_path, progress)
    try:
        registry = u.AssetRegistryHelpers.get_asset_registry()
        options = u.AssetRegistryDependencyOptions(include_soft_package_references=True,
            include_hard_package_references=True, include_searchable_names=False,
            include_soft_management_references=True, include_hard_management_references=True)
        current_files, _ = inventory(root)
        require(current_files == baseline['all_content_files'], 'Content changed while backing up')
        require(digest(guard.capture(u, root, NEW_MAP)) == digest(original_scene), 'Live scene changed while backing up')
        for package in order:
            refs = registry.get_referencers(package, options)
            require(refs is not None and not (set(str(p) for p in refs) - set(rows)),
                    'New external reference before deletion: ' + package)
            require(not u.EditorLoadingAndSavingUtils.get_dirty_map_packages() and
                    not u.EditorLoadingAndSavingUtils.get_dirty_content_packages(), 'Unsaved package appeared before deletion')
            for name, spec in rows[package]['files'].items():
                require((root / name).is_file() and sha(root / name) == spec['sha256'], 'Package bytes changed: ' + name)
            progress.update(phase='deleting', in_progress_package=package)
            write(progress_path, progress)
            require(u.EditorAssetLibrary.delete_asset(package), 'UE refused to delete package: ' + package)
            for name in rows[package]['files']:
                require(not (root / name).exists(), 'UE left a package file behind: ' + name)
                progress['deleted_files'].append(name)
            progress['deleted_packages'].append(package)
            progress['in_progress_package'] = None
            write(progress_path, progress)
        registry.scan_paths_synchronous(['/Game'], True)
        registry.wait_for_completion()
        after_files, _ = inventory(root)
        require(after_files == retained, 'Retained Content changed or deletion set incomplete')
        after_scene = guard.capture(u, root, NEW_MAP)
        require(digest(after_scene) == digest(original_scene), 'Live scene changed during cleanup')
        require(sha(root / 'Content/Maps/MPR_CAD_Warehouse_B50B57.umap') == baseline['map_sha256'],
                'Current user-saved map bytes changed')
        for package in rows:
            require(not u.EditorAssetLibrary.does_asset_exist(package), 'Deleted package remains in registry: ' + package)
        write(out / 'legacy_after_scene_snapshot.json', after_scene)
        result = dict(progress, success=True, phase='complete',
            retained_content_hashes={name: spec['sha256'] for name, spec in retained.items()},
            deleted_file_hashes={name: spec['sha256'] for name, spec in removed_files.items()},
            deleted_package_count=len(rows), deleted_file_count=len(removed_files),
            retained_legacy_package_count=current['retained_count'],
            live_scene_unchanged=True, current_map_file_unchanged=True, retained_content_unchanged=True,
            scene_actor_count=len(after_scene['actors']), scene_guids=current['scene_guids'],
            after_scene_snapshot_sha256=sha(out / 'legacy_after_scene_snapshot.json'),
            source_files_deleted=False, assets_saved=False,
            tool_sha256=sha(root / 'Tools/MPRWarehouse/retire_mpr_legacy_assets.py'))
        write(result_path, result)
        progress.update(success=True, phase='complete')
        write(progress_path, progress)
        print('MPR_LEGACY_DELETE ' + json.dumps({k: result[k] for k in
            ['success', 'deleted_package_count', 'deleted_file_count', 'retained_legacy_package_count', 'map_sha256']}))
        return result
    except Exception:
        progress.update(success=False, phase='failed', error=traceback.format_exc())
        write(progress_path, progress)
        write(result_path, progress)
        raise


def main(mode='audit'):
    require(mode in {'audit', 'apply'}, 'Unknown cleanup mode')
    import unreal as u
    root = Path(u.Paths.convert_relative_path_to_full(u.Paths.project_dir())).resolve()
    try:
        return audit(u) if mode == 'audit' else apply(u)
    except Exception:
        result = dict(success=False, mode=mode, assets_saved=False, error=traceback.format_exc())
        if mode == 'audit':
            result['assets_deleted'] = False
        else:
            result['deletion_progress'] = 'legacy_delete_progress.json'
        write(root / OUT_REL / ('legacy_' + mode + '_error.json'), result)
        u.log_error(result['error'])
        raise


if __name__ == '__main__':
    main(globals().get('MPR_LEGACY_MODE', 'audit'))
