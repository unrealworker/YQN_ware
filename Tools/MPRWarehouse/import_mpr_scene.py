"""Create only MPR packages; never resave GHS assets or mutate their defaults."""
import json, math, sys, hashlib, traceback
from pathlib import Path
from collections import defaultdict
import unreal as u

ROOT=Path(u.Paths.convert_relative_path_to_full(u.Paths.project_dir()));SRC=ROOT/'SourceAssets/MPR';DEST='/Game/MPRWarehouse'
MAP='/Game/Maps/MPR_CAD_Warehouse';OWNER='mpr-cad-scene-v1'
REPORT=ROOT/'Saved/MPR/scene_build.json';REPORT.parent.mkdir(parents=True,exist_ok=True)
LIB=u.EditorAssetLibrary;TOOLS=u.AssetToolsHelpers.get_asset_tools()
A=u.get_editor_subsystem(u.EditorActorSubsystem);L=u.get_editor_subsystem(u.LevelEditorSubsystem)
E=u.get_editor_subsystem(u.UnrealEditorSubsystem);SM=u.get_editor_subsystem(u.StaticMeshEditorSubsystem)
sys.path.insert(0,str(ROOT/'Scripts/ghs'))
sys.path.insert(0,str(ROOT/'Tools/MPRWarehouse'))
from mpr_scene_ownership import verify_owned_scene, record_successful_build
CAD=json.loads((SRC/'mpr_cad_layout.json').read_text(encoding='utf-8'))
result=dict(success=False,owner=OWNER,map=MAP,meshes=[],materials_created=[],groups=[],reused_assets=[],assumptions=list(CAD['assumptions']))
MATS={};MESHES={};INSTANCE_MATS={}
USAGE=u.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES
MATLIB=u.MaterialEditingLibrary

def write():REPORT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def load(path):
    asset=LIB.load_asset(path)
    if not asset:raise RuntimeError('Missing required asset: '+path)
    return asset
def xyz(v):return [v.x,v.y,v.z]
def pos(p):return u.Vector(p[0]*100,-p[1]*100,(p[2] if len(p)>2 else 0)*100)
def transform(row):return u.Transform(location=pos(row['position_m']),rotation=u.Rotator(yaw=-row.get('rotation_deg',0)),scale=u.Vector(*row.get('scale',[1,1,1])))

def material(role):
    if role in MATS:return MATS[role]
    zcool={'Porcelain','WallTop','PaleGray','Cargo','CargoSeam','Cobalt','SoftBlue','Charcoal','Rubber','Metal','Glass','Cyan','SafetyRed','SafetyAmber','Skin'}
    if role in zcool:path='/Game/GHSZcoolSmartFactory/Materials/M_Zcool_'+role
    elif role=='Floor':path='/Game/GHSZcoolSmartFactory/Materials/M_Zcool_PaleGray'
    elif role=='Skylight':path='/Game/GHSZcoolSmartFactory/Roof/Materials/M_GHSRoof_Skylight'
    elif role=='Sky':path='/Game/GHSZcoolSmartFactory/Materials/M_Zcool_Sky'
    elif role=='Water':path='/Game/GHSZcoolSmartFactory/Park/Materials/M_GHSPark_Solar'
    else:path='/Game/GHSZcoolSmartFactory/Park/Materials/M_GHSPark_'+role
    MATS[role]=load(path);return MATS[role]

def planned_instance_materials(manifests):
    # Inspect sources before loading the generated level: editor auto-usage can
    # otherwise mask the missing runtime shader permutation.
    candidates={};roles={'Porcelain','Cobalt','Cargo','CargoSeam','Charcoal','Metal','SoftBlue'}
    for category,path in manifests:
        for row in read(path)['meshes']:
            if row.get('instance_only') or category=='Equipment':roles.update(row['material_roles'])
    custom=read(SRC/'environment/environment_manifest.json').get('material_overrides',{})
    for role in sorted(roles-set(custom)):
        mat=material(role);candidates[mat.get_path_name()]=mat
    truck=load('/Game/GHSZcoolSmartFactory/Park/Meshes/SM_GHSPark_ClosedTruck')
    for slot in truck.static_materials:
        mat=slot.material_interface;candidates[mat.get_path_name()]=mat
    return [(mat,DEST+'/Materials/MI_MPR_HISM_'+mat.get_name()) for mat in candidates.values()
            if not MATLIB.has_material_usage(mat,USAGE)]


