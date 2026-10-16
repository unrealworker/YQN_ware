"""Run with UnrealEditor-Cmd -run=pythonscript -script=<this file>."""
import json
import traceback
from pathlib import Path

import unreal

ROOT = Path(r"D:\UEPro\Test")
SOURCE = ROOT / "SourceAssets" / "SpongeBob"
REPORT = ROOT / "Saved" / "SpongeBob_ImportReport.json"
DEST = "/Game/SpongeBob"
MAP = "/Game/Maps/SpongeBobScene"


def main():
    manifest = json.loads((SOURCE / "manifest.json").read_text(encoding="utf-8"))
    assets = unreal.AssetToolsHelpers.get_asset_tools()
    asset_lib = unreal.EditorAssetLibrary
    material_lib = unreal.MaterialEditingLibrary
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    task = unreal.AssetImportTask()
    task.filename = str(SOURCE / "SM_SpongeBob.fbx")
    task.destination_path = DEST + "/Meshes"
    task.destination_name = "SM_SpongeBob"
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
    task.options = options
    assets.import_asset_tasks([task])
    mesh = asset_lib.load_asset(DEST + "/Meshes/SM_SpongeBob")
    assert isinstance(mesh, unreal.StaticMesh), "Static mesh import failed"

    materials = {}
    for item in manifest["materials"]:
        path = DEST + "/Materials"
        mat = asset_lib.load_asset(path + "/" + item["name"]) if asset_lib.does_asset_exist(path + "/" + item["name"]) else assets.create_asset(item["name"], path, unreal.Material, unreal.MaterialFactoryNew())
        material_lib.delete_all_material_expressions(mat)
        if "texture" in item:
            tex_task = unreal.AssetImportTask()
            tex_task.filename = item["texture"]
            tex_task.destination_path = DEST + "/Textures"
            tex_task.automated = True
            tex_task.replace_existing = True
            tex_task.save = True
            assets.import_asset_tasks([tex_task])
            texture = asset_lib.load_asset(DEST + "/Textures/" + Path(item["texture"]).stem)
            assert texture
            color = material_lib.create_material_expression(mat, unreal.MaterialExpressionTextureSample, -350, 0)
            color.set_editor_property("texture", texture)
            material_lib.connect_material_property(color, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)
        else:
            color = material_lib.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector, -350, 0)
            color.set_editor_property("constant", unreal.LinearColor(*item["base_color"]))
            material_lib.connect_material_property(color, "", unreal.MaterialProperty.MP_BASE_COLOR)
        for key, prop in [("roughness", unreal.MaterialProperty.MP_ROUGHNESS), ("metallic", unreal.MaterialProperty.MP_METALLIC)]:
            scalar = material_lib.create_material_expression(mat, unreal.MaterialExpressionConstant, -350, 180 if key == "roughness" else 280)
            scalar.set_editor_property("r", item[key])
            material_lib.connect_material_property(scalar, "", prop)
        material_lib.recompile_material(mat)
        assert asset_lib.save_loaded_asset(mat)
        materials[item["name"]] = mat
    slot_names = []
    for index, slot in enumerate(mesh.get_editor_property("static_materials")):
        name = str(slot.get_editor_property("imported_material_slot_name"))
        if name not in materials:
            name = str(slot.get_editor_property("material_slot_name"))
        assert name in materials, "Unmatched material slot: " + name
        mesh.set_material(index, materials[name])
        slot_names.append(name)
    assert asset_lib.save_loaded_asset(mesh)

    bp_path = DEST + "/Blueprints/BP_SpongeBob"
    if asset_lib.does_asset_exist(bp_path):
        blueprint = asset_lib.load_asset(bp_path)
    else:
        factory = unreal.BlueprintFactory()
        factory.set_editor_property("parent_class", unreal.StaticMeshActor)
        blueprint = assets.create_asset("BP_SpongeBob", DEST + "/Blueprints", unreal.Blueprint, factory)
    unreal.BlueprintEditorLibrary.compile_blueprint(blueprint)
    default_actor = unreal.get_default_object(blueprint.generated_class())
    default_component = default_actor.get_component_by_class(unreal.StaticMeshComponent)
    default_component.set_static_mesh(mesh)
    default_component.set_mobility(unreal.ComponentMobility.MOVABLE)
    unreal.BlueprintEditorLibrary.compile_blueprint(blueprint)
    assert asset_lib.save_loaded_asset(blueprint)

    if asset_lib.does_asset_exist(MAP):
        assert levels.load_level(MAP)
    else:
        assert levels.new_level_from_template(MAP, "/Engine/Maps/Templates/Template_Default")
    for existing in actors.get_all_level_actors():
        if existing.get_actor_label() == "SpongeBob":
            actors.destroy_actor(existing)
    actor = actors.spawn_actor_from_class(blueprint.generated_class(), unreal.Vector(0, 0, 0))
    assert actor
    actor.set_actor_label("SpongeBob")
    actor.set_folder_path("Characters")
    component = actor.get_component_by_class(unreal.StaticMeshComponent)
    assert component.static_mesh == mesh, "Blueprint default mesh did not persist"
    origin, extent = actor.get_actor_bounds(False)
    assert 179 < extent.z * 2 < 181, "Unexpected imported model height: " + str(extent.z * 2)
    camera_pos = unreal.Vector(-180, 420, 160)
    camera_rot = unreal.MathLibrary.find_look_at_rotation(camera_pos, unreal.Vector(0, 0, 90))
    unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).set_level_viewport_camera_info(camera_pos, camera_rot)
    actors.set_selected_level_actors([actor])
    assert levels.save_current_level()
    asset_lib.save_directory(DEST, only_if_is_dirty=False, recursive=True)
    result = {"success": True, "blueprint": bp_path, "blueprint_compiled": True,
              "mesh": mesh.get_path_name(), "map": MAP, "actor": actor.get_path_name(),
              "actor_label": actor.get_actor_label(), "height_cm": extent.z * 2,
              "material_slots": slot_names, "material_count": len(materials),
              "source_parts": len(manifest["source_parts"])}
    REPORT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    unreal.log("SPONGEBOB_IMPORT_COMPLETE " + json.dumps(result))


try:
    main()
except Exception:
    REPORT.write_text(json.dumps({"success": False, "error": traceback.format_exc()}, indent=2), encoding="utf-8")
    raise
