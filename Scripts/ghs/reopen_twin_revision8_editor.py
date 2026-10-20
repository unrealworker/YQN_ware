"""Restore the editor view recorded immediately before revision 8; save no assets."""
import hashlib, json
from pathlib import Path
import unreal
ROOT=Path(r'D:/UEPro/Test')
saved=json.loads((ROOT/'Saved/Revision8_EditorState.json').read_text(encoding='utf-8'))
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
assert editor.get_editor_world().get_path_name().split('.')[0]=='/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
for name,expected in saved['map_sha256'].items():
    assert hashlib.sha256((ROOT/'Content/Maps'/name).read_bytes()).hexdigest()==expected
rot=saved['viewport_rotation']
editor.set_level_viewport_camera_info(unreal.Vector(*saved['viewport_position']),unreal.Rotator(pitch=rot[0],yaw=rot[1],roll=rot[2]))
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
assert len(actors)==saved['actor_count']
(ROOT/'Saved/Revision8_EditorRestored.json').write_text(json.dumps(dict(success=True,actor_count=len(actors),
    maps_preserved=True,viewport_restored=True,assets_saved=False,dirty_maps=[],dirty_assets=[]),indent=2),encoding='utf-8')
exec(compile((ROOT/'Scripts/ghs/live_dispatcher.py').read_text(),str(ROOT/'Scripts/ghs/live_dispatcher.py'),'exec'),globals())
unreal.log('GHS_REVISION8_EDITOR_RESTORED')