def exterior_material_plan():
    specs=read(SRC/'environment/environment_manifest.json').get('material_overrides',{})
    return [(role,spec,DEST+'/Materials/MI_MPR_Exterior_'+role) for role,spec in specs.items()]


EXTERIOR_MASTER=DEST+'/Materials/M_MPR_ExteriorSurface'


def preflight_materials(instance_plan,exterior_plan):
    # Validate references and destination classes before saving any package.
    for parent,path in instance_plan:
        assert parent
        if LIB.does_asset_exist(path):assert isinstance(load(path),u.MaterialInstanceConstant),path
    for role,spec,path in exterior_plan:
        assert isinstance(material(spec['parent']),u.MaterialInterface),role
        assert len(spec['color'])==3 and all(math.isfinite(v) and 0<=v<=1 for v in spec['color']),role
        if LIB.does_asset_exist(path):assert isinstance(load(path),u.MaterialInstanceConstant),path
    if LIB.does_asset_exist(EXTERIOR_MASTER):assert isinstance(load(EXTERIOR_MASTER),u.Material)


def create_exterior_master():
    # Use one MPR-owned, default-lit surface with the same
    # four physical inputs; never rewrite a shared GHS material to add parameters.
    reference=material('Roads')
    source=ROOT/('Content/'+reference.get_path_name().split('.')[0].removeprefix('/Game/')+'.uasset')
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    mat=load(EXTERIOR_MASTER) if LIB.does_asset_exist(EXTERIOR_MASTER) else TOOLS.create_asset(
        EXTERIOR_MASTER.rsplit('/',1)[-1],EXTERIOR_MASTER.rsplit('/',1)[0],u.Material,u.MaterialFactoryNew())
    while MATLIB.get_num_material_expressions(mat):
        previous=MATLIB.get_num_material_expressions(mat)
        MATLIB.delete_all_material_expressions(mat)
        assert MATLIB.get_num_material_expressions(mat)<previous,'Cannot clear MPR material graph'
    mat.set_editor_property('blend_mode',u.BlendMode.BLEND_OPAQUE)
    mat.set_editor_property('shading_model',u.MaterialShadingModel.MSM_DEFAULT_LIT)
    tint=MATLIB.create_material_expression(mat,u.MaterialExpressionVectorParameter)
    tint.set_editor_property('parameter_name','SurfaceTint');tint.set_editor_property('default_value',u.LinearColor(.4,.5,.6,1))
    assert MATLIB.connect_material_property(tint,'',u.MaterialProperty.MP_BASE_COLOR)
    for name,value,prop in [('Roughness',.9,u.MaterialProperty.MP_ROUGHNESS),('Metallic',0.,u.MaterialProperty.MP_METALLIC),('Specular',.15,u.MaterialProperty.MP_SPECULAR)]:
        node=MATLIB.create_material_expression(mat,u.MaterialExpressionScalarParameter)
        node.set_editor_property('parameter_name',name);node.set_editor_property('default_value',value)
        assert MATLIB.connect_material_property(node,'',prop)
    MATLIB.set_material_usage(mat,USAGE)
    MATLIB.recompile_material(mat)
    assert MATLIB.get_num_material_expressions(mat)==4
    assert LIB.save_loaded_asset(mat,only_if_is_dirty=False)
    result['materials_created'].append(dict(path=EXTERIOR_MASTER,parent=reference.get_path_name(),parent_sha256=digest,
        usage='InstancedStaticMeshes',role='ExteriorSurfaceMaster',reference_only=True))
    return mat


