"""Render campus views in the live editor; restore its view and do not save."""
import json
import struct
import time
import traceback
from pathlib import Path
import unreal

ROOT=Path('D:/UEPro/Test')
OUT=ROOT/'Saved/ParkExpansion'
EDITOR=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
ACTORS=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
LEVELS=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assert not LEVELS.is_in_play_in_editor()
assert 'ZcoolSmartFactory' in EDITOR.get_editor_world().get_name()
original_view=EDITOR.get_level_viewport_camera_info()
original_selection=ACTORS.get_selected_level_actors()
original_game_view=LEVELS.editor_get_game_view()
LEVELS.editor_set_game_view(True)
views=[]
by={a.get_actor_label():a for a in ACTORS.get_all_level_actors()}
for name in ['Overview','Yard','SitePlan']:
    views.append((name,by['GHSPark_'+name]))
ACTORS.set_selected_level_actors([])
performance=unreal.get_default_object(unreal.load_class(None,'/Script/UnrealEd.EditorPerformanceSettings'))
throttle=performance.get_editor_property('bThrottleCPUWhenNotForeground')
performance.set_editor_property('bThrottleCPUWhenNotForeground',False)
started=time.monotonic()
task=pending=handle=None
index=0
done=False
busy=False
result=dict(success=False,captures=[],assets_saved=False)

def write(): (OUT/'capture_report.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
def finish(error=None):
    global done
    if done:return
    done=True
    if handle:unreal.unregister_slate_post_tick_callback(handle)
    EDITOR.set_level_viewport_camera_info(*original_view)
    ACTORS.set_selected_level_actors(original_selection)
    LEVELS.editor_set_game_view(original_game_view)
    performance.set_editor_property('bThrottleCPUWhenNotForeground',throttle)
    result.update(success=error is None,error=error,elapsed=time.monotonic()-started)
    write()
    unreal.log('GHS_PARK_CAPTURE_COMPLETE' if not error else 'GHS_PARK_CAPTURE_FAILED '+error)

def tick(dt):
    global index,task,pending,busy
    if done or busy:return
    busy=True
    try:
        assert time.monotonic()-started<240,'Capture timeout'
        if task:
            if not task.is_task_done():return
            path=pending['path']
            if not path.exists() or path.stat().st_mtime_ns==pending['old']:return
            head=path.read_bytes()[:24]
            assert head[:8]==b'\x89PNG\r\n\x1a\n'
            assert struct.unpack('>II',head[16:24])==(1920,1080)
            result['captures'].append(dict(view=pending['name'],path=str(path),bytes=path.stat().st_size))
            task=pending=None
            write()
        if index==len(views):finish();return
        name,camera=views[index];index+=1
        EDITOR.set_level_viewport_camera_info(camera.get_actor_location(),camera.get_actor_rotation())
        path=OUT/(name+'.png')
        pending=dict(name=name,path=path,old=path.stat().st_mtime_ns if path.exists() else 0)
        task=unreal.AutomationLibrary.take_high_res_screenshot(1920,1080,str(path),camera=camera,delay=2.)
        assert task
    except Exception:finish(traceback.format_exc())
    finally:busy=False

write()
handle=unreal.register_slate_post_tick_callback(tick)
