"""Compare wall joints from the user's original viewport; restore saved camera."""
import json,time,traceback
from pathlib import Path
import unreal
ROOT=Path(r'D:\UEPro\Test')
phase=(ROOT/'Saved/GHS_WallCapturePhase.txt').read_text().strip()
assert phase in ['Before','After']
before=json.loads((ROOT/'Saved/GHS_WallEdgeLiveBefore.json').read_text())
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
camera=next(a for a in actors.get_all_level_actors() if a.get_actor_label()=='CAM_GHS_FloorStorage')
original=camera.get_actor_transform();component=camera.get_component_by_class(unreal.CameraComponent)
fov=component.get_editor_property('field_of_view')
view=before['viewport'];position=unreal.Vector(*view['position_cm']);rot=view['rotation']
rotation=unreal.Rotator(pitch=rot[0],yaw=rot[1],roll=rot[2])
camera.set_actor_location_and_rotation(position,rotation,False,True)
component.set_editor_property('field_of_view',70)
editor.set_level_viewport_camera_info(position,rotation)
actors.set_selected_level_actors([])
path=ROOT/'Saved'/('GHS_WallJoints_'+phase+'.png')
task=unreal.AutomationLibrary.take_high_res_screenshot(2400,1600,str(path),camera=camera,delay=1)
started=time.monotonic();done=False;handle=None
def tick(delta):
    global done
    if done:return
    if not task.is_task_done() and time.monotonic()-started<60:return
    done=True;error=None
    try:assert task.is_task_done() and path.is_file(),'Wall screenshot timed out'
    except Exception:error=traceback.format_exc()
    finally:
        camera.set_actor_transform(original,False,True)
        component.set_editor_property('field_of_view',fov)
        unreal.unregister_slate_post_tick_callback(handle)
    (ROOT/'Saved'/('GHS_WallCapture'+phase+'.json')).write_text(json.dumps(dict(success=error is None,error=error,path=str(path),camera_restored=True)))
handle=unreal.register_slate_post_tick_callback(tick)
