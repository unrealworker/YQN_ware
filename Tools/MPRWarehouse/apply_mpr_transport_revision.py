"""Apply only the reviewed B50B57 transport replacement, preserving user edits.

Call run(unreal, apply=True) after legacy cleanup. The default is a read-only
preflight. For the reviewed Interchange interruption, freeze prepare_resume()
first, then explicitly call run(unreal, apply=True, resume=True). No map is
opened or created; no material, source, or unused mesh is deleted. Failed
partial imports retain their original report and verified disk backups.
"""
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager
import json
import re
import shutil
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
import rebuild_preservation as guard
import validate_mpr_current as validation
import retire_mpr_legacy_assets as retirement

SOURCE = 'SourceAssets/MPR/rebuild_b50b57'
REVISION = SOURCE+'/transport_revision_20261105'
OUTPUT = 'Saved/MPR/cleanup_20261105'
MAP_FILE = validation.MAP_FILE
require = guard.require
sha = guard.sha
read = validation.read
inside = validation.inside


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')
    temporary.replace(path)


def source_inventory(root):
    base = (root/'SourceAssets/MPR').resolve()
    answer = {}
    for path in sorted(base.rglob('*')):
        if path.is_file():
            require(path.resolve().is_relative_to(base), 'Source path escaped MPR directory')
            answer[path.relative_to(root).as_posix()] = sha(path)
    return answer


def validate_manifest(root, manifest, base_manifest):
    require(manifest.get('map') == guard.MAP and manifest.get('rebuild_namespace') == guard.DEST,
            'Transport manifest names another map or namespace')
    require(manifest.get('transport_revision') is True and not manifest.get('instances'),
            'Transport revision may not create instances')
    require(manifest.get('base_manifest') == SOURCE+'/manifest.json', 'Unexpected base manifest')
    allowed = validation.transport_packages(base_manifest)
    rows = manifest['meshes']; removed = manifest['remove_mesh_names']
    names = [r['name'] for r in rows]
    require(rows and len(set(names)) == len(names), 'Empty or duplicate transport replacement list')
    require(len(set(removed)) == len(removed) and not set(names)&set(removed), 'Invalid transport removal list')
    for name in names+removed:
        require(re.fullmatch(r'SM_MPRR_[A-Za-z0-9_-]+', name) and guard.DEST+'/Site/Meshes/'+name in allowed,
                'Transport revision references an unapproved or new mesh: '+name)
    for row in rows:
        require(row['category'] == 'Site' and not row.get('instance_only') and not row.get('lod_files')
                and not row.get('lod_material_roles'), 'Unexpected transport import mode')
        require(not row['name'].endswith('_RailBed'), 'Removed/user-deleted RailBed may not be recreated')
        require(row['full_precision_uvs'] is True, 'Transport UV precision must be preserved')
        path = inside(root, row['fbx'])
        require(path.is_relative_to((root/REVISION).resolve()) and path.suffix.lower() == '.fbx',
                'Transport FBX outside isolated revision namespace')
        require(path.is_file() and sha(path) == row['sha256'], 'Transport FBX hash mismatch: '+row['name'])
        require(row['material_roles'] and set(row['material_roles']) <= set(base_manifest['materials']),
                'Transport replacement requests unknown materials')
    for name, digest in manifest['source_hashes'].items():
        require(sha(inside(root/SOURCE, name)) == digest, 'Original source changed: '+name)
    return rows, removed


def plan_removals(snapshot, names, base_manifest, ownership):
    packages = {guard.DEST+'/Site/Meshes/'+name for name in names}
    allowed = validation.transport_packages(base_manifest)
    core = set(ownership['retention']['source_to_copy_guid'].values())
    removed = []; found = set()
    for actor in snapshot['actors']:
        meshes = {c['mesh'].split('.')[0] for c in actor['components'] if c.get('mesh')}
        if not meshes & packages:
            continue
        require(actor['guid'] not in core and validation.is_transport_actor(actor, allowed),
                'Removal would affect protected/nontransport actor: '+actor['label'])
        require(meshes <= packages, 'Mixed mesh actor cannot be removed: '+actor['label'])
        removed.append(actor['guid']); found.update(meshes)
    return sorted(removed), sorted(packages-found)


