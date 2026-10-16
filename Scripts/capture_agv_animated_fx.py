"""Capture AGV decal stills in the live UE editor.

UE high-resolution screenshot mode can freeze shader time, so animation proof
must come from foreground viewport screen recordings, not this still sequence.
"""
import json
import time
import traceback
from pathlib import Path
import unreal
af_root=Path(r'D:\UEPro\Test')
af_dir=af_root/'Saved/AGVFX_Frames';af_dir.mkdir(parents=True,exist_ok=True)
af_actor_sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
af_editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
af_level_sub=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
af_by={a.get_actor_label():a for a in af_actor_sub.get_all_level_actors()}
af_robot=af_by['CBD50-1'];af_p=af_robot.get_actor_location()
af_camera=af_actor_sub.spawn_actor_from_class(unreal.CameraActor,af_p+unreal.Vector(430,-650,650))
af_camera.set_actor_label('TEMP_AGVFX_Capture')
af_target=af_p+unreal.Vector(-60,0,20)
af_camera.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(af_camera.get_actor_location(),af_target),False)
af_camera.get_component_by_class(unreal.CameraComponent).set_field_of_view(47)
af_actor_sub.set_selected_level_actors([])
af_started=time.monotonic();af_busy=False;af_done=False;af_task=None;af_pending=None;af_index=0
af_report=dict(success=False,status='warming',mode='UE high-resolution stills; animation verified separately by live viewport capture',frames=[])
af_report_path=af_root/'Saved/AGVFX_CaptureReport.json'

def af_write():af_report_path.write_text(json.dumps(af_report,indent=2),encoding='utf-8')

def af_finish(error=None):
    global af_done
    if af_done:return
    af_done=True;unreal.unregister_slate_post_tick_callback(af_handle)
    position=af_camera.get_actor_location();rotation=af_camera.get_actor_rotation()
    af_actor_sub.destroy_actor(af_camera)
    af_editor.set_level_viewport_camera_info(position,rotation)
    assert af_level_sub.save_current_level()
    af_report.update(success=error is None,status='complete' if error is None else 'failed',
                     temporary_camera_removed=True,elapsed_seconds=time.monotonic()-af_started)
    if error:af_report['error']=error
    af_write();unreal.log('AGV_FX_ANIMATION_CAPTURE_COMPLETE' if error is None else error)

def af_tick(delta):
    global af_busy,af_task,af_pending,af_index
    if af_busy or af_done:return
    af_busy=True
    try:
        now=time.monotonic();assert now-af_started<160,'Animation capture timed out'
        if now-af_started<12:return
        if af_task is not None:
            if not af_task.is_task_done():return
            path=Path(af_pending['path'])
            assert path.exists() and path.stat().st_mtime_ns!=af_pending['previous_mtime_ns'],'Frame not refreshed'
            af_pending['captured_seconds']=now-af_started;af_report['frames'].append(af_pending)
            af_task=None;af_write()
        if af_index==24:af_finish();return
        path=af_dir/('frame_%03d.png'%af_index)
        af_pending=dict(index=af_index,path=str(path),requested_seconds=now-af_started,
                        previous_mtime_ns=path.stat().st_mtime_ns if path.exists() else None)
        af_index+=1;af_report['status']='capturing'
        af_task=unreal.AutomationLibrary.take_high_res_screenshot(960,720,str(path),camera=af_camera,delay=.16)
        assert af_task is not None
    except Exception:af_finish(traceback.format_exc())
    finally:af_busy=False

af_handle=unreal.register_slate_post_tick_callback(af_tick)
af_write()
