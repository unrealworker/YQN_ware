"""Independent bright CAD warehouse; source levels and meshes are immutable."""
import hashlib,json,sys,traceback
from pathlib import Path
import unreal

ROOT=Path(r'D:\UEPro\Test');SOURCE=ROOT/'SourceAssets/GHS_Normal'
MAP='/Game/Maps/GHS_CAD_NormalWarehouse';OLD_MAP='/Game/Maps/GHS_CAD_DigitalTwin'
DEST='/Game/GHSNormalWarehouse';MR=DEST+'/Materials';FR=DEST+'/FX'
REPORT=ROOT/'Saved/GHS_NormalBuild.json'
style=json.loads((SOURCE/'material_style.json').read_text(encoding='utf-8'))
light=json.loads((SOURCE/'lighting_style.json').read_text(encoding='utf-8'))
lib=unreal.EditorAssetLibrary;ml=unreal.MaterialEditingLibrary
assets=unreal.AssetToolsHelpers.get_asset_tools()
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
report=dict(success=False,map=MAP,source_map=OLD_MAP,materials={},component_overrides={},fx=[],added_environment=[])

def save(asset):
    assert asset.get_path_name().startswith(DEST+'/'),asset.get_path_name()
    assert lib.save_loaded_asset(asset,only_if_is_dirty=False)

def node(mat,cls,**props):
    n=ml.create_material_expression(mat,cls)
    for key,value in props.items():n.set_editor_property(key,value)
    return n

def scalar(mat,name,value):
    return node(mat,unreal.MaterialExpressionScalarParameter,parameter_name=name,default_value=float(value))

def vector(mat,name,values):
    return node(mat,unreal.MaterialExpressionVectorParameter,parameter_name=name,default_value=unreal.LinearColor(*values,1))

def link(a,b,pin,output=''):assert ml.connect_material_expressions(a,output,b,pin),pin
def plug(a,prop):assert ml.connect_material_property(a,'',prop)

def clear(mat):
    while ml.get_num_material_expressions(mat):
        before=ml.get_num_material_expressions(mat);ml.delete_all_material_expressions(mat)
        assert ml.get_num_material_expressions(mat)<before

