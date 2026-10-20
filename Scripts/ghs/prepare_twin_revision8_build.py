"""User-authorized clean PIE stop and normal editor exit for revision 8 build."""
import hashlib, json, os, time
from pathlib import Path
import unreal

ROOT=Path(r'D:/UEPro/Test')
assert os.getpid() in (47436,57704), 'Unexpected editor process'
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
started=time.monotonic()
handle=None
def finish(delta):
    global handle
    if levels.is_in_play_in_editor():
        assert time.monotonic()-started<30, 'PIE stop timeout'
        return
    unreal.unregister_slate_post_tick_callback(handle)
    assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages(), 'Unsaved maps; keep editor open'
    assert not unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages(), 'Unsaved assets; keep editor open'
    world=editor.get_editor_world()
    assert world.get_path_name().split('.')[0]=='/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
    eye,rot=editor.get_level_viewport_camera_info()
    hashes={name:hashlib.sha256((ROOT/'Content/Maps'/name).read_bytes()).hexdigest() for name in ['GHS_CAD_NormalWarehouse.umap','GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap']}
    result=dict(success=True,pid=os.getpid(),assets_saved=False,dirty_maps=[],dirty_assets=[],map_sha256=hashes,
        viewport_position=[eye.x,eye.y,eye.z],viewport_rotation=[rot.pitch,rot.yaw,rot.roll],
        actor_count=len(unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()))
    (ROOT/'Saved/Revision8_EditorState.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    unreal.SystemLibrary.quit_editor()
if levels.is_in_play_in_editor(): levels.editor_request_end_play()
handle=unreal.register_slate_post_tick_callback(finish)
