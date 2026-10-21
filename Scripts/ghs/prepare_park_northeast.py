"""Preserve the current editor map and source hashes before the NE refinement."""
import hashlib
import json
import shutil
from pathlib import Path
import unreal

ROOT=Path('D:/UEPro/Test')
OUT=ROOT/'Saved/ParkNortheast/Before'
MAP='/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assert not levels.is_in_play_in_editor()
assert editor.get_editor_world().get_path_name().split('.')[0]==MAP
assert all(p.get_path_name()==MAP for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
OUT.mkdir(parents=True,exist_ok=True)
assert levels.save_current_level()
target=OUT/'current_user_saved.umap'
assert not target.exists(), 'Do not overwrite this pre-change saved editor snapshot'
shutil.copy2(ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap',target)
shutil.copy2(ROOT/'Saved/ParkExpansion/scene_inspection_latest.json',OUT/'editor_snapshot.json')
sources=[ROOT/'Content/GHSNormalWarehouse/TrucksLong/SM_GHN_LongDockTruck.uasset',
         ROOT/'SourceAssets/GHS_Normal/TrucksLong/dock_truck_long.blend',
         ROOT/'SourceAssets/GHS_Normal/TrucksLong/SM_GHN_LongDockTruck.fbx',
         ROOT/'Content/GHSDigitalTwin/Blueprints/BP_GHS_InstanceGroup.uasset']
hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
(OUT/'source_hashes.json').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
unreal.log('GHS_PARK_NE_BACKUP_SAVED')
