"""Restore the user's editor view and local script bridge after compilation."""
import json
import runpy
import time
from pathlib import Path
import unreal
ROOT=Path('D:/UEPro/Test')
START=time.monotonic()
HANDLE=None
def restore(delta):
    global HANDLE
    if time.monotonic()-START<3:return
    unreal.unregister_slate_post_tick_callback(HANDLE)
    state=json.loads((ROOT/'Saved/DockNumbers/editor_before.json').read_text(encoding='utf-8'))
    editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    assert editor.get_editor_world().get_path_name()==state['map']
    assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
    pitch,yaw,roll=state['rotation']
    editor.set_level_viewport_camera_info(unreal.Vector(*state['eye']),unreal.Rotator(pitch=pitch,yaw=yaw,roll=roll))
    (ROOT/'Saved/DockNumbers/editor_restored.json').write_text(json.dumps(dict(success=True,map=state['map'])),encoding='utf-8')
    runpy.run_path(str(ROOT/'Scripts/ghs/live_dispatcher.py'),run_name='__main__')
HANDLE=unreal.register_slate_post_tick_callback(restore)
