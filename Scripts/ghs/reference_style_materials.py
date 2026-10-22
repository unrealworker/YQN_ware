"""Apply reference palette/light values without rebuilding or saving the map.

Only the explicitly whitelisted materials and two ground component bindings
are changed. Preview calls keep changes in memory; a final apply may save the
owned material assets. Existing dirty user materials, including Truck assets,
are protected. Call apply(style, save_assets=False) for lighting previews.
"""
from pathlib import Path
import builtins
import hashlib
import math
import shutil

import unreal

ROOT=Path('D:/UEPro/Test')
MAP='/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
PARK='/Game/GHSZcoolSmartFactory/Park/Materials'
ROOF='/Game/GHSZcoolSmartFactory/Roof/Materials/M_GHSRoof_Roof'
BACKDROP='/Game/GHSZcoolSmartFactory/Presentation/M_GHSReference_Backdrop'
BACKUPS=ROOT/'Saved/ParkReferenceStyle/Before/Assets'
ROLES={'Ground','Hardstand','Roads','ContextRoads','CampusRoads','Curbs',
       'Markings','Buildings','Roofs','Landscape','Trees','TreesLight','TreesDark','Trunk'}
ROUGHNESS={'Ground':.9,'Landscape':.9,'Hardstand':.9,'CampusRoads':.9,
           'Roads':.92,'ContextRoads':.92,'Trees':.86,'TreesDark':.86,'TreesLight':.86,
           'Curbs':.82,'Buildings':.82,'Roofs':.82,'Markings':.82,'Trunk':.9}
STATE_NAME='_ghs_reference_style_materials_state_v1'
LIB=unreal.EditorAssetLibrary
ML=unreal.MaterialEditingLibrary


def _package(path):
    return str(path).split('.',1)[0]


def _close(actual,expected,tolerance=1e-5):
    assert abs(float(actual)-float(expected))<tolerance,(actual,expected)


def _color(values):
    assert isinstance(values,(list,tuple)) and len(values)==3,values
    result=[float(v) for v in values]
    assert all(math.isfinite(v) and 0<=v<=1 for v in result),values
    return result


def _scalar(value,minimum=0.,maximum=100000.):
    value=float(value)
    assert math.isfinite(value) and minimum<=value<=maximum,value
    return value


def _dirty():
    return {p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()}


def _transform(actor):
    t=actor.get_actor_transform()
    return dict(location=[float(t.translation.x),float(t.translation.y),float(t.translation.z)],
                rotation=[float(t.rotation.x),float(t.rotation.y),float(t.rotation.z),float(t.rotation.w)],
                scale=[float(t.scale3d.x),float(t.scale3d.y),float(t.scale3d.z)])


def _values(obj,names):
    result={}
    for name in names:
        value=obj.get_editor_property(name)
        if isinstance(value,(bool,str,int,float,type(None))):result[name]=value
        elif all(hasattr(value,k) for k in ('r','g','b')):
            result[name]=[value.r,value.g,value.b,getattr(value,'a',1)]
        else:result[name]=str(value)
    return result


def _backup(package):
    """Keep the first on-disk version; never replace an existing backup."""
    assert package.startswith('/Game/')
    source=ROOT/'Content'/(package.removeprefix('/Game/')+'.uasset')
    assert source.resolve().is_relative_to((ROOT/'Content').resolve())
    if not source.is_file():return dict(existed=False,path=str(source))
    destination=BACKUPS/'Content'/source.relative_to(ROOT/'Content')
    destination.parent.mkdir(parents=True,exist_ok=True)
    if not destination.exists():shutil.copy2(source,destination)
    return dict(existed=True,path=str(destination),sha256=hashlib.sha256(destination.read_bytes()).hexdigest())


