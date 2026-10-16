"""Save the current Normal scene before native camera update, preserving user edits."""
import json
import sys
from pathlib import Path
import unreal

ROOT=Path(r'D:\UEPro\Test')
sys.path.insert(0,str(ROOT/'Scripts/ghs'))
from sync_wall_heights import snapshot
E=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
A=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
L=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assert not L.is_in_play_in_editor(),'Stop Play before saving and restarting'
assert E.get_editor_world().get_path_name().split('.')[0]=='/Game/Maps/GHS_CAD_NormalWarehouse'
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages(),'Unsaved content assets: preserve them before restart'
assert all(p.get_name()=='/Game/Maps/GHS_CAD_NormalWarehouse' for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())
before=snapshot({a.get_actor_label():a for a in A.get_all_level_actors()})
assert 'GHS_WarehouseCamera' in before
assert L.save_current_level()
checkpoint=json.loads((ROOT/'Saved/GHS_WarehouseCameraGroundRevision.json').read_text(encoding='utf-8-sig'))
Path(checkpoint['backup_root'],'live_before.json').write_text(json.dumps(before,indent=2),encoding='utf8')
(ROOT/'Saved/GHS_WarehouseCameraGroundRestart.json').write_text(json.dumps(dict(success=True,actor_count=len(before))),encoding='utf8')
unreal.SystemLibrary.quit_editor()
