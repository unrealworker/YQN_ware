"""Archive completed transport evidence, never partial import success.

Run only after canonical apply, independent disk reload and runtime captures
all succeed. Sources and Content are read-only. Backups are never traversed;
only their explicit manifest is included. Earlier failed attempts are history.
"""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
CACHE_REL = 'Saved/MPR/cleanup_20261105'
SOURCE_REL = 'SourceAssets/MPR/rebuild_b50b57/transport_revision_20261105'
MAP = '/Game/Maps/MPR_CAD_Warehouse_B50B57'
MAP_FILE = 'Content/Maps/MPR_CAD_Warehouse_B50B57.umap'
NAMESPACE = '/Game/MPRWarehouse/RebuildB50B57/Site/Meshes/'
VIEW_NAMES = (
    '01-main-aerial-preserved', '02-removed-west-spurs', '03-two-road-junctions',
    '04-former-sleeper-density-boundary', '05-railbed-seam-close',
    '06-railbed-northeast-low', '07-interior-preserved',
)


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def file_sha(path):
    return sha(path.read_bytes())


def data_digest(value):
    return sha(json.dumps(value, sort_keys=True, ensure_ascii=False,
                          separators=(',', ':'), allow_nan=False).encode('utf8'))


def completed(record, label, *, phase=None):
    require(record.get('success') is True, label + ' has not succeeded')
    if phase:
        require(record.get('phase') == phase, label + ' is not complete')


def confined(path, base):
    path = Path(path).resolve()
    require(path.is_relative_to(base.resolve()) and path.is_file(), 'Missing or escaping evidence: ' + str(path))
    return path


def compressed(data):
    stream = io.BytesIO()
    with gzip.GzipFile(filename='', fileobj=stream, mode='wb', mtime=0) as zipped:
        zipped.write(data)
    result = stream.getvalue()
    require(gzip.decompress(result) == data, 'gzip roundtrip failed')
    return result