def create_exterior_materials(planned):
    master=create_exterior_master()
    for role,spec,path in planned:
        parent=master
        source=ROOT/('Content/'+parent.get_path_name().split('.')[0].removeprefix('/Game/')+'.uasset')
        digest=hashlib.sha256(source.read_bytes()).hexdigest()
        mat=load(path) if LIB.does_asset_exist(path) else TOOLS.create_asset(
            path.rsplit('/',1)[-1],path.rsplit('/',1)[0],u.MaterialInstanceConstant,u.MaterialInstanceConstantFactoryNew())
        assert isinstance(mat,u.MaterialInstanceConstant)
        MATLIB.set_material_instance_parent(mat,parent)
        # UE 5.8 setters currently return false even after applying the value.
        # Read the effective parameter back instead of treating that as failure.
        MATLIB.set_material_instance_vector_parameter_value(mat,'SurfaceTint',u.LinearColor(*spec['color'],1.))
        tint=MATLIB.get_material_instance_vector_parameter_value(mat,'SurfaceTint')
        assert max(abs(a-b) for a,b in zip([tint.r,tint.g,tint.b],spec['color']))<1e-5,role
        for key,value in [('Roughness',spec.get('roughness',.85)),('Metallic',spec.get('metallic',0)),('Specular',.15)]:
            MATLIB.set_material_instance_scalar_parameter_value(mat,key,float(value))
            assert abs(MATLIB.get_material_instance_scalar_parameter_value(mat,key)-float(value))<1e-5,(role,key)
        MATLIB.set_material_usage_override(mat,USAGE,True,True)
        MATLIB.update_material_instance(mat)
        assert LIB.save_loaded_asset(mat,only_if_is_dirty=False)
        MATS[role]=mat
        result['materials_created'].append(dict(path=path,parent=parent.get_path_name(),parent_sha256=digest,
            usage='InstancedStaticMeshes',role=role,overrides=spec))


def create_instance_materials(planned):
    for parent,path in planned:
        source=ROOT/('Content/'+parent.get_path_name().split('.')[0].removeprefix('/Game/')+'.uasset')
        digest=hashlib.sha256(source.read_bytes()).hexdigest()
        mat=load(path) if LIB.does_asset_exist(path) else TOOLS.create_asset(
            path.rsplit('/',1)[-1],path.rsplit('/',1)[0],u.MaterialInstanceConstant,u.MaterialInstanceConstantFactoryNew())
        assert mat and isinstance(mat,u.MaterialInstanceConstant)
        MATLIB.set_material_instance_parent(mat,parent)
        # UE 5.8 usage overrides retain the GHS parent, including later style edits.
        MATLIB.set_material_usage_override(mat,USAGE,True,True)
        MATLIB.update_material_instance(mat)
        assert MATLIB.has_material_usage(mat,USAGE),path
        assert LIB.save_loaded_asset(mat,only_if_is_dirty=False)
        INSTANCE_MATS[parent.get_path_name()]=mat
        result['materials_created'].append(dict(path=path,parent=parent.get_path_name(),parent_sha256=digest,usage='InstancedStaticMeshes'))


def instance_material(mat):
    compatible=INSTANCE_MATS.get(mat.get_path_name(),mat)
    assert MATLIB.has_material_usage(compatible,USAGE),('Unplanned incompatible HISM material',mat.get_path_name())
    return compatible


