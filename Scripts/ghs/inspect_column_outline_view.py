"""Record the user's current column inspection view without moving anything."""
import json
from pathlib import Path
import unreal
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
position,rotation=editor.get_level_viewport_camera_info()
assert editor.get_editor_world().get_path_name().split('.')[0]=='/Game/Maps/GHS_CAD_DigitalTwin'
Path(r'D:\UEPro\Test\Saved\GHS_ColumnOutlineView.json').write_text(json.dumps(dict(viewport=dict(position_cm=[position.x,position.y,position.z],rotation=[rotation.pitch,rotation.yaw,rotation.roll]))))
