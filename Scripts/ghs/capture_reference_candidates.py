"""Compare three real UE light balances at the reference camera."""
import copy
import importlib
import json
from pathlib import Path
import sys
import time
import traceback
import unreal
ROOT=Path('D:/UEPro/Test');OUT=ROOT/'Saved/ParkReferenceStyle'
sys.path.insert(0,str(ROOT/'Scripts/ghs'))
import reference_style_materials
importlib.reload(reference_style_materials)
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert not levels.is_in_play_in_editor()
by={a.get_actor_label():a for a in actors.get_all_level_actors()}
camera=by['GHSPark_Yard'];original=camera.get_actor_transform()
view=editor.get_level_viewport_camera_info();selection=actors.get_selected_level_actors()
gameview=levels.editor_get_game_view();levels.editor_set_game_view(True);actors.set_selected_level_actors([])
performance=unreal.get_default_object(unreal.load_class(None,'/Script/UnrealEd.EditorPerformanceSettings'))
throttle=performance.get_editor_property('bThrottleCPUWhenNotForeground')
performance.set_editor_property('bThrottleCPUWhenNotForeground',False)
base=json.loads((ROOT/'SourceAssets/GHS/Park/reference_style.json').read_text(encoding='utf-8'))
variants=[('Reference_A',3.6,.46,8.),('Reference_B',3.0,.50,10.),('Reference_C',3.8,.34,8.)]
report=dict(success=False,captures=[]);task=pending=handle=None;index=0;done=busy=False;started=time.monotonic()
def write(): (OUT/'candidate_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
def finish(error=None):
    global done
    if done:return
    done=True
    try:
        if handle:unreal.unregister_slate_post_tick_callback(handle)
        reference_style_materials.apply(base,save_assets=False)
        camera.set_actor_transform(original,False,True);editor.set_level_viewport_camera_info(*view)
        actors.set_selected_level_actors(selection);levels.editor_set_game_view(gameview)
        performance.set_editor_property('bThrottleCPUWhenNotForeground',throttle)
    except Exception:error=(error+'\n' if error else '')+traceback.format_exc()
    finally:
        report.update(success=error is None,error=error,elapsed=time.monotonic()-started,assets_saved=False)
        write()
def tick(dt):
    global busy,task,pending,index
    if busy or done:return
    busy=True
    try:
        assert time.monotonic()-started<180
        if task:
            if not task.is_task_done():return
            if not pending['path'].exists() or pending['path'].stat().st_mtime_ns==pending['old']:return
            report['captures'].append(dict(name=pending['name'],path=str(pending['path']),lighting=pending['lighting']))
            task=pending=None;write()
        if index==len(variants):finish();return
        name,key,sky,angle=variants[index];index+=1
        style=copy.deepcopy(base)
        style['lighting'].update(directional_intensity=key,skylight_intensity=sky,directional_source_angle=angle)
        reference_style_materials.apply(style,save_assets=False)
        ref=style['reference_camera'];uv=ref['target_uv_m']
        target=unreal.Vector((uv[0]-239.33385)*100,(uv[1]-60.24019)*100,uv[2]*100)
        rotation=unreal.Rotator(pitch=ref['pitch'],yaw=ref['yaw'])
        eye=target-unreal.MathLibrary.get_forward_vector(rotation)*ref['distance_cm']
        camera.set_actor_location_and_rotation(eye,rotation,False,True);editor.set_level_viewport_camera_info(eye,rotation)
        path=OUT/(name+'.png');pending=dict(name=name,path=path,lighting=style['lighting'],old=path.stat().st_mtime_ns if path.exists() else 0)
        task=unreal.AutomationLibrary.take_high_res_screenshot(1920,1080,str(path),camera=camera,delay=4.)
        assert task
    except Exception:finish(traceback.format_exc())
    finally:busy=False
write();handle=unreal.register_slate_post_tick_callback(tick)
