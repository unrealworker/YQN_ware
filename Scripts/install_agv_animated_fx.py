"""Native animated deferred decals, attached to AGVs; no effect meshes."""
import json
import math
import shutil
import sys
import traceback
from datetime import datetime
from pathlib import Path
import unreal

FX_ROOT=Path(r'D:\UEPro\Test')
sys.path.insert(0,str(FX_ROOT/'Scripts/video_reference'))
from agv_fx_shader import RINGS_HLSL,RADAR_HLSL
FX_DEST='/Game/VideoDigitalTwin/FX'
FX_MAP='/Game/Maps/VideoDigitalTwinWarehouse'
fx_lib=unreal.EditorAssetLibrary
fx_ml=unreal.MaterialEditingLibrary
fx_assets=unreal.AssetToolsHelpers.get_asset_tools()
fx_actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
fx_levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
fx_editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
fx_report_path=FX_ROOT/'Saved/AGVFX_InstallReport.json'
fx_report=dict(success=False,implementation='Deferred Decal + procedural time-driven HLSL',effect_meshes_used=False)

def fx_save(asset):assert fx_lib.save_loaded_asset(asset,only_if_is_dirty=False),asset.get_path_name()

def fx_link(a,b,pin,output=''):assert fx_ml.connect_material_expressions(a,output,b,pin),pin

def fx_param(material,name,value,vector=False):
    cls=unreal.MaterialExpressionVectorParameter if vector else unreal.MaterialExpressionScalarParameter
    n=fx_ml.create_material_expression(material,cls);n.set_editor_property('parameter_name',name)
    n.set_editor_property('default_value',unreal.LinearColor(*value,1) if vector else float(value));return n

