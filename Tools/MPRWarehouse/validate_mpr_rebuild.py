"""Independent native reload validation for the new MPR map; never saves assets."""
import json,sys,traceback
from pathlib import Path
import unreal as u
ROOT=Path(u.Paths.convert_relative_path_to_full(u.Paths.project_dir())).resolve()
sys.path.insert(0,str(ROOT/'Tools/MPRWarehouse'))
import rebuild_preservation as guard
SRC=ROOT/'SourceAssets/MPR/rebuild_b50b57'
OUT=ROOT/'Saved/MPR/rebuild_20261104'
require=guard.require
sha=guard.sha

def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))

def assert_saved_state(saved,current):
    expected=[guard.canonical_actor(r) for r in saved['actors']]
    actual=[guard.canonical_actor(r) for r in current['actors']]
    require(expected==actual,'New map reload changed actor/component/instance state')
    require(saved['world_settings']==current['world_settings'],'New map reload changed world settings')
    require(guard.canonical_coverage(saved.get('world_actor_coverage',[]))==
            guard.canonical_coverage(current.get('world_actor_coverage',[])),
            'New map reload changed unfiltered engine auxiliary actors')
    return guard.digest(actual)

def run():
    imported=read(OUT/'import_report.json')
    require(imported.get('success') is True,'No successful new-map import')
    require(sha(SRC/'scene_ownership.json')==imported['ownership_sha256'],'New-map ownership changed')
    ownership=read(SRC/'scene_ownership.json')
    require(ownership['map']==guard.MAP and ownership['namespace']==guard.DEST and ownership['owner']==guard.TAG,
            'New-map ownership identity mismatch')
    checks={'source_snapshot.json':'source_snapshot_sha256','old_content_hashes.json':'old_content_hashes_sha256',
            'old_ownership_hashes.json':'old_ownership_hashes_sha256','after_import.json':'after_import_sha256'}
    for filename,key in checks.items():require(sha(OUT/filename)==ownership[key],'Changed audit snapshot: '+filename)
    require(sha(SRC/'protection_plan.json')==ownership['protection_plan_sha256'],'Retention plan changed')
    require(sha(SRC/'manifest.json')==ownership['source_manifest_sha256'],'Imported source manifest changed')
    manifest=read(SRC/'manifest.json')
    require(ownership['material_changes']==imported['material_changes'],'Material exception records disagree')
    require(ownership['mesh_changes']==imported['mesh_changes'],'Solar mesh exception records disagree')
    solar_rows,solar_files=guard.solar_source_contract(ROOT,manifest)
    expected_sources={r['fbx']:r['sha256'] for r in manifest['meshes']};expected_sources.update(solar_files)
    require(ownership['source_files']==expected_sources,'Source ownership omits or changes an imported FBX/solar LOD')
    guard.retained_material_spec_map(manifest.get('retained_material_overrides',[]),manifest['materials'])
    for filename,expected in ownership['source_files'].items():
        path=(ROOT/filename).resolve()
        require(path.is_relative_to(SRC.resolve()) and sha(path)==expected,'Imported source changed: '+filename)
    old_files=read(OUT/'old_content_hashes.json')
    new_files=guard.assert_old_files(ROOT,old_files)
    require(new_files==ownership['new_files'],'New-map package set/bytes changed')
    for filename,expected in read(OUT/'old_ownership_hashes.json').items():
        require(sha(ROOT/filename)==expected,'Original ownership file changed: '+filename)
    source=read(OUT/'source_snapshot.json');plan=read(SRC/'protection_plan.json')
    guard.assert_source_plan(plan,source)
    require(sha(ROOT/'Content/Maps/MPR_CAD_Warehouse.umap')==ownership['source_map_sha256'],
            'Original MPR map was modified')
    saved=read(OUT/'after_import.json')
    current=guard.capture(u,ROOT,guard.MAP)
    (OUT/'after_reload_observed.json').write_text(json.dumps(current,ensure_ascii=False),encoding='utf-8')
    guard.assert_clean(current)
    retained=guard.assert_retained(source,current,plan,
        guid_map=ownership['retention']['source_to_copy_guid'],lighting_changes=ownership['lighting_changes'],
        material_changes=ownership['material_changes'],material_overrides=manifest.get('retained_material_overrides',[]),
        mesh_changes=ownership['mesh_changes'],mesh_overrides=manifest.get('retained_mesh_overrides',[]))
    require(retained==ownership['retention'],'Retained building audit changed')
    new_guids=guard.assert_new_actor_scope(source,current,plan)
    require(new_guids==ownership['new_actor_guids'],'New actor set changed on reload')
    require(assert_saved_state(saved,current)==ownership['actor_digest'],'Durable new-map actor digest changed')
    require(current['map_file_sha256']==ownership['map_sha256']==imported['map_sha256'],'New map bytes changed')
    dependencies=guard.assert_independent_dependencies(u)
    solar_audit=guard.audit_solar_meshes(u,solar_rows)
    require(solar_audit==ownership['solar_mesh_audit']==imported['solar_mesh_audit'],'Solar LOD/material audit changed on reload')
    normalized=dict(current,actors=[guard.canonical_actor(r) for r in current['actors']],
                    world_actor_coverage=guard.canonical_coverage(current['world_actor_coverage']))
    (OUT/'after_reload_normalized.json').write_text(json.dumps(normalized,ensure_ascii=False),encoding='utf-8')
    return dict(success=True,map=guard.MAP,map_sha256=current['map_file_sha256'],
        original_map_sha256=ownership['source_map_sha256'],original_map_unchanged=True,
        unchanged_original_content_files=len(old_files),new_package_files=len(new_files),
        retained=retained,new_actor_count=len(new_guids),actor_count=len(current['actors']),
        editor_sprite_names_normalized_only=True,all_retained_geometry_instances_exact=not bool(ownership['mesh_changes']),
        all_retained_geometry_materials_instances_exact=not bool(ownership['material_changes'] or ownership['mesh_changes']),
        retained_geometry_unchanged_except_approved_solar_meshes=True,retained_transforms_instances_exact=True,
        mesh_changes=ownership['mesh_changes'],solar_mesh_audit=solar_audit,solar_source_files_verified=len(solar_files),
        retained_material_changes_limited_to_approved_slots=True,material_changes=ownership['material_changes'],
        source_manifest_sha256=ownership['source_manifest_sha256'],lighting_changes=ownership['lighting_changes'],
        dependency_packages=dependencies,cancelled_extension_dependencies=False)

