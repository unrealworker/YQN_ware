"""Shared Blender asset helpers. All dimensions are metres."""
import bpy
import json
import math
from pathlib import Path
from mathutils import Vector

OUT = Path(r"D:\UEPro\Test\SourceAssets\LogisticsWarehouse")
OUT.mkdir(parents=True, exist_ok=True)
MATERIALS = {}

def reset():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0

def material(name, color, roughness=0.6, metallic=0.0, **metadata):
    name = "M_WH_" + name if not name.startswith("M_WH_") else name
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.diffuse_color = (*color[:3], 1.0)
    mat.use_nodes = True
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*color[:3], 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    MATERIALS[name] = dict(name=name, base_color=[*color[:3], 1.0], roughness=roughness, metallic=metallic, **metadata)
    return mat

def box(name, loc, size, mat, bevel=0.02):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    if bevel:
        mod = obj.modifiers.new("Edge bevel", "BEVEL")
        mod.width = min(bevel, min(size) * 0.18)
        mod.segments = 2
        normal = obj.modifiers.new("Weighted normals", "WEIGHTED_NORMAL")
    return obj

def cylinder(name, loc, radius, depth, mat, vertices=16, rotation=None):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc)
    obj = bpy.context.object
    obj.name = name
    if rotation:
        obj.rotation_euler = rotation
    obj.data.materials.append(mat)
    for face in obj.data.polygons:
        face.use_smooth = len(face.vertices) == 4
    return obj

def beam(name, a, b, radius, mat, vertices=10):
    a, b = Vector(a), Vector(b)
    obj = cylinder(name, (a+b)/2, radius, (b-a).length, mat, vertices)
    obj.rotation_euler = (b-a).to_track_quat("Z", "Y").to_euler()
    return obj

def mesh(name, verts, faces, mat):
    data = bpy.data.meshes.new(name)
    data.from_pydata(verts, [], faces)
    data.update()
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    data.materials.append(mat)
    return obj

def export_asset(name, objects=None):
    objects = list(objects) if objects is not None else [o for o in bpy.context.scene.objects if o.type == "MESH"]
    assert objects
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.convert(target="MESH")
    bpy.ops.object.join()
    obj = bpy.context.object
    obj.name = name
    bpy.context.scene.cursor.location = (0, 0, 0)
    bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if not obj.data.uv_layers:
        obj.data.uv_layers.new(name="UVMap")
    # Cube projection keeps untextured detail meshes valid for tangent generation.
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.cube_project(cube_size=2.0)
    bpy.ops.object.mode_set(mode="OBJECT")
    path = OUT / (name + ".fbx")
    bpy.ops.export_scene.fbx(filepath=str(path), use_selection=True, object_types={"MESH"},
        axis_forward="-Y", axis_up="Z", apply_unit_scale=True, bake_anim=False,
        mesh_smooth_type="FACE", use_mesh_modifiers=True, add_leaf_bones=False)
    bounds = [[min(v.co[i] for v in obj.data.vertices), max(v.co[i] for v in obj.data.vertices)] for i in range(3)]
    result = dict(name=name, fbx=str(path), slots=[m.name for m in obj.data.materials], bounds_m=bounds,
                  vertices=len(obj.data.vertices), polygons=len(obj.data.polygons))
    bpy.data.objects.remove(obj, do_unlink=True)
    return result

def save_manifest(filename, meshes):
    used = {slot for asset in meshes for slot in asset["slots"]}
    path = OUT / filename
    path.write_text(json.dumps(dict(meshes=meshes, materials=[MATERIALS[k] for k in sorted(used)]), indent=2), encoding="utf-8")
    print("WAREHOUSE_ASSETS_COMPLETE " + str(path))
