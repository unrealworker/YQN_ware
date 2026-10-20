"""Restore the user's saved editor view after the native UI build; save no assets."""
import json,hashlib
from pathlib import Path
import unreal
ROOT=Path(r'D:\UEPro\Test')
saved=json.loads((ROOT/'Saved/GHS_TwinUI_PrepareBuild.json').read_text(encoding='utf-8'))
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
assert editor.get_editor_world().get_path_name().split('.')[0]==saved['target_map']
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
view=saved['after']
rotation=view['viewport_rotation']
editor.set_level_viewport_camera_info(unreal.Vector(*view['viewport_position']),unreal.Rotator(pitch=rotation[0],yaw=rotation[1],roll=rotation[2]))
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
assert len(actors)==view['actor_count']
def sha(path):return hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
assert sha('Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap')==saved['map_sha256_after']
assert sha('Content/Maps/GHS_CAD_NormalWarehouse.umap')==saved['original_map_sha256_after']
result=dict(success=True,editor_world=editor.get_editor_world().get_path_name(),actor_count=len(actors),
    source_map_preserved=True,current_map_preserved=True,viewport_restored=True,assets_saved=False)
(ROOT/'Saved/GHS_TwinUI_EditorRestored.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
exec(compile((ROOT/'Scripts/ghs/live_dispatcher.py').read_text(),str(ROOT/'Scripts/ghs/live_dispatcher.py'),'exec'),globals())
unreal.log('GHS_TWIN_EDITOR_RESTORED')
