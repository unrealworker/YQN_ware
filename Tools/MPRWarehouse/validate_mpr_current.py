"""Validate the saved B50B57 map after legacy retirement or a transport patch.

Start UE on /Game/Maps/MPR_CAD_Warehouse_B50B57 and execute this file, or call
run(unreal_module). No packages are saved, no map is switched and no quit is
issued. Historical migration evidence remains immutable. Ordinary Python can
import the pure comparison helpers without loading Unreal.
"""
from copy import deepcopy
from pathlib import Path
import gzip
import json
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
import rebuild_preservation as guard

SOURCE = 'SourceAssets/MPR/rebuild_b50b57'
OUTPUT = 'Saved/MPR/cleanup_20261105'
MAP_FILE = 'Content/Maps/MPR_CAD_Warehouse_B50B57.umap'
TRANSPORT_PREFIXES = ('SM_MPRR_Roads_', 'SM_MPRR_Curblines_',
    'SM_MPRR_WhiteEdges_', 'SM_MPRR_RoadDashes_', 'SM_MPRR_Rail_',
    'SM_MPRR_RailCorridor_', 'SM_MPRR_CrossingDeck_', 'SM_MPRR_CrossingRamp_')
require = guard.require
sha = guard.sha


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def inside(root, relative):
    require(isinstance(relative, str) and '\\' not in relative, 'Expected canonical relative path')
    path = Path(relative)
    require(not path.is_absolute() and '..' not in path.parts, 'Unsafe relative path: '+relative)
    target = (Path(root)/path).resolve()
    require(target.is_relative_to(Path(root).resolve()), 'Path escaped project: '+relative)
    return target


def package_file(root, package):
    require(package.startswith('/Game/') and '..' not in package.split('/'), 'Invalid package: '+package)
    stem = 'Content/'+package.removeprefix('/Game/')
    files = [inside(root, stem+ext) for ext in ('.uasset', '.umap')]
    found = [p for p in files if p.is_file()]
    require(len(found) == 1, 'Missing or ambiguous /Game package: '+package)
    return found[0]


def archived_json(root, index, name):
    path = inside(root, SOURCE+'/validation/'+name)
    row = index['files'][name]
    require(sha(path) == row['sha256'], 'Historical validation archive changed: '+name)
    raw = gzip.decompress(path.read_bytes()) if name.endswith('.gz') else path.read_bytes()
    if 'source_sha256' in row:
        import hashlib
        require(hashlib.sha256(raw).hexdigest() == row['source_sha256'], 'Historical archive payload changed: '+name)
    return json.loads(raw.decode('utf-8-sig'))


def transport_packages(manifest):
    return {guard.DEST+'/Site/Meshes/'+row['name'] for row in manifest['meshes']
            if row['category'] == 'Site' and row['name'].startswith(TRANSPORT_PREFIXES)}


def is_transport_actor(row, packages):
    meshes = [c['mesh'].split('.')[0] for c in row['components'] if c.get('mesh')]
    return (row['class'] == '/Script/Engine.StaticMeshActor'
            and row['folder'] == guard.FOLDER+'/Site' and guard.TAG in row['tags']
            and bool(meshes) and set(meshes) <= packages and row['attachment_parent'] is None)


