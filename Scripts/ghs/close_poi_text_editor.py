import json
import shutil
import hashlib
from pathlib import Path
import unreal
root=Path('D:/UEPro/Test'); out=root/'Saved/VisualPolish'
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert not levels.is_in_play_in_editor(), 'Preserve running preview'
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages(), 'Preserve unsaved content'
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages(), 'Preserve unsaved maps'
map_path=editor.get_editor_world().get_path_name().split('.')[0]
assert map_path=='/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
map_file=root/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'
map_hash=hashlib.sha256(map_file.read_bytes()).hexdigest()
assert map_hash=='1413dadf962894b54cecf07d6c84e5f6a978eaa567c67fa2bc0d806c7de7fe65', 'Map changed since inspection'
session_path=out/'editor_rebuild_session.json'
session=json.loads(session_path.read_text(encoding='utf-8'))
shutil.copy2(session_path,out/'editor_session_before_click_view.json')
shutil.copy2(map_file,out/'user_saved_map_before_click_view.umap')
loc,rot=editor.get_level_viewport_camera_info()
session.update(map=map_path,viewport_location=[loc.x,loc.y,loc.z],viewport_rotation=[rot.pitch,rot.yaw,rot.roll],selected_actor_labels=[a.get_actor_label() for a in actors.get_selected_level_actors()],map_sha256=map_hash,scene_matches_after=False,preserve_newer_saved_user_map=True)
session_path.write_text(json.dumps(session,ensure_ascii=False,indent=2),encoding='utf-8')
unreal.log('GHS_POI_TEXT_EDITOR_SAFELY_CLOSED')
unreal.SystemLibrary.quit_editor()