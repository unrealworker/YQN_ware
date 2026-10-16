"""Read current lights, post process and user viewport before lighting changes."""
import json
from pathlib import Path
import unreal
root=Path(r'D:\UEPro\Test')
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert editor.get_editor_world().get_path_name().split('.')[0]=='/Game/Maps/GHS_CAD_DigitalTwin'
def vector(v):return [float(v.x),float(v.y),float(v.z)]
def properties(obj,names):
    result={}
    for name in names:
        try:
            value=obj.get_editor_property(name)
            result[name]=value if isinstance(value,(str,float,int,bool,type(None))) else str(value)
        except Exception as exc:result[name]='Unavailable: '+str(exc)
    return result
p,r=editor.get_level_viewport_camera_info()
result=dict(viewport=dict(position_cm=vector(p),rotation=[r.pitch,r.yaw,r.roll]),lights=[],post_process=[])
for actor in actors.get_all_level_actors():
    if isinstance(actor,(unreal.Light,unreal.SkyLight)):
        component=actor.get_component_by_class(unreal.LightComponentBase)
        result['lights'].append(dict(label=actor.get_actor_label(),type=actor.get_class().get_name(),position_cm=vector(actor.get_actor_location()),rotation=str(actor.get_actor_rotation()),properties=properties(component,['intensity','light_color','mobility','cast_shadows','cast_dynamic_shadows','affect_dynamic_indirect_lighting','volumetric_scattering_intensity','visible','attenuation_radius','source_width','source_height','source_type','cubemap','real_time_capture'])))
    if isinstance(actor,unreal.PostProcessVolume):
        settings=actor.get_editor_property('settings')
        result['post_process'].append(dict(label=actor.get_actor_label(),unbound=actor.get_editor_property('unbound'),settings=properties(settings,['dynamic_global_illumination_method','reflection_method','auto_exposure_method','auto_exposure_min_brightness','auto_exposure_max_brightness','auto_exposure_bias','vignette_intensity','ambient_occlusion_intensity','ambient_occlusion_radius','ambient_occlusion_quality','bloom_intensity','local_exposure_highlight_contrast_scale','local_exposure_shadow_contrast_scale'])))
(root/'Saved/GHS_LightingBefore.json').write_text(json.dumps(result,indent=2))
