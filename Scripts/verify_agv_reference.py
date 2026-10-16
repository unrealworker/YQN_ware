"""Run in a fresh UE 5.4 process after import_agv_reference.py has exited."""
import json
import traceback
from pathlib import Path

import unreal


ROOT = Path(r"D:\UEPro\Test")
SOURCE = ROOT / "SourceAssets" / "AGV_Reference"
REPORT = ROOT / "Saved" / "AGV_Verification.json"
REGISTRY = ROOT / "SourceAssets" / "LogisticsWarehouse" / "twin_asset_registry.json"
DEST = "/Game/AGV_Reference"
MAP = "/Game/Maps/LogisticsWarehouse"
MESH_PATH = DEST + "/Meshes/SM_AGV_Reference"
BLUEPRINT_PATH = DEST + "/Blueprints/BP_AGV_Reference"
ACTOR_LABEL = "AGV_01_Reference"
CAMERA_LABEL = "CAM_AGV_Reference"
POSITION_CM = (-2700.0, 4700.0, 8.0)


def xyz(vector):
    return [float(vector.x), float(vector.y), float(vector.z)]


def main():
    manifest = json.loads((SOURCE / "manifest.json").read_text(encoding="utf-8"))
    expected_materials = {item["name"] for item in manifest["materials"]}
    expected_size = [(axis[1] - axis[0]) * 100.0 for axis in manifest["bounds_m"]]
    assert len(expected_size) == 3 and all(value > 0 for value in expected_size)
    assert abs(manifest["bounds_m"][2][0]) < 0.005, "Source must rest at Z=0"

    lib = unreal.EditorAssetLibrary
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    assert levels.load_level(MAP), "Could not reload warehouse map"
    mesh = lib.load_asset(MESH_PATH)
    assert isinstance(mesh, unreal.StaticMesh), "Saved static mesh is missing"
    blueprint = lib.load_asset(BLUEPRINT_PATH)
    assert isinstance(blueprint, unreal.Blueprint), "Saved Blueprint is missing"
    generated_class = blueprint.generated_class()
    assert generated_class, "Saved Blueprint has no generated class"
    default_actor = unreal.get_default_object(generated_class)
    default_component = default_actor.get_component_by_class(unreal.StaticMeshComponent)
    assert default_component and default_component.static_mesh == mesh, "Blueprint default mesh was not saved"
    assert default_component.get_editor_property("mobility") == unreal.ComponentMobility.MOVABLE

    all_actors = actors.get_all_level_actors()
    matches = [actor for actor in all_actors if actor.get_actor_label() == ACTOR_LABEL]
    assert len(matches) == 1, "Expected exactly one saved " + ACTOR_LABEL
    actor = matches[0]
    assert actor.get_class() == generated_class, "AGV is not the saved Blueprint class"
    component = actor.get_component_by_class(unreal.StaticMeshComponent)
    assert component and component.static_mesh == mesh, "Placed actor uses the wrong mesh"
    assert component.get_editor_property("mobility") == unreal.ComponentMobility.MOVABLE
    assert str(actor.get_folder_path()) == "Vehicles/AGV"
    assert "TwinId=" + ACTOR_LABEL in [str(tag) for tag in actor.tags]
    position = xyz(actor.get_actor_location())
    assert all(abs(actual - expected) < 0.01 for actual, expected in zip(position, POSITION_CM)), position
    rotation = actor.get_actor_rotation()
    assert max(abs(rotation.pitch), abs(rotation.yaw), abs(rotation.roll)) < 0.01, "Unexpected AGV rotation"
    assert all(abs(value - 1.0) < 0.0001 for value in xyz(actor.get_actor_scale3d()))

    slots = mesh.get_editor_property("static_materials")
    assert slots and component.get_num_materials() == len(slots)
    material_paths = []
    slot_names = []
    for index, slot in enumerate(slots):
        name = str(slot.get_editor_property("imported_material_slot_name"))
        if name not in expected_materials:
            name = str(slot.get_editor_property("material_slot_name"))
        assert name in expected_materials, "Unexpected material slot: " + name
        expected_path = DEST + "/Materials/" + name
        expected_material = lib.load_asset(expected_path)
        assert expected_material, "Saved material is missing: " + expected_path
        saved_material = slot.get_editor_property("material_interface")
        actor_material = component.get_material(index)
        default_material = default_component.get_material(index)
        assert saved_material and actor_material and default_material, "Empty material slot: " + name
        assert saved_material == actor_material == default_material == expected_material, "Material assignment did not persist: " + name
        assert "WorldGrid" not in saved_material.get_path_name(), "WorldGrid material remains"
        material_paths.append(saved_material.get_path_name())
        slot_names.append(name)
    for name in expected_materials:
        assert lib.does_asset_exist(DEST + "/Materials/" + name), "Missing manifest material: " + name

    origin, extent = actor.get_actor_bounds(False)
    size = [value * 2.0 for value in xyz(extent)]
    for axis, (actual, expected) in enumerate(zip(size, expected_size)):
        tolerance = max(1.0, expected * 0.01)
        assert abs(actual - expected) <= tolerance, "Size mismatch on axis %d: %s != %s cm" % (axis, actual, expected)
    bottom = float(origin.z - extent.z)
    assert abs(bottom - POSITION_CM[2]) < 0.5, "Expected model ground near 8 cm, got " + str(bottom)

    cameras = [candidate for candidate in all_actors if candidate.get_actor_label() == CAMERA_LABEL]
    assert len(cameras) == 1, "Expected exactly one AGV inspection camera"
    camera = cameras[0]
    camera_component = camera.get_component_by_class(unreal.CameraComponent)
    assert camera_component, "Inspection camera has no CameraComponent"
    assert abs(camera_component.get_editor_property("field_of_view") - 35.0) < 0.01
    assert all(abs(actual - expected) < 0.01 for actual, expected in zip(xyz(camera.get_actor_location()), (-3000.0, 4920.0, 220.0)))

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    records = [record for record in registry if record.get("id") == ACTOR_LABEL]
    assert len(records) == 1, "Expected exactly one AGV registry entry"
    assert records[0] == {
        "id": ACTOR_LABEL,
        "category": "Vehicles/AGV",
        "mesh": "SM_AGV_Reference",
        "position_m": [-27, 47, 0.08],
        "yaw": 0,
    }, "Registry entry does not match the placed AGV"

    result = {
        "success": True,
        "verification_mode": "reload_saved_assets; run this script in a separate UE process",
        "map": MAP,
        "actor_count": len(matches),
        "actor": actor.get_path_name(),
        "actor_class": actor.get_class().get_path_name(),
        "blueprint": BLUEPRINT_PATH,
        "blueprint_default_mesh_persisted": True,
        "movable": True,
        "mesh": mesh.get_path_name(),
        "position_cm": position,
        "size_cm": size,
        "expected_size_cm": expected_size,
        "ground_z_cm": bottom,
        "material_count": len(expected_materials),
        "material_slot_count": len(slots),
        "material_slots": slot_names,
        "materials": material_paths,
        "all_material_assignments_persisted": True,
        "camera": camera.get_path_name(),
        "registry_entry_verified": True,
        "source_parts": len(manifest["source_parts"]),
    }
    REPORT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    unreal.log("AGV_REFERENCE_SAVED_ASSETS_VERIFIED " + json.dumps(result))


REPORT.parent.mkdir(parents=True, exist_ok=True)
try:
    main()
except Exception:
    REPORT.write_text(json.dumps({"success": False, "error": traceback.format_exc()}, indent=2), encoding="utf-8")
    raise
