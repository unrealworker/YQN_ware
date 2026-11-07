"""Apply the reviewed sorter simulation to the existing MPR map only.

Owned full editor: -ExecutePythonScript=... -MPRSorterApply
Independent owned commandlet: -run=pythonscript -script=... --verify-only
The apply path requires StaticMeshEditorSubsystem for explicit source LODs.
No arguments defaults to read-only verification, never to mutation.
"""
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys
import traceback

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).parent))
import rebuild_preservation as guard
import mpr_scene_patch_guard as patch

MAP='/Game/Maps/MPR_CAD_Warehouse_B50B57'
MAP_FILE=ROOT/'Content/Maps/MPR_CAD_Warehouse_B50B57.umap'
SRC=ROOT/'SourceAssets/MPR/sorter_simulation'
OUT=ROOT/'Saved/MPR/sorter_sim_20261107/application'
DEST='/Game/MPRWarehouse/SorterSimulation'
CLASS='/Script/Test.MPRSorterSimulationActor'
LABEL='MPR_SorterSimulation'
ROLES=['Porcelain','Cobalt','SoftBlue','Metal','Charcoal','Rubber','Glass']
BODY_NAMES={'cad64':'SM_MPR_SorterSimBody64','cad120':'SM_MPR_SorterSimBody120'}
ROOT_NAMES={*BODY_NAMES.values(),'SM_MPR_SorterSimTower','SM_MPR_SorterSimTray'}
COMPONENT_NAMES={'MovingColumns','LiftTrays','MovingParcels','CollectedParcels','ActiveCells','FullCells'}


def sha(path):return guard.sha(path)


def object_path(package):return package+'.'+package.rsplit('/',1)[-1]


def role_name(name):return str(name).removeprefix('M_Zcool_').split('.')[0]


def material_slots(mesh):return list(mesh.get_editor_property('static_materials'))


def slot_role(slot):
    # ImportedMaterialSlotName is editor-visible, not BlueprintReadWrite in UE
    # 5.8 FStaticMaterial, so Python exposes it through get_editor_property.
    return role_name(slot.get_editor_property('imported_material_slot_name'))


def asset_path(value):return value.get_path_name() if value else None


def canonical_layout(layout):return json.dumps(layout,ensure_ascii=False,separators=(',',':'))


def derive_plan(before,layout):
    """Authorize whole HISM groups only after every one of 22 poses matches."""
    assert before['map']==layout['snapshot_map']==MAP
    assert layout['schema_version']==1 and layout['units']=='UE cm'
    assert len(layout['machines'])==22
    assert len({r['id'] for r in layout['machines']})==22
    actors={a['guid']:a for a in before['actors']}
    assert not any(a['class']==CLASS or a['label']==LABEL for a in actors.values()),'Simulation already exists; use --verify-only'
    groups=defaultdict(list)
    for machine in layout['machines']:
        assert machine['profile'] in BODY_NAMES
        groups[(machine['actor_guid'],machine['component_name'])].append(machine)
    assert len(groups)==3,'The 18+4 machines occupy exactly three existing HISM groups'
    result=[]
    for (guid,name),machines in groups.items():
        actor=actors[guid]
        assert actor['folder']=='MPR/Equipment'
        assert actor['label']==machines[0]['actor_label']
        assert actor['class']=='/Game/GHSDigitalTwin/Blueprints/BP_GHS_InstanceGroup.BP_GHS_InstanceGroup_C'
        assert not actor['hidden'] and not actor['tick_enabled'] and not actor['collision_enabled']
        components=[c for c in actor['components'] if 'instance_transforms' in c]
        assert len(components)==1 and components[0]['name']==name
        c=components[0]
        identity=dict(translation_cm=[0.,0.,0.],rotation_xyzw=[0.,0.,0.,1.],scale=[1.,1.,1.])
        assert not patch.differences(actor['transform'],identity),'Layout world poses require the original identity group transform'
        assert not patch.differences(c['transform'],identity),'Layout world poses require the original identity HISM transform'
        assert len(c['materials'])==7 and c['num_custom_data_floats']==0
        assert sorted(r['instance_index'] for r in machines)==list(range(c['instance_count']))
        assert len({r['profile'] for r in machines})==1
        for machine in machines:
            assert c['mesh']==machine['original_mesh']
            errors=patch.differences(c['instance_transforms'][machine['instance_index']],machine['world_transform'])
            assert not errors,(machine['id'],errors)
        profile=machines[0]['profile']
        result.append(dict(actor_guid=guid,component_name=name,profile=profile,old_mesh=c['mesh'],
                           new_mesh=object_path(DEST+'/Meshes/'+BODY_NAMES[profile]),
                           original_actor=actor,instance_count=c['instance_count']))
    assert sorted(r['instance_count'] for r in result)==[1,4,17]
    return result