def import_mesh(row,category):
    target=DEST+'/'+category+'/Meshes/'+row['name'];fbx=ROOT/row['fbx']
    assert fbx.is_file(),fbx
    task=u.AssetImportTask();task.filename=str(fbx);task.destination_path=target.rsplit('/',1)[0]
    task.destination_name=row['name'];task.automated=True;task.replace_existing=True;task.replace_existing_settings=True;task.save=False
    opts=u.FbxImportUI();opts.import_mesh=True;opts.import_as_skeletal=False;opts.import_materials=False;opts.import_textures=False
    opts.import_animations=False;opts.mesh_type_to_import=u.FBXImportType.FBXIT_STATIC_MESH;opts.automated_import_should_detect_type=False
    data=opts.static_mesh_import_data;data.combine_meshes=True;data.auto_generate_collision=False;data.generate_lightmap_u_vs=False
    data.convert_scene=True;data.convert_scene_unit=True;data.force_front_x_axis=False
    data.normal_import_method=u.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
    data.normal_generation_method=u.FBXNormalGenerationMethod.BUILT_IN
    task.options=opts;task.factory=u.FbxFactory();TOOLS.import_asset_tasks([task])
    mesh=load(target);slots=mesh.static_materials
    assert len(slots)==len(row['material_roles']),(row['name'],len(slots),row['material_roles'])
    for i,slot in enumerate(slots):
        imported=str(slot.get_editor_property('imported_material_slot_name'))
        role=imported if imported in row['material_roles'] else row['material_roles'][i]
        mat=material(role)
        slot.material_interface=instance_material(mat) if row.get('instance_only') or category=='Equipment' else mat
        slots[i]=slot
    mesh.set_editor_property('static_materials',slots)
    b=mesh.get_bounds();actual=[[b.origin.x-b.box_extent.x,b.origin.x+b.box_extent.x],[b.origin.y-b.box_extent.y,b.origin.y+b.box_extent.y],[b.origin.z-b.box_extent.z,b.origin.z+b.box_extent.z]]
    expected=row['bounds_m'];expected=[[expected[0][0]*100,expected[0][1]*100],[-expected[1][1]*100,-expected[1][0]*100],[expected[2][0]*100,expected[2][1]*100]]
    assert max(abs(a-b) for aa,bb in zip(actual,expected) for a,b in zip(aa,bb))<2.0,(row['name'],'axis/scale',actual,expected)
    if row.get('lod_files'):
        for index,filename in enumerate(row['lod_files'],1):
            assert SM.import_lod(mesh,index,str(ROOT/filename))==index
        SM.set_lod_screen_sizes(mesh,row.get('lod_screen_sizes',[1.,.15,.045]))
    elif not row.get('skip_auto_lods') and row.get('instance_only') and row.get('triangles',0)>1000:
        reduction=u.StaticMeshReductionOptions()
        reduction.auto_compute_lod_screen_size=False
        reduction.reduction_settings=[u.StaticMeshReductionSettings(percent_triangles=p,screen_size=s) for p,s in [(1.,1.),(.55,.12),(.24,.04)]]
        assert SM.set_lods(mesh,reduction)>=3
    if row.get('full_precision_uvs'):
        for index in range(SM.get_lod_count(mesh)):
            settings=SM.get_lod_build_settings(mesh,index)
            settings.set_editor_property('use_full_precision_u_vs',True)
            settings.set_editor_property('recompute_tangents',True)
            SM.set_lod_build_settings(mesh,index,settings)
    assert LIB.save_loaded_asset(mesh,only_if_is_dirty=False)
    MESHES[row['name']]=mesh
    result['meshes'].append(dict(name=row['name'],path=target,bounds_cm=actual,material_slots=len(slots),source_triangles=row.get('triangles'),lod_count=SM.get_lod_count(mesh)))
    return mesh

def tag(a,folder,extra=()):
    a.set_folder_path('MPR/'+folder);a.tags=['MPRWarehouse',OWNER,*extra];a.set_actor_tick_enabled(False);a.set_actor_enable_collision(False)

def spawn_mesh(label,mesh,folder='Architecture',location=(0,0,0),rotation=0,scale=(1,1,1),roles=None):
    a=A.spawn_actor_from_class(u.StaticMeshActor,pos(location),u.Rotator(yaw=-rotation));a.set_actor_label(label);tag(a,folder)
    c=a.get_component_by_class(u.StaticMeshComponent);c.set_static_mesh(mesh);c.set_mobility(u.ComponentMobility.STATIC)
    c.set_collision_profile_name('NoCollision');c.set_editor_property('receives_decals',False)
    if roles:
        for i,role in enumerate(roles):c.set_material(i,material(role))
    a.set_actor_scale3d(u.Vector(*scale));return a