def main(*, root=ROOT, apply_report=None, reload_report=None, views_report=None,
         recovery_report=None, extra_history=()):
    root = root.resolve()
    cache, source = root / CACHE_REL, root / SOURCE_REL
    output = source / 'validation'
    apply_path = confined(apply_report or cache / 'transport_apply.json', cache)
    # This first prerequisite is checked before output directories are created.
    applied = read(apply_path)
    completed(applied, 'Canonical transport apply', phase='complete')
    require(applied.get('final_map_saved') is True and applied.get('other_content_unchanged') is True,
            'Apply lacks final save or Content preservation proof')
    reload_path = confined(reload_report or cache / 'reload/current_validation.json', cache)
    views_path = confined(views_report or cache / 'transport/runtime_views/capture_report.json', cache)
    reloaded, views = read(reload_path), read(views_path)
    completed(reloaded, 'Independent disk reload')
    completed(views, 'Runtime captures')
    require(reloaded.get('reload_requested') is True and reloaded.get('assets_saved') is False,
            'Final validation did not perform a read-only disk reload')
    require(views.get('map_unchanged') is True and views.get('assets_saved') is False,
            'Runtime capture did not preserve the map')
    require(reloaded['map'] == MAP and not reloaded['missing_game_packages'], 'Reload map/dependencies are invalid')
    manifest_path = source / 'manifest.json'
    manifest = read(manifest_path)
    require(manifest['map'] == MAP and manifest['transport_revision'] is True, 'Wrong transport manifest')
    rows = manifest['meshes']
    names = [row['name'] for row in rows]
    packages = {NAMESPACE + name for name in names}
    require(len(names) == len(packages) == 89, 'Expected exactly 89 transport replacement meshes')
    require(applied['revision_manifest_sha256'] == file_sha(manifest_path), 'Canonical apply manifest changed')
    require(applied['geometry_audit_sha256'] == file_sha(source / 'geometry_audit.json'), 'Geometry audit changed')
    require(applied.get('completed_meshes') == 89 and set(applied['mesh_assets_saved']) == packages,
            'Partial or mismatched imported mesh set')
    changes = {row['package']: row for row in applied['changed_meshes']}
    require(len(applied['changed_meshes']) == len(changes) == 89 and set(changes) == packages,
            'Final asset hash contract is incomplete')
    final_hashes = {MAP_FILE: applied['map_sha256_after']}
    for package, row in changes.items():
        final_hashes['Content/' + package.removeprefix('/Game/') + '.uasset'] = row['after_sha256']
    modified = applied['modified_files']
    expected_changed = {'Content/' + package.removeprefix('/Game/') + '.uasset'
                        for package, row in changes.items() if row['before_sha256'] != row['after_sha256']}
    if applied['map_sha256_before'] != applied['map_sha256_after']:
        expected_changed.add(MAP_FILE)
    require(set(modified) == expected_changed and
            all(row['after_sha256'] == final_hashes[name] for name, row in modified.items()),
            'Apply changed files outside final map and 89 transport assets')
    require(applied['map_sha256_after'] == reloaded['map_sha256'] == views['map_sha256'],
            'Final map hashes disagree across apply/reload/captures')
    require(reloaded['transport_patch_sha256'] == file_sha(apply_path), 'Reload used a different apply report')
    require(reloaded['transport_mesh_changes'] == {k: v for k, v in final_hashes.items() if k != MAP_FILE},
            'Reload has a different final mesh contract')
    require(not reloaded.get('historical_migration_evidence_modified'), 'Historical validation was modified')
    require(reloaded['preservation']['core_actor_count'] == 256, 'Protected main warehouse/interior count changed')
    require(not reloaded['preservation']['added_transport_actors'], 'Unexpected added transport actors')
    for field in ('core_actor_count', 'core_actor_digest', 'actor_count', 'removed_transport_actors',
                  'added_transport_actors', 'unchanged_existing_actors'):
        require(reloaded['preservation'][field] == applied['preservation'][field],
                'Independent reload disagrees with final preservation: ' + field)
    for name, value in final_hashes.items():
        require(file_sha(confined(root / name, root / 'Content')) == value, 'Final Content differs: ' + name)
    blend = confined(root / manifest['blend'], source)
    for row in rows:
        require(file_sha(confined(root / row['fbx'], source)) == row['sha256'], 'Saved FBX changed: ' + row['name'])
    for name, value in manifest['source_hashes'].items():
        require(file_sha(confined(source.parent / name, source.parent)) == value, 'Original source changed: ' + name)

    # Keep a complete explicit input set in memory before creating any archive.
    inputs = {}
    def add(path, destination, *, zip_data=True, label='evidence'):
        path = Path(path).resolve()
        require(path.is_relative_to(root) and path.is_file(), 'Invalid archive source: ' + str(path))
        target = destination + ('.gz' if zip_data else '')
        require(not Path(target).is_absolute() and '..' not in Path(target).parts, 'Invalid archive target')
        data = path.read_bytes()
        if target in inputs:
            require(inputs[target]['data'] == data, 'Archive name collision: ' + target)
            return
        inputs[target] = dict(path=path, data=data, compressed=zip_data, label=label)

    add(apply_path, 'transport_apply.json')
    add(reload_path, 'reload/current_validation.json')
    reload_snapshot = confined(reload_path.with_name('current_snapshot.json'), cache)
    require(file_sha(reload_snapshot) == reloaded['snapshot_sha256'], 'Reload snapshot changed')
    add(reload_snapshot, 'reload/current_snapshot.json')
    add(views_path, 'runtime_views/capture_report.json', zip_data=False)
    require([row['name'] for row in views['captures']] == list(VIEW_NAMES), 'Expected all seven scoped runtime views')
    for row in views['captures']:
        path = confined(row['path'], views_path.parent)
        require(file_sha(path) == row['sha256'], 'Runtime screenshot changed: ' + row['name'])
        require(path.suffix.lower() == '.png', 'Unexpected runtime screenshot format')
        add(path, 'runtime_views/' + row['name'] + '.png', zip_data=False)
    geometry_path = cache / 'transport/geometry_validation.json'
    clearance_path = cache / 'transport/saved_fbx_clearance.json'
    geometry, clearance = read(geometry_path), read(clearance_path)
    completed(geometry, 'CPU geometry validation')
    completed(clearance, 'Saved FBX terrain clearance')
    require(geometry['patch_meshes'] == 89, 'Geometry check has wrong mesh count')
    for group in clearance['groups'].values():
        require(group['missing'] == 0 and group['min_clearance_m'] > 0, 'Saved FBX intersects or misses terrain')
    payload = cache / 'transport/geometry_payload.json.gz'
    require(file_sha(payload) == geometry['payload_sha256'], 'Geometry payload changed')
    add(geometry_path, 'geometry_validation.json', zip_data=False)
    add(clearance_path, 'saved_fbx_clearance.json', zip_data=False)
    add(payload, 'geometry_payload.json.gz', zip_data=False)
    add(cache / 'transport/geometry_audit.json', 'geometry_audit_before_export.json')
    add(source / 'geometry_audit.json', 'geometry_audit.json')
    add(cache / 'transport/layout.json', 'layout.json')
    add(cache / 'transport/road_preview.json', 'road_preview.json')

    actual_rail_path = cache / 'transport/actual_rail_fbx_review.json'
    actual_rail = read(actual_rail_path)
    # This measured review can be schema-versioned without a success flag;
    # require its actual geometry conclusions instead of inventing one.
    require(actual_rail.get('success', True) is True, 'Actual rail FBX review failed')
    sleepers = actual_rail['sleepers']
    require(sleepers['components'] == 6044 and sleepers['near_or_far_sheet_profiles_remaining'] == 0 and
            sleepers['centers_within_0_42m'] == 0 and sleepers['cross_tile_duplicate_triangles'] == 0,
            'Actual saved FBX sleeper geometry is inconsistent')
    require(actual_rail['old_railbed_effective_count'] == 0 and actual_rail['actual_fbx_files_checked'] == 63 and
            actual_rail['no_original_or_content_mutation'] is True, 'Actual rail review scope differs')
    require(set(actual_rail['branch_absence']) == {'TPX_RAILWAYS_AXES_E6F', 'TPX_RAILWAYS_AXES_E9C'} and
            all(row['residual_hits'] == 0 and row['bed_residual_m2'] == 0
                for row in actual_rail['branch_absence'].values()), 'Removed rail branches retain geometry')
    require(actual_rail['rail_web']['components'] == actual_rail['rail_web']['head_components'] and
            all(0 < value < .08 for value in actual_rail['rail_web']['raised_web_thickness_m_range']),
            'Actual rail head/web geometry differs')
    add(actual_rail_path, 'actual_rail_fbx_review.json', zip_data=False)

    # The color policy experiment is part of this recovery, not its acceptance.
    # Bind inspection -> one-asset probe -> successful final recovery -> reload.
    inspection_path = cache / 'transport_color_inspection_v2.json'
    probe_path = cache / 'transport_color_probe.json'
    inspected, probe = read(inspection_path), read(probe_path)
    completed(inspected, 'Read-only color inspection v2')
    completed(probe, 'One-mesh color policy probe')
    require(inspected['assets_saved'] is False and inspected['assets_modified'] is False and
            inspected['vertex_colors']['valid'] is True and inspected['vertex_colors']['matches_original_fade'] is True,
            'Color inspection changed assets or failed exported fade verification')
    require(probe['inspection_sha256'] == file_sha(inspection_path) and probe['before_sha256'] == inspected['mesh_sha256'],
            'Color probe is not based on the inspected bytes')
    require(probe['map_sha256'] == inspected['map_sha256'] == applied['map_sha256_before'], 'Color probe map baseline differs')
    require(probe['map_saved'] is False and probe['materials_modified'] is False and probe['actors_modified'] is False and
            probe['assets_saved'] == [inspected['mesh_package']], 'Color probe changed unapproved assets or scene state')
    require(probe['vertex_colors']['matches_original_fade'] is True and probe['interchange_flag_restored'] is True,
            'Color probe did not restore the importer flag or preserve the fade')
    probe_row = next(row for row in rows if NAMESPACE + row['name'] == inspected['mesh_package'])
    require(inspected['manifest_sha256'] == file_sha(manifest_path) and inspected['source_fbx_sha256'] == probe_row['sha256'],
            'Color probe used different exported source geometry')
    for name, digest_key in [('transport_color_inspection_v2_scene.json', 'scene_digest'),
                             ('transport_color_inspection_v2_content.json', 'content_digest')]:
        require(data_digest(read(cache / name)) == inspected[digest_key], 'Color inspection snapshot changed: ' + name)
        add(cache / name, 'color_policy/' + name)
    require(data_digest(read(cache / 'transport_color_probe_content_after.json')) == probe['content_digest_after'],
            'Color probe Content snapshot changed')
    for name in ['transport_color_inspection_v2.json', 'transport_color_probe.json', 'transport_color_probe_content_after.json']:
        add(cache / name, 'color_policy/' + name)
    require(recovery_report is not None, 'Specify the successful final --recovery-report; prior failed resumes are history')
    recovery_path = confined(recovery_report, cache)
    recovery = read(recovery_path)
    completed(recovery, 'Final compatibility recovery', phase='complete')
    require(recovery['final_map_saved'] is True and recovery['map_sha256_after'] == applied['map_sha256_after'] and
            recovery['changed_meshes'] == applied['changed_meshes'] and recovery['modified_files'] == applied['modified_files'],
            'Successful recovery is not the canonical final Content contract')
    # Final recovery must link the actual reviewed probe, not just report success.
    probe_links = [recovery.get(key) for key in ('color_probe_sha256', 'probe_sha256') if key in recovery]
    require(probe_links and all(value == file_sha(probe_path) for value in probe_links),
            'Final recovery lacks the exact successful color probe link')
    if 'inspection_sha256' in recovery:
        require(recovery['inspection_sha256'] == file_sha(inspection_path), 'Recovery inspection hash differs')
    add(recovery_path, 'recovery/final_recovery.json', label='successful_final_recovery')

    native_path = cache / 'transport/native_validation/validation.json'
    native = read(native_path)
    completed(native, 'Native Blender FBX roundtrip')
    require(native['manifest_sha256'] == file_sha(manifest_path) and native['blend_sha256'] == file_sha(blend),
            'Native Blender validation uses different source bytes')
    require(native['fbx_roundtrip_meshes'] == 89 and [row['name'] for row in native['meshes']] == names,
            'Native Blender validation is incomplete')
    require(all(row['coordinate_color_roundtrip']['multiset_equal'] for row in native['meshes']), 'FBX coordinate/color roundtrip failed')
    add(native_path, 'native_validation/validation.json')
    collected = []
    for batch in native['batches']:
        require(batch['exit_code'] == 0, 'Native Blender batch process failed')
        path = confined(batch['report'], native_path.parent)
        record = read(path)
        completed(record, 'Native Blender batch')
        require(record['manifest_sha256'] == native['manifest_sha256'] and record['blend_sha256'] == native['blend_sha256'],
                'Native batch source differs')
        collected.extend(row['name'] for row in record['meshes'])
        add(path, 'native_validation/' + path.relative_to(native_path.parent).as_posix())
        log = confined(batch['log'], native_path.parent)
        add(log, 'native_validation/' + log.relative_to(native_path.parent).as_posix())
    require(collected == names, 'Native batch coverage differs')

    for name, key in [('transport_before.json', 'before_snapshot_sha256'), ('transport_after.json', 'after_snapshot_sha256')]:
        path = cache / name
        require(file_sha(path) == applied[key], 'Apply snapshot changed: ' + name)
        add(path, name)
    for name in ('transport_content_before.json', 'transport_sources_before.json', 'transport_preflight.json'):
        add(cache / name, name)
    backup_manifest = cache / 'transport_backup/manifest.json'
    add(backup_manifest, 'transport_backup_manifest.json')
    # Archive the original failure and compatibility recovery as history only.
    # This filename-only allowlist never walks a backup or Saved directory.
    history = set()
    for path in cache.glob('transport_*.json'):
        if (re.fullmatch(r'transport_.*failed.*\.json', path.name) or
                re.fullmatch(r'transport_.*recovery.*\.json', path.name) or
                path.name in {'transport_resume_plan.json', 'transport_resume_before.json',
                              'transport_resume_preflight.json', 'transport_resume_apply.json',
                              'transport_color_inspection.json', 'transport_color_inspection_content.json',
                              'transport_color_inspection_scene.json', 'transport_color_metadata.json'}):
            history.add(path.resolve())
    for path in extra_history:
        checked = confined(path, cache)
        require(checked.parent == cache.resolve() and checked.suffix == '.json',
                'Extra history must be one explicit top-level cleanup JSON report')
        history.add(checked)
    history.discard(recovery_path)
    # An old failure can move under a historical name after canonical success.
    history_hashes = {file_sha(path) for path in history}
    require(probe['initial_failure_sha256'] in history_hashes and probe['resume_failure_sha256'] in history_hashes,
            'Original import/resume failure reports are missing from preserved history')
    for path in sorted(history):
        add(path, 'attempt_history/' + path.name, label='attempt_history_not_final_success')
    recovery_bindings = {}
    for original_name, expected_hash in recovery.get('recovery_evidence_hashes', {}).items():
        matches = [name for name, row in inputs.items() if sha(row['data']) == expected_hash]
        require(matches, 'Successful recovery historical hash is not preserved: ' + original_name)
        recovery_bindings[original_name] = dict(sha256=expected_hash, archived_files=sorted(matches))

    tools = {path.relative_to(root).as_posix(): file_sha(path) for path in [
        Path(__file__), root / 'Tools/MPRWarehouse/apply_mpr_transport_revision.py',
        root / 'Tools/MPRWarehouse/recover_mpr_transport_revision.py',
        root / 'Tools/MPRWarehouse/probe_mpr_transport_colors.py', root / 'Tools/MPRWarehouse/import_mpr_scene.py',
        root / 'Tools/MPRWarehouse/validate_mpr_current.py', root / 'Tools/MPRWarehouse/validate_mpr_current_reload.py',
        root / 'Tools/MPRWarehouse/capture_mpr_transport_views.py', root / 'Tools/MPRWarehouse/verify_mpr_transport_blender.py',
    ]}
    require(tools['Tools/MPRWarehouse/capture_mpr_transport_views.py'] == views['capture_tool_sha256'], 'Capture tool changed')
    require(tools['Tools/MPRWarehouse/verify_mpr_transport_blender.py'] == native['verifier_sha256'], 'Blender verifier changed')
    outputs, indexed = {}, {}
    for name, row in inputs.items():
        data = compressed(row['data']) if row['compressed'] else row['data']
        outputs[name] = data
        indexed[name] = dict(sha256=sha(data), bytes=len(data),
            source=row['path'].relative_to(root).as_posix(), source_sha256=sha(row['data']),
            source_bytes=len(row['data']), compression='gzip' if row['compressed'] else None, role=row['label'])
    index = dict(schema_version=1, success=True, map=MAP, map_sha256=applied['map_sha256_after'],
        baseline_map_sha256=applied['map_sha256_before'], revised_mesh_count=89,
        final_content_hashes=final_hashes, source_manifest_sha256=file_sha(manifest_path),
        source_blend_sha256=file_sha(blend), apply_sha256=file_sha(apply_path),
        reload_sha256=file_sha(reload_path), capture_report_sha256=file_sha(views_path),
        actual_rail_fbx_review_sha256=file_sha(actual_rail_path),
        color_inspection_v2_sha256=file_sha(inspection_path), color_probe_sha256=file_sha(probe_path),
        final_recovery_sha256=file_sha(recovery_path),
        recovery_evidence_sources=recovery_bindings,
        preservation=reloaded['preservation'], native_triangle_count=native['triangles'],
        backup_entities_archived=False, canonical_apply_complete=True, independent_reload_complete=True,
        runtime_view_count=7, attempt_history_is_not_acceptance=True,
        source_tools=tools, files=indexed)
    outputs['index.json'] = (json.dumps(index, ensure_ascii=False, indent=2) + '\n').encode('utf8')
    # All prerequisites and output-collision checks finish before the first write.
    for name, data in outputs.items():
        target = output / name
        require(not target.exists() or target.read_bytes() == data, 'Refusing to overwrite different final evidence: ' + name)
    for name, data in outputs.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(data)
        require(target.read_bytes() == data, 'Archive output verification failed: ' + name)
    for row in inputs.values():
        require(row['path'].read_bytes() == row['data'], 'Evidence changed while archiving: ' + str(row['path']))
    for name, value in final_hashes.items():
        require(file_sha(root / name) == value, 'Final Content changed during archive: ' + name)
    print(json.dumps(dict(success=True, files=len(outputs), revised_meshes=89,
        map_sha256=index['map_sha256'], output=output.relative_to(root).as_posix()), ensure_ascii=False))
    return index


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply-report', type=Path)
    parser.add_argument('--reload-report', type=Path)
    parser.add_argument('--views-report', type=Path)
    parser.add_argument('--recovery-report', type=Path, help='Successful final compatibility recovery report, required')
    parser.add_argument('--history', type=Path, action='append', default=[])
    args = parser.parse_args()
    main(apply_report=args.apply_report, reload_report=args.reload_report,
         views_report=args.views_report, recovery_report=args.recovery_report, extra_history=args.history)
