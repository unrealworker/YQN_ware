"""Select one unpacked truck for editing without modifying or saving the map."""
import json
import math
from pathlib import Path
import unreal

actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
by = {a.get_actor_label(): a for a in actors.get_all_level_actors()}
truck = by['GHS_DockTruck_041']
actors.set_selected_level_actors([truck])
assert actors.get_selected_level_actors() == [truck]
origin = truck.get_actor_location()
angle = math.radians(truck.get_actor_rotation().yaw)
forward = unreal.Vector(math.cos(angle), math.sin(angle), 0)
right = unreal.Vector(-math.sin(angle), math.cos(angle), 0)
target = origin + forward*450 + unreal.Vector(0, 0, 180)
camera = origin + forward*750 + right*1250 + unreal.Vector(0, 0, 850)
editor.set_level_viewport_camera_info(camera, unreal.MathLibrary.find_look_at_rotation(camera, target))
Path(r'D:\UEPro\Test\Saved\GHS_TruckModelsSplitEditorView.json').write_text(json.dumps(dict(
    success=True, selected=truck.get_actor_label(), selected_count=1,
    folder=str(truck.get_folder_path()), actor_class=truck.get_class().get_path_name(),
    mesh=truck.get_component_by_class(unreal.StaticMeshComponent).get_editor_property('static_mesh').get_path_name(),
    dirty_maps=[p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()]
), indent=2), encoding='utf-8')
