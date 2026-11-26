"""Extract movable pallet loads from the exact CAD24 A1 capacity-slot triangles."""
from collections import Counter
from itertools import product
import hashlib
import json
from pathlib import Path
import re
import sys

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]
RACKS = ROOT / 'Saved/GHS_CAD24/Models'
OUT = ROOT / 'SourceAssets/GHS/OrderReplay'
MATERIALS = ('Pallet', 'Cargo', 'CargoEdges', 'Detail')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_mesh(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(path))
    [obj] = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    obj.data.calc_loop_triangles()
    return obj


def faces(obj, slot=None):
    mesh = obj.data
    uv = mesh.uv_layers['UVMap']
    capacity = mesh.uv_layers.get('CapacitySlot')
    if slot is not None:
        assert capacity
    rotation = obj.matrix_world.to_3x3().inverted().transposed()
    for tri in mesh.loop_triangles:
        loops = tri.loops
        if slot is not None:
            values = {round(capacity.data[i].uv.x) for i in loops}
            assert len(values) == 1
            if slot not in values:
                continue
        material = re.sub(r'\.\d{3}$', '', mesh.materials[tri.material_index].name)
        assert material.removeprefix('M_GHS_CADRack_') in MATERIALS
        yield (material, tuple(obj.matrix_world @ mesh.vertices[i].co for i in tri.vertices),
               tuple(uv.data[i].uv.copy() for i in loops),
               tuple((rotation @ mesh.corner_normals[i].vector).normalized() for i in loops))


def to_load(p):
    return Vector((p.y, -p.x, p.z))


def to_rack(p):
    return Vector((-p.y, p.x, p.z))


def bounds(points):
    return [[min(p[i] for p in points), max(p[i] for p in points)] for i in range(3)]


def export(name, triangles, pivot):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mesh = bpy.data.meshes.new(name)
    vertices, indices, lookup = [], [], {}
    for _, coords, _, _ in triangles:
        face = []
        for coord in coords:
            key = tuple(coord)
            if key not in lookup:
                lookup[key] = len(vertices)
                vertices.append(to_load(coord - pivot))
            face.append(lookup[key])
        indices.append(face)
    mesh.from_pydata(vertices, [], indices)
    slots = sorted({t[0] for t in triangles}, key=lambda s: MATERIALS.index(s.removeprefix('M_GHS_CADRack_')))
    for slot in slots:
        mesh.materials.append(bpy.data.materials.new(slot))
    uv = mesh.uv_layers.new(name='UVMap')
    normals = []
    for face,(material, _, uvs, corner_normals) in zip(mesh.polygons,triangles):
        face.material_index = slots.index(material)
        face.use_smooth = True
        for i, value in zip(face.loop_indices, uvs):
            uv.data[i].uv = value
        normals.extend(to_load(n) for n in corner_normals)
    mesh.normals_split_custom_set(normals)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    path = OUT/(name + '.fbx')
    bpy.ops.export_scene.fbx(filepath=str(path), use_selection=True, object_types={'MESH'},
                             axis_forward='-Y', axis_up='Z', apply_unit_scale=True,
                             bake_space_transform=False, add_leaf_bones=False)
    return path


def triangle_signature(rows, point):
    # Preserve the material assigned to each triangle and all three face corners.
    return Counter((material,tuple(sorted(tuple(round(v,4) for v in point(p)) for p in coords)))
                   for material, coords, _, _ in rows)


def verify(path, reference, pivot):
    obj = read_mesh(path)
    extracted = list(faces(obj))
    assert triangle_signature(reference, lambda p:p) == triangle_signature(extracted, lambda p:to_rack(p)+pivot), path
    local = bounds([p for _, coords, _, _ in extracted for p in coords])
    original = bounds([p for _, coords, _, _ in reference for p in coords])
    # At UE rack yaw 0 and load yaw -90, convert the two handednesses explicitly.
    source_corners = [Vector((x,-y,z)) for x,y,z in product(*original)]
    load_corners = [Vector((pivot.x-y, -pivot.y-x, pivot.z+z)) for x,y,z in product(*local)]
    error = max(min((p-q).length for q in source_corners) for p in load_corners)
    assert error < .00001, (path,error)
    return local, [m.name for m in obj.data.materials]


def main():
    mesh_index = RACKS/'meshes.json'
    cad_hash = digest(ROOT/'SourceAssets/GHS/CAD24/racks.json')
    if (not mesh_index.exists() or not (RACKS/'SM_GHS_V2Rack_CAD24_A1_Capacity.fbx').exists()
            or json.loads(mesh_index.read_bytes())['cad_sha256']!=cad_hash):
        sys.path.insert(0,str(ROOT/'Scripts/ghs'))
        import build_cad24_racks
        build_cad24_racks.main()
    [rack] = [r for r in json.loads(mesh_index.read_bytes())['meshes'] if r['variant']=='A1']
    source = RACKS/(rack['name']+'.fbx')
    assert digest(source)==rack['fbx_sha256']
    manifest_path = OUT/'replay_assets.json'
    manifest = json.loads(manifest_path.read_bytes())
    existing = {r['name']:r for r in manifest['meshes']}
    for level,column in ((2,2),(1,2),(1,3)):
        [slot] = [s for s in rack['slots'] if (s['level'],s['column'])==(level,column)]
        [stack] = [s for s in rack['cargo_stacks'] if (s['level'],s['column'])==(level,column)]
        name = f'SM_Replay_CargoRack_A1_L{level}_C{column}'
        pivot = Vector((stack['pallet_center_x_m'],0,stack['base_z_m']))
        original = list(faces(read_mesh(source),slot['index']))
        assert original
        path = OUT/(name+'.fbx')
        previous = existing.get(name,{})
        if not (path.exists() and previous.get('source_fbx_sha256')==rack['fbx_sha256'] and previous.get('sha256')==digest(path)):
            export(name,original,pivot)
        extent, slots = verify(path,original,pivot)
        entry = dict(name=name,fbx=str(path),slots=slots,bounds_m=extent,source_parts=1,
                     triangles=len(original),sha256=digest(path),source_fbx_sha256=rack['fbx_sha256'],
                     source_capacity_slot=slot['index'])
        if name in existing:
            previous.update(entry)
        else:
            manifest['meshes'].append(entry)
        print('RACK_LOAD_VERIFIED',name,len(original),entry['sha256'],slots,flush=True)
    manifest_path.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')


if __name__=='__main__':
    main()
