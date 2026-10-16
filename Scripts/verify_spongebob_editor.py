"""Verify saved assets in the editor and capture the imported actor."""
import json
import time
import traceback
from pathlib import Path
import unreal

ROOT = Path(r"D:\UEPro\Test")
REPORT = ROOT / "Saved" / "SpongeBob_Verification.json"
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assert levels.load_level("/Game/Maps/SpongeBobScene")
all_actors = actors.get_all_level_actors()
found = [a for a in all_actors if a.get_actor_label() == "SpongeBob"]
assert len(found) == 1, "Expected exactly one saved SpongeBob actor"
actor = found[0]
component = actor.get_component_by_class(unreal.StaticMeshComponent)
mesh = component.static_mesh
assert mesh and mesh.get_name() == "SM_SpongeBob"
assert component.get_num_materials() == 17
assert all(component.get_material(i) for i in range(17))
bp = unreal.load_asset("/Game/SpongeBob/Blueprints/BP_SpongeBob")
default_actor = unreal.get_default_object(bp.generated_class())
assert default_actor.get_component_by_class(unreal.StaticMeshComponent).static_mesh == mesh
origin, extent = actor.get_actor_bounds(False)
assert 179 < 2 * extent.z < 181
assert abs(origin.z - extent.z) < 0.1
REPORT.write_text(json.dumps({"success": True, "actor_count": len(found),
    "map": "/Game/Maps/SpongeBobScene", "actor_class": actor.get_class().get_path_name(),
    "mesh": mesh.get_path_name(), "height_cm": extent.z * 2,
    "material_count": component.get_num_materials(), "blueprint_default_mesh_persisted": True}, indent=2), encoding="utf-8")

for preview_actor in actors.get_all_level_actors():
    if preview_actor.get_actor_label() == "SpongeBob Preview Camera":
        actors.destroy_actor(preview_actor)
camera = actors.spawn_actor_from_class(unreal.CameraActor, unreal.Vector(0, 440, 155))
camera.set_actor_label("SpongeBob Preview Camera")
camera_component = camera.get_component_by_class(unreal.CameraComponent)
camera_component.set_field_of_view(45.0)
camera_component.set_editor_property("constrain_aspect_ratio", False)
sb_positions = [unreal.Vector(0, 440, 155), unreal.Vector(-180, 420, 160)]
sb_index = 0
sb_started = time.monotonic()
sb_capture_task = None
sb_busy = False
sb_done = False


def tick(delta):
    global sb_index, sb_started, sb_capture_task, sb_handle, sb_busy, sb_done
    if sb_busy or sb_done:
        return
    sb_busy = True
    try:
        if time.monotonic() - sb_started < 5:
            return
        if sb_capture_task is not None and not sb_capture_task.is_task_done():
            return
        if sb_index >= len(sb_positions):
            sb_done = True
            position = sb_positions[1]
            rotation = unreal.MathLibrary.find_look_at_rotation(position, unreal.Vector(0, 0, 90))
            unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).set_level_viewport_camera_info(position, rotation)
            actors.destroy_actor(camera)
            actors.set_selected_level_actors([actor])
            levels.save_current_level()
            unreal.unregister_slate_post_tick_callback(sb_handle)
            unreal.log("SPONGEBOB_VISUAL_VERIFICATION_COMPLETE")
            return
        position = sb_positions[sb_index]
        camera.set_actor_location(position, False, False)
        camera.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(position, unreal.Vector(0, 0, 90)), False)
        filename = str(ROOT / "Saved" / ("SpongeBob_UE_Final" + str(sb_index) + ".png"))
        sb_index += 1
        sb_capture_task = unreal.AutomationLibrary.take_high_res_screenshot(1200, 1000,
            filename, camera=camera)
        sb_started = time.monotonic()
    except Exception:
        unreal.log_error(traceback.format_exc())
        sb_done = True
        unreal.unregister_slate_post_tick_callback(sb_handle)
    finally:
        sb_busy = False


sb_handle = unreal.register_slate_post_tick_callback(tick)
unreal.log("SPONGEBOB_SAVED_ASSETS_VERIFIED")
