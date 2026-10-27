"""Capture the imported CAD cart in the actual warehouse editor viewport."""
from pathlib import Path
import unreal

root = Path('D:/UEPro/Test')
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert editor.get_editor_world().get_path_name().split('.')[0] == '/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
target = next(a for a in actors.get_all_level_actors() if a.get_actor_label() == 'GHN_FloorStacker_9')
assert target.get_component_by_class(unreal.StaticMeshComponent).static_mesh.get_name() == 'SM_CartShell_1026'
actors.set_selected_level_actors([])
position = target.get_actor_location()
eye = position + unreal.Vector(48, 66, 62)
focus = position + unreal.Vector(0, 0, 9)
editor.set_level_viewport_camera_info(eye, unreal.MathLibrary.find_look_at_rotation(eye, focus))
output = root / 'SourceAssets/CartShell_1026/20k/ue_scene_close.png'
capture_task = unreal.AutomationLibrary.take_high_res_screenshot(1600, 1100, str(output), delay=1.0)
unreal.log('CART_SHELL_CAPTURE_QUEUED ' + str(output))
