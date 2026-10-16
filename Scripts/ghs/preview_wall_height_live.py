"""Show the corrected wall junction without resaving either map."""
import unreal
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
assert editor.get_editor_world().get_path_name().split('.')[0] in ['/Game/Maps/GHS_CAD_DigitalTwin','/Game/Maps/GHS_CAD_NormalWarehouse']
position=unreal.Vector(22600,-3600,2000)
target=unreal.Vector(21400,-5100,200)
editor.set_level_viewport_camera_info(position,unreal.MathLibrary.find_look_at_rotation(position,target))
unreal.get_editor_subsystem(unreal.EditorActorSubsystem).set_selected_level_actors([])