def group(label,mesh,rows,folder,roles=None,cull=0):
    if not rows:return
    # Set actor properties BEFORE filling HISM. Blueprint reconstruction clears
    # per-instance data when actor tags are changed after the batch is filled.
    bp=load('/Game/GHSDigitalTwin/Blueprints/BP_GHS_InstanceGroup')
    a=A.spawn_actor_from_class(bp.generated_class(),u.Vector())
    a.set_actor_label(label);tag(a,folder,['InstanceCount='+str(len(rows))])
    c=a.get_component_by_class(u.HierarchicalInstancedStaticMeshComponent)
    c.set_editor_property('receives_decals',False)
    # UE 5.8 property edits can reconstruct SCS components. Resolve the current
    # component again before assigning the mesh and instance data.
    c=a.get_component_by_class(u.HierarchicalInstancedStaticMeshComponent)
    c.set_static_mesh(mesh);c.set_collision_profile_name('NoCollision')
    mats=[material(role) for role in roles] if roles else [s.material_interface for s in mesh.static_materials]
    for i,mat in enumerate(mats):c.set_material(i,instance_material(mat))
    if cull:c.set_cull_distances(int(cull*.85),int(cull))
    added=c.add_instances([transform(row) for row in rows],should_return_indices=True,world_space=True,update_navigation=False)
    actual=a.get_component_by_class(u.HierarchicalInstancedStaticMeshComponent)
    assert actual.get_instance_count()==len(rows),(label,actual.get_instance_count(),len(rows),len(added),c.get_path_name(),actual.get_path_name())
    result['groups'].append(dict(actor=label,mesh=mesh.get_path_name(),count=len(rows),cull_distance_cm=cull,lods=SM.get_lod_count(mesh)))

def tiled_groups(prefix,mesh,rows,folder,roles=None,cull=0):
    tiles=defaultdict(list)
    for row in rows:
        x,y=row['position_m'][:2];tiles[(math.floor(x/60),math.floor(y/60))].append(row)
    for (tx,ty),items in sorted(tiles.items()):group(prefix+'_%d_%d'%(tx,ty),mesh,items,folder,roles,cull)

def reused(path):
    if path not in result['reused_assets']:result['reused_assets'].append(path)
    return load(path)

def storage():
    rack=reused('/Game/GHSRefinementV2/Meshes/SM_GHS_V2Rack_A')
    rows=[];wide=[]
    for r in CAD['racks']:
        (wide if '192' in r['block'] else rows).append(dict(position_m=[*r['position_m'],0],rotation_deg=r['mesh_long_x_yaw_deg'],scale=[1,1,1]))
    tiled_groups('MPR_Racks',rack,rows,'Storage/Racks',['Porcelain','Cobalt','Porcelain','Cobalt','Cargo','CargoSeam','Charcoal'])
    tiled_groups('MPR_Racks_192',MESHES['SM_MPR_Rack_42D_192'],wide,'Storage/Racks')
    cargo=reused('/Game/GHSZcoolSmartFactory/DoublePallet/Meshes/SM_GHS_Presentation_CargoLow')
    pallets=CAD['pallet_positions']+read(SRC/'operations/instances.json').get('additional_pallet_positions',[])
    rows=[dict(position_m=[*r['position_m'][:2],0],rotation_deg=r.get('rotation_deg',0)+90,scale=[1.2192/1.2,1.016,1]) for r in pallets]
    tiled_groups('MPR_Pallets',cargo,rows,'Storage/Floor',['Cobalt','Cargo','CargoSeam'])
    cube=load('/Engine/BasicShapes/Cube')
    rows=[dict(position_m=[*r['position_m'],6.1],scale=[r['size_m'][0],r['size_m'][1],12.2]) for r in CAD['columns']]
    tiled_groups('MPR_Columns',cube,rows,'Architecture/Columns',['Porcelain'])
    rows=[dict(position_m=[*r['position_m'],.13],scale=[.57,.57,.26]) for r in CAD['columns']]
    tiled_groups('MPR_ColumnBases',cube,rows,'Architecture/Columns',['Cobalt'])

