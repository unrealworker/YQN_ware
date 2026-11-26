"""Export the actual GHS variant-0 tree for MPR, without editing either scene.

Run in a private Blender process. Reuses park_vegetation.build_tree unchanged;
only one uniform scale adapts the GHS crown to the existing MPR planting radius.
All foliage remains in LeafMid; unused slots retain MPR's material-slot contract.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'Scripts/ghs/park_vegetation.py'
OUT = ROOT / 'SourceAssets/MPR/ghs_tree_reuse'
NAME = 'SM_MPR_GHS_Tree'
TARGET_RADIUS_M = 6.4180411992666615
OLD_MPR_HEIGHT_M = 15.8644437789917
SLOTS = ['Trunk', 'LeafMid', 'LeafLight', 'LeafShade']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bounds(geo):
    return [[min(v.co[i] for v in geo.vertices), max(v.co[i] for v in geo.vertices)]
            for i in range(3)]


def main():
    sys.path.insert(0, str(SOURCE.parent))
    from park_vegetation import build_tree, PALETTE

    parts = []
    source_meta = build_tree({'mesh': lambda role, vertices, faces:
                             parts.append((role, vertices, faces))},
                            0., 0., size=1., variant=0, base_z=0.)
    assert len(parts) == 9 and source_meta['triangles'] == 1856
    assert set(p[0] for p in parts) == {'Trunk', 'Trees'}
    uniform_scale = TARGET_RADIUS_M / source_meta['radius_m']
    vertices, faces, face_slots = [], [], []
    for role, source_vertices, source_faces in parts:
        offset = len(vertices)
        # Same source UV -> Blender reflection as build_park_geometry.mesh.
        vertices.extend((x * uniform_scale, -y * uniform_scale, z * uniform_scale)
                        for x, y, z in source_vertices)
        faces.extend(tuple(offset + i for i in reversed(face)) for face in source_faces)
        face_slots.extend([0 if role == 'Trunk' else 1] * len(source_faces))
    # GHS's leaning trunk has a tilted base cap. Seat its lowest point on Z=0.
    root_offset_m = -min(v[2] for v in vertices)
    vertices = [(x, y, z + root_offset_m) for x, y, z in vertices]

    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1.
    geo = bpy.data.meshes.new(NAME)
    geo.from_pydata(vertices, [], faces)
    geo.update()
    assert not geo.validate()
    for slot, source_role in zip(SLOTS, ['Trunk', 'Trees', 'TreesLight', 'TreesDark']):
        mat = bpy.data.materials.new(slot)
        mat.diffuse_color = (*PALETTE[source_role], 1.)
        mat.use_nodes = True
        shader = mat.node_tree.nodes.get('Principled BSDF')
        shader.inputs['Base Color'].default_value = (*PALETTE[source_role], 1.)
        shader.inputs['Roughness'].default_value = .9 if slot == 'Trunk' else .86
        geo.materials.append(mat)
    for poly, slot in zip(geo.polygons, face_slots):
        poly.material_index = slot
        poly.use_smooth = slot != 0
    geo.calc_loop_triangles()
    assert len(geo.loop_triangles) == 1856
    actual_bounds = bounds(geo)
    radius = max(math.hypot(v.co.x, v.co.y) for v in geo.vertices)
    assert abs(radius - TARGET_RADIUS_M) < 1e-5
    assert abs(actual_bounds[2][0]) < 1e-7
    assert actual_bounds[2][1] <= OLD_MPR_HEIGHT_M
    obj = bpy.data.objects.new(NAME, geo)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    OUT.mkdir(parents=True, exist_ok=True)
    fbx = OUT / (NAME + '.fbx')
    bpy.ops.export_scene.fbx(filepath=str(fbx), use_selection=True,
        object_types={'MESH'}, axis_forward='-Y', axis_up='Z',
        apply_unit_scale=True, bake_anim=False, mesh_smooth_type='FACE',
        use_mesh_modifiers=True, add_leaf_bones=False, path_mode='AUTO')

    expected_vertex_count = len(geo.vertices)
    expected_triangle_slots = [sum(t.material_index == i for t in geo.loop_triangles)
                               for i in range(4)]
    # Reimport the exported payload to verify coordinates, slots and topology.
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.fbx(filepath=str(fbx), use_custom_normals=True)
    imported = [o for o in bpy.context.selected_objects if o.type == 'MESH']
    assert len(imported) == 1
    restored = imported[0]
    roundtrip = restored.data
    roundtrip.calc_loop_triangles()
    assert len(roundtrip.loop_triangles) == 1856
    assert len(roundtrip.vertices) == expected_vertex_count
    actual_slots = [m.name.split('.')[0] for m in roundtrip.materials]
    assert actual_slots == SLOTS, actual_slots
    errors = [abs(a - b) for aa, bb in zip(actual_bounds, bounds(roundtrip))
              for a, b in zip(aa, bb)]
    assert max(errors) < 1e-5
    assert all(abs(v - 1.) < 1e-6 for v in restored.scale)
    assert all(abs(v) < 1e-6 for v in restored.location)
    assert [sum(t.material_index == i for t in roundtrip.loop_triangles)
            for i in range(4)] == expected_triangle_slots

    manifest = dict(success=True, name=NAME, fbx=fbx.relative_to(ROOT).as_posix(),
        fbx_sha256=sha(fbx), source_generator=SOURCE.relative_to(ROOT).as_posix(),
        source_sha256=sha(SOURCE), source_palette='SourceAssets/GHS/Park/reference_style.json',
        source_palette_sha256=sha(ROOT / 'SourceAssets/GHS/Park/reference_style.json'),
        source_function='build_tree', source_variant=0, source_height_m=source_meta['height_m'],
        source_radius_m=source_meta['radius_m'], source_parts=len(parts),
        uniform_scale=uniform_scale, vertices=expected_vertex_count, triangles=1856,
        slot_names=SLOTS, material_triangle_counts=dict(zip(SLOTS, expected_triangle_slots)),
        bounds_blender_m=actual_bounds,
        bounds_ue_cm=dict(min=[actual_bounds[0][0]*100, -actual_bounds[1][1]*100, actual_bounds[2][0]*100],
                          max=[actual_bounds[0][1]*100, -actual_bounds[1][0]*100, actual_bounds[2][1]*100]),
        radial_extent_m=radius, height_m=actual_bounds[2][1], ground_origin=True,
        root_seating_offset_m=root_offset_m,
        previous_mpr_height_m=OLD_MPR_HEIGHT_M, previous_mpr_triangles=11292,
        triangle_reduction_percent=100*(1-1856/11292),
        roundtrip_max_bounds_error_m=max(errors), roundtrip_slots=actual_slots,
        shape_policy='Unmodified GHS variant 0 geometry, uniformly scaled to the prior MPR crown radius; height is lower to preserve GHS proportions.',
        material_policy='Trunk uses slot 0; all five GHS crown lobes use LeafMid slot 1; slots 2 and 3 are retained without triangles for the existing MPR four-slot bindings.',
        source_scene_modified=False)
    (OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('MPR_GHS_TREE_REUSE_READY', json.dumps(manifest, ensure_ascii=False))


if __name__ == '__main__':
    main()
