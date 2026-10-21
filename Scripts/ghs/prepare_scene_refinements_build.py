"""Preserve the clean editor, then close it for the requested native rebuild."""
import json
import os
from pathlib import Path
import unreal

root=Path('D:/UEPro/Test')
out=root/'Saved/SceneRefinements'
before=json.loads((out/'editor_before.json').read_text(encoding='utf-8'))
applied=json.loads((out/'apply_report.json').read_text(encoding='utf-8'))
assert applied['success'] and applied['saved_and_reloaded']
assert os.getpid()==before['pid']
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
assert not levels.is_in_play_in_editor()
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
assert editor.get_editor_world().get_path_name()==before['map']
eye,rotation=editor.get_level_viewport_camera_info()
before.update(eye=[eye.x,eye.y,eye.z],rotation=[rotation.pitch,rotation.yaw,rotation.roll])
(out/'editor_reopen.json').write_text(json.dumps(before,ensure_ascii=False,indent=2),encoding='utf-8')
unreal.SystemLibrary.quit_editor()
