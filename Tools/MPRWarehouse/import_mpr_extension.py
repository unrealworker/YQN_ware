"""Append B50B57 geometry; only replace three explicitly authorized road tails.

Run in an isolated editor after build_mpr_extension.py. No old mesh/material is saved.
The exact original map is backed up before its one append save. All new outputs
are journaled so an interrupted attempt can be reviewed/rolled back separately.
"""
import hashlib, json, os, re, shutil, sys, tempfile, traceback
from pathlib import Path
from collections import defaultdict
import unreal as u

ROOT=Path(u.Paths.convert_relative_path_to_full(u.Paths.project_dir())).resolve()
sys.path.insert(0,str(ROOT/'Tools/MPRWarehouse'))
import extension_preservation as guard
import import_mpr_scene as core
from mpr_scene_ownership import verify_owned_scene, refresh_map_hash
OUT=ROOT/'Saved/MPR/extension_20261104'
SRC=ROOT/'SourceAssets/MPR/extension_b50b57'
DEST=guard.EXTENSION_NAMESPACE
MAP_FILE=ROOT/'Content/Maps/MPR_CAD_Warehouse.umap'
REPORT=OUT/'import_report.json'
OLD_OWNERSHIP=ROOT/'SourceAssets/MPR/scene_ownership.json'
EXTENSION_OWNERSHIP=SRC/'scene_ownership.json'
result=dict(success=False,namespace=DEST,created_packages=[],created_actors=[],
            source_manifest_sha256=None,old_packages_saved=False,
            map_save_attempted=False,map_saved=False,phase='preflight')

def write_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,
                prefix='.'+path.name+'-',suffix='.tmp',delete=False) as stream:
            temp=Path(stream.name)
            json.dump(data,stream,ensure_ascii=False,indent=2)
            stream.write('\n')
        os.replace(temp,path)
    finally:
        if temp and temp.exists():temp.unlink()

def write():
    write_json(REPORT,result)

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def require(condition,message):
    if not condition:raise guard.PreservationError(message)

def validate_manifest(manifest,before):
    require(manifest.get('extension_namespace')==DEST,'Unexpected extension namespace')
    require(manifest.get('read_only_inputs_unchanged') is True,'Build has not verified its read-only inputs')
    rows=manifest['meshes']
    require(bool(rows),'Empty extension mesh manifest')
    names=[r['name'] for r in rows]
    require(all(re.fullmatch(r'SM_MPRE_[A-Za-z0-9_-]+',n) for n in names),'Invalid extension mesh name')
    planned=[DEST+'/Meshes/'+n for n in names]
    guard.assert_new_package_destinations(ROOT,planned)
    for row in rows:
        source=(ROOT/row['fbx']).resolve()
        require(source.is_relative_to(SRC.resolve()) and source.suffix.lower()=='.fbx',
                'Mesh source is outside extension source directory: '+row['fbx'])
        require(not row.get('lod_files'),'This extension contract has no external LOD sources')
        require(bool(row['material_roles']) and all(re.fullmatch(r'[A-Za-z0-9_]+',r)
                for r in row['material_roles']),'Invalid extension material roles')
    specs=manifest.get('allowed_replacements',[])
    require(len(specs)==3 and {r['old_mesh'] for r in specs}==guard.TERMINAL_MESHES,
            'Exactly the three authorized road-terminal replacement slots are required')
    replacements={r['old_mesh']:DEST+'/Meshes/'+r['new_mesh']+'.'+r['new_mesh'] for r in specs}
    targets={r['new_mesh'] for r in specs}
    require(len(targets)==3 and targets.issubset(names),'Missing/duplicate terminal replacement output')
    require({r['name'] for r in rows if r.get('replacement_only')}==targets,
            'replacement_only flags do not match the three terminal targets')
    plan=guard.terminal_mesh_replacement_plan(before,replacements)
    for name,instances in manifest.get('instances',{}).items():
        require(name in manifest.get('reused_meshes',{}),'Missing reused mesh: '+name)
        path=manifest['reused_meshes'][name]
        require(path.split('.')[0] in before['asset_hashes'],'Reused mesh lacks baseline hashes: '+path)
        for instance in instances:
            require(len(instance.get('tile',[]))==2 and all(isinstance(v,int) for v in instance['tile']),
                    'Invalid HISM tile: '+name)
    return rows,planned,plan

