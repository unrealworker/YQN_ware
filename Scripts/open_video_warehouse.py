"""Preserve the user's currently edited level, then open the new video map."""
from pathlib import Path
import unreal
root=Path(r'D:\UEPro\Test')
world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
if world.get_path_name().split('.')[0]!='/Game/Maps/VideoDigitalTwinWarehouse':
    snapshot='/Game/Maps/Backups/LogisticsWarehouse_BeforeVideo_20261015_1730'
    assert not unreal.EditorAssetLibrary.does_asset_exist(snapshot),'Snapshot path already exists'
    assert unreal.EditorLoadingAndSavingUtils.save_map(world,snapshot),'Could not preserve the current level'
exec(compile((root/'Scripts/capture_video_warehouse.py').read_text(encoding='utf-8'),'capture_video_warehouse.py','exec'),globals())