def _matches(mat,color,roughness,metallic,specular):
    if ML.get_num_material_expressions(mat)!=4:return False
    if mat.get_editor_property('blend_mode')!=unreal.BlendMode.BLEND_OPAQUE:return False
    if mat.get_editor_property('shading_model')!=unreal.MaterialShadingModel.MSM_DEFAULT_LIT:return False
    tint=ML.get_material_default_vector_parameter_value(mat,'SurfaceTint')
    if max(abs(a-b) for a,b in zip((tint.r,tint.g,tint.b),color))>=1e-5:return False
    return all(abs(ML.get_material_default_scalar_parameter_value(mat,name)-value)<1e-5
               for name,value in [('Roughness',roughness),('Metallic',metallic),('Specular',specular)])


def _material(package,color,roughness,metallic,state,save_assets):
    folder,name=package.rsplit('/',1)
    existed=LIB.does_asset_exist(package)
    mat=LIB.load_asset(package) if existed else None
    assert mat is None or isinstance(mat,unreal.Material),package
    matches=mat is not None and _matches(mat,color,roughness,metallic,.15)
    # Establish ownership before mutation so a failure can be retried without
    # treating our own dirty asset as an unrelated user edit.
    state['owned'].add(package)
    if mat is None:
        LIB.make_directory(folder)
        mat=unreal.AssetToolsHelpers.get_asset_tools().create_asset(name,folder,unreal.Material,unreal.MaterialFactoryNew())
        assert mat,package
    if not matches:
        while ML.get_num_material_expressions(mat):
            previous=ML.get_num_material_expressions(mat)
            ML.delete_all_material_expressions(mat)
            assert ML.get_num_material_expressions(mat)<previous,(package,'Could not clear old material parameters')
        mat.set_editor_property('blend_mode',unreal.BlendMode.BLEND_OPAQUE)
        mat.set_editor_property('shading_model',unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
        tint=ML.create_material_expression(mat,unreal.MaterialExpressionVectorParameter)
        tint.set_editor_property('parameter_name','SurfaceTint')
        tint.set_editor_property('default_value',unreal.LinearColor(*color,1.))
        assert ML.connect_material_property(tint,'',unreal.MaterialProperty.MP_BASE_COLOR)
        for label,value,prop in [('Roughness',roughness,unreal.MaterialProperty.MP_ROUGHNESS),
                                  ('Metallic',metallic,unreal.MaterialProperty.MP_METALLIC),
                                  ('Specular',.15,unreal.MaterialProperty.MP_SPECULAR)]:
            node=ML.create_material_expression(mat,unreal.MaterialExpressionScalarParameter)
            node.set_editor_property('parameter_name',label)
            node.set_editor_property('default_value',value)
            assert ML.connect_material_property(node,'',prop)
        ML.recompile_material(mat)
    assert _matches(mat,color,roughness,metallic,.15),(package,'Material parameter cache differs from requested values')
    # A reused preview material still needs saving when the caller commits the
    # final candidate. Never call SaveAllAssets or save any unrelated package.
    saved=False
    if save_assets and (not matches or package in _dirty()):
        assert LIB.save_loaded_asset(mat,only_if_is_dirty=False),package
        saved=True
    return mat,dict(path=mat.get_path_name(),color_linear=color,roughness=roughness,
                    metallic=metallic,specular=.15,reused=matches,saved=saved,
                    expressions=ML.get_num_material_expressions(mat))


def apply(style:dict,save_assets:bool=True)->dict:
    assert isinstance(style,dict) and isinstance(save_assets,bool)
    palette=style['palette']
    assert isinstance(palette,dict) and set(palette).issubset(ROLES),set(palette)-ROLES
    assert 'Ground' in palette,'Ground must be supplied for the separate backdrop'
    colors={role:_color(value) for role,value in palette.items()}
    roof_color=_color(style['roof_color_linear'])
    lighting=style['lighting']
    ground_path=PARK+'/M_GHSPark_Ground'
    assert _package(style.get('ground_material',ground_path))==ground_path
    assert _package(style.get('studio_ground_material',BACKDROP))==BACKDROP
    targets={PARK+'/M_GHSPark_'+role for role in palette}|{ROOF,BACKDROP}
    levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    assert not levels.is_in_play_in_editor(),'Exit PIE before applying the reference style'
    assert editor.get_editor_world().get_path_name().split('.')[0]==MAP
    actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
    by={a.get_actor_label():a for a in actors}
    assert len(by)==len(actors),'Ambiguous actor labels'
    components={}
    for label in ('GHSPark_Ground','GHN_StudioGround'):
        actor=by[label]
        meshes=actor.get_components_by_class(unreal.StaticMeshComponent)
        assert len(meshes)==1,(label,'Expected exactly one ground component')
        components[label]=meshes[0]
    keys=[a for a in actors if a.get_component_by_class(unreal.DirectionalLightComponent)]
    skies=[a for a in actors if a.get_component_by_class(unreal.SkyLightComponent)]
    volumes=[a for a in actors if isinstance(a,unreal.PostProcessVolume)]
    assert len(keys)==len(skies)==len(volumes)==1,'Keep exactly the existing key, sky and post-process volume'
    key_actor,sky_actor,pp_actor=keys[0],skies[0],volumes[0]
    key=key_actor.get_component_by_class(unreal.DirectionalLightComponent)
    sky=sky_actor.get_component_by_class(unreal.SkyLightComponent)
    settings=pp_actor.get_editor_property('settings')
    heavy_names=('override_dynamic_global_illumination_method','dynamic_global_illumination_method',
                 'override_reflection_method','reflection_method')
    heavy_before=_values(settings,heavy_names)
    assert settings.get_editor_property('override_dynamic_global_illumination_method')
    assert settings.get_editor_property('dynamic_global_illumination_method')==unreal.DynamicGlobalIlluminationMethod.NONE
    assert settings.get_editor_property('override_reflection_method')
    assert settings.get_editor_property('reflection_method')==unreal.ReflectionMethod.NONE
    assert _scalar(lighting.get('exposure_ev100',0),-10,20)==0,'This module keeps the approved locked EV0'
    rotation=[float(v) for v in lighting['directional_rotation']]
    assert len(rotation)==3 and all(math.isfinite(v) for v in rotation)
    key_color=_color(lighting['directional_color']);sky_color=_color(lighting['skylight_color'])
    hemisphere=_color(lighting['lower_hemisphere_color'])
    key_intensity=_scalar(lighting['directional_intensity'])
    sky_intensity=_scalar(lighting['skylight_intensity'])
    source_angle=_scalar(lighting['directional_source_angle'],0,90)
    pp_values=dict(ambient_occlusion_intensity=_scalar(lighting['ambient_occlusion_intensity'],0,5),
        ambient_occlusion_radius=_scalar(lighting['ambient_occlusion_radius_cm'],0,10000),
        ambient_occlusion_quality=_scalar(lighting.get('ambient_occlusion_quality',80),0,100),
        bloom_intensity=_scalar(lighting.get('bloom_intensity',0),0,100),
        auto_exposure_min_brightness=0.,auto_exposure_max_brightness=0.,auto_exposure_bias=0.)
    dirty_before=_dirty()
    # Store ownership on builtins so importlib.reload / runpy preview invocations
    # in the same UE Python process do not discard ownership of our dirty assets.
    state=getattr(builtins,STATE_NAME,None)
    if state is None:
        state=dict(initial_dirty=set(dirty_before),owned=set())
        setattr(builtins,STATE_NAME,state)
    assert not targets.intersection(state['initial_dirty']),('Target materials already have user edits',sorted(targets.intersection(state['initial_dirty'])))
    assert not (targets.intersection(dirty_before)-state['owned']),('Target materials have new unrelated edits',sorted(targets.intersection(dirty_before)-state['owned']))
    backups={path:_backup(path) for path in sorted(targets)}
    bindings=[]
    for label,component in components.items():
        material=component.get_material(0)
        bindings.append(dict(actor=label,component=component.get_name(),
            before=material.get_path_name() if material else None,transform_before=_transform(by[label])))
    light_names=('intensity','light_color','light_source_angle','cast_shadows')
    sky_names=('intensity','light_color','source_type','cubemap','real_time_capture',
               'lower_hemisphere_is_black','lower_hemisphere_color','cast_shadows')
    before=dict(directional=_values(key,light_names),directional_transform=_transform(key_actor),
                skylight=_values(sky,sky_names),post_process=_values(settings,pp_values.keys()),
                heavy_post_process=heavy_before)
    report=dict(materials={},bindings=bindings,lighting_before=before,backups=backups,
                save_assets=save_assets,map_saved=False,actor_count=len(actors))
    mats={}
    for role,color in colors.items():
        path=PARK+'/M_GHSPark_'+role
        mats[role],record=_material(path,color,ROUGHNESS[role],0.,state,save_assets)
        report['materials'][role]=record
    _,record=_material(ROOF,roof_color,.75,.08,state,save_assets)
    report['materials']['MainRoof']=record
    backdrop,record=_material(BACKDROP,colors['Ground'],.9,0.,state,save_assets)
    report['materials']['Backdrop']=record
    for label,mat in [('GHSPark_Ground',mats['Ground']),('GHN_StudioGround',backdrop)]:
        components[label].set_material(0,mat)
    for binding in bindings:
        label=binding['actor'];component=components[label]
        binding['after']=component.get_material(0).get_path_name()
        binding['transform_after']=_transform(by[label])
        assert binding['transform_after']==binding['transform_before'],(label,'Ground transform changed')
    key.set_intensity(key_intensity)
    key.set_light_color(unreal.LinearColor(*key_color,1.))
    key.set_editor_property('light_source_angle',source_angle)
    key_actor.set_actor_rotation(unreal.Rotator(pitch=rotation[0],yaw=rotation[1],roll=rotation[2]),False)
    sky.set_intensity(sky_intensity)
    sky.set_light_color(unreal.LinearColor(*sky_color,1.))
    sky.set_editor_property('lower_hemisphere_is_black',bool(lighting.get('lower_hemisphere_is_black',True)))
    sky.set_editor_property('lower_hemisphere_color',unreal.LinearColor(*hemisphere,1.))
    recapture=getattr(sky,'recapture_sky',None)
    if callable(recapture):recapture()
    for name,value in pp_values.items():
        settings.set_editor_property('override_'+name,True)
        settings.set_editor_property(name,value)
    pp_actor.set_editor_property('settings',settings)
    settings=pp_actor.get_editor_property('settings')
    assert _values(settings,heavy_names)==heavy_before,'GI/reflection settings changed'
    for name,value in pp_values.items():_close(settings.get_editor_property(name),value)
    _close(key.get_editor_property('intensity'),key_intensity)
    _close(key.get_editor_property('light_source_angle'),source_angle)
    _close(sky.get_editor_property('intensity'),sky_intensity)
    assert sky.get_editor_property('lower_hemisphere_is_black')==bool(lighting.get('lower_hemisphere_is_black',True))
    actual_hemisphere=sky.get_editor_property('lower_hemisphere_color')
    for actual,expected in zip((actual_hemisphere.r,actual_hemisphere.g,actual_hemisphere.b),hemisphere):_close(actual,expected)
    actual_rotation=key_actor.get_actor_rotation()
    for actual,expected in zip((actual_rotation.pitch,actual_rotation.yaw,actual_rotation.roll),rotation):
        _close((actual-expected+180)%360-180,0.,1e-4)
    assert _dirty()-state['owned']==dirty_before-state['owned'],'Unrelated dirty packages changed'
    assert len(unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors())==len(actors)
    report.update(success=True,lighting_applied=dict(directional_intensity=key_intensity,
        directional_color=key_color,directional_rotation=rotation,directional_source_angle=source_angle,
        skylight_intensity=sky_intensity,skylight_color=sky_color,lower_hemisphere_color=hemisphere,
        lower_hemisphere_is_black=bool(lighting.get('lower_hemisphere_is_black',True)),post_process=pp_values),
        lighting_after=dict(directional=_values(key,light_names),directional_transform=_transform(key_actor),
            skylight=_values(sky,sky_names),post_process=_values(settings,pp_values.keys()),heavy_post_process=_values(settings,heavy_names)),
        recaptured_skylight=callable(recapture),unrelated_dirty_assets_preserved=sorted(dirty_before-state['owned']),
        owned_dirty_assets=sorted(_dirty().intersection(state['owned'])))
    return report