def planned_effective_material_changes(snapshot, rows, base_manifest, ownership):
    revised = {r['name']:r for r in rows}
    original = {r['name']:r for r in base_manifest['meshes']}
    packages = validation.transport_packages(base_manifest)
    core = set(ownership['retention']['source_to_copy_guid'].values()); changes=[]
    def paths(roles):return [guard.DEST+'/Materials/MI_'+r+'.MI_'+r for r in roles]
    for actor in snapshot['actors']:
        for component in actor['components']:
            mesh = component.get('mesh')
            if not mesh:continue
            name = mesh.split('.')[0].rsplit('/',1)[-1]
            if name not in revised:continue
            wanted = paths(revised[name]['material_roles'])
            if wanted==component['materials']:continue
            require(actor['guid'] not in core and validation.is_transport_actor(actor,packages),
                    'New mesh slot affects a protected/nontransport component')
            require(component['materials']==paths(original[name]['material_roles']),
                    'User material overrides on revised mesh require separate review: '+actor['label'])
            changes.append(dict(guid=actor['guid'],component=component['name'],mesh=mesh,
                                before=component['materials'],after=wanted))
    return sorted(changes,key=lambda r:(r['guid'],r['component']))


def capture_overrides(u, actor_subsystem, guids):
    answer={}
    for actor in actor_subsystem.get_all_level_actors():
        guid=u.GuidLibrary.conv_guid_to_string(actor.get_editor_property('actor_guid'))
        if guid not in guids:continue
        for component in actor.get_components_by_class(u.StaticMeshComponent):
            answer[guid+'/'+component.get_name()]=[
                m.get_path_name() if m is not None else None for m in component.get_editor_property('override_materials')]
    return answer


def package_files(root, package):
    primary = validation.package_file(root, package)
    suffixes = {primary.suffix, * (guard.SUFFIXES-{'.uasset','.umap'})}
    return [p for suffix in sorted(suffixes) if (p := primary.with_suffix(suffix)).is_file()]


def content_scope(before, after, allowed_files):
    """Return actual file changes, failing closed for any unrelated mutation."""
    changed = {}
    for name in sorted(set(before)|set(after)):
        left = before.get(name); right = after.get(name)
        if left == right:
            continue
        require(name in allowed_files and right is not None, 'Unexpected Content change or deletion: '+name)
        changed[name] = dict(before_sha256=left['sha256'] if left else None,
                            after_sha256=right['sha256'], bytes=right['bytes'])
    return changed


@contextmanager
def legacy_fbx_import(u):
    """FbxImportUI settings require the legacy factory on UE 5.8.

    This is the same scoped selector used by import_mpr_scene.run(). Passing
    FbxFactory alone does not suppress Interchange. Never change project config.
    """
    name='Interchange.FeatureFlags.Import.FBX'
    previous=u.SystemLibrary.get_console_variable_int_value(name)
    try:
        u.SystemLibrary.execute_console_command(None,name+' 0')
        require(u.SystemLibrary.get_console_variable_int_value(name)==0, 'Cannot select legacy FBX factory')
        yield previous
    finally:
        u.SystemLibrary.execute_console_command(None,name+' '+str(previous))
        require(u.SystemLibrary.get_console_variable_int_value(name)==previous, 'FBX importer flag did not restore')


