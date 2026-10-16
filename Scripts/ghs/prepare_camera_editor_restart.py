"""Preserve the current Normal-map session before loading a new native Pawn."""
import unreal,json,sys
from pathlib import Path
ROOT=Path(r'D:\UEPro\Test');sys.path.insert(0,str(ROOT/'Scripts/ghs'))
from sync_wall_heights import snapshot
E=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
A=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
L=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assert E.get_editor_world().get_path_name().split('.')[0]=='/Game/Maps/GHS_CAD_NormalWarehouse'
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages(),'Unsaved content assets need preserving before restart'
dirty=unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
assert all(p.get_name()=='/Game/Maps/GHS_CAD_NormalWarehouse' for p in dirty),'Another unsaved map is open'
before=snapshot({a.get_actor_label():a for a in A.get_all_level_actors()})
assert len(before)==263,'Unexpected scene changes; inspect before restart'
assert L.save_current_level()
checkpoint=json.loads((ROOT/'Saved/GHS_WarehouseCameraCheckpoint.json').read_text())
Path(checkpoint['backup_root'],'live_before.json').write_text(json.dumps(before,indent=2))
v,r=E.get_level_viewport_camera_info()
(ROOT/'Saved/GHS_WarehouseCameraRestart.json').write_text(json.dumps(dict(success=True,actor_count=len(before),
 viewport_position=[v.x,v.y,v.z],viewport_rotation=[r.pitch,r.yaw,r.roll])))
unreal.SystemLibrary.quit_editor()