def docks():
    mesh=reused('/Game/GHSRefinementV2/Meshes/SM_GHS_V2DockDoor')
    rows=[]
    for r in CAD['dock_doors']+CAD['drive_in_doors']:
        n=r['outward_normal_xy'];p=r['position_m'];yaw=math.degrees(math.atan2(n[1],n[0]))-90
        rows.append(dict(position_m=[p[0]+n[0]*.12,p[1]+n[1]*.12,0],rotation_deg=yaw,scale=[r['opening_width_m']/3.04165,1,4.5/4.2 if r in CAD['drive_in_doors'] else 1]))
    tiled_groups('MPR_DockDoors',mesh,rows,'Architecture/Docks',['Porcelain','Cobalt','Charcoal','SoftBlue'])
    # Sparse stationary trailers; these are visualization context, not business traffic.
    truck=reused('/Game/GHSZcoolSmartFactory/Park/Meshes/SM_GHSPark_ClosedTruck');b=truck.get_bounds()
    # The shared truck faces local +X. Anchor its actual rear bumper 25cm
    # outside the dock instead of leaving a fixed 11m centre offset.
    rear_x_m=(b.origin.x-b.box_extent.x)/100
    dock_offset=.25-rear_x_m
    assert 0<dock_offset<20,('Unexpected shared truck bounds',rear_x_m)
    truck_rows=[]
    for i,r in enumerate(CAD['dock_doors']):
        if i%5:continue
        n=r['outward_normal_xy'];p=r['position_m'];yaw=math.degrees(math.atan2(n[1],n[0]))
        truck_rows.append(dict(position_m=[p[0]+n[0]*dock_offset,p[1]+n[1]*dock_offset,-1.2-(b.origin.z-b.box_extent.z)/100],rotation_deg=yaw,scale=[1,1,1]))
    tiled_groups('MPR_ParkedTruck',truck,truck_rows,'Environment/Vehicles',cull=100000)
    result['parked_truck_alignment']=dict(local_rear_x_m=rear_x_m,origin_offset_m=dock_offset,rear_clearance_m=.25,count=len(truck_rows))