if __name__=='__main__':
    try:
        # Start this process on the original map to measure the real baseline,
        # then prove both activation and restoration by loading each world.
        world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
        require(world.get_path_name().split('.')[0]==guard.SOURCE_MAP,'Start reload validation on the original map')
        cvar='r.LumenScene.GlobalSDF.ClipmapExtent'
        baseline=u.SystemLibrary.get_console_variable_float_value(cvar)
        levels=u.get_editor_subsystem(u.LevelEditorSubsystem)
        require(levels.load_level(guard.MAP),'Cannot load independent map for reload validation')
        expected=read(SRC/'manifest.json')['render_profile']['lumen_clipmap_extent']
        active=u.SystemLibrary.get_console_variable_float_value(cvar)
        require(abs(active-expected)<.01,'Map render profile is not active after reload')
        result=run()
        require(levels.load_level(guard.SOURCE_MAP),'Cannot reload original map for profile restoration test')
        restored=u.SystemLibrary.get_console_variable_float_value(cvar)
        require(abs(restored-baseline)<.01,'New-map render profile leaked into original map')
        result['render_profile_lifecycle']=dict(success=True,cvar=cvar,before=baseline,active=active,restored=restored)
    except Exception:
        result=dict(success=False,error=traceback.format_exc());u.log_error(result['error'])
    (OUT/'reload_report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('MPR_REBUILD_RELOAD',result.get('success'))
