"""Capture one corrected pillar at close range, restoring the saved camera."""
import json
import time
import traceback
from pathlib import Path
import unreal

ROOT=Path(r'D:\UEPro\Test')
data=json.loads((ROOT/'SourceAssets/GHS/clearance_layout.json').read_text())
row=next(c for c in data['columns'] if c['id']==data['blocked_storage'][0]['blocking_column_ids'][0])
actor_system=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
camera=next(a for a in actor_system.get_all_level_actors() if a.get_actor_label()=='CAM_GHS_FloorStorage')
original_transform=camera.get_actor_transform()
target=unreal.Vector(row['position_m'][0]*100,-row['position_m'][1]*100,110)
position=target+unreal.Vector(760,980,800)
rotation=unreal.MathLibrary.find_look_at_rotation(position,target)
camera.set_actor_location_and_rotation(position,rotation,False,True)
editor.set_level_viewport_camera_info(position,rotation)
output=ROOT/'Saved/GHS_Clearance_UE_ColumnDetail.png'
capture_task=unreal.AutomationLibrary.take_high_res_screenshot(2400,1600,str(output),camera=camera,delay=.5)
started=time.monotonic()
done=False
handle=None
def tick(delta):
    global done
    if done:return
    if not capture_task.is_task_done() and time.monotonic()-started<60:return
    done=True
    error=None
    try:
        assert capture_task.is_task_done() and output.is_file(),'Column detail capture timed out'
    except Exception:error=traceback.format_exc()
    finally:
        camera.set_actor_transform(original_transform,False,True)
        unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
        unreal.unregister_slate_post_tick_callback(handle)
    (ROOT/'Saved/GHS_ColumnDetailCapture.json').write_text(json.dumps(dict(success=error is None,error=error,path=str(output),column=row['id'],camera_restored=True)))
handle=unreal.register_slate_post_tick_callback(tick)
