"""Normal exit for module rebuild; refuse any unsaved work or active PIE."""
import json
from pathlib import Path
import unreal
root=Path('D:/UEPro/Test');out=root/'Saved/RoofScan'
assert not unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor()
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
assert json.loads((out/'roof_dissolve_apply.json').read_text(encoding='utf8'))['success']
exec(compile((root/'Scripts/ghs/inspect_roof_scan_session.py').read_text(encoding='utf8'),'inspect_roof_scan_session.py','exec'))
unreal.SystemLibrary.quit_editor()
