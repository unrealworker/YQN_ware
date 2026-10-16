"""Map-local constant ambient light with one inexpensive directional key."""
import json
from pathlib import Path
import unreal
ROOT=Path(r'D:\UEPro\Test')

def configure():
    style=json.loads((ROOT/'SourceAssets/GHS/lighting_style.json').read_text())
    actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    assert editor.get_editor_world().get_path_name().split('.')[0]=='/Game/Maps/GHS_CAD_DigitalTwin'
    existing=actors.get_all_level_actors()
    key=next((a for a in existing if isinstance(a,unreal.DirectionalLight)),None)
    assert key,'Expected original approved directional light'
    sky=next((a for a in existing if isinstance(a,unreal.SkyLight)),None)
    if sky is None:
        sky=actors.spawn_actor_from_class(unreal.SkyLight,unreal.Vector(0,0,2000))
    cube=unreal.load_asset(style['skylight_cubemap'])
    assert isinstance(cube,unreal.TextureCube), 'Uniform engine cubemap missing'
    key.set_actor_label('GHS_CoolOverheadKey');key.set_folder_path('GHS/Environment/Lights')
    dc=key.get_component_by_class(unreal.DirectionalLightComponent)
    dc.set_mobility(unreal.ComponentMobility.MOVABLE)
    dc.set_intensity(style['directional_intensity'])
    if 'directional_rotation' in style:
        p,y,r=style['directional_rotation']
        key.set_actor_rotation(unreal.Rotator(pitch=p,yaw=y,roll=r),False)
    if 'directional_color' in style:
        dc.set_light_color(unreal.LinearColor(*style['directional_color'],1.0))
    dc.set_editor_property('cast_shadows',style.get('directional_cast_shadows',False))
    dc.set_editor_property('light_source_angle',style.get('directional_source_angle',.5357))
    dc.set_editor_property('volumetric_scattering_intensity',0.0)
    sky.set_actor_label('GHS_UniformAmbient');sky.set_folder_path('GHS/Environment/Lights')
    sc=sky.get_component_by_class(unreal.SkyLightComponent)
    sc.set_mobility(unreal.ComponentMobility.MOVABLE)
    sc.set_editor_property('source_type',unreal.SkyLightSourceType.SLS_SPECIFIED_CUBEMAP)
    sc.set_editor_property('real_time_capture',False)
    sc.set_editor_property('cubemap_resolution',64)
    sc.set_editor_property('lower_hemisphere_is_black',False)
    sc.set_editor_property('cast_shadows',False)
    sc.set_editor_property('volumetric_scattering_intensity',0.0)
    sc.set_cubemap(cube)
    sc.set_light_color(unreal.LinearColor(*style['skylight_color'],1.0))
    sc.set_intensity(style['skylight_intensity'])
    volumes=[a for a in existing if isinstance(a,unreal.PostProcessVolume)]
    assert len(volumes)==1
    pp=volumes[0];pp.set_actor_label('GHS_ApprovedDigitalTwinLook');pp.set_folder_path('GHS/Environment')
    pp.set_editor_property('unbound',True)
    settings=pp.get_editor_property('settings')
    changes=dict(dynamic_global_illumination_method=unreal.DynamicGlobalIlluminationMethod.NONE,
        reflection_method=unreal.ReflectionMethod.NONE, vignette_intensity=0.0,
        ambient_occlusion_intensity=style['ambient_occlusion_intensity'],
        ambient_occlusion_radius=style['ambient_occlusion_radius_cm'],
        ambient_occlusion_quality=style['ambient_occlusion_quality'],
        auto_exposure_min_brightness=0.0,auto_exposure_max_brightness=0.0,auto_exposure_bias=0.0)
    for name,value in changes.items():
        settings.set_editor_property('override_'+name,True)
        settings.set_editor_property(name,value)
    pp.set_editor_property('settings',settings)
    removed=[]
    for actor in existing:
        if isinstance(actor,(unreal.Light,unreal.SkyLight)) and actor not in (key,sky):
            removed.append(actor.get_actor_label())
            assert actors.destroy_actor(actor)
    return dict(removed_lights=removed,skylight=dict(intensity=style['skylight_intensity'],
        cubemap=cube.get_path_name(),real_time_capture=False,cast_shadows=False,color=style['skylight_color']),
        directional=dict(intensity=style['directional_intensity'],cast_shadows=style.get('directional_cast_shadows',False)),
        post_process={k:str(v) if not isinstance(v,(float,int,bool)) else v for k,v in changes.items()})