def configure_saved_import_data(u, mesh, row):
    """UE5.8 unattended reimport reads this object instead of task options.

    EditorFactories.cpp, UReimportFbxStaticMeshFactory::Reimport assigns the
    asset ImportData to ReimportUI before ApplyImportUIToImportOptions. Match
    the settings already requested by core.import_mesh, without changing core.
    """
    data=mesh.get_editor_property('asset_import_data')
    require(isinstance(data,u.FbxStaticMeshImportData),'Expected legacy saved FBX import data')
    settings=dict(combine_meshes=True,auto_generate_collision=False,generate_lightmap_u_vs=False,
        convert_scene=True,convert_scene_unit=True,force_front_x_axis=False,
        normal_import_method=u.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS,
        normal_generation_method=u.FBXNormalGenerationMethod.BUILT_IN)
    if row.get('vertex_color_fade'):settings['vertex_color_import_option']=u.VertexColorImportOption.REPLACE
    changes=[]
    for name,value in settings.items():
        previous=data.get_editor_property(name)
        if previous!=value:
            data.set_editor_property(name,value)
            changes.append(dict(property=name,before=str(previous),after=str(value)))
        require(data.get_editor_property(name)==value,'Saved FBX option did not persist: '+name)
    return changes


def finalize_transport_mesh(u, mesh):
    """Remove only unneeded generated collision/lightmap settings on this mesh."""
    sm=u.get_editor_subsystem(u.StaticMeshEditorSubsystem)
    before=dict(simple=sm.get_simple_collision_count(mesh),convex=sm.get_convex_collision_count(mesh))
    require(all(value>=0 for value in before.values()),'Collision inspection failed')
    changed_lods=[]
    for lod in range(sm.get_lod_count(mesh)):
        settings=sm.get_lod_build_settings(mesh,lod)
        if settings.get_editor_property('generate_lightmap_u_vs'):
            settings.set_editor_property('generate_lightmap_u_vs',False)
            sm.set_lod_build_settings(mesh,lod,settings);changed_lods.append(lod)
        require(not sm.get_lod_build_settings(mesh,lod).get_editor_property('generate_lightmap_u_vs'),
                'Generated lightmap UVs remained enabled')
    if before['simple'] or before['convex']:
        require(sm.remove_collisions(mesh),'Could not remove generated transport collision')
    after=dict(simple=sm.get_simple_collision_count(mesh),convex=sm.get_convex_collision_count(mesh))
    require(after==dict(simple=0,convex=0),'Transport mesh retains unnecessary simple/convex collision')
    require(u.EditorAssetLibrary.save_loaded_asset(mesh,only_if_is_dirty=False),'Could not save transport import settings')
    return dict(collision_before=before,collision_after=after,lightmap_generation_disabled_lods=changed_lods)


