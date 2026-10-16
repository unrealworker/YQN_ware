"""Import the Blender AGV and place it in the existing UE 5.4 warehouse map."""
import json
import traceback
from pathlib import Path

import unreal


ROOT = Path(r"D:\UEPro\Test")
SOURCE = ROOT / "SourceAssets" / "AGV_Reference"
REPORT = ROOT / "Saved" / "AGV_ImportReport.json"
REGISTRY = ROOT / "SourceAssets" / "LogisticsWarehouse" / "twin_asset_registry.json"
DEST = "/Game/AGV_Reference"
MAP = "/Game/Maps/LogisticsWarehouse"
MESH_PATH = DEST + "/Meshes/SM_AGV_Reference"
BLUEPRINT_PATH = DEST + "/Blueprints/BP_AGV_Reference"
ACTOR_LABEL = "AGV_01_Reference"
CAMERA_LABEL = "CAM_AGV_Reference"
POSITION_CM = (-2700.0, 4700.0, 8.0)


def save_asset(asset):
    # UE's Python property writes do not always mark packages dirty.
    assert unreal.EditorAssetLibrary.save_loaded_asset(asset, only_if_is_dirty=False), "Could not save " + asset.get_path_name()


def make_material(item, assets, lib, material_lib):
    name = item["name"]
    path = DEST + "/Materials/" + name
    material = lib.load_asset(path) if lib.does_asset_exist(path) else assets.create_asset(
        name, DEST + "/Materials", unreal.Material, unreal.MaterialFactoryNew()
    )
    assert isinstance(material, unreal.Material), "Could not create material: " + name
    material_lib.delete_all_material_expressions(material)
    color = material_lib.create_material_expression(material, unreal.MaterialExpressionConstant3Vector, -500, 0)
    color.set_editor_property("constant", unreal.LinearColor(*item["base_color"]))
    assert material_lib.connect_material_property(color, "", unreal.MaterialProperty.MP_BASE_COLOR)
    for key, prop, y in [
        ("roughness", unreal.MaterialProperty.MP_ROUGHNESS, 160),
        ("metallic", unreal.MaterialProperty.MP_METALLIC, 240),
    ]:
        value = material_lib.create_material_expression(material, unreal.MaterialExpressionConstant, -500, y)
        value.set_editor_property("r", float(item[key]))
        assert material_lib.connect_material_property(value, "", prop)
    emission = float(item.get("emission", 0.0))
    if emission:
        strength = material_lib.create_material_expression(material, unreal.MaterialExpressionConstant, -500, 360)
        strength.set_editor_property("r", emission)
        multiply = material_lib.create_material_expression(material, unreal.MaterialExpressionMultiply, -220, 360)
        assert material_lib.connect_material_expressions(color, "", multiply, "A")
        assert material_lib.connect_material_expressions(strength, "", multiply, "B")
        assert material_lib.connect_material_property(multiply, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    material_lib.recompile_material(material)
    save_asset(material)
    return material


def upsert_record(records, record):
    """Keep unrelated records and their order, replacing any older AGV entry."""
    result = []
    inserted = False
    for existing in records:
        if existing.get("id") == record["id"]:
            if not inserted:
                result.append(record)
                inserted = True
        else:
            result.append(existing)
    if not inserted:
        result.append(record)
    return result


def main():
    manifest = json.loads((SOURCE / "manifest.json").read_text(encoding="utf-8"))
    source_fbx = SOURCE / "SM_AGV_Reference.fbx"
    assert source_fbx.is_file(), "Missing Blender export: " + str(source_fbx)
    assert manifest["materials"], "Manifest has no materials"
    names = [item["name"] for item in manifest["materials"]]
    assert len(names) == len(set(names)), "Duplicate material names in manifest"
    expected_size = [(axis[1] - axis[0]) * 100.0 for axis in manifest["bounds_m"]]
    assert len(expected_size) == 3 and all(value > 0 for value in expected_size)
    assert abs(manifest["bounds_m"][2][0]) < 0.005, "Source must rest at Z=0"
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assert isinstance(registry, list), "Expected warehouse registry to be a list"

    assets = unreal.AssetToolsHelpers.get_asset_tools()
    lib = unreal.EditorAssetLibrary
    material_lib = unreal.MaterialEditingLibrary
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    assert lib.does_asset_exist(MAP), "Existing warehouse map is missing"

    task = unreal.AssetImportTask()
    task.filename = str(source_fbx)
    task.destination_path = DEST + "/Meshes"
    task.destination_name = "SM_AGV_Reference"
    task.automated = True
    task.replace_existing = True
    task.save = True
    options = unreal.FbxImportUI()
    options.import_mesh = True
    options.import_as_skeletal = False
    options.mesh_type_to_import = unreal.FBXImportType.FBXIT_STATIC_MESH
    options.automated_import_should_detect_type = False
    options.import_materials = False
    options.import_textures = False
    options.import_animations = False
    static_options = options.static_mesh_import_data
    static_options.combine_meshes = True
    static_options.generate_lightmap_u_vs = False
    static_options.auto_generate_collision = True
    static_options.normal_import_method = unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
    static_options.normal_generation_method = unreal.FBXNormalGenerationMethod.BUILT_IN
    task.options = options
    assets.import_asset_tasks([task])
    mesh = lib.load_asset(MESH_PATH)
    assert isinstance(mesh, unreal.StaticMesh), "Static mesh import failed"

    materials = {item["name"]: make_material(item, assets, lib, material_lib) for item in manifest["materials"]}
    slots = mesh.get_editor_property("static_materials")
    assert slots, "Imported mesh has no material slots"
    slot_names = []
    for index, slot in enumerate(slots):
        name = str(slot.get_editor_property("imported_material_slot_name"))
        if name not in materials:
            name = str(slot.get_editor_property("material_slot_name"))
        assert name in materials, "Unmatched imported material slot: " + name
        slot.set_editor_property("material_interface", materials[name])
        # StaticMaterial values yielded by the array are copies in UE Python.
        slots[index] = slot
        slot_names.append(name)
    mesh.set_editor_property("static_materials", slots)
    save_asset(mesh)

    if lib.does_asset_exist(BLUEPRINT_PATH):
        blueprint = lib.load_asset(BLUEPRINT_PATH)
    else:
        factory = unreal.BlueprintFactory()
        factory.set_editor_property("parent_class", unreal.StaticMeshActor)
        blueprint = assets.create_asset("BP_AGV_Reference", DEST + "/Blueprints", unreal.Blueprint, factory)
    assert isinstance(blueprint, unreal.Blueprint), "Blueprint creation failed"
    unreal.BlueprintEditorLibrary.compile_blueprint(blueprint)
    default_actor = unreal.get_default_object(blueprint.generated_class())
    default_component = default_actor.get_component_by_class(unreal.StaticMeshComponent)
    assert default_component, "Blueprint has no StaticMeshComponent"
    default_component.set_static_mesh(mesh)
    default_component.set_mobility(unreal.ComponentMobility.MOVABLE)
    unreal.BlueprintEditorLibrary.compile_blueprint(blueprint)
    save_asset(blueprint)

    assert levels.load_level(MAP), "Could not load warehouse map"
    existing_actors = actors.get_all_level_actors()
    cameras = [actor for actor in existing_actors if actor.get_actor_label() == CAMERA_LABEL]
    assert len(cameras) <= 1, "Multiple existing AGV cameras require review"
    for existing in existing_actors:
        if existing.get_actor_label() == ACTOR_LABEL:
            assert actors.destroy_actor(existing), "Could not replace existing AGV"
    actor = actors.spawn_actor_from_class(
        blueprint.generated_class(),
        unreal.Vector(*POSITION_CM),
        unreal.Rotator(pitch=0, yaw=0, roll=0),
    )
    assert actor, "Could not spawn AGV Blueprint"
    actor.set_actor_label(ACTOR_LABEL)
    actor.set_folder_path("Vehicles/AGV")
    actor.set_editor_property("tags", ["LogisticsWarehouse", "TwinId=" + ACTOR_LABEL, "Category=Vehicles"])
    component = actor.get_component_by_class(unreal.StaticMeshComponent)
    assert component and component.static_mesh == mesh, "Blueprint default mesh was not retained"
    assert component.get_editor_property("mobility") == unreal.ComponentMobility.MOVABLE
    origin, extent = actor.get_actor_bounds(False)
    size = [float(extent.x) * 2, float(extent.y) * 2, float(extent.z) * 2]
    for axis, (actual, expected) in enumerate(zip(size, expected_size)):
        assert abs(actual - expected) <= max(1.0, expected * 0.01), "Import size mismatch on axis %d: %s != %s cm" % (axis, actual, expected)
    bottom = float(origin.z - extent.z)
    assert abs(bottom - POSITION_CM[2]) < 0.5, "Imported model must rest near Z=8 cm"

    camera_position = unreal.Vector(-3000, 4920, 220)
    camera_rotation = unreal.MathLibrary.find_look_at_rotation(camera_position, unreal.Vector(-2700, 4700, 60))
    camera = cameras[0] if cameras else actors.spawn_actor_from_class(unreal.CameraActor, camera_position, camera_rotation)
    assert camera, "Could not create AGV camera"
    camera_component = camera.get_component_by_class(unreal.CameraComponent)
    assert camera_component, "Existing AGV camera label does not identify a CameraActor"
    camera.set_actor_label(CAMERA_LABEL)
    camera.set_folder_path("Cameras")
    camera.set_actor_location(camera_position, False, False)
    camera.set_actor_rotation(camera_rotation, False)
    camera_component.set_field_of_view(35.0)
    camera_component.set_editor_property("constrain_aspect_ratio", False)
    camera.set_editor_property("tags", ["LogisticsWarehouse", "TwinId=" + CAMERA_LABEL])
    unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).set_level_viewport_camera_info(camera_position, camera_rotation)
    actors.set_selected_level_actors([actor])
    assert levels.save_current_level(), "Could not save warehouse map"
    assert lib.save_directory(DEST, only_if_is_dirty=False, recursive=True), "Could not save AGV asset directory"

    record = {
        "id": ACTOR_LABEL,
        "category": "Vehicles/AGV",
        "mesh": "SM_AGV_Reference",
        "position_m": [-27, 47, 0.08],
        "yaw": 0,
    }
    updated_registry = upsert_record(registry, record)
    REGISTRY.write_text(json.dumps(updated_registry, indent=2), encoding="utf-8")
    result = {
        "success": True,
        "mesh": mesh.get_path_name(),
        "blueprint": BLUEPRINT_PATH,
        "blueprint_compiled": True,
        "map": MAP,
        "actor": actor.get_path_name(),
        "actor_label": ACTOR_LABEL,
        "position_cm": list(POSITION_CM),
        "size_cm": size,
        "expected_size_cm": expected_size,
        "ground_z_cm": bottom,
        "material_count": len(materials),
        "material_slot_count": len(slots),
        "material_slots": slot_names,
        "source_parts": len(manifest["source_parts"]),
        "nominal_length_m": manifest["nominal_length_m"],
        "camera": camera.get_path_name(),
        "registry_entry": record,
    }
    REPORT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    unreal.log("AGV_REFERENCE_IMPORT_COMPLETE " + json.dumps(result))


REPORT.parent.mkdir(parents=True, exist_ok=True)
try:
    main()
except Exception:
    REPORT.write_text(json.dumps({"success": False, "error": traceback.format_exc()}, indent=2), encoding="utf-8")
    raise