def validate_scope(before,after,plan,controller_guid,*,reload=False):
    old={r['guid']:patch.normalize(r,commandlet_compat=reload) for r in before['actors']}
    actual={r['guid']:patch.normalize(r,commandlet_compat=reload) for r in after['actors']}
    assert set(actual)==set(old)|{controller_guid},'Unexpected actor addition/deletion'
    expected=deepcopy(old)
    for row in plan:
        component=next(c for c in expected[row['actor_guid']]['components'] if c['name']==row['component_name'])
        assert component['mesh']==row['old_mesh'];component['mesh']=row['new_mesh']
        if 'new_materials' in row:component['materials']=row['new_materials']
    for guid,row in expected.items():
        errors=patch.differences(row,actual[guid])
        assert not errors,(row['label'],errors[:10])
    controller=actual[controller_guid]
    assert controller['class']==CLASS and controller['label']==LABEL
    assert controller['folder']=='MPR/Simulation' and controller['tags']==['MPRWarehouse','mpr-sorter-simulation-20261107']
    assert controller['transform']==dict(translation_cm=[0.,0.,0.],rotation_xyzw=[0.,0.,0.,1.],scale=[1.,1.,1.])
    assert controller['tick_enabled'] and not controller['collision_enabled'] and not controller['hidden']
    assert controller['attachment_parent'] is None
    instances=[c for c in controller['components'] if 'instance_transforms' in c]
    assert {c['name'] for c in instances}==COMPONENT_NAMES
    assert all(c['instance_count']==0 and c['collision_profile']=='NoCollision' for c in instances),'Runtime instances must not be baked into the editor level'
    assert not patch.differences(before['world_settings'],after['world_settings'])
    assert not patch.differences(patch.normalized_coverage(before['world_actor_coverage'],commandlet_compat=reload),
                                 patch.normalized_coverage(after['world_actor_coverage'],commandlet_compat=reload))
    return dict(preserved_actors=len(old)-len(plan),changed_hism_groups=len(plan),preserved_instances=22,new_native_actors=1)


def live_targets(u,plan):
    actors={u.GuidLibrary.conv_guid_to_string(a.get_editor_property('actor_guid')):a for a in u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors()}
    result={}
    for row in plan:
        actor=actors[row['actor_guid']]
        component=next(c for c in actor.get_components_by_class(u.HierarchicalInstancedStaticMeshComponent) if c.get_name()==row['component_name'])
        result[row['actor_guid']]=(actor,component)
    return result


def override_state(component):
    return [asset_path(m) for m in component.get_editor_property('override_materials')]


def material(u,role,created):
    """Use compatible existing references; clone only incompatible parents."""
    lib=u.EditorAssetLibrary;usage=u.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES
    candidates=[f'/Game/MPRWarehouse/Materials/MI_MPR_HISM_M_Zcool_{role}',
                f'/Game/GHSZcoolSmartFactory/Materials/M_Zcool_{role}']
    for path in candidates:
        if not lib.does_asset_exist(path):continue
        mat=lib.load_asset(path)
        if u.MaterialEditingLibrary.has_material_usage(mat,usage):return mat
    source=candidates[-1];path=DEST+'/Materials/M_MPRSorter_'+role
    assert lib.does_asset_exist(source) and not lib.does_asset_exist(path)
    mat=lib.duplicate_asset(source,path);assert mat
    if isinstance(mat,u.MaterialInstanceConstant):
        u.MaterialEditingLibrary.set_material_usage_override(mat,usage,True,True)
        u.MaterialEditingLibrary.update_material_instance(mat)
    else:
        u.MaterialEditingLibrary.set_base_material_usage(mat,usage,True)
        u.MaterialEditingLibrary.recompile_material(mat)
    assert u.MaterialEditingLibrary.has_material_usage(mat,usage)
    created[path]=mat
    return mat


