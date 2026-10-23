"""Preservation-first, repeatable material/light polish of the open GHS map.

Execute in the live Unreal Editor, outside PIE. This script never moves an
actor, edits a mesh, changes an instance, modifies original material assets,
or saves unrelated content. Its only vertex offset flattens the uniquely
identified forest pads (original local Z=8/-16 cm) onto the existing ground.
"""
from datetime import datetime, timezone
from pathlib import Path
import builtins
import copy
import hashlib
import json
import math
import runpy
import shutil
import traceback
import unreal

ROOT=Path('D:/UEPro/Test')
OUT=ROOT/'Saved/VisualPolish'
CONFIG=ROOT/'SourceAssets/GHS/VisualPolish/visual_polish.json'
MAP='/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
MAP_FILE=ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'
DEST='/Game/GHSZcoolSmartFactory/VisualPolish'
LIB=unreal.EditorAssetLibrary
ML=unreal.MaterialEditingLibrary
VERSION='visual-polish-v1'
OWNER='GHS.VisualPolish.Owner'
STATE='_ghs_visual_polish_owned_v1'
ROLES={'GHSPark_Ground':'Ground','GHN_StudioGround':'Backdrop',
       'GHSPark_Hardstand':'Hardstand','GHSPark_Landscape':'Landscape',
       'GHSPark_ContextRoads':'ContextRoad','GHSPark_CampusRoads':'CampusRoad',
       'GHSContextTransition_Landscape':'ContextLandscape'}
LIGHT_NAMES=['intensity','light_color','light_source_angle','contact_shadow_length','shadow_bias','shadow_slope_bias','cast_shadows']
SKY_NAMES=['intensity','light_color','lower_hemisphere_is_black','lower_hemisphere_color','cast_shadows','source_type','real_time_capture','cubemap']
PP_NAMES=['ambient_occlusion_intensity','ambient_occlusion_radius','ambient_occlusion_quality','bloom_intensity']
HEAVY_NAMES=['override_dynamic_global_illumination_method','dynamic_global_illumination_method','override_reflection_method','reflection_method',
             'auto_exposure_method','auto_exposure_min_brightness','auto_exposure_max_brightness','auto_exposure_bias']

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path): return json.loads(path.read_text(encoding='utf-8-sig'))
def write(path,data): path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def package(path): return path.split('.',1)[0]
def dirty(): return {p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()}
def asset_file(path): return ROOT/'Content'/(package(path).removeprefix('/Game/')+'.uasset')

def values(obj,names):
    result={}
    for name in names:
        value=obj.get_editor_property(name)
        if isinstance(value,(str,int,float,bool,type(None))): result[name]=value
        elif hasattr(value,'r'): result[name]=[value.r,value.g,value.b,value.a]
        elif hasattr(value,'x') and hasattr(value,'y'):
            result[name]=[float(value.x),float(value.y)]
            if hasattr(value,'z'):result[name].append(float(value.z))
        elif hasattr(value,'get_path_name'): result[name]=value.get_path_name()
        else: result[name]=str(value)
    return result

def scene_snapshot(actors):
    snap=runpy.run_path(str(ROOT/'Scripts/ghs/validate_park_expansion.py'))['snapshot']
    rows=[snap(a,unreal) for a in actors]
    for row in rows: row['components'].sort(key=lambda c:c['name'])
    return sorted(rows,key=lambda r:r['label'])

def assert_preserved(before,after,bindings):
    expected=copy.deepcopy(before)
    allowed={(b['actor'],b['component'],b['slot']):b['after'] for b in bindings}
    for row in expected:
        for component in row['components']:
            for slot in range(len(component['materials'])):
                key=(row['label'],component['name'],slot)
                if key in allowed: component['materials'][slot]=allowed[key]
    assert expected==after,'Unexpected actor/component/material/instance change; map was not saved'

def node(mat,cls,**props):
    result=ML.create_material_expression(mat,cls)
    for name,value in props.items(): result.set_editor_property(name,value)
    return result

def connect(a,b,pin,out=''):
    assert ML.connect_material_expressions(a,out,b,pin),(a,b,pin)

def connect_world_position_offset(mat,expression):
    """UE5.4 hides WPO from Python; use the narrowly scoped native helper."""
    assert unreal.GHSVisualMaterialLibrary.connect_world_position_offset(mat,expression)
    assert unreal.GHSVisualMaterialLibrary.has_world_position_offset(mat)

