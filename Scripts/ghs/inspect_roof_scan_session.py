"""Read-only snapshot of the live editor before the roof animation revision."""
import hashlib,json,os
from pathlib import Path
import unreal
root=Path('D:/UEPro/Test');out=root/'Saved/RoofScan';out.mkdir(parents=True,exist_ok=True)
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
pos,rot=editor.get_level_viewport_camera_info()
report=dict(pid=os.getpid(),world=editor.get_editor_world().get_path_name(),
 position=[pos.x,pos.y,pos.z],rotation=[rot.pitch,rot.yaw,rot.roll],
 selected=[a.get_name() for a in actors.get_selected_level_actors()],count=len(actors.get_all_level_actors()),
 playing=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor(),
 dirty_content=[p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()],
 dirty_maps=[p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()],
 map_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'Content/Maps').glob('GHS_CAD_NormalWarehouse*.umap')})
(out/'editor-before.json').write_text(json.dumps(report,indent=2),encoding='utf8')
unreal.log('GHS_ROOF_SCAN_EDITOR_SNAPSHOT')