def parcel_material(u,created):
    """Private warm cardboard material; shared warehouse materials stay intact."""
    path=DEST+'/Materials/M_MPR_SorterParcel'
    lib=u.EditorAssetLibrary;ml=u.MaterialEditingLibrary
    assert not lib.does_asset_exist(path),path
    mat=u.AssetToolsHelpers.get_asset_tools().create_asset(path.rsplit('/',1)[-1],path.rsplit('/',1)[0],u.Material,u.MaterialFactoryNew())
    assert mat
    mat.set_editor_property('shading_model',u.MaterialShadingModel.MSM_DEFAULT_LIT)
    color=ml.create_material_expression(mat,u.MaterialExpressionConstant3Vector)
    color.set_editor_property('constant',u.LinearColor(.34,.19,.075,1.))
    assert ml.connect_material_property(color,'',u.MaterialProperty.MP_BASE_COLOR)
    for value,prop in [(.8,u.MaterialProperty.MP_ROUGHNESS),(0.,u.MaterialProperty.MP_METALLIC)]:
        node=ml.create_material_expression(mat,u.MaterialExpressionConstant)
        node.set_editor_property('r',value)
        assert ml.connect_material_property(node,'',prop)
    usage=u.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES
    ml.set_base_material_usage(mat,usage,True);ml.recompile_material(mat)
    assert ml.has_material_usage(mat,usage)
    created[path]=mat
    return mat


def mesh_bounds(mesh):
    b=mesh.get_bounds()
    return [[b.origin.x-b.box_extent.x,b.origin.x+b.box_extent.x],
            [b.origin.y-b.box_extent.y,b.origin.y+b.box_extent.y],
            [b.origin.z-b.box_extent.z,b.origin.z+b.box_extent.z]]


def check_mesh(u,mesh,row,sm=None):
    src=row['bounds_m'];expected=[[src[0][0]*100,src[0][1]*100],[-src[1][1]*100,-src[1][0]*100],[src[2][0]*100,src[2][1]*100]]
    actual=mesh_bounds(mesh)
    assert max(abs(a-b) for aa,bb in zip(actual,expected) for a,b in zip(aa,bb))<.05,(row['name'],actual,expected)
    assert len(material_slots(mesh))==7
    assert [slot_role(s) for s in material_slots(mesh)]==ROLES
    if sm:
        assert sm.get_lod_count(mesh)==1+len(row.get('lod_files',[]))
    return dict(path=mesh.get_path_name(),bounds_cm=actual,material_roles=ROLES,
                lod_count=1+len(row.get('lod_files',[])),source_sha256=sha(ROOT/row['fbx']))