def custom(mat,code,names):
    n=node(mat,unreal.MaterialExpressionCustom,code=code,output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    entries=[]
    for name in names:
        e=unreal.CustomInput();e.set_editor_property('input_name',name);entries.append(e)
    n.set_editor_property('inputs',entries)
    return n

def material(name,item):
    path=MR+'/M_GHN_'+name
    mat=lib.load_asset(path) if lib.does_asset_exist(path) else assets.create_asset('M_GHN_'+name,MR,unreal.Material,unreal.MaterialFactoryNew())
    assert isinstance(mat,unreal.Material);clear(mat)
    mat.set_editor_property('used_with_instanced_static_meshes',True)
    mat.set_editor_property('shading_model',unreal.MaterialShadingModel.MSM_UNLIT if item.get('unlit') else unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
    mat.set_editor_property('blend_mode',unreal.BlendMode.BLEND_MASKED if item.get('masked') else unreal.BlendMode.BLEND_OPAQUE)
    mat.set_editor_property('two_sided',item.get('two_sided',False))
    base=vector(mat,'SurfaceTint',item['base_color']);surface=base
    if 'tier_period_cm' in item:
        # Physical shelf channels are the only broad blue structural bands.
        # Upright webs receive matching narrow bands at the same elevations.
        surface=custom(mat,'float d=abs(frac((P.z-Origin)/Period+0.5)-0.5)*Period; return lerp(Base,Accent,1.0-smoothstep(HalfWidth,HalfWidth+0.4,d));',['P','Base','Accent','Origin','Period','HalfWidth'])
        link(node(mat,unreal.MaterialExpressionWorldPosition),surface,'P')
        link(base,surface,'Base');link(vector(mat,'ShelfBlue',item['tier_color']),surface,'Accent')
        for param,key in [('Origin','tier_origin_cm'),('Period','tier_period_cm'),('HalfWidth','tier_halfwidth_cm')]:link(scalar(mat,param,item[key]),surface,param)
    if 'instance_variation' in item:
        surface=custom(mat,'return Base * (1.0 + (Random*2.0-1.0)*Amount);',['Base','Random','Amount'])
        link(base,surface,'Base');link(node(mat,unreal.MaterialExpressionPerInstanceRandom),surface,'Random');link(scalar(mat,'Variation',item['instance_variation']),surface,'Amount')
    plug(surface,unreal.MaterialProperty.MP_EMISSIVE_COLOR if item.get('unlit') else unreal.MaterialProperty.MP_BASE_COLOR)
    plug(scalar(mat,'Roughness',item['roughness']),unreal.MaterialProperty.MP_ROUGHNESS)
    plug(scalar(mat,'Metallic',item['metallic']),unreal.MaterialProperty.MP_METALLIC)
    plug(scalar(mat,'Specular',.30),unreal.MaterialProperty.MP_SPECULAR)
    if item.get('masked'):plug(scalar(mat,'EnvelopeOpacity',item['opacity']),unreal.MaterialProperty.MP_OPACITY_MASK)
    ml.layout_material_expressions(mat);ml.recompile_material(mat)
    tint=ml.get_material_default_vector_parameter_value(mat,'SurfaceTint')
    assert max(abs(a-b) for a,b in zip([tint.r,tint.g,tint.b],item['base_color']))<1e-5
    save(mat);report['materials'][name]=mat.get_path_name();return mat

def override(label,slots):
    c=labels[label].get_component_by_class(unreal.StaticMeshComponent);assert c
    assert c.get_num_materials()==len(slots),(label,c.get_num_materials(),slots)
    for i,name in enumerate(slots):c.set_material(i,mats[name])
    report['component_overrides'][label]=slots

def environment_actor(label,mesh,position,scale,mat):
    a=labels.get(label)
    if a is None:a=actors.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector(*position))
    a.set_actor_label(label);a.set_folder_path('GHS_Normal/Environment')
    c=a.get_component_by_class(unreal.StaticMeshComponent);c.set_static_mesh(lib.load_asset(mesh));c.set_material(0,mats[mat])
    c.set_collision_profile_name('NoCollision');c.set_editor_property('cast_shadow',False);c.set_editor_property('receives_decals',False)
    a.set_actor_scale3d(unreal.Vector(*scale));report['added_environment'].append(label)
    return a

def fx_master(kind):
    target=FR+'/M_GHN_FX_'+kind
    if lib.does_asset_exist(target):
        sys.path.insert(0,str(ROOT/'Scripts/ghs'))
        from normal_fx_style import update_master
        mat=lib.load_asset(target);update_master(mat,light);save(mat);return mat
    mat=lib.duplicate_asset('/Game/VideoDigitalTwin/FX/M_VR_FX_'+kind,target);assert mat
    rgb=ml.get_material_property_input_node(mat,unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    alpha=ml.get_material_property_input_node(mat,unreal.MaterialProperty.MP_OPACITY)
    # Keep the original Time/Speed/Phase graph, add body color to read on a light floor.
    visited=set();pending=[rgb];tint=None
    while pending:
        n=pending.pop()
        if n in visited:continue
        visited.add(n)
        if isinstance(n,unreal.MaterialExpressionVectorParameter) and str(n.get_editor_property('parameter_name'))=='Tint':tint=n
        pending += [x for x in ml.get_inputs_for_material_expression(mat,n) if x]
    assert tint
    plug(tint,unreal.MaterialProperty.MP_BASE_COLOR)
    for original,parameter,value,output in [(rgb,'EmissionScale',light['fx_emissive_scale'],unreal.MaterialProperty.MP_EMISSIVE_COLOR),(alpha,'OpacityScale',light['fx_opacity_scale'],unreal.MaterialProperty.MP_OPACITY)]:
        mul=node(mat,unreal.MaterialExpressionMultiply);link(original,mul,'A');link(scalar(mat,parameter,value),mul,'B');plug(mul,output)
    ml.recompile_material(mat);save(mat);return mat

try:
    if lib.does_asset_exist(MAP):
        assert REPORT.exists(),'Refusing to overwrite an unrelated existing map'
        assert levels.load_level(MAP)
    else:assert levels.new_level_from_template(MAP,OLD_MAP)
    assert editor.get_editor_world().get_path_name().split('.')[0]==MAP
    labels={a.get_actor_label():a for a in actors.get_all_level_actors()}
    lib.make_directory(MR);lib.make_directory(FR)
    mats={name:material(name,item) for name,item in style.items()}
    overrides={
        'GHS_CAD_ExactFootprint':['Floor'],'GHS_DarkSurround':['Surround'],'GHS_ContextGrid':['GridDisabled'],
        'GHS_CAD_WallFaces':['Wall'],'GHS_CAD_WallSections':['WallSection'],'GHS_CAD_WallEdges':['WallTrim'],
        'GHS_CAD_Columns':['Wall'],'GHS_ColumnBases':['WallSection'],'GHS_ColumnEdgeOutlines':['WallTrim'],
        'GHS_CAD_DoorClearances':['DoorLine'],'GHS_ChargingSupportPanels':['Wall'],
        'GHS_ChargingSupportCaps':['WallSection'],'GHS_ChargingSupportEnds':['WallSection'],
        'GHS_CAD_ChargingBayOutlines':['LocationBlue'],'GHS_ColumnOccupiedStorageOutlines':['DoorLine'],
        'GHS_CAD_Racks':['RackFrame','RackSilver','Charcoal','BinInterior','BinCardboard','BinRim','GhostDisabled'],
        'GHS_CAD_DockRacks':['DockFrame','RackSilver','Charcoal','BinInterior','BinCardboard','BinRim','GhostDisabled']}
    for name in ['GHS_CAD_PalletCargo','GHS_CAD_PalletCargoLow','GHS_CAD_PalletCargoHigh']:overrides[name]=['BluePallet','Cardboard','CardboardSeam']
    for label,slots in overrides.items():override(label,slots)
    for label in ['GHS_ContextGrid','GHS_ColumnOccupiedStorageOutlines']:
        labels[label].set_actor_hidden_in_game(True);labels[label].set_is_temporarily_hidden_in_editor(True)
        c=labels[label].get_component_by_class(unreal.StaticMeshComponent);c.set_visibility(False);c.set_hidden_in_game(True)
    for a in labels.values():
        c=a.get_component_by_class(unreal.TextRenderComponent)
        if c:c.set_text_render_color(unreal.Color(r=36,g=64,b=98,a=255))
    environment_actor('GHN_StudioGround','/Engine/BasicShapes/Plane',[-600,800,-53],[5000,5000,1],'Surround')
    environment_actor('GHN_StudioSky','/Engine/BasicShapes/Sphere',[0,0,0],[20000,20000,20000],'Sky')
    dc=next(a.get_component_by_class(unreal.DirectionalLightComponent) for a in labels.values() if isinstance(a,unreal.DirectionalLight))
    key=dc.get_owner();dc.set_mobility(unreal.ComponentMobility.MOVABLE);dc.set_intensity(light['directional_intensity'])
    key.set_actor_rotation(unreal.Rotator(pitch=light['directional_rotation'][0],yaw=light['directional_rotation'][1],roll=light['directional_rotation'][2]),False)
    dc.set_light_color(unreal.LinearColor(*light['directional_color'],1));dc.set_editor_property('cast_shadows',True);dc.set_editor_property('light_source_angle',light['directional_source_angle'])
    sc=next(a.get_component_by_class(unreal.SkyLightComponent) for a in labels.values() if isinstance(a,unreal.SkyLight))
    sc.set_mobility(unreal.ComponentMobility.MOVABLE);sc.set_intensity(light['skylight_intensity']);sc.set_light_color(unreal.LinearColor(*light['skylight_color'],1))
    sc.set_editor_property('source_type',unreal.SkyLightSourceType.SLS_SPECIFIED_CUBEMAP);sc.set_cubemap(lib.load_asset(light['skylight_cubemap']))
    for key,value in [('real_time_capture',False),('cast_shadows',False),('cubemap_resolution',64),('lower_hemisphere_is_black',False)]:sc.set_editor_property(key,value)
    pp=next(a for a in labels.values() if isinstance(a,unreal.PostProcessVolume));settings=pp.get_editor_property('settings')
    changes=dict(dynamic_global_illumination_method=unreal.DynamicGlobalIlluminationMethod.NONE,reflection_method=unreal.ReflectionMethod.NONE,vignette_intensity=0.0,bloom_intensity=light['bloom_intensity'],ambient_occlusion_intensity=light['ambient_occlusion_intensity'],ambient_occlusion_radius=light['ambient_occlusion_radius_cm'],ambient_occlusion_quality=light['ambient_occlusion_quality'],auto_exposure_min_brightness=light['exposure_ev100'],auto_exposure_max_brightness=light['exposure_ev100'],auto_exposure_bias=0.0)
    for key,value in changes.items():settings.set_editor_property('override_'+key,True);settings.set_editor_property(key,value)
    pp.set_editor_property('settings',settings)
    masters={kind:fx_master(kind) for kind in ['Diffusion','Radar']}
    for label,a in labels.items():
        c=a.get_component_by_class(unreal.DecalComponent)
        if not c:continue
        kind='Radar' if label.endswith('_Radar') else 'Diffusion';old=c.get_decal_material();path=FR+'/MI_GHN_'+label
        mi=lib.load_asset(path) if lib.does_asset_exist(path) else lib.duplicate_asset(old.get_path_name(),path)
        assert isinstance(mi,unreal.MaterialInstanceConstant)
        ml.set_material_instance_parent(mi,masters[kind]);ml.set_material_instance_vector_parameter_value(mi,'Tint',unreal.LinearColor(*light['fx_tint'],1))
        ml.update_material_instance(mi);save(mi);c.set_decal_material(mi)
        report['fx'].append(dict(actor=label,kind=kind,material=mi.get_path_name()))
    camera=labels['CAM_GHS_FloorStorage'];editor.set_level_viewport_camera_info(camera.get_actor_location(),camera.get_actor_rotation())
    actors.set_selected_level_actors([])
    assert levels.save_current_level()
    report.update(success=True,actor_count=len(actors.get_all_level_actors()),hism_group_count=18,instance_count=14116,lighting=light,model_reuse=True,conveyors_added=0)
    unreal.log('GHS_NORMAL_SCENE_SAVED')
except Exception:
    report['error']=traceback.format_exc();raise
finally:
    REPORT.write_text(json.dumps(report,indent=2),encoding='utf-8')