def lighting_and_camera():
    sun=A.spawn_actor_from_class(u.DirectionalLight,u.Vector(0,0,18000));sun.set_actor_label('MPR_KeyLight');tag(sun,'Lighting')
    sun.set_actor_rotation(u.Rotator(pitch=-55,yaw=-38),False);c=sun.get_component_by_class(u.DirectionalLightComponent)
    c.set_mobility(u.ComponentMobility.MOVABLE);c.set_intensity(3.65);c.set_light_color(u.LinearColor(1,.985,.965,1));c.set_editor_property('light_source_angle',9)
    sky=A.spawn_actor_from_class(u.SkyLight,u.Vector());sky.set_actor_label('MPR_Ambient');tag(sky,'Lighting')
    c=sky.get_component_by_class(u.SkyLightComponent);c.set_mobility(u.ComponentMobility.MOVABLE);c.set_intensity(.42)
    c.set_editor_property('source_type',u.SkyLightSourceType.SLS_SPECIFIED_CUBEMAP);c.set_cubemap(load('/Engine/EngineResources/GrayLightTextureCube'))
    c.set_light_color(u.LinearColor(.87,.94,1,1));c.set_editor_property('real_time_capture',False);c.set_editor_property('cast_shadows',False)
    c.set_editor_property('lower_hemisphere_is_black',False);c.set_editor_property('lower_hemisphere_color',u.LinearColor(.055,.075,.1,1))
    pp=A.spawn_actor_from_class(u.PostProcessVolume,u.Vector());pp.set_actor_label('MPR_GHS_Style');tag(pp,'Lighting');pp.set_editor_property('unbound',True)
    s=pp.get_editor_property('settings')
    changes=dict(dynamic_global_illumination_method=u.DynamicGlobalIlluminationMethod.NONE,reflection_method=u.ReflectionMethod.NONE,
                 vignette_intensity=0.,bloom_intensity=.015,ambient_occlusion_intensity=1.1,ambient_occlusion_radius=150.,ambient_occlusion_quality=80.,
                 auto_exposure_min_brightness=0.,auto_exposure_max_brightness=0.,auto_exposure_bias=0.,motion_blur_amount=0.)
    for k,v in changes.items():s.set_editor_property('override_'+k,True);s.set_editor_property(k,v)
    pp.set_editor_property('settings',s)
    sky_actor=spawn_mesh('MPR_StudioSky',load('/Engine/BasicShapes/Sphere'),'Lighting',scale=[20000]*3,roles=['Sky'])
    sky_actor.get_component_by_class(u.StaticMeshComponent).set_editor_property('cast_shadow',False)
    world=E.get_editor_world();world.get_world_settings().set_editor_property('default_game_mode',u.load_class(None,'/Script/Test.GHSWarehouseGameMode'))
    bp=load('/Game/GHSNormalWarehouse/Camera/BP_GHS_WarehouseCamera')
    cam=A.spawn_actor_from_class(bp.generated_class(),u.Vector());cam.set_actor_label('MPR_WarehouseCamera');cam.set_folder_path('MPR/Cameras')
    cam.tags=['MPRWarehouse','MPR_Camera'];cam.set_editor_property('auto_possess_player',u.AutoReceiveInput.PLAYER0)
    for k,v in dict(overview_center=u.Vector(0,0,1200),overview_distance=58000.,overview_pitch=-42.,overview_yaw=-75.,maximum_pan=u.Vector2D(60000,50000)).items():cam.set_editor_property(k,v)
    cam.reset_overview(True)
    rot=u.Rotator(pitch=-42,yaw=-75);eye=u.Vector(0,0,1200)-u.MathLibrary.get_forward_vector(rot)*58000
    view=A.spawn_actor_from_class(u.CameraActor,eye,rot);view.set_actor_label('MPR_ReviewCamera');view.set_folder_path('MPR/Cameras');view.tags=['MPRWarehouse']
    view.get_component_by_class(u.CameraComponent).set_field_of_view(56)
    E.set_level_viewport_camera_info(eye,rot)