def import_assets(u,manifest,materials,reference_slots,sm):
    lib=u.EditorAssetLibrary;tools=u.AssetToolsHelpers.get_asset_tools();imported={};audit=[]
    main=[r for r in manifest['meshes'] if r['lod']==0]
    assert len(manifest['meshes'])==8 and {r['name'] for r in main}==ROOT_NAMES
    for row in main:
        assert row['material_roles']==ROLES
        path=DEST+'/Meshes/'+row['name'];source=ROOT/row['fbx']
        assert source.resolve()==(SRC/(row['name']+'.fbx')).resolve()
        assert not lib.does_asset_exist(path),'Refusing to overwrite an existing private package: '+path
        task=u.AssetImportTask();task.filename=str(source);task.destination_path=DEST+'/Meshes';task.destination_name=row['name']
        task.automated=True;task.replace_existing=False;task.save=False
        opts=u.FbxImportUI();opts.import_mesh=True;opts.import_as_skeletal=False;opts.import_materials=False;opts.import_textures=False;opts.import_animations=False
        opts.mesh_type_to_import=u.FBXImportType.FBXIT_STATIC_MESH;opts.automated_import_should_detect_type=False
        data=opts.static_mesh_import_data;data.combine_meshes=True;data.auto_generate_collision=False;data.generate_lightmap_u_vs=False
        data.convert_scene=True;data.convert_scene_unit=True;data.force_front_x_axis=False
        data.normal_import_method=u.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS;data.normal_generation_method=u.FBXNormalGenerationMethod.BUILT_IN
        task.options=opts;task.factory=u.FbxFactory();tools.import_asset_tasks([task])
        mesh=lib.load_asset(path);assert isinstance(mesh,u.StaticMesh)
        for index,filename in enumerate(row.get('lod_files',[]),1):
            assert sm.import_lod(mesh,index,str(ROOT/filename))==index
        imported_roles=[slot_role(s) for s in material_slots(mesh)]
        assert set(imported_roles)<=set(ROLES)
        section_roles=[]
        for lod in range(sm.get_lod_count(mesh)):
            section_roles.append([imported_roles[sm.get_lod_material_slot(mesh,lod,section)] for section in range(mesh.get_num_sections(lod))])
        # Preserve the old seven-slot override contract even when an unused FBX
        # material (e.g. Glass after opening the cabinet) was omitted on import.
        mesh.set_editor_property('static_materials',list(reference_slots))
        for i,role in enumerate(ROLES):mesh.set_material(i,materials[role])
        for lod,roles in enumerate(section_roles):
            for section,role in enumerate(roles):sm.set_lod_material_slot(mesh,ROLES.index(role),lod,section)
        screen=[1.,.22,.065] if row.get('lod_files') else [1.]
        assert sm.set_lod_screen_sizes(mesh,screen)
        assert max(abs(a-b) for a,b in zip(sm.get_lod_screen_sizes(mesh),screen))<1e-5
        for lod,roles in enumerate(section_roles):
            assert [sm.get_lod_material_slot(mesh,lod,i) for i in range(len(roles))]==[ROLES.index(r) for r in roles]
        imported[path]=mesh;audit.append(check_mesh(u,mesh,row,sm))
    return imported,audit


def controller_properties(actor):
    return dict(layout_json=actor.get_editor_property('layout_json'),
                auto_start=bool(actor.get_editor_property('auto_start')),
                **{key:asset_path(actor.get_editor_property(key)) for key in ('tower_mesh','tray_mesh','parcel_material','active_material','full_material')})


def check_content(before,*,allow_map_change,allowed_new):
    current=guard.content_hashes(ROOT);map_key=MAP_FILE.relative_to(ROOT).as_posix()
    changed=[p for p,digest in before.items() if current.get(p)!=digest and not (allow_map_change and p==map_key)]
    assert not changed,('Existing Content package changed',changed[:12])
    unexpected=[p for p in set(current)-set(before) if Path(p).with_suffix('').as_posix() not in allowed_new]
    assert not unexpected,('Unexpected new Content packages',unexpected)
    return current


def load_existing_map(u,*,apply=False):
    commandlet='-run=pythonscript' in u.SystemLibrary.get_command_line().lower()
    if commandlet:
        assert not apply,'Explicit LOD import requires an owned full editor, not a commandlet'
        assert u.EditorLoadingAndSavingUtils.load_map(MAP)
    # A full editor must already have this map open; no switching or new maps.
    before=guard.capture(u,ROOT,MAP);guard.assert_clean(before)
    return before,commandlet