def verify_sources(rows):
    require(sha(SRC/'manifest.json')==result['source_manifest_sha256'],'Build manifest changed during import')
    for row in rows:
        require(sha(ROOT/row['fbx'])==row['sha256'],row['name']+' source changed')

def assert_snapshot_content_equal(expected,actual,stage):
    expected_rows={r['guid']:r for r in expected['actors']}
    actual_rows={r['guid']:r for r in actual['actors']}
    changed=sorted(g for g in set(expected_rows)|set(actual_rows)
                   if expected_rows.get(g)!=actual_rows.get(g))
    require(not changed,stage+' changed actor/component/instance state: '+', '.join(changed[:12]))
    require(expected['asset_hashes']==actual['asset_hashes'],stage+' changed dependency package bytes')

def assert_generated_actor_types(before,after):
    existing={r['guid'] for r in before['actors']}
    allowed={'/Script/Engine.StaticMeshActor',
             '/Game/GHSDigitalTwin/Blueprints/BP_GHS_InstanceGroup.BP_GHS_InstanceGroup_C'}
    for row in after['actors']:
        if row['guid'] not in existing:
            require(row['class'] in allowed,'Unexpected generated scene controller/actor class: '+row['class'])

def tagged(actor,folder,extra=()):
    actor.set_folder_path(guard.EXTENSION_FOLDER+'/'+folder)
    actor.tags=['MPRWarehouse',guard.EXTENSION_TAG,*extra]
    actor.set_actor_tick_enabled(False)
    actor.set_actor_enable_collision(False)
    result['created_actors'].append(actor.get_actor_label())

def snapshot(before):
    return guard.capture_editor_snapshot(u,project_root=ROOT,
        additional_packages=before['asset_hashes'],frozen_paths=before['frozen_files'])

def synchronize_new_package_registry(packages):
    """Publish saved new package dependencies before any level mutation."""
    files=[]
    for package in packages:
        require(package.startswith(DEST+'/Meshes/'),
                'Registry refresh escaped the new mesh namespace: '+package)
        path=(ROOT/'Content'/package[len('/Game/'):]).with_suffix('.uasset')
        require(path.resolve().is_relative_to((ROOT/'Content'/DEST[len('/Game/'):]).resolve()),
                'Registry refresh path escaped the extension namespace: '+str(path))
        require(path.is_file(),'Imported package has not been saved: '+package)
        files.append(str(path))
    registry=u.AssetRegistryHelpers.get_asset_registry()
    registry.scan_modified_asset_files(files)
    registry.scan_paths_synchronous([DEST],True)
    registry.wait_for_completion()
    options=u.AssetRegistryDependencyOptions(include_soft_package_references=True,
        include_hard_package_references=True,include_searchable_names=False,
        include_soft_management_references=False,include_hard_management_references=False)
    counts={}
    for package in packages:
        dependencies=registry.get_dependencies(package,options)
        require(dependencies is not None,
                'Saved new package dependency node unavailable after synchronous registry scan: '+package)
        counts[package]=len(dependencies)
    return dict(namespace=DEST,files_scanned=len(files),dependency_counts=counts,
                wait_for_completion=True)

