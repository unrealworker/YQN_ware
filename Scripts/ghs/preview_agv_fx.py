"""Show the north-aisle KUKA's actual shader animation in the editor viewport."""
import unreal
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
assert editor.get_editor_world().get_path_name().split('.')[0]=='/Game/Maps/GHS_CAD_DigitalTwin'
p=unreal.Vector(20100,-5100,420)
t=unreal.Vector(20500,-5520,20)
editor.set_level_viewport_camera_info(p,unreal.MathLibrary.find_look_at_rotation(p,t))
unreal.get_editor_subsystem(unreal.EditorActorSubsystem).set_selected_level_actors([])