def apply(u):
    before,commandlet=load_existing_map(u,apply=True)
    sm=u.get_editor_subsystem(u.StaticMeshEditorSubsystem)
    assert sm,'StaticMeshEditorSubsystem is required before any import'
    layout=patch.read(SRC/'layout.json');manifest=patch.read(SRC/'manifest.json')
    quality=patch.read(SRC/'geometry_validation.json');assert quality['status']=='passed'
    assert [r['fbx_sha256'] for r in quality['fbx']]==[sha(ROOT/r['fbx']) for r in manifest['meshes']]
    plan=derive_plan(before,layout);targets=live_targets(u,plan)
    overrides={guid:override_state(component) for guid,(_,component) in targets.items()}
    reference=u.EditorAssetLibrary.load_asset(plan[0]['old_mesh']);reference_slots=material_slots(reference)
    assert len(reference_slots)==7 and [slot_role(s) for s in reference_slots]==ROLES
    for row in plan:
        old=u.EditorAssetLibrary.load_asset(row['old_mesh'])
        assert [slot_role(s) for s in material_slots(old)]==ROLES
    cls=u.load_class(None,CLASS);assert cls,'Compile MPRSorterSimulationActor before applying'
    assert not any(u.EditorAssetLibrary.does_asset_exist(DEST+'/Meshes/'+name) for name in ROOT_NAMES),'Private mesh already exists; use verify-only'
    assert not u.EditorAssetLibrary.does_asset_exist(DEST+'/Materials/M_MPR_SorterParcel'),'Private parcel material already exists; use verify-only'
    for row in plan:
        for name in overrides[row['actor_guid']]:
            if name:assert u.MaterialEditingLibrary.has_material_usage(u.EditorAssetLibrary.load_asset(name),u.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES),('Existing override is not ISM compatible; refusing shared mutation',name)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');run=OUT/'runs'/stamp;run.mkdir(parents=True)
    existing=guard.content_hashes(ROOT)
    patch.write(run/'before.json.gz',before);patch.write(run/'content_before.json',existing)
    shutil.copy2(MAP_FILE,run/'before_MPR_CAD_Warehouse_B50B57.umap')
    patch.write(OUT/'pending_run.json',dict(run_directory=str(run)))
    created_materials={};materials={role:material(u,role,created_materials) for role in [*ROLES,'Cyan','SafetyAmber']}
    parcel=parcel_material(u,created_materials)
    old_flag=u.SystemLibrary.get_console_variable_int_value('Interchange.FeatureFlags.Import.FBX')
    try:
        u.SystemLibrary.execute_console_command(None,'Interchange.FeatureFlags.Import.FBX 0')
        imported,import_audit=import_assets(u,manifest,materials,reference_slots,sm)
    finally:
        u.SystemLibrary.execute_console_command(None,'Interchange.FeatureFlags.Import.FBX '+str(old_flag))
    properties=dict(layout_json=canonical_layout(layout),auto_start=True,
                    tower_mesh=object_path(DEST+'/Meshes/SM_MPR_SorterSimTower'),tray_mesh=object_path(DEST+'/Meshes/SM_MPR_SorterSimTray'),
                    parcel_material=parcel.get_path_name(),active_material=materials['Cyan'].get_path_name(),full_material=materials['SafetyAmber'].get_path_name())
    for row in plan:
        override=overrides[row['actor_guid']]
        row['new_materials']=[override[i] if i<len(override) and override[i] else asset_path(materials[role]) for i,role in enumerate(ROLES)]
    actor_sub=u.get_editor_subsystem(u.EditorActorSubsystem)
    with u.ScopedEditorTransaction('为现有MPR长机接入闭环播种仿真'):
        for row in plan:
            actor,component=targets[row['actor_guid']];component.modify()
            component.set_static_mesh(u.EditorAssetLibrary.load_asset(row['new_mesh']))
            assert override_state(component)==overrides[row['actor_guid']],'Material overrides changed'
        controller=actor_sub.spawn_actor_from_class(cls,u.Vector())
        controller.set_actor_label(LABEL);controller.set_folder_path('MPR/Simulation')
        controller.tags=['MPRWarehouse','mpr-sorter-simulation-20261107'];controller.set_actor_enable_collision(False);controller.set_actor_tick_enabled(True)
        for key,value in properties.items():
            controller.set_editor_property(key,u.EditorAssetLibrary.load_asset(value) if key.endswith('_mesh') or key.endswith('_material') else value)
    guid=u.GuidLibrary.conv_guid_to_string(controller.get_editor_property('actor_guid'))
    assert controller_properties(controller)==properties
    after=guard.capture(u,ROOT,MAP)
    scope=validate_scope(before,after,plan,guid)
    allowed_packages={*imported,*created_materials}
    allowed_files={('Content/'+p.removeprefix('/Game/')) for p in allowed_packages}
    assert set(after['dirty_content'])<=allowed_packages,('Unrelated dirty packages',after['dirty_content'])
    assert set(after['dirty_maps'])<={MAP}
    check_content(existing,allow_map_change=False,allowed_new=allowed_files)
    contract=dict(plan=plan,controller_guid=guid,controller_properties=properties,
                  overrides=overrides,import_audit=import_audit,allowed_new_files=sorted(allowed_files),
                  layout_sha256=sha(SRC/'layout.json'),manifest_sha256=sha(SRC/'manifest.json'))
    patch.write(run/'contract.json',contract);patch.write(run/'candidate.json.gz',after)
    for asset in [*created_materials.values(),*imported.values()]:assert u.EditorAssetLibrary.save_loaded_asset(asset,only_if_is_dirty=False)
    assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level()
    saved=guard.capture(u,ROOT,MAP);guard.assert_clean(saved)
    scope=validate_scope(before,saved,plan,guid)
    assert controller_properties(controller)==properties
    assert all(override_state(c)==overrides[guid] for guid,(_,c) in live_targets(u,plan).items())
    hashes=check_content(existing,allow_map_change=True,allowed_new=allowed_files)
    patch.write(run/'after.json.gz',saved)
    new_hashes={p:h for p,h in hashes.items() if p not in existing}
    patch.write(run/'new_asset_hashes.json',new_hashes)
    report=dict(success=True,run_directory=str(run),map=MAP,map_before=before['map_file_sha256'],map_after=sha(MAP_FILE),
                **scope,created_assets=sorted(new_hashes),imported=import_audit,controller_guid=guid,
                preserved_existing_content_packages=len(existing)-1)
    patch.write(OUT/'apply_report.json',report);patch.write(OUT/'latest_run.json',dict(run_directory=str(run)))
    print('MPR_SORTER_APPLIED '+json.dumps(report,ensure_ascii=False))