def run():
    source_bytes=(SRC/'manifest.json').read_bytes()
    manifest=json.loads(source_bytes)
    result['source_manifest_sha256']=hashlib.sha256(source_bytes).hexdigest()
    before=json.loads((OUT/'baseline.json').read_text(encoding='utf-8'))
    result['baseline_map_sha256']=before['map_file_sha256']
    require(sha(MAP_FILE)==before['map_file_sha256'],'Map changed after baseline; capture a fresh baseline.')
    require(not EXTENSION_OWNERSHIP.exists(),'Extension already has ownership; refusing an unreviewed rebuild')
    ownership_token=verify_owned_scene(ROOT)
    original_ownership=json.loads(OLD_OWNERSHIP.read_text(encoding='utf-8'))
    original_owned_assets=[r for r in original_ownership['packages'] if r['package']!=guard.MAP]
    result['original_owned_package_count']=len(original_owned_assets)
    result['original_owned_packages_digest']=guard.canonical_digest(original_owned_assets)
    # Verify the live scene is still the same as the clean baseline, including
    # all extra material roots reserved for read-only reuse.
    live=snapshot(before)
    guard.assert_clean_baseline(live)
    guard.assert_preserved(before,live)
    rows,planned,plan=validate_manifest(manifest,before)
    result['planned_packages']=planned
    result['allowed_mesh_replacements']=plan
    verify_sources(rows)
    backup=OUT/'pre_extension_MPR_CAD_Warehouse.umap'
    if backup.exists():assert sha(backup)==sha(MAP_FILE),'Existing backup is not this baseline'
    else:shutil.copy2(MAP_FILE,backup)
    ownership_backup=OUT/'pre_extension_scene_ownership.json'
    if ownership_backup.exists():
        require(sha(ownership_backup)==ownership_token['manifest_sha256'],'Ownership backup is not this baseline')
    else:shutil.copy2(OLD_OWNERSHIP,ownership_backup)
    result['baseline_map_sha256']=sha(MAP_FILE)
    result['backup']=str(backup)
    result['ownership_backup']=str(ownership_backup)
    core.DEST=DEST
    core.tag=tagged
    core.MATS.clear();core.MESHES.clear();core.INSTANCE_MATS.clear()
    core.result=dict(meshes=[],groups=[],materials_created=[],reused_assets=[])
    for role in sorted({r for row in rows for r in row['material_roles']}):
        path='/Game/MPRWarehouse/ReferenceV4/Materials/MI_'+role
        require(path in before['asset_hashes'],'Shared material lacks protected baseline hash: '+path)
        core.MATS[role]=core.load(path)
    # Reused HISM materials are already runtime-ready; never auto-create or
    # modify a parent material usage permutation in this incremental import.
    def readonly_instance_material(mat):
        require(mat is not None,'Missing HISM material')
        require(core.MATLIB.has_material_usage(mat,core.USAGE),mat.get_path_name()+' missing HISM usage')
        return mat
    core.instance_material=readonly_instance_material
    reused={}
    for name,instances in manifest.get('instances',{}).items():
        if not instances:continue
        mesh=core.load(manifest['reused_meshes'][name])
        for slot in mesh.static_materials:
            mat=readonly_instance_material(slot.material_interface)
            require(mat.get_path_name().split('.')[0] in before['asset_hashes'],
                    'HISM material lacks protected baseline hash: '+mat.get_path_name())
        reused[name]=mesh
    guard.assert_clean_baseline(snapshot(before))
    result['phase']='importing_new_packages'
    write()
    for row in rows:
        # core adds category/Meshes: use the namespace's last segment as the
        # category so its final destination exactly matches the preflight.
        core.DEST=DEST.rsplit('/',1)[0]
        mesh=core.import_mesh(row,DEST.rsplit('/',1)[1])
        require(mesh.get_path_name().split('.')[0]==DEST+'/Meshes/'+row['name'],'Unexpected imported mesh package')
        result['created_packages'].append(mesh.get_path_name().split('.')[0])
        write()
    core.DEST=DEST
    require(sorted(result['created_packages'])==sorted(planned),'Imported package set differs from the plan')
    result['phase']='synchronizing_new_package_registry'
    write()
    result['asset_registry_sync']=synchronize_new_package_registry(planned)
    replaced_names={r['new_mesh'] for r in manifest['allowed_replacements']}
    result['phase']='applying_terminal_mesh_replacements'
    write()
    actors=core.A.get_all_level_actors()
    by_guid={u.GuidLibrary.conv_guid_to_string(a.get_editor_property('actor_guid')):a for a in actors}
    for replacement in plan:
        actor=by_guid[replacement['actor_guid']]
        component=next(c for c in actor.get_components_by_class(u.StaticMeshComponent)
                       if c.get_name()==replacement['component_name'])
        original_materials=[component.get_material(i) for i in range(component.get_num_materials())]
        require(component.set_static_mesh(core.load(replacement['new_mesh'])),'Terminal mesh assignment failed')
        for i,mat in enumerate(original_materials):
            if component.get_material(i)!=mat:component.set_material(i,mat)
    result['phase']='adding_actors'
    for row in rows:
        if row['name'] in replaced_names:continue
        actor=core.spawn_mesh(row['name'],core.MESHES[row['name']],folder='Geometry')
        component=actor.get_component_by_class(u.StaticMeshComponent)
        if row.get('disable_shadow_casting'):component.set_editor_property('cast_shadow',False)
    for name,instances in manifest.get('instances',{}).items():
        if not instances:continue
        mesh=reused[name]
        tiles=defaultdict(list)
        for row in instances:tiles[tuple(row['tile'])].append(row)
        for (x,y),items in sorted(tiles.items()):
            core.group('MPRE_'+name+'_%d_%d'%(x,y),mesh,items,'Vegetation',cull=230000)
    after=snapshot(before)
    assert_generated_actor_types(before,after)
    validation=guard.assert_preserved(before,after,allowed_mesh_replacements=plan)
    result['preservation_before_save']=validation
    guard.verify_protected_files(before,project_root=ROOT)
    verify_sources(rows)
    require(sha(MAP_FILE)==before['map_file_sha256'],'Map bytes changed before this importer could save')
    require(verify_owned_scene(ROOT)==ownership_token,'Original ownership changed during import')
    result['phase']='validated_before_save'
    write()
    result['map_save_attempted']=True
    result['phase']='saving_map'
    write()
    require(core.L.save_current_level(),'Incremental map save failed')
    result['map_saved']=True
    result['phase']='verifying_saved_map'
    write()
    before_save=after
    after=snapshot(before)
    result['preservation_after_save']=guard.assert_preserved(before,after,
        allowed_mesh_replacements=plan,expected_new_guids=validation['new_actor_guids'])
    guard.assert_clean_baseline(after)
    assert_snapshot_content_equal(before_save,after,'Map save')
    guard.verify_protected_files(before,project_root=ROOT)
    refreshed=refresh_map_hash(ROOT,ownership_token)
    require([r for r in refreshed['packages'] if r['package']!=guard.MAP]==original_owned_assets,
            'Refreshing the map changed original asset ownership')
    result['original_ownership_refreshed']=True
    result['original_ownership_sha256']=sha(OLD_OWNERSHIP)
    new_hashes=guard.package_hashes(ROOT,planned)
    extension_ownership=dict(schema_version=1,owner=guard.EXTENSION_TAG,namespace=DEST,map=guard.MAP,
        importer='Tools/MPRWarehouse/import_mpr_extension.py',
        baseline_map_sha256=before['map_file_sha256'],pre_save_map_sha256=result['baseline_map_sha256'],
        post_save_map_sha256=sha(MAP_FILE),source_manifest_sha256=result['source_manifest_sha256'],
        source_files={r['fbx']:r['sha256'] for r in rows},
        packages=[dict(package=p,files=new_hashes[p]) for p in sorted(new_hashes)],
        original_owned_packages_digest=result['original_owned_packages_digest'],
        original_owned_package_count=len(original_owned_assets),
        original_ownership_sha256=result['original_ownership_sha256'],
        new_actor_guids=validation['new_actor_guids'],allowed_mesh_replacements=plan)
    extension_ownership['actor_snapshot_digest']=guard.canonical_digest(after['actors'])
    write_json(EXTENSION_OWNERSHIP,extension_ownership)
    result['extension_ownership_sha256']=sha(EXTENSION_OWNERSHIP)
    write_json(OUT/'after_import.json',after)
    result['after_import_sha256']=sha(OUT/'after_import.json')
    result.update(success=True,map_sha256=sha(MAP_FILE),meshes=core.result['meshes'],
                  groups=core.result['groups'],phase='complete')
    write()
    print('MPRE_IMPORT_SUCCESS',len(rows),len(result['created_actors']))

try:run()
except Exception:
    result['error']=traceback.format_exc()
    if MAP_FILE.exists():
        result['failure_map_sha256']=sha(MAP_FILE)
        result['map_changed_from_baseline']=result['failure_map_sha256']!=result.get('baseline_map_sha256',result['failure_map_sha256'])
    write()
    u.log_error(result['error'])
