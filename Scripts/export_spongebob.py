"""Export the character from the source blend without changing the original."""
import json
import re
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(r"D:\UEPro\Test")
OUT = ROOT / "SourceAssets" / "SpongeBob"
OUT.mkdir(parents=True, exist_ok=True)
scene = bpy.context.scene
collection = bpy.data.collections.get("3D | Character")
assert collection, "Character collection missing"
objects = [o for o in collection.all_objects if o.type in {"MESH", "CURVE", "SURFACE", "FONT"}]
assert objects, "No character geometry"
source_names = [o.name for o in objects]

# Resolve curves and modifiers before combining; this preserves eyelashes and seams.
bpy.ops.object.select_all(action="DESELECT")
for obj in objects:
    obj.hide_set(False)
    obj.hide_viewport = False
    obj.select_set(True)
bpy.context.view_layer.objects.active = objects[0]
bpy.ops.object.convert(target="MESH")
objects = list(bpy.context.selected_objects)

materials = sorted({m for o in objects for m in o.data.materials if m}, key=lambda m: m.name)
manifest = {"source": r"D:\BlenderModel\spongebob-3d.blend", "source_parts": source_names, "materials": []}
for mat in materials:
    old_name = mat.name
    mat.name = "M_SB_" + re.sub(r"[^A-Za-z0-9]+", "_", old_name.split(" | ")[-1]).strip("_")
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    entry = {"name": mat.name, "source_name": old_name,
             "base_color": list(bsdf.inputs["Base Color"].default_value),
             "roughness": bsdf.inputs["Roughness"].default_value,
             "metallic": bsdf.inputs["Metallic"].default_value}
    if bsdf.inputs["Base Color"].is_linked:
        targets = [o for o in objects if mat.name in o.data.materials]
        assert len(targets) == 1, "Procedural bake expects one body object"
        body = targets[0]
        bpy.ops.object.select_all(action="DESELECT")
        body.select_set(True)
        bpy.context.view_layer.objects.active = body
        if not body.data.uv_layers:
            body.data.uv_layers.new(name="UVMap")
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(angle_limit=1.1519173, island_margin=0.015)
        bpy.ops.object.mode_set(mode="OBJECT")
        image = bpy.data.images.new("T_SB_LemonSponge_BaseColor", width=2048, height=2048, alpha=False)
        image.generated_color = (1.0, 0.9, 0.1, 1.0)
        for body_mat in body.data.materials:
            node = body_mat.node_tree.nodes.new("ShaderNodeTexImage")
            node.image = image
            body_mat.node_tree.nodes.active = node
        scene.render.engine = "CYCLES"
        scene.cycles.device = "CPU"
        scene.cycles.samples = 1
        scene.render.bake.use_pass_direct = False
        scene.render.bake.use_pass_indirect = False
        scene.render.bake.use_pass_color = True
        scene.render.bake.margin = 16
        bpy.ops.object.bake(type="DIFFUSE")
        image.filepath_raw = str(OUT / "T_SB_LemonSponge_BaseColor.png")
        image.file_format = "PNG"
        image.save()
        entry["texture"] = image.filepath_raw
    manifest["materials"].append(entry)

# Converted curves may have no usable UVs. Give them real UVs for UE tangents.
for obj in objects:
    uv = obj.data.uv_layers.active
    coordinates = [v.uv for v in uv.data] if uv else []
    if coordinates and max(v.x for v in coordinates) - min(v.x for v in coordinates) > 0.00001 and max(v.y for v in coordinates) - min(v.y for v in coordinates) > 0.00001:
        continue
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    if not uv:
        obj.data.uv_layers.new(name="UVMap")
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=1.1519173, island_margin=0.015)
    bpy.ops.object.mode_set(mode="OBJECT")

bpy.ops.object.select_all(action="DESELECT")
for obj in objects:
    obj.select_set(True)
bpy.context.view_layer.objects.active = objects[0]
bpy.ops.object.join()
combined = bpy.context.object
combined.name = "SM_SpongeBob"
scene.cursor.location = (0, 0, 0)
bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
points = [combined.matrix_world @ Vector(v) for v in combined.bound_box]
minimum = Vector(tuple(min(p[i] for p in points) for i in range(3)))
maximum = Vector(tuple(max(p[i] for p in points) for i in range(3)))
height = maximum.z - minimum.z
# A 180 cm tall reusable actor, origin at the centre of its feet.
factor = 1.8 / height
centre = Vector(((minimum.x + maximum.x) / 2, (minimum.y + maximum.y) / 2, minimum.z))
for vertex in combined.data.vertices:
    vertex.co = (vertex.co - centre) * factor
combined.data.update()
manifest.update({"source_height_metres": height, "height_cm": 180,
                 "vertices": len(combined.data.vertices), "polygons": len(combined.data.polygons),
                 "slots": [m.name for m in combined.data.materials]})
bpy.ops.export_scene.fbx(filepath=str(OUT / "SM_SpongeBob.fbx"), use_selection=True,
                         object_types={"MESH"}, axis_forward="-Y", axis_up="Z",
                         apply_unit_scale=True, apply_scale_options="FBX_SCALE_NONE",
                         use_mesh_modifiers=True, mesh_smooth_type="FACE", bake_anim=False,
                         add_leaf_bones=False, path_mode="AUTO")
(OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print("EXPORT_COMPLETE " + json.dumps({k: v for k, v in manifest.items() if k not in {"materials", "source_parts", "slots"}}))