def custom(mat,code,inputs,kind):
    fields=[]
    for name in inputs:
        item=unreal.CustomInput();item.set_editor_property('input_name',name);fields.append(item)
    return node(mat,unreal.MaterialExpressionCustom,code=code,inputs=fields,
                output_type=kind,description='GHS visual polish '+VERSION)

def vec(values): return 'float3('+','.join(format(float(x),'.8g') for x in values)+')'

def source_tint(mat,fallback):
    if isinstance(mat,unreal.Material):
        names=[str(x) for x in ML.get_vector_parameter_names(mat)]
        if 'SurfaceTint' in names:
            c=ML.get_material_default_vector_parameter_value(mat,'SurfaceTint')
            return [c.r,c.g,c.b]
    return fallback

def own(path,state):
    if LIB.does_asset_exist(path):
        obj=LIB.load_asset(path)
        assert LIB.get_metadata_tag(obj,OWNER)==VERSION,('Existing destination is not ours',path)
        assert path not in dirty() or path in state['owned'],('Unrelated unsaved destination edit',path)
    state['owned'].add(path)

def texture(config,state):
    path=DEST+'/T_VisualPolish_CampusMask'
    own(path,state)
    texture=LIB.load_asset(path) if LIB.does_asset_exist(path) else None
    expected=config['mask']['sha256']
    assert sha(Path(config['mask']['file']))==expected,'Mask PNG differs from reviewed configuration'
    if texture is None or LIB.get_metadata_tag(texture,'GHS.VisualPolish.SourceHash')!=expected:
        task=unreal.AssetImportTask()
        for key,val in dict(filename=config['mask']['file'],destination_path=DEST,destination_name='T_VisualPolish_CampusMask',automated=True,replace_existing=True,save=False).items():task.set_editor_property(key,val)
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        texture=LIB.load_asset(path);assert isinstance(texture,unreal.Texture2D)
        LIB.set_metadata_tag(texture,OWNER,VERSION)
        LIB.set_metadata_tag(texture,'GHS.VisualPolish.SourceHash',expected)
    texture.set_editor_property('srgb',False)
    texture.set_editor_property('compression_settings',unreal.TextureCompressionSettings.TC_MASKS)
    texture.set_editor_property('address_x',unreal.TextureAddress.TA_CLAMP)
    texture.set_editor_property('address_y',unreal.TextureAddress.TA_CLAMP)
    return texture