def resume_disk_state(root):
    """Read-only proof that the interrupted attempt touched only its prefix."""
    root=Path(root).resolve();out=root/OUTPUT
    failed_path=out/'transport_apply.json';failed=read(failed_path)
    require(failed.get('success') is False and failed.get('failed_phase')=='importing_meshes'
            and not failed.get('final_map_saved'), 'Only an interrupted pre-map-save mesh import is resumable')
    require('InterchangeAssetImportData' in failed.get('error','') and 'vertex_color_import_option' in failed.get('error',''),
            'Resume is limited to the reviewed Interchange metadata failure')
    manifest_path=root/REVISION/'manifest.json';manifest=read(manifest_path)
    require(sha(manifest_path)==failed['revision_manifest_sha256'], 'Revision changed after interrupted import')
    require(sha(root/REVISION/'geometry_audit.json')==failed['geometry_audit_sha256'], 'Geometry audit changed after failure')
    rows,_=validate_manifest(root,manifest,read(root/SOURCE/'manifest.json'))
    count=failed['completed_meshes'];require(type(count) is int and 0<=count<len(rows), 'Invalid interrupted import index')
    packages=[guard.DEST+'/Site/Meshes/'+r['name'] for r in rows]
    require(failed['mesh_assets_saved']==packages[:count] and failed['current_mesh']==rows[count]['name'],
            'Interrupted report does not identify an exact imported prefix')
    before=read(out/'transport_content_before.json');current,_=retirement.inventory(root)
    allowed=set()
    for package in packages[:count+1]:
        primary=validation.package_file(root,package)
        allowed.update(primary.with_suffix(s).relative_to(root).as_posix()
            for s in {primary.suffix,*(guard.SUFFIXES-{'.uasset','.umap'})})
    changes=content_scope(before,current,allowed)
    require(sha(root/MAP_FILE)==failed['map_sha256_before'], 'Current map changed after interrupted import')
    snapshot=read(out/'transport_before.json')
    require(snapshot['map_file_sha256']==failed['map_sha256_before'], 'Interrupted original snapshot map differs')
    backup=out/'transport_backup';backup_manifest=read(backup/'manifest.json')
    expected_backups={MAP_FILE}
    for package in [guard.MAP,*packages]:
        stem='Content/'+package.removeprefix('/Game/')
        expected_backups.update(stem+suffix for suffix in guard.SUFFIXES if stem+suffix in before)
    require(set(backup_manifest)==expected_backups, 'Original transport backup package set is incomplete')
    for name,info in backup_manifest.items():
        require(before.get(name)==info and sha(inside(backup,name))==info['sha256'], 'Original transport backup is not intact: '+name)
    sources=read(out/'transport_sources_before.json')
    require(source_inventory(root)==sources, 'Sources changed since interrupted import')
    return dict(success=True,failed_report_sha256=sha(failed_path),revision_manifest_sha256=sha(manifest_path),
        geometry_audit_sha256=failed['geometry_audit_sha256'],completed_meshes=count,
        attempted_packages=packages[:count+1],partial_modified_files=changes,current_content_files=current,
        current_content_digest=guard.digest(current),original_snapshot_sha256=sha(out/'transport_before.json'),
        original_content_sha256=sha(out/'transport_content_before.json'),original_sources_sha256=sha(out/'transport_sources_before.json'),
        backup_manifest_sha256=sha(backup/'manifest.json'),map_sha256=failed['map_sha256_before'])


def prepare_resume(*, root=ROOT):
    """Freeze a CPU-only resume plan; no UE objects or Content files are touched."""
    root=Path(root).resolve();path=root/OUTPUT/'transport_resume_plan.json'
    require(not path.exists(), 'Resume plan already exists; review it rather than overwrite')
    result=resume_disk_state(root);write(path,result)
    return result


def assert_resume_clean(snapshot, attempted_packages):
    require(set(snapshot['dirty_maps']) <= {guard.MAP}, 'Unrelated dirty map prevents transport resume')
    require(set(snapshot['dirty_content']) <= set(attempted_packages),
            'Unsaved Content outside interrupted mesh prefix prevents resume')


