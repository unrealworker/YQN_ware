"""Restore the preserved editor camera and local script dispatcher after rebuild."""
import json
import runpy
import time
from pathlib import Path
import unreal

root=Path('D:/UEPro/Test')
start=time.monotonic()
handle=None
def restore(delta):
    global handle
    if time.monotonic()-start<3: return
    unreal.unregister_slate_post_tick_callback(handle)
    state=json.loads((root/'Saved/RoundedHUD/editor_before.json').read_text(encoding='utf-8'))
    editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    assert editor.get_editor_world().get_path_name()==state['map']
    pitch,yaw,roll=state['rotation']
    editor.set_level_viewport_camera_info(unreal.Vector(*state['eye']),unreal.Rotator(pitch=pitch,yaw=yaw,roll=roll))
    (root/'Saved/RoundedHUD/editor_restored.json').write_text(json.dumps(dict(success=True,map=state['map'])),encoding='utf-8')
    runpy.run_path(str(root/'Scripts/ghs/live_dispatcher.py'),run_name='__main__')
handle=unreal.register_slate_post_tick_callback(restore)
