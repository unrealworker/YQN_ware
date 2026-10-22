"""Read and preserve the live map state before the roof/style addition."""
import hashlib
import json
from pathlib import Path
import runpy
import unreal

ROOT=Path('D:/UEPro/Test')
OUT=ROOT/'Saved/ParkRoofStyle'
MAP='/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert not levels.is_in_play_in_editor()
assert editor.get_editor_world().get_path_name().split('.')[0]==MAP
snapshot=runpy.run_path(str(ROOT/'Scripts/ghs/validate_park_expansion.py'))['snapshot']

def properties(obj,names):
    result={}
    for name in names:
        value=obj.get_editor_property(name)
        result[name]=value if isinstance(value,(str,float,int,bool,type(None))) else str(value)
    return result

state=dict(map=MAP,actors=[],lights=[],post_process=[],dirty_assets=[p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()])
for actor in actors.get_all_level_actors():
    state['actors'].append(snapshot(actor,unreal))
    direction=actor.get_component_by_class(unreal.DirectionalLightComponent)
    sky=actor.get_component_by_class(unreal.SkyLightComponent)
    if direction:
        state['lights'].append(dict(label=actor.get_actor_label(),kind='directional',values=properties(direction,
            ['intensity','light_color','light_source_angle','contact_shadow_length','cast_shadows'])))
    if sky:
        state['lights'].append(dict(label=actor.get_actor_label(),kind='sky',values=properties(sky,
            ['intensity','light_color','source_type','cubemap','real_time_capture'])))
    if isinstance(actor,unreal.PostProcessVolume):
        state['post_process'].append(dict(label=actor.get_actor_label(),values=properties(actor.get_editor_property('settings'),
            ['ambient_occlusion_intensity','ambient_occlusion_radius','ambient_occlusion_quality','bloom_intensity',
             'auto_exposure_min_brightness','auto_exposure_max_brightness','auto_exposure_bias','vignette_intensity'])))
state['actors'].sort(key=lambda r:r['label'])
state['map_sha256']=hashlib.sha256((ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap').read_bytes()).hexdigest()
path=OUT/'Before/scene_state.json'
if path.exists():path=OUT/'scene_state_latest.json'
path.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
unreal.log('GHS_ROOF_STYLE_INSPECTED')
