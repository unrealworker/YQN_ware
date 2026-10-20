"""Leave the saved Zcool map open at the user's original editor view after QA."""
import json
from pathlib import Path
import unreal
ROOT = Path(r'D:/UEPro/Test')
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
assert not levels.is_in_play_in_editor()
assert editor.get_editor_world().get_path_name().split('.')[0] == '/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
state = json.loads((ROOT / 'Saved/GHS_TwinUI_PrepareBuild.json').read_text(encoding='utf-8'))['after']
rot = state['viewport_rotation']
editor.set_level_viewport_camera_info(unreal.Vector(*state['viewport_position']), unreal.Rotator(pitch=rot[0], yaw=rot[1], roll=rot[2]))
(ROOT / 'Saved/GHS_TwinUI_ManualAction.json').write_text(json.dumps(dict(label='EditorFinalRestored', capture=False)), encoding='utf-8')
exec(compile((ROOT / 'Scripts/ghs/probe_twin_ui_manual.py').read_text(encoding='utf-8'), str(ROOT / 'Scripts/ghs/probe_twin_ui_manual.py'), 'exec'), {})
unreal.log('GHS_TWIN_UI_MANUAL_FINISHED_EDITOR_OPEN')
