"""Preserve the user's editor state and close only a clean editor for rebuilding."""
import json
import os
import time
import shutil
from pathlib import Path
import unreal

out=Path('D:/UEPro/Test/Saved/RoundedHUD')
out.mkdir(parents=True,exist_ok=True)
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
was_playing=levels.is_in_play_in_editor()
if was_playing: levels.editor_request_end_play()
started=time.monotonic()
handle=None
def close_clean_editor(delta):
    global handle
    if levels.is_in_play_in_editor() or time.monotonic()-started<2: return
    unreal.unregister_slate_post_tick_callback(handle)
    editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    world=editor.get_editor_world()
    assert world, 'Editor world is not available; editor left open'
    eye,rotation=editor.get_level_viewport_camera_info()
    state=dict(pid=os.getpid(),map=world.get_path_name(),pie=was_playing,
        dirty_maps=[p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()],
        dirty_assets=[p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()],
        eye=[eye.x,eye.y,eye.z],rotation=[rotation.pitch,rotation.yaw,rotation.roll])
    (out/'editor_before.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
    assert not state['dirty_assets'], 'Unexpected unsaved assets; editor left open'
    if state['dirty_maps']:
        target='/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
        assert state['dirty_maps']==[target] and state['map'].startswith(target+'.'), 'Unexpected unsaved map; editor left open'
        backup=out/('map_before_user_save_'+str(time.time_ns())+'.umap')
        shutil.copy2(Path('D:/UEPro/Test/Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'),backup)
        assert levels.save_current_level(), 'Current scene did not save; editor left open'
        state['saved_current_scene']=True
        state['disk_backup']=str(backup)
        (out/'editor_before.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
    assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
    unreal.SystemLibrary.quit_editor()
handle=unreal.register_slate_post_tick_callback(close_clean_editor)
