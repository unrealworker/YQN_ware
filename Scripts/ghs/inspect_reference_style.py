"""Read actual scene rendering state before the reference-matching revision."""
import json
from pathlib import Path
import runpy
import unreal
ROOT=Path('D:/UEPro/Test');OUT=ROOT/'Saved/ParkReferenceStyle'
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert not levels.is_in_play_in_editor()
assert 'ZcoolSmartFactory' in editor.get_editor_world().get_path_name()
fn=runpy.run_path(str(ROOT/'Scripts/ghs/validate_park_expansion.py'))['snapshot']
def values(obj,names):
    result={}
    for name in names:
        try:
            v=obj.get_editor_property(name)
            if isinstance(v,(str,int,float,bool,type(None))):result[name]=v
            elif hasattr(v,'r'):result[name]=[v.r,v.g,v.b,v.a]
            else:result[name]=str(v)
        except Exception as error:result[name]=dict(unavailable=str(error))
    return result
result=dict(actors=[],lights=[],post_process=[],cvars={})
for actor in actors.get_all_level_actors():
    result['actors'].append(fn(actor,unreal))
    light=actor.get_component_by_class(unreal.DirectionalLightComponent)
    sky=actor.get_component_by_class(unreal.SkyLightComponent)
    if light or sky:
        component=light or sky
        rotation=actor.get_actor_rotation()
        result['lights'].append(dict(label=actor.get_actor_label(),kind='directional' if light else 'sky',
            rotation=[rotation.pitch,rotation.yaw,rotation.roll],values=values(component,
            ['intensity','light_color','cast_shadows','mobility','light_source_angle','contact_shadow_length'] if light else
            ['intensity','light_color','cast_shadows','source_type','lower_hemisphere_is_black','lower_hemisphere_color','real_time_capture'])))
    if isinstance(actor,unreal.PostProcessVolume):
        result['post_process'].append(dict(label=actor.get_actor_label(),values=values(actor.get_editor_property('settings'),
            ['dynamic_global_illumination_method','reflection_method','auto_exposure_method',
             'auto_exposure_min_brightness','auto_exposure_max_brightness','auto_exposure_bias',
             'ambient_occlusion_intensity','ambient_occlusion_radius','ambient_occlusion_quality','bloom_intensity',
             'local_exposure_highlight_contrast_scale','local_exposure_shadow_contrast_scale'])))
for name in ['r.Shadow.Virtual.Enable','r.Shadow.Virtual.SMRT.RayCountDirectional','r.Shadow.Virtual.SMRT.SamplesPerRayDirectional',
             'r.AmbientOcclusionLevels','sg.ShadowQuality','sg.PostProcessQuality']:
    result['cvars'][name]=unreal.SystemLibrary.get_console_variable_int_value(name)
result['actors'].sort(key=lambda r:r['label'])
result['dirty_assets']=[p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()]
path=OUT/'Before/scene_state.json'
if path.exists():path=OUT/'scene_state_latest.json'
path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