def run():
    assert not L.is_in_play_in_editor()
    dirty=[p.get_path_name() for p in u.EditorLoadingAndSavingUtils.get_dirty_map_packages()+u.EditorLoadingAndSavingUtils.get_dirty_content_packages()]
    assert not dirty,('Unsaved packages must be preserved',dirty)
    before_path=E.get_editor_world().get_path_name().split('.')[0];result['previous_map']=before_path
    previous_map=ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'
    previous_sha=hashlib.sha256(previous_map.read_bytes()).hexdigest()
    result['ghs_map_sha256_before']=previous_sha
    manifests=[('Architecture',SRC/'architecture/mpr_architecture.json'),('Environment',SRC/'environment/environment_manifest.json'),('Operations',SRC/'operations/mpr_operations.json'),('Storage',SRC/'storage/manifest.json')]
    equipment=SRC/'equipment/sorter_manifest.json'
    if equipment.exists():manifests.append(('Equipment',equipment))
    variants=SRC/'equipment/sorter_variants_manifest.json'
    if variants.exists():manifests.append(('Equipment',variants))
    planned_assets=[DEST+'/'+category+'/Meshes/'+row['name'] for category,path in manifests
                    for row in read(path)['meshes'] if row.get('lod',0)==0]
    instance_materials=planned_instance_materials(manifests)
    planned_assets.extend(path for _,path in instance_materials)
    exterior_materials=exterior_material_plan()
    planned_assets.extend(path for _,_,path in exterior_materials)
    planned_assets.append(EXTERIOR_MASTER)
    ownership=verify_owned_scene(ROOT,owner=OWNER,map_path=MAP,planned_assets=planned_assets,allow_new=True)
    preflight_materials(instance_materials,exterior_materials)
    create_exterior_materials(exterior_materials)
    create_instance_materials(instance_materials)
    if LIB.does_asset_exist(MAP):
        assert L.load_level(MAP)
        assert all(a.actor_has_tag('MPRWarehouse') or isinstance(a,(u.WorldSettings,u.Brush)) for a in A.get_all_level_actors()),'Unowned map edits'
        for a in list(A.get_all_level_actors()):
            if a.actor_has_tag('MPRWarehouse'):A.destroy_actor(a)
    else:assert L.new_level(MAP)
    old_flag=u.SystemLibrary.get_console_variable_int_value('Interchange.FeatureFlags.Import.FBX')
    u.SystemLibrary.execute_console_command(None,'Interchange.FeatureFlags.Import.FBX 0')
    try:
        for category,path in manifests:
            data=read(path)
            for row in data['meshes']:
                if row.get('lod',0)>0:continue
                if category=='Equipment':
                    row=dict(row)
                    lodrows=sorted([r for r in data['meshes'] if r['name'].startswith(row['name']+'_LOD')],key=lambda r:r['lod'])
                    row['lod_files']=[r['fbx'] for r in lodrows]
                mesh=import_mesh(row,category)
                if category in ('Architecture','Environment') and not row.get('instance_only'):
                    label=row['name'].replace('SM_','');a=spawn_mesh(label,mesh,category)
                    if row['name'].startswith('SM_MPR_Roof'):tag(a,'Architecture/RemovableRoof',['MPR_Roof'])
            instance_data=data.get('instances',{})
            if category=='Operations':instance_data=read(SRC/'operations/instances.json')['instances']
            if path.name=='sorter_variants_manifest.json':instance_data=read(SRC/'equipment/sorter_instances.json')['instances']
            if isinstance(instance_data,list):
                batches=defaultdict(list)
                for row in instance_data:batches[row['mesh']].append(row)
                instance_data=batches
            for name,rows in instance_data.items():
                mesh=MESHES.get(name) or load(name)
                roles=['Cobalt','Porcelain','Metal','Charcoal','Metal'] if name=='/Game/GHSDigitalTwin/Meshes/SM_GHS_Shared_Conveyor' else None
                safe_name=name.rsplit('/',1)[-1]
                tiled_groups('MPR_'+safe_name,mesh,rows,category,roles,cull=120000 if category=='Environment' else 0)
            result['stage']=category;write()
    finally:u.SystemLibrary.execute_console_command(None,'Interchange.FeatureFlags.Import.FBX '+str(old_flag))
    storage();docks();lighting_and_camera()
    A.set_selected_level_actors([]);L.editor_set_game_view(True)
    assert L.save_current_level()
    assert hashlib.sha256(previous_map.read_bytes()).hexdigest()==previous_sha,'GHS original map changed'
    for row in result['materials_created']:
        source=ROOT/('Content/'+row['parent'].split('.')[0].removeprefix('/Game/')+'.uasset')
        assert hashlib.sha256(source.read_bytes()).hexdigest()==row['parent_sha256'],'Shared material changed'
    result.update(success=True,actor_count=len(A.get_all_level_actors()),instance_count=sum(g['count'] for g in result['groups']),
                  source_rack_count=len(CAD['racks']),source_column_count=len(CAD['columns']),source_dock_count=len(CAD['dock_doors']),
                  ghs_map_preserved=True,materials_reused={k:v.get_path_name() for k,v in MATS.items()},
                  performance_policy='60m spatial HISM batches, shared 4-LOD racks and pallets, no collision or static tick, bounded environment culling')
    record_successful_build(ROOT,result,ownership)
    write();print('MPR_SCENE_BUILT',result['actor_count'],result['instance_count'])

if __name__=='__main__':
    try:run()
    except Exception:
        result['success']=False;result['error']=traceback.format_exc();write();raise