def compare_snapshot(saved, current, ownership, manifest, patch=None, transport_manifest=None):
    """Protect the audited user state, with only exact transport exceptions."""
    require(saved['map'] == current['map'] == guard.MAP, 'Not the active B50B57 map')
    before = {a['guid']:guard.canonical_actor(a) for a in saved['actors']}
    after = {a['guid']:guard.canonical_actor(a) for a in current['actors']}
    require(len(before) == len(saved['actors']) and len(after) == len(current['actors']), 'Duplicate actor GUID')
    historical_core = set(ownership['retention']['source_to_copy_guid'].values())
    require(len(historical_core) == 256, 'Historical core identity set is not the reviewed 256 actors')
    core = historical_core & set(before)
    expected = deepcopy(before)
    removed, added = set(), set()
    packages = transport_packages(manifest)
    if patch is not None:
        require(patch.get('success') is True, 'Transport patch was not successful')
        require(patch['map_sha256_before'] == saved['map_file_sha256'], 'Transport patch starts from another map')
        require(patch['map_sha256_after'] == current['map_file_sha256'], 'Current map differs from transport patch')
        removed = set(patch['removed_actor_guids']); added = set(patch['added_actor_guids'])
        require(len(removed) == len(patch['removed_actor_guids']) and len(added) == len(patch['added_actor_guids']),
                'Duplicate transport actor exception')
        require(not (removed|added)&historical_core and not removed&added, 'Transport patch may not change main-building actors')
        require(removed <= set(before) and not added&set(before), 'Invalid transport actor addition/removal')
        for guid in removed:
            require(is_transport_actor(before[guid], packages), 'Removed actor is not an approved transport actor')
            del expected[guid]
        additions = {a['guid']:guard.canonical_actor(a) for a in patch.get('added_actors', [])}
        require(set(additions) == added and len(additions) == len(patch.get('added_actors', [])),
                'Transport additions require their complete serialized actor records')
        for guid, row in additions.items():
            require(is_transport_actor(row, packages), 'Added actor is not an approved transport actor')
            require(row['path'].startswith(guard.MAP+'.') and row['name'] not in {a['name'] for a in expected.values()},
                    'Added actor identity is not unique in the new map')
            expected[guid] = row
        material_changes = patch.get('actor_material_changes', [])
        if material_changes:
            require(transport_manifest is not None, 'Transport material changes require the reviewed revision manifest')
            revised = {r['name']:r for r in transport_manifest['meshes']}
            seen = set()
            for change in material_changes:
                guid = change['guid']; key = (guid, change['component'])
                require(key not in seen and guid in before and guid in expected and guid not in historical_core,
                        'Invalid/duplicate protected actor material change')
                seen.add(key); actor = expected[guid]
                require(is_transport_actor(actor, packages), 'Material change is not a transport actor')
                components = [c for c in actor['components'] if c['name']==change['component']]
                require(len(components)==1, 'Transport material component is ambiguous')
                component = components[0]; mesh = component['mesh']
                require(mesh==change['mesh'] and component['materials']==change['before'], 'Transport material baseline differs')
                name = mesh.split('.')[0].rsplit('/',1)[-1]
                require(name in revised, 'Transport material changes affect an unlisted mesh')
                wanted = [guard.DEST+'/Materials/MI_'+role+'.MI_'+role for role in revised[name]['material_roles']]
                require(change['after']==wanted, 'Transport effective slots do not match reviewed mesh roles')
                component['materials'] = wanted
    else:
        require(current['map_file_sha256'] == saved['map_file_sha256'], 'Map bytes changed without a transport patch record')
    require(set(expected) == set(after), 'Scene actor set differs from baseline plus approved transport edits')
    for guid in sorted(core):
        require(after[guid] == before[guid], 'Protected core actor changed: '+before[guid]['label'])
    for guid, row in expected.items():
        require(after[guid] == row, 'Actor/component state changed outside the exact transport manifest: '+row['label'])
    require(saved['world_settings'] == current['world_settings'], 'World settings changed')
    # Coverage contains only auxiliary actors omitted by the editor enumeration;
    # transport additions/removals never exempt or add auxiliary records.
    require(guard.canonical_coverage(saved['world_actor_coverage']) ==
            guard.canonical_coverage(current['world_actor_coverage']),
            'Unfiltered engine/auxiliary actor state changed')
    return dict(core_actor_count=len(core),actor_count=len(after),core_actor_digest=guard.digest([after[g] for g in sorted(core)]),
                actor_digest=guard.digest([after[g] for g in sorted(after)]),removed_transport_actors=sorted(removed),
                added_transport_actors=sorted(added),unchanged_existing_actors=len(before)-len(removed))


def historical_differences(archived, user_state, ownership):
    """Informational only: never undo or reject changes already made by the user."""
    old = {a['guid']:guard.canonical_actor(a) for a in archived['actors']}
    new = {a['guid']:guard.canonical_actor(a) for a in user_state['actors']}
    core = set(ownership['retention']['source_to_copy_guid'].values())
    changed = []
    for guid in sorted(set(old)&set(new)):
        if old[guid] != new[guid]:
            changed.append(dict(guid=guid,label=new[guid]['label'],historical_core=guid in core,
                fields=sorted(key for key in set(old[guid])|set(new[guid]) if old[guid].get(key)!=new[guid].get(key))))
    return dict(informational_only=True,historical_actor_count=len(old),user_actor_count=len(new),
        removed_actor_guids=sorted(set(old)-set(new)),added_actor_guids=sorted(set(new)-set(old)),
        changed_actors=changed,historical_core_present=len(core&set(new)),
        historical_core_removed=sorted(core-set(new)),world_settings_changed=archived['world_settings']!=user_state['world_settings'],
        historical_map_sha256=archived['map_file_sha256'],user_map_sha256=user_state['map_file_sha256'])