def verify_only(u):
    actual,commandlet=load_existing_map(u)
    run=Path(patch.read(OUT/'latest_run.json')['run_directory'])
    assert run.resolve().is_relative_to((OUT/'runs').resolve())
    before=patch.read(run/'before.json.gz');saved=patch.read(run/'after.json.gz');contract=patch.read(run/'contract.json')
    assert sha(SRC/'layout.json')==contract['layout_sha256'] and sha(SRC/'manifest.json')==contract['manifest_sha256']
    assert actual['map_file_sha256']==saved['map_file_sha256']
    expected=[patch.normalize(r,commandlet_compat=True) for r in saved['actors']]
    current=[patch.normalize(r,commandlet_compat=True) for r in actual['actors']]
    assert not patch.differences(expected,current),'Saved actor records did not reload identically'
    scope=validate_scope(before,actual,contract['plan'],contract['controller_guid'],reload=True)
    actors=u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors()
    controller=next(a for a in actors if u.GuidLibrary.conv_guid_to_string(a.get_editor_property('actor_guid'))==contract['controller_guid'])
    assert controller_properties(controller)==contract['controller_properties']
    assert all(override_state(c)==contract['overrides'][guid] for guid,(_,c) in live_targets(u,contract['plan']).items())
    check_content(patch.read(run/'content_before.json'),allow_map_change=True,allowed_new=set(contract['allowed_new_files']))
    for path,digest in patch.read(run/'new_asset_hashes.json').items():assert sha(ROOT/path)==digest,path
    manifest=patch.read(SRC/'manifest.json')
    for row in manifest['meshes']:
        if row['lod']==0:check_mesh(u,u.EditorAssetLibrary.load_asset(DEST+'/Meshes/'+row['name']),row)
    report=dict(success=True,map_sha256=sha(MAP_FILE),run_directory=str(run),independent_reload=commandlet,**scope)
    patch.write(OUT/'reload_report.json',report);print('MPR_SORTER_RELOADED '+json.dumps(report))


if __name__=='__main__':
    import unreal as u
    cli=u.SystemLibrary.get_command_line().lower()
    try:
        if '-mprsorterapply' in cli:apply(u)
        else:verify_only(u)
    except Exception:
        patch.write(OUT/'failure_report.json',dict(success=False,traceback=traceback.format_exc()))
        raise
