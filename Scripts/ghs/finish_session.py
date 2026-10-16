"""Restore the saved overview and retire this task's session-only dispatcher."""
import unreal
from pathlib import Path
import json
performance_restore=Path(r'D:\UEPro\Test\Saved\GHS_CapturePerformanceRestore.json')
if performance_restore.is_file():
    previous=json.loads(performance_restore.read_text())
    unreal.get_default_object(unreal.load_class(None,'/Script/UnrealEd.EditorPerformanceSettings')).set_editor_property(previous['property_name'],previous['throttle'])
    performance_restore.unlink()
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assert editor.get_editor_world().get_path_name().split('.')[0]=='/Game/Maps/GHS_CAD_DigitalTwin'
camera=next(a for a in actors.get_all_level_actors() if a.get_actor_label()=='CAM_GHS_Overview')
editor.set_level_viewport_camera_info(camera.get_actor_location(),camera.get_actor_rotation())
actors.set_selected_level_actors([])
assert levels.save_current_level()
import __main__
import sys
stopped=False
if getattr(__main__,'bridge_handle',None) is not None:
    unreal.unregister_slate_post_tick_callback(__main__.bridge_handle)
    __main__.bridge_handle=None
    stopped=True
caller=sys._getframe(1)
while caller is not None and not stopped:
    if caller.f_code.co_name=='bridge_tick':
        handle=caller.f_globals.get('bridge_handle')
        if handle is not None:
            unreal.unregister_slate_post_tick_callback(handle)
            caller.f_globals['bridge_handle']=None
            stopped=True
    caller=caller.f_back
import json
from pathlib import Path
Path(r'D:\UEPro\Test\Saved\GHS_FinalEditorState.json').write_text(json.dumps(dict(success=True,map='/Game/Maps/GHS_CAD_DigitalTwin',viewport='Overview',dispatcher_stopped=stopped)))
unreal.log('GHS_SESSION_FINISHED')