def fx_material(name,code):
    path=FX_DEST+'/'+name
    m=fx_lib.load_asset(path) if fx_lib.does_asset_exist(path) else fx_assets.create_asset(name,FX_DEST,unreal.Material,unreal.MaterialFactoryNew())
    fx_ml.delete_all_material_expressions(m)
    m.set_editor_property('blend_mode',unreal.BlendMode.BLEND_TRANSLUCENT)
    m.set_editor_property('material_domain',unreal.MaterialDomain.MD_DEFERRED_DECAL)
    # UE 5.4 derives emissive-only decal passes from the connected outputs.
    custom=fx_ml.create_material_expression(m,unreal.MaterialExpressionCustom)
    custom.set_editor_property('code',code);custom.set_editor_property('output_type',unreal.CustomMaterialOutputType.CMOT_FLOAT4)
    custom.set_editor_property('description','Analytic animated AGV projection; no mesh, no texture')
    inputs=[]
    for name_in in ['UV','T','Tint','Phase']:
        entry=unreal.CustomInput();entry.set_editor_property('input_name',name_in);inputs.append(entry)
    custom.set_editor_property('inputs',inputs)
    uv=fx_ml.create_material_expression(m,unreal.MaterialExpressionTextureCoordinate)
    clock=fx_ml.create_material_expression(m,unreal.MaterialExpressionTime);clock.set_editor_property('ignore_pause',False)
    speed=fx_param(m,'Speed',1)
    t=fx_ml.create_material_expression(m,unreal.MaterialExpressionMultiply)
    fx_link(clock,t,'A');fx_link(speed,t,'B')
    fx_link(uv,custom,'UV');fx_link(t,custom,'T')
    fx_link(fx_param(m,'Tint',(.04,.8,.22),True),custom,'Tint');fx_link(fx_param(m,'Phase',0),custom,'Phase')
    rgb=fx_ml.create_material_expression(m,unreal.MaterialExpressionComponentMask)
    alpha=fx_ml.create_material_expression(m,unreal.MaterialExpressionComponentMask)
    for channel in ['r','g','b','a']:
        rgb.set_editor_property(channel,channel!='a');alpha.set_editor_property(channel,channel=='a')
    fx_link(custom,rgb,'');fx_link(custom,alpha,'')
    assert fx_ml.connect_material_property(rgb,'',unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    assert fx_ml.connect_material_property(alpha,'',unreal.MaterialProperty.MP_OPACITY)
    fx_ml.layout_material_expressions(m);fx_ml.recompile_material(m);fx_save(m)
    return m

def fx_instance(name,parent,tint,phase,speed=1):
    path=FX_DEST+'/'+name
    m=fx_lib.load_asset(path) if fx_lib.does_asset_exist(path) else fx_assets.create_asset(name,FX_DEST,unreal.MaterialInstanceConstant,unreal.MaterialInstanceConstantFactoryNew())
    fx_ml.set_material_instance_parent(m,parent)
    # UE 5.4 setters return false unconditionally; verify the values by reading back.
    fx_ml.set_material_instance_vector_parameter_value(m,'Tint',unreal.LinearColor(*tint,1))
    fx_ml.set_material_instance_scalar_parameter_value(m,'Phase',phase)
    fx_ml.set_material_instance_scalar_parameter_value(m,'Speed',speed)
    fx_ml.update_material_instance(m)
    got=fx_ml.get_material_instance_vector_parameter_value(m,'Tint')
    assert all(abs(a-b)<1e-5 for a,b in zip((got.r,got.g,got.b),tint))
    assert abs(fx_ml.get_material_instance_scalar_parameter_value(m,'Phase')-phase)<1e-5
    assert abs(fx_ml.get_material_instance_scalar_parameter_value(m,'Speed')-speed)<1e-5
    fx_save(m);return m

def fx_decal(label,parent,material,radius_cm,yaw,sort):
    by={a.get_actor_label():a for a in fx_actors.get_all_level_actors()}
    a=by.get(label)
    if a is None:a=fx_actors.spawn_actor_from_class(unreal.DecalActor,parent.get_actor_location())
    assert isinstance(a,unreal.DecalActor),label
    c=a.get_component_by_class(unreal.DecalComponent);c.set_mobility(unreal.ComponentMobility.MOVABLE)
    c.set_editor_property('decal_size',unreal.Vector(3,radius_cm,radius_cm))
    c.set_fade_screen_size(0);c.set_sort_order(sort);c.set_decal_material(material)
    c.set_editor_property('fade_start_delay',0.0);c.set_editor_property('fade_duration',0.0)
    p=parent.get_actor_location()
    a.set_actor_location(unreal.Vector(p.x,p.y,1.5),False,False)
    a.set_actor_rotation(unreal.Rotator(pitch=-90,yaw=yaw,roll=0),False)
    a.set_actor_scale3d(unreal.Vector(1,1,1));a.set_actor_label(label);a.set_folder_path('VideoTwin/FX/AnimatedDecals')
    rule=unreal.AttachmentRule.KEEP_WORLD
    assert a.attach_to_actor(parent,'',rule,rule,rule,False),label
    a.set_editor_property('tags',['AGVAnimatedFX','FXOwner='+parent.get_actor_label(),'NoEffectMesh'])
    assert not a.get_components_by_class(unreal.StaticMeshComponent)
    return dict(actor=label,parent=parent.get_actor_label(),material=material.get_path_name(),radius_cm=radius_cm,
                projection_depth_cm=6,rotation_yaw=yaw,type='Radar' if 'Radar' in label else 'Diffusion')

try:
    assert fx_editor.get_editor_world().get_path_name().split('.')[0]==FX_MAP
    assert fx_levels.save_current_level()
    backup_dir=FX_ROOT/'Saved/Backups';backup_dir.mkdir(parents=True,exist_ok=True)
    backup=backup_dir/('VideoWarehouse_BeforeAnimatedFX_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.umap')
    shutil.copy2(FX_ROOT/'Content/Maps/VideoDigitalTwinWarehouse.umap',backup)
    fx_report['backup']=str(backup)
    by={a.get_actor_label():a for a in fx_actors.get_all_level_actors()}
    rings=fx_material('M_VR_FX_Diffusion',RINGS_HLSL);radar=fx_material('M_VR_FX_Radar',RADAR_HLSL)
    records=[]
    for i,name in enumerate(['CDD14-1','CDD14-2','CDD14-3','CDD14-4','CBD50-1','HR-1','DN-1']):
        parent=by[name]
        tint=(1,.15,.015) if name=='DN-1' else (.05,.80,.17)
        mi=fx_instance('MI_VR_FX_'+name.replace('-','_'),rings,tint,i*.173)
        records.append(fx_decal('FX_'+name+'_Diffusion',parent,mi,175 if name=='DN-1' else 155,parent.get_actor_rotation().yaw,30))
    parent=by['CBD50-1']
    mi=fx_instance('MI_VR_FX_CBD50_Radar',radar,(.04,.75,.31),.13)
    # Preserve the reference scan direction toward the avoidance cone.
    # DeferredDecal.usf uses UV=(local Z, local Y); the old FBX fan faces local -Y.
    radar_yaw=by['SCAN_AvoidanceFan'].get_actor_rotation().yaw+180
    records.append(fx_decal('FX_CBD50-1_Radar',parent,mi,350,radar_yaw,20))
    old_labels=[name+'_StatusRing' for name in ['CDD14-1','CDD14-2','CDD14-3','CDD14-4','CBD50-1','HR-1']]+['ALARM_DN1_Ring','SCAN_AvoidanceFan']
    for name in old_labels:
        c=by[name].get_component_by_class(unreal.StaticMeshComponent)
        c.set_visibility(False,True);c.set_hidden_in_game(True,True)
    # Keep the registry in sync with the user's current editor placements.
    registry_path=FX_ROOT/'SourceAssets/VideoReference/scene_registry.json'
    registry=json.loads(registry_path.read_text(encoding='utf-8'))
    for record in registry:
        a=by[record['id']];p=a.get_actor_location();record['position_m']=[p.x/100,p.y/100,p.z/100];record['yaw']=a.get_actor_rotation().yaw
    registry_path.write_text(json.dumps(registry,indent=2),encoding='utf-8')
    fx_manifest=dict(implementation='Native deferred decals with Time-driven procedural shader',effect_meshes=False,
                     master_materials=[rings.get_path_name(),radar.get_path_name()],effects=records,hidden_legacy_actors=old_labels)
    (FX_ROOT/'SourceAssets/VideoReference/animated_fx.json').write_text(json.dumps(fx_manifest,indent=2),encoding='utf-8')
    assert fx_levels.save_current_level()
    fx_report.update(success=True,effect_count=len(records),legacy_mesh_effects_disabled=len(old_labels),effects=records)
    fx_report_path.write_text(json.dumps(fx_report,indent=2),encoding='utf-8')
    unreal.log('AGV_ANIMATED_FX_INSTALLED: 8 native decals, zero effect meshes')
    exec(compile((FX_ROOT/'Scripts/capture_agv_animated_fx.py').read_text(encoding='utf-8'),'capture_agv_animated_fx.py','exec'),globals())
except Exception:
    fx_report['error']=traceback.format_exc();fx_report_path.write_text(json.dumps(fx_report,indent=2),encoding='utf-8');raise
