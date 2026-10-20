"""Normally close only the clean final editor for the verified short-drag fix."""
import hashlib
import json
import os
from pathlib import Path
import unreal
ROOT=Path(r'D:/UEPro/Test')
assert os.getpid()==25452, 'Wrong editor process'
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
assert not levels.is_in_play_in_editor()
assert editor.get_editor_world().get_path_name().split('.')[0]=='/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
saved=json.loads((ROOT/'Saved/GHS_TwinUI_PrepareBuild.json').read_text(encoding='utf-8'))
assert hashlib.sha256((ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap').read_bytes()).hexdigest()==saved['map_sha256_after']
assert hashlib.sha256((ROOT/'Content/Maps/GHS_CAD_NormalWarehouse.umap').read_bytes()).hexdigest()==saved['original_map_sha256_after']
eye,rot=editor.get_level_viewport_camera_info()
(ROOT/'Saved/GHS_TwinUI_DragFixEditorClose.json').write_text(json.dumps(dict(success=True,pid=os.getpid(),assets_saved=False,dirty_maps=[],dirty_assets=[],viewport_position=[eye.x,eye.y,eye.z],viewport_rotation=[rot.pitch,rot.yaw,rot.roll],normal_exit_requested=True),indent=2),encoding='utf-8')
unreal.log('GHS_TWIN_UI_DRAG_FIX_CLEAN_EDITOR_NORMAL_EXIT')
unreal.SystemLibrary.quit_editor()