def changed_mesh_contract(root, patch, manifest, baseline_hashes):
    result = {}
    if patch is None:return result
    allowed = transport_packages(manifest)
    require(isinstance(patch['changed_meshes'], list), 'Transport changes must be a list')
    for row in patch['changed_meshes']:
        package = row['package']
        require(package in allowed, 'Unapproved changed mesh package: '+package)
        relative = 'Content/'+package.removeprefix('/Game/')+'.uasset'
        require(relative not in result, 'Duplicate changed transport mesh')
        require(baseline_hashes.get(relative) == row['before_sha256'], 'Transport asset baseline mismatch: '+package)
        require(sha(inside(root, relative)) == row['after_sha256'], 'Transport asset post-edit hash mismatch: '+package)
        result[relative] = row['after_sha256']
    return result


def check_retirement(root, manifest, approved_hashes=None):
    if manifest is None:return dict(checked=False,deleted_files=0,retained_content_files=0)
    require(manifest.get('success') is True, 'Legacy deletion is not marked successful')
    deleted = manifest['deleted_files']; retained = manifest['retained_content_hashes']
    require(isinstance(deleted, list) and len(set(deleted)) == len(deleted), 'Invalid duplicate deleted file list')
    require(isinstance(retained, dict) and MAP_FILE in retained, 'Retained hashes must include the new map')
    require(not set(deleted)&set(retained), 'Deleted and retained file sets overlap')
    approved_hashes = approved_hashes or {}
    require(set(approved_hashes) <= set(retained), 'Approved transport hashes are not retained Content')
    for name in deleted:
        require(name.startswith('Content/MPRWarehouse/') or name == 'Content/Maps/MPR_CAD_Warehouse.umap',
                'Deletion report reaches outside legacy MPR resources')
        require(not name.startswith('Content/MPRWarehouse/RebuildB50B57/'), 'Deletion report includes new assets')
        require(not inside(root, name).exists(), 'Retired legacy file is still present: '+name)
    for name, digest in retained.items():
        require(name.startswith('Content/'), 'Retained hashes must be Content paths')
        path = inside(root, name)
        require(path.is_file() and sha(path) == approved_hashes.get(name, digest), 'Retained Content changed or missing: '+name)
    return dict(checked=True,deleted_files=len(deleted),retained_content_files=len(retained),
                approved_transport_hash_overrides=approved_hashes)


def dependencies(u, root):
    registry = u.AssetRegistryHelpers.get_asset_registry()
    registry.search_all_assets(synchronous_search=True)
    registry.scan_paths_synchronous(['/Game'], True)
    registry.wait_for_completion()
    options = u.AssetRegistryDependencyOptions(include_soft_package_references=True,
        include_hard_package_references=True,include_searchable_names=False,
        include_soft_management_references=True,include_hard_management_references=True)
    pending, visited, hashes = [guard.MAP], set(), {}
    while pending:
        package = pending.pop()
        if package in visited:continue
        require(package != guard.SOURCE_MAP and not package.startswith('/Game/MPRWarehouse/ExtensionB50B57/'),
                'Current map depends on retired map/extension: '+package)
        path = package_file(root, package)
        require(u.EditorAssetLibrary.does_asset_exist(package), 'Package not available in Asset Registry: '+package)
        hashes[path.relative_to(root).as_posix()] = sha(path)
        children = registry.get_dependencies(package, options)
        require(children is not None, 'Asset Registry dependency node unavailable: '+package)
        visited.add(package)
        pending.extend(str(p) for p in children if str(p).startswith('/Game/'))
    return sorted(visited), hashes