def make_material(role,config,mask,old_tint,ground_z,state):
    path=DEST+'/M_VisualPolish_'+role
    own(path,state)
    fingerprint=hashlib.sha256(json.dumps(dict(config=config,role=role,old_tint=old_tint,ground_z=ground_z,version=VERSION),sort_keys=True).encode()).hexdigest()
    mat=LIB.load_asset(path) if LIB.does_asset_exist(path) else None
    if mat and LIB.get_metadata_tag(mat,'GHS.VisualPolish.Fingerprint')==fingerprint:
        return mat,dict(path=mat.get_path_name(),reused=True,expressions=ML.get_num_material_expressions(mat))
    if mat is None:
        mat=unreal.AssetToolsHelpers.get_asset_tools().create_asset(path.rsplit('/',1)[1],DEST,unreal.Material,unreal.MaterialFactoryNew())
        assert mat
        LIB.set_metadata_tag(mat,OWNER,VERSION)
    while ML.get_num_material_expressions(mat):
        previous_count=ML.get_num_material_expressions(mat)
        ML.delete_all_material_expressions(mat)
        assert ML.get_num_material_expressions(mat)<previous_count
    mat.set_editor_property('blend_mode',unreal.BlendMode.BLEND_OPAQUE)
    mat.set_editor_property('shading_model',unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
    mat.set_editor_property('used_with_instanced_static_meshes',True)
    palette=config['palette']
    if role in ('CampusRoad','ContextRoad'):
        color=palette['campus_road' if role=='CampusRoad' else 'context_road']
        base=node(mat,unreal.MaterialExpressionVectorParameter,parameter_name='SurfaceTint',default_value=unreal.LinearColor(*color,1))
    else:
        world=node(mat,unreal.MaterialExpressionWorldPosition,world_position_shader_offset=unreal.WorldPositionIncludedOffsets.WPT_EXCLUDE_ALL_SHADER_OFFSETS)
        u0,v0,u1,v1=config['atlas_bounds_uv_m'];ou,ov=config['cad_origin_uv_m']
        coordinates=custom(mat,f'return (Position.xy * 0.01 + float2({ou},{ov}) - float2({u0},{v0})) / float2({u1-u0},{v1-v0});',['Position'],unreal.CustomMaterialOutputType.CMOT_FLOAT2)
        connect(world,coordinates,'Position')
        sample=node(mat,unreal.MaterialExpressionTextureSampleParameter2D,parameter_name='CampusMask',texture=mask,sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
        # MaterialEditingLibrary compares the graph's shortened pin names:
        # UE5.4 MaterialGraphNode::GetShortenPinName maps Coordinates to UVs.
        assert 'UVs' in ML.get_material_expression_input_names(sample)
        connect(coordinates,sample,'UVs')
        center=config['far_fade_center_uv_m']
        code=f'''float2 uv = Position.xy * 0.01 + float2({ou},{ov});
float fade = smoothstep({config['far_fade_start_m']},{config['far_fade_end_m']},length(uv-float2({center[0]},{center[1]})));
float3 field = lerp({vec(palette['campus'])},{vec(palette['outer_green'])},Mask.g);
field = lerp(field,{vec(palette['far_ground'])},fade);
'''
        if role=='Landscape':
            code+=f'float forest = (abs(Position.z-8.0)<0.2 || abs(Position.z+16.0)<0.2) ? 1.0 : 0.0;\nreturn lerp({vec(old_tint)},field,forest);'
            offset=custom(mat,f'float forest=(abs(Position.z-8.0)<0.2 || abs(Position.z+16.0)<0.2)?1.0:0.0; return float3(0,0,({ground_z+.12}-Position.z)*forest);',['Position'],unreal.CustomMaterialOutputType.CMOT_FLOAT3)
            connect(world,offset,'Position');connect_world_position_offset(mat,offset)
        elif role=='Hardstand':
            code+=f'float3 surface=lerp({vec(old_tint)},{vec(palette["campus"])},Mask.r); return lerp(surface,{vec(palette["boundary"])},Mask.b*{config["boundary_opacity"]});'
        else:
            code+=f'return lerp(field,{vec(palette["boundary"])},Mask.b*{config["boundary_opacity"]});'
        base=custom(mat,code,['Position','Mask'],unreal.CustomMaterialOutputType.CMOT_FLOAT3)
        connect(world,base,'Position');connect(sample,base,'Mask')
    assert ML.connect_material_property(base,'',unreal.MaterialProperty.MP_BASE_COLOR)
    for name,value,prop in [('Roughness',.9,unreal.MaterialProperty.MP_ROUGHNESS),('Specular',.12,unreal.MaterialProperty.MP_SPECULAR),('Metallic',0.,unreal.MaterialProperty.MP_METALLIC)]:
        scalar=node(mat,unreal.MaterialExpressionScalarParameter,parameter_name=name,default_value=value)
        assert ML.connect_material_property(scalar,'',prop)
    ML.recompile_material(mat)
    LIB.set_metadata_tag(mat,'GHS.VisualPolish.Fingerprint',fingerprint)
    return mat,dict(path=mat.get_path_name(),reused=False,expressions=ML.get_num_material_expressions(mat),opaque=True,texture_samples=0 if role in ('CampusRoad','ContextRoad') else 1)

def main():
    config=read(CONFIG);assert config['map']==MAP and config['asset_root']==DEST
    levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actors_system=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    assert not levels.is_in_play_in_editor(),'Stop PIE first'
    assert unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world().get_path_name().split('.')[0]==MAP
    actors=actors_system.get_all_level_actors();by={a.get_actor_label():a for a in actors}
    assert len(by)==len(actors),'Ambiguous actor labels'
    assert set(ROLES).issubset(by)
    for label in ROLES:
        comps=by[label].get_components_by_class(unreal.StaticMeshComponent)
        assert len(comps)==1 and comps[0].get_num_materials()==1,label
        if label.startswith('GHSPark_'): assert comps[0].static_mesh.get_name()=='SM_'+label,label
    keys=[a.get_component_by_class(unreal.DirectionalLightComponent) for a in actors if a.get_component_by_class(unreal.DirectionalLightComponent)]
    skies=[a.get_component_by_class(unreal.SkyLightComponent) for a in actors if a.get_component_by_class(unreal.SkyLightComponent)]
    volumes=[a for a in actors if isinstance(a,unreal.PostProcessVolume)]
    assert len(keys)==len(skies)==len(volumes)==1
    key,sky,volume=keys[0],skies[0],volumes[0]
    pp=volume.get_editor_property('settings')
    assert pp.get_editor_property('dynamic_global_illumination_method')==unreal.DynamicGlobalIlluminationMethod.NONE
    assert pp.get_editor_property('reflection_method')==unreal.ReflectionMethod.NONE
    OUT.mkdir(parents=True,exist_ok=True)
    run=OUT/datetime.now().strftime('%Y%m%d-%H%M%S-%f');run.mkdir()
    disk_backup=run/'GHS_CAD_NormalWarehouse_ZcoolSmartFactory.before.umap'
    shutil.copy2(MAP_FILE,disk_backup)
    before=scene_snapshot(actors)
    write(run/'before_scene.json',before)
    # Also serialize unsaved map edits into a recoverable private map before
    # touching bindings. This preserves manual changes beyond the on-disk map.
    snapshot_path=DEST+'/Backups/Before_'+run.name.replace('-','_')
    assert LIB.duplicate_asset(MAP,snapshot_path), 'Could not back up in-memory map'
    assert LIB.save_asset(snapshot_path,only_if_is_dirty=False)
    initial_dirty=dirty()
    state=getattr(builtins,STATE,None)
    if state is None: state={'owned':set()};setattr(builtins,STATE,state)
    report=dict(success=False,map=MAP,run_directory=str(run),map_disk_backup=str(disk_backup),map_live_backup=snapshot_path,
        before_map_sha256=sha(MAP_FILE),bindings=[],materials=[],actor_count=len(actors),before_lighting=dict(key=values(key,LIGHT_NAMES),sky=values(sky,SKY_NAMES),pp=values(pp,PP_NAMES),heavy=values(pp,HEAVY_NAMES)))
    original_paths={package(m) for row in before for c in row['components'] for m in c['materials'] if m and m.startswith('/Game/') and not m.startswith(DEST+'/')}
    original_hashes={p:sha(asset_file(p)) for p in original_paths if asset_file(p).is_file()}
    report['protected_original_material_hashes']=original_hashes
    original_bindings=[]
    light_backup={name:key.get_editor_property(name) for name in LIGHT_NAMES}
    sky_backup={name:sky.get_editor_property(name) for name in SKY_NAMES}
    pp_backup=volume.get_editor_property('settings')
    camera=by['GHS_WarehouseCamera']
    camera_before=values(camera,['overview_center','overview_distance','overview_pitch','overview_yaw','maximum_pan'])
    camera_initial=OUT/'original_camera.json'
    if not camera_initial.exists():write(camera_initial,camera_before)
    camera_original=read(camera_initial)
    pitch_original=float(camera_original['overview_pitch'])
    pitch_target=-43. if abs(pitch_original+48.)<.001 else pitch_original+4.
    assert -65.<pitch_target<-20.,('Unexpected current camera pitch',pitch_original)
    report['camera_before']=camera_before
    report['camera_target_pitch']=pitch_target
    try:
        LIB.make_directory(DEST)
        mask=texture(config,state)
        ground=by['GHSPark_Ground'].get_component_by_class(unreal.StaticMeshComponent)
        xf=ground.get_world_transform();rotation=xf.rotation
        assert abs(rotation.x)+abs(rotation.y)+abs(rotation.z)<1e-5,'Rotated ground needs a reviewed plane calculation'
        bounds=ground.static_mesh.get_bounds()
        assert bounds.box_extent.z<.1,'Ground must be a flat plane'
        ground_z=xf.translation.z+bounds.origin.z*xf.scale3d.z
        land=by['GHSPark_Landscape'].get_component_by_class(unreal.StaticMeshComponent)
        lxf=land.get_world_transform()
        assert max(abs(lxf.translation.x),abs(lxf.translation.y),abs(lxf.translation.z),abs(lxf.rotation.x),abs(lxf.rotation.y),abs(lxf.rotation.z),abs(lxf.scale3d.x-1),abs(lxf.scale3d.y-1),abs(lxf.scale3d.z-1))<1e-5,'Landscape transform changed; do not classify forest vertices by Z'
        baseline_file=OUT/'original_surface_tints.json'
        if baseline_file.exists(): original_tints=read(baseline_file)
        else:
            original_tints={label:source_tint(by[label].get_component_by_class(unreal.StaticMeshComponent).get_material(0),[.47,.53,.48] if label=='GHSPark_Landscape' else [.53,.6,.68]) for label in ROLES}
            write(baseline_file,original_tints)
        for label,role in ROLES.items():
            component=by[label].get_component_by_class(unreal.StaticMeshComponent)
            old=component.get_material(0)
            mat,record=make_material(role,config,mask,original_tints[label],ground_z,state)
            original_bindings.append((component,old))
            component.set_material(0,mat)
            report['materials'].append(record)
            report['bindings'].append(dict(actor=label,component=component.get_name(),slot=0,before=old.get_path_name() if old else None,after=mat.get_path_name()))
        lighting=config['lighting']
        key.set_intensity(lighting['directional_intensity']);key.set_light_color(unreal.LinearColor(*lighting['directional_color'],1))
        key.set_editor_property('light_source_angle',lighting['directional_source_angle'])
        sky.set_intensity(lighting['skylight_intensity']);sky.set_light_color(unreal.LinearColor(*lighting['skylight_color'],1))
        for name in PP_NAMES:
            pp.set_editor_property('override_'+name,True);pp.set_editor_property(name,lighting[name])
        volume.set_editor_property('settings',pp)
        camera.set_editor_property('overview_pitch',pitch_target)
        camera_after=values(camera,['overview_center','overview_distance','overview_pitch','overview_yaw','maximum_pan'])
        camera_expected=dict(camera_before,overview_pitch=pitch_target)
        assert camera_after==camera_expected,'Unexpected camera setting change'
        assert values(volume.get_editor_property('settings'),HEAVY_NAMES)==report['before_lighting']['heavy']
        after=scene_snapshot(actors_system.get_all_level_actors())
        assert_preserved(before,after,report['bindings'])
        assert original_hashes=={p:sha(asset_file(p)) for p in original_hashes},'Original material changed'
        assert dirty()-state['owned']==initial_dirty-state['owned'],'Unrelated dirty content changed'
        for path in sorted(state['owned']): assert path.startswith(DEST+'/') and LIB.save_asset(path,only_if_is_dirty=False),path
        assert levels.save_current_level(),'Could not save target map'
        write(run/'after_scene.json',after)
        report.update(success=True,preserved_actor_count=len(after),all_actor_component_instance_transforms_preserved=True,
            original_material_assets_preserved=True,roof_and_dissolve_bindings_preserved=True,parking_and_curb_bindings_preserved=True,
            original_ground_transform=next(row['transform'] for row in before if row['label']=='GHSPark_Ground'),
            forest_pad_target_z_cm=ground_z+.12,material_texture_samples_max=1,
            camera_after=camera_after,camera_defaults_untouched=True,
            after_lighting=dict(key=values(key,LIGHT_NAMES),sky=values(sky,SKY_NAMES),pp=values(volume.get_editor_property('settings'),PP_NAMES),heavy=values(volume.get_editor_property('settings'),HEAVY_NAMES)),
            after_map_sha256=sha(MAP_FILE),saved_owned_assets=sorted(state['owned']),unrelated_dirty_content_preserved=sorted(initial_dirty-state['owned']))
    except Exception:
        report['error']=traceback.format_exc()
        for component,old in original_bindings: component.set_material(0,old)
        for name,value in light_backup.items(): key.set_editor_property(name,value)
        for name,value in sky_backup.items(): sky.set_editor_property(name,value)
        volume.set_editor_property('settings',pp_backup)
        camera.set_editor_property('overview_pitch',camera_before['overview_pitch'])
        report['bindings_and_lighting_restored_in_memory']=True
        unreal.log_error(report['error'])
    finally:
        report['finished_utc']=datetime.now(timezone.utc).isoformat();write(run/'report.json',report);write(OUT/'apply_report.json',report)
    assert report['success'],report.get('error')
    unreal.log('GHS_VISUAL_POLISH_APPLIED')

if __name__=='__main__': main()
