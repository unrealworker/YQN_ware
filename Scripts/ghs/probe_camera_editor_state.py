import unreal,json
from pathlib import Path
E=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
v,r=E.get_level_viewport_camera_info()
p=Path(r'D:\UEPro\Test\Saved\GHS_WarehouseCameraEditorState.json')
p.write_text(json.dumps(dict(map=E.get_editor_world().get_path_name(),
 dirty_maps=[x.get_name() for x in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()],
 dirty_assets=[x.get_name() for x in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()],
 viewport_position=[v.x,v.y,v.z],viewport_rotation=[r.pitch,r.yaw,r.roll]),indent=2))