def run(u=None, *, root=ROOT, report_path=None, transport_patch=None, deletion_manifest=None, user_audit=None):
    """Write a fresh report and return it; a failure is explicit, never a save/quit."""
    root = Path(root).resolve()
    report_path = Path(report_path) if report_path else root/OUTPUT/'current_validation.json'
    result = dict(success=False,map=guard.MAP,assets_saved=False,maps_switched=False,
                  historical_migration_evidence_modified=False)
    try:
        if u is None:import unreal as u
        source = root/SOURCE
        index = read(source/'validation/index.json')
        historical = archived_json(root, index, 'after_reload_normalized.json.gz')
        imported = archived_json(root, index, 'import_report.json')
        ownership = read(source/'scene_ownership.json'); manifest = read(source/'manifest.json')
        require(sha(source/'scene_ownership.json') == imported['ownership_sha256'], 'Historical ownership baseline changed')
        require(ownership['map'] == guard.MAP and ownership['namespace'] == guard.DEST and ownership['owner'] == guard.TAG,
                'Wrong B50B57 ownership identity')
        require(index['map_sha256'] == ownership['map_sha256'] == historical['map_file_sha256'], 'Historical map identities disagree')
        audit_path = Path(user_audit) if user_audit else root/OUTPUT/'legacy_audit.json'
        audit = read(audit_path)
        require(audit.get('success') is True and audit['new_map'] == guard.MAP, 'Current user baseline audit is invalid')
        baseline_path = inside(audit_path.parent, audit['scene_snapshot'])
        require(sha(baseline_path) == audit['scene_snapshot_sha256'], 'User baseline snapshot changed')
        saved = read(baseline_path); guard.assert_clean(saved)
        require(saved['map_file_sha256'] == audit['map_sha256'], 'User baseline map identities disagree')
        require(guard.digest(audit['all_content_files']) == audit['all_content_files_digest'], 'User baseline Content inventory changed')
        require(guard.digest([guard.canonical_actor(a) for a in saved['actors']]) == audit['scene_actor_digest'],
                'User baseline actor digest changed')
        history = historical_differences(historical, saved, ownership)
        patch_path = Path(transport_patch) if transport_patch else root/OUTPUT/'transport_apply.json'
        retire_path = Path(deletion_manifest) if deletion_manifest else root/OUTPUT/'legacy_delete.json'
        patch = read(patch_path) if patch_path.exists() else None
        retirement = read(retire_path) if retire_path.exists() else None
        baseline_hashes = {name:row['sha256'] for name,row in audit['all_content_files'].items()}
        modified = changed_mesh_contract(root, patch, manifest, baseline_hashes)
        current = guard.capture(u, root, guard.MAP); guard.assert_clean(current)
        revised = None
        if patch and patch.get('actor_material_changes'):
            revision_path = root/SOURCE/'transport_revision_20261105/manifest.json'
            require(sha(revision_path)==patch['revision_manifest_sha256'], 'Transport revision manifest changed')
            revised = read(revision_path)
        state = compare_snapshot(saved, current, ownership, manifest, patch, revised)
        reachable, hashes = dependencies(u, root)
        for name, digest in hashes.items():
            expected = current['map_file_sha256'] if name == MAP_FILE else modified.get(name, baseline_hashes.get(name))
            require(digest == expected, 'Unapproved current dependency bytes: '+name)
        solar_rows, _ = guard.solar_source_contract(root, manifest)
        solar_audit = guard.audit_solar_meshes(u, solar_rows)
        require(len(solar_audit) == 5, 'Expected five solar banks with validated LODs')
        retirement_overrides = dict(modified, **{MAP_FILE:current['map_file_sha256']}) if patch else {}
        if retirement is not None:
            for name in retirement_overrides:
                require(retirement['retained_content_hashes'].get(name) == baseline_hashes[name],
                        'Retirement manifest differs from pre-transport baseline: '+name)
        retirement_check = check_retirement(root, retirement, retirement_overrides)
        cvar = 'r.LumenScene.GlobalSDF.ClipmapExtent'
        active = u.SystemLibrary.get_console_variable_float_value(cvar)
        require(abs(active-manifest['render_profile']['lumen_clipmap_extent']) < .01, 'Current map render profile inactive')
        for name, digest in hashes.items():require(sha(root/name) == digest, 'Dependency file changed during validation')
        require(sha(root/MAP_FILE) == current['map_file_sha256'], 'Map bytes changed during validation')
        snapshot_path = report_path.with_name('current_snapshot.json')
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(json.dumps(current,ensure_ascii=False),encoding='utf8')
        result.update(success=True,map_sha256=current['map_file_sha256'],historical_map_sha256=historical['map_file_sha256'],
            user_baseline_sha=sha(baseline_path),user_baseline_map_sha256=saved['map_file_sha256'],
            user_audit_sha256=sha(audit_path),historical_differences=history,
            preservation=state,dependency_packages=reachable,dependency_hashes=hashes,missing_game_packages=[],
            solar_mesh_audit=solar_audit,retirement=retirement_check,transport_mesh_changes=modified,
            render_profile=dict(cvar=cvar,active=active),snapshot=str(snapshot_path),snapshot_sha256=sha(snapshot_path),
            transport_patch_sha256=sha(patch_path) if patch else None,
            deletion_manifest_sha256=sha(retire_path) if retirement else None)
    except Exception:
        result['error'] = traceback.format_exc()
    report_path.parent.mkdir(parents=True,exist_ok=True)
    report_path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print('MPR_CURRENT_VALIDATION',result['success'],str(report_path))
    if result.get('error'):print(result['error'])
    return result


if __name__ == '__main__':
    run()