def run(u=None, *, root=ROOT, apply=False, resume=False):
    root = Path(root).resolve(); out = root/OUTPUT
    report = out/('transport_resume_apply.json' if resume and apply else
                 'transport_resume_preflight.json' if resume else
                 'transport_apply.json' if apply else 'transport_preflight.json')
    require(not (apply and report.exists()), 'Existing transport apply report requires review before retry')
    resume_state=None;failed=None
    if resume:
        resume_state=resume_disk_state(root)
        require(read(out/'transport_resume_plan.json')==resume_state, 'Current partial state differs from the reviewed resume plan')
        failed=read(out/'transport_apply.json')
    result = dict(success=False,phase='preflight',map=guard.MAP,namespace=guard.DEST,
                  created_utc=datetime.now(timezone.utc).isoformat(),apply=apply,
                  added_actor_guids=[],added_actors=[],removed_actor_guids=[],changed_meshes=[],
                  assets_deleted=False,materials_modified=False,source_files_modified=False,maps_switched=False,
                  mesh_assets_saved=[],final_map_saved=False,resume=resume)
    old_core = None
    def progress(phase, **values):
        result.update(phase=phase, **values); write(report, result)
        print('MPR_TRANSPORT_PROGRESS', phase, result.get('completed_meshes',0), '/',result.get('mesh_count',0),flush=True)
    try:
        if u is None:import unreal as u
        manifest_path=root/REVISION/'manifest.json'; manifest=read(manifest_path)
        base=read(root/SOURCE/'manifest.json'); ownership=read(root/SOURCE/'scene_ownership.json')
        rows, remove_names=validate_manifest(root,manifest,base)
        geometry=read(root/REVISION/'geometry_audit.json')
        require(geometry.get('success') is True and geometry.get('native_export_complete') is True,
                'Transport native export is incomplete')
        require(set(geometry['mesh_names']) == {r['name'] for r in rows} and geometry['remove_mesh_names']==remove_names,
                'Transport geometry audit disagrees with import list')
        require(not geometry['new_mesh_names'], 'Transport revision may not create new packages or actors')
        audit_path=out/'legacy_audit.json'; audit=read(audit_path)
        require(audit.get('success') is True and audit['new_map']==guard.MAP, 'Missing reviewed current-map baseline')
        baseline_path=inside(out,audit['scene_snapshot'])
        require(sha(baseline_path)==audit['scene_snapshot_sha256'], 'User baseline snapshot changed')
        baseline=read(baseline_path); guard.assert_clean(baseline)
        require(baseline['map_file_sha256']==audit['map_sha256'], 'User baseline map hash mismatch')
        require(guard.digest(audit['all_content_files'])==audit['all_content_files_digest'], 'Audit file inventory changed')
        observed=guard.capture(u,root,guard.MAP)
        if resume:assert_resume_clean(observed,resume_state['attempted_packages'])
        else:guard.assert_clean(observed)
        before=read(out/'transport_before.json') if resume else observed
        validation.compare_snapshot(baseline,before,ownership,base)
        removed, absent=plan_removals(before,remove_names,base,ownership)
        material_changes=planned_effective_material_changes(before,rows,base,ownership)
        partial_material_changes=[]
        if resume:
            partial_material_changes=[r for r in material_changes if r['mesh'].split('.')[0] in resume_state['attempted_packages']]
            partial_contract=dict(success=True,map_sha256_before=before['map_file_sha256'],
                map_sha256_after=observed['map_file_sha256'],removed_actor_guids=[],added_actor_guids=[],
                actor_material_changes=partial_material_changes)
            validation.compare_snapshot(before,observed,ownership,base,partial_contract,manifest)
        content_before=read(out/'transport_content_before.json') if resume else retirement.inventory(root)[0]
        require(all(audit['all_content_files'].get(k)==v for k,v in content_before.items()),
                'Content differs from audited user state')
        deleted=set(audit['all_content_files'])-set(content_before)
        deletion_path=out/'legacy_delete.json'; deletion=read(deletion_path) if deletion_path.exists() else None
        if deletion is not None:
            require(set(deletion['deleted_files'])==deleted, 'Legacy deletion differs from the audited file delta')
            partial_hashes={k:v['after_sha256'] for k,v in resume_state['partial_modified_files'].items()} if resume else {}
            validation.check_retirement(root,deletion,partial_hashes)
        else:require(not deleted, 'Content was removed without a verified cleanup report')
        packages=[guard.DEST+'/Site/Meshes/'+r['name'] for r in rows]
        file_paths={MAP_FILE:root/MAP_FILE}; allowed_files=set()
        for package in [guard.MAP,*packages]:
            primary=validation.package_file(root,package)
            allowed_files.update(primary.with_suffix(s).relative_to(root).as_posix()
                for s in {primary.suffix, *(guard.SUFFIXES-{'.uasset','.umap'})})
            for path in package_files(root,package):file_paths[path.relative_to(root).as_posix()]=path
        import import_mpr_scene as core
        affected_guids={a['guid'] for a in before['actors'] if any(
            c.get('mesh') and c['mesh'].split('.')[0] in packages for c in a['components'])}
        overrides_before=capture_overrides(u,core.A,affected_guids)
        if resume:require(overrides_before==failed['actor_material_overrides_before'], 'Actor material overrides changed after interruption')
        roles={role for row in rows for role in row['material_roles']}; materials={}
        for role in sorted(roles):
            path=guard.DEST+'/Materials/MI_'+role
            validation.package_file(root,path)
            mat=core.load(path)
            require(isinstance(mat,u.MaterialInterface) and mat.get_path_name().split('.')[0]==path,
                    'Transport material is not an existing rebuild material: '+role)
            materials[role]=mat
        progress('hashing_sources',mesh_count=len(rows),removed_actor_guids=removed,
                 already_absent_removal_packages=absent,map_sha256_before=before['map_file_sha256'],
                 user_baseline_sha=sha(baseline_path),user_audit_sha256=sha(audit_path),
                 actor_material_changes=material_changes,actor_material_overrides_before=overrides_before,
                 revision_manifest_sha256=sha(manifest_path),geometry_audit_sha256=sha(root/REVISION/'geometry_audit.json'))
        sources_before=read(out/'transport_sources_before.json') if resume else source_inventory(root)
        # Loading existing mesh/material assets is also included in this clean-state check.
        loaded=guard.capture(u,root,guard.MAP)
        if resume:assert_resume_clean(loaded,resume_state['attempted_packages'])
        else:guard.assert_clean(loaded)
        validation.compare_snapshot(before,loaded,ownership,base,partial_contract if resume else None,manifest if resume else None)
        if not resume:
            write(out/'transport_before.json',before)
            write(out/'transport_content_before.json',content_before)
            write(out/'transport_sources_before.json',sources_before)
        if not apply:
            result.update(success=True,phase='preflight_complete',source_file_count=len(sources_before),
                          backup_file_count=len(file_paths),material_roles=sorted(roles))
            write(report,result);return result
        backup=out/'transport_backup'
        if resume:
            failure_archive=out/'transport_apply_failed_interchange.json'
            require(not failure_archive.exists(), 'Failure archive must never be overwritten')
            shutil.copy2(out/'transport_apply.json',failure_archive)
            require(sha(failure_archive)==resume_state['failed_report_sha256'], 'Failure report archive differs')
            write(out/'transport_resume_before.json',observed)
            result.update(resume_plan_sha256=sha(out/'transport_resume_plan.json'),
                failed_report_archive=str(failure_archive),failed_report_sha256=sha(failure_archive),
                resume_dirty_maps=observed['dirty_maps'],resume_dirty_content=observed['dirty_content'],
                interrupted_content_digest=resume_state['current_content_digest'],
                interrupted_modified_files=resume_state['partial_modified_files'])
        else:
            require(not backup.exists(), 'Existing transport backup must not be overwritten')
            backup.mkdir(parents=True)
            progress('backing_up')
            for name,path in file_paths.items():
                target=inside(backup,name);target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(path,target)
                require(sha(target)==content_before[name]['sha256'], 'Transport backup verification failed: '+name)
            write(backup/'manifest.json',{name:content_before[name] for name in sorted(file_paths)})
        old_core={key:getattr(core,key) for key in ('ROOT','DEST','MATS','MESHES','result','material')}
        core.ROOT=root;core.DEST=guard.DEST;core.MATS=materials;core.MESHES={}
        core.result=dict(meshes=[])
        def readonly_material(role):
            require(role in materials, 'Unplanned material role during transport import: '+role)
            return materials[role]
        core.material=readonly_material
        progress('importing_meshes',completed_meshes=0)
        with legacy_fbx_import(u) as previous_flag:
            result['fbx_importer']=dict(mode='legacy_fbx',previous_interchange_flag=previous_flag,scoped=True)
            for index,row in enumerate(rows,1):
                result['current_mesh']=row['name'];write(report,result)
                existing=core.load(guard.DEST+'/Site/Meshes/'+row['name'])
                configure_saved_import_data(u,existing,row)
                mesh=core.import_mesh(row,'Site')
                finalize_transport_mesh(u,mesh)
                package=guard.DEST+'/Site/Meshes/'+row['name']
                require(mesh.get_path_name().split('.')[0]==package, 'Importer saved an unexpected transport package')
                require(isinstance(mesh.get_editor_property('asset_import_data'),u.FbxStaticMeshImportData),
                        'Transport import bypassed the legacy FBX factory')
                result['mesh_assets_saved'].append(package)
                progress('importing_meshes',completed_meshes=index)
        result['fbx_importer']['flag_restored']=True
        # Effective default slots can grow exactly as reviewed; actor overrides,
        # transforms and all other component properties remain unchanged.
        after_import=guard.capture(u,root,guard.MAP)
        contract=dict(success=True,map_sha256_before=before['map_file_sha256'],
                      map_sha256_after=after_import['map_file_sha256'],removed_actor_guids=[],added_actor_guids=[],added_actors=[],
                      actor_material_changes=material_changes)
        validation.compare_snapshot(before,after_import,ownership,base,contract,manifest)
        require(capture_overrides(u,core.A,affected_guids)==overrides_before, 'Transport import changed actor material overrides')
        guard.assert_clean(after_import,allow_new_map=True)
        live={u.GuidLibrary.conv_guid_to_string(a.get_editor_property('actor_guid')):a
              for a in core.A.get_all_level_actors()}
        progress('removing_listed_transport_actors')
        for guid in removed:
            require(guid in live and core.A.destroy_actor(live[guid]), 'Cannot remove listed transport actor: '+guid)
        after=guard.capture(u,root,guard.MAP);guard.assert_clean(after,allow_new_map=True)
        contract.update(map_sha256_after=after['map_file_sha256'],removed_actor_guids=removed)
        validation.compare_snapshot(before,after,ownership,base,contract,manifest)
        content_partial,_=retirement.inventory(root);content_scope(content_before,content_partial,allowed_files)
        require(source_inventory(root)==sources_before, 'Source files changed during transport import')
        progress('saving_current_map')
        require(core.L.save_current_level(), 'Failed to save current MPR map')
        result['final_map_saved']=True
        registry=u.AssetRegistryHelpers.get_asset_registry()
        registry.scan_modified_asset_files([str(p) for p in file_paths.values()]);registry.wait_for_completion()
        final=guard.capture(u,root,guard.MAP);guard.assert_clean(final)
        contract['map_sha256_after']=final['map_file_sha256']
        state=validation.compare_snapshot(before,final,ownership,base,contract,manifest)
        require(capture_overrides(u,core.A,affected_guids)==overrides_before, 'Saving changed actor material overrides')
        write(out/'transport_after.json',final)
        content_after,_=retirement.inventory(root)
        changes=content_scope(content_before,content_after,allowed_files)
        require(source_inventory(root)==sources_before, 'Source files changed before transport completion')
        for package in packages:
            name='Content/'+package.removeprefix('/Game/')+'.uasset'
            result['changed_meshes'].append(dict(package=package,before_sha256=content_before[name]['sha256'],
                                                after_sha256=content_after[name]['sha256']))
        overrides={name:row['after_sha256'] for name,row in changes.items()}
        validation.check_retirement(root,deletion,overrides)
        result.update(success=True,phase='complete',map_sha256_after=final['map_file_sha256'],
            modified_files=changes,preservation=state,source_file_count=len(sources_before),
            source_files_sha256=guard.digest(sources_before),other_content_unchanged=True,
            before_snapshot_sha256=sha(out/'transport_before.json'),after_snapshot_sha256=sha(out/'transport_after.json'),
            imported_meshes=core.result['meshes'],backup_directory=str(backup),
            removed_mesh_packages_retained=[guard.DEST+'/Site/Meshes/'+name for name in remove_names])
    except Exception:
        result.update(success=False,failed_phase=result['phase'],phase='failed',error=traceback.format_exc())
        print(result['error'],flush=True)
    finally:
        if old_core is not None:
            for key,value in old_core.items():setattr(core,key,value)
    write(report,result)
    if resume and result['success']:
        require(sha(out/'transport_apply.json')==resume_state['failed_report_sha256'], 'Original failure report changed during resume')
        write(out/'transport_apply.json',result)
    print('MPR_TRANSPORT_APPLY',result['success'],result['phase'],str(report),flush=True)
    return result


if __name__=='__main__':run()
