"""Show the saved Normal warehouse result in the editor without modifying assets."""
import json
from pathlib import Path
import unreal

editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
world = editor.get_editor_world()
assert world.get_path_name().startswith('/Game/Maps/GHS_CAD_NormalWarehouse.'), world.get_path_name()
placed = [a for a in actors.get_all_level_actors() if a.get_actor_label() == 'GHS_WarehouseCamera']
assert len(placed) == 1
pawn = placed[0]
assert abs(pawn.get_actor_location().z) < 0.001
actors.clear_actor_selection_set()
editor.set_level_viewport_camera_info(pawn.get_desired_camera_world_location(), pawn.get_editor_property('desired_rotation'))
Path(r'D:\UEPro\Test\Saved\GHS_GroundCameraEditorReady.json').write_text(json.dumps({
    'ready': True, 'map': world.get_path_name(), 'pawn_z': pawn.get_actor_location().z,
    'actor_count': len(actors.get_all_level_actors()),
    'truck_count': sum(a.get_actor_label().startswith('GHS_DockTruck_') for a in actors.get_all_level_actors())
}, indent=2), encoding='utf8')
unreal.log('GROUND_CAMERA_LONG_TRUCKS_EDITOR_READY')
