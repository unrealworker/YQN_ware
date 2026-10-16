"""Show the new floor stacker without saving or modifying scene objects."""
import json
from pathlib import Path
import unreal
root=Path(r'D:\UEPro\Test')
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
assert editor.get_editor_world().get_path_name().split('.')[0]=='/Game/Maps/GHS_CAD_NormalWarehouse'
report=json.loads((root/'Saved/GHS_NormalStackers_CaptureReport.json').read_text())
view=next(v for v in report['view_plan'] if v['view']=='Close')['camera']
rotation=view['rotation_degrees']
editor.set_level_viewport_camera_info(unreal.Vector(*view['position_cm']),unreal.Rotator(pitch=rotation[0],yaw=rotation[1],roll=rotation[2]))
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors.set_selected_level_actors([a for a in actors.get_all_level_actors() if a.get_actor_label()=='GHN_FloorStacker_05'])
unreal.log('GHS_NORMAL_STACKER_PREVIEW: selected independently editable GHN_FloorStacker_05')
