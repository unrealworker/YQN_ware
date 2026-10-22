"""Independent background-Blender round-trip check of the exported facade."""
from pathlib import Path
import hashlib
import json
import bpy
import bmesh

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
manifest = json.loads((OUT / 'facade_manifest.json').read_text(encoding='utf-8'))
expected = manifest['mesh']
layout_path = OUT / 'facade_layout.json'
layout = json.loads(layout_path.read_text(encoding='utf-8-sig'))
assert hashlib.sha256(layout_path.read_bytes()).hexdigest() == manifest['layout_sha256']
assert layout['groups'] == manifest['additional_groups']
assert manifest['bay_count'] == 8 + sum(g['bay_count'] for g in layout['groups'])
assert manifest['pane_count'] == sum(b['pane_count'] for b in manifest['bays'])
assert manifest['checks']['original_corner_part_count'] == 243
assert manifest['checks']['original_corner_geometry_preserved']
assert manifest['checks']['door_overlap_volume_m3'] < 1e-8
assert manifest['checks']['loading_door_overlap_area_m2'] < 1e-8
assert manifest['materials']['Glass']['color_linear'] == [.027, .085, .155]
assert hashlib.sha256((OUT / 'SM_GHS_OfficeGlassFacade.fbx').read_bytes()).hexdigest() == expected['sha256']
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
bpy.ops.import_scene.fbx(filepath=str(OUT / 'SM_GHS_OfficeGlassFacade.fbx'))
objects = list(bpy.context.scene.objects)
assert len(objects) == 1 and objects[0].type == 'MESH', [(o.name, o.type) for o in objects]
ob = objects[0]
mesh = ob.data
mesh.calc_loop_triangles()
assert ob.name == expected['name']
assert len(mesh.vertices) == expected['vertices']
assert len(mesh.loop_triangles) == expected['triangles']
assert len(mesh.loop_triangles) < manifest['checks']['triangle_budget'] == 30000
assert [m.name for m in mesh.materials] == expected['slot_names']
assert set(p.material_index for p in mesh.polygons) == set(range(5))
coords = [ob.matrix_world @ v.co for v in mesh.vertices]
bounds = dict(min=[min(p.x for p in coords)*100, -max(p.y for p in coords)*100, min(p.z for p in coords)*100],
              max=[max(p.x for p in coords)*100, -min(p.y for p in coords)*100, max(p.z for p in coords)*100])
max_error = max(abs(bounds[k][i] - expected['bounds_ue_cm'][k][i]) for k in ('min', 'max') for i in range(3))
assert max_error < .01, (max_error, bounds)
bm = bmesh.new()
bm.from_mesh(mesh)
assert all(e.is_manifold for e in bm.edges)
assert all(f.calc_area() > 1e-10 for f in bm.faces)
assert bm.calc_volume(signed=True) > 0
bm.free()
assert all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == h
           for p, h in manifest['checks']['source_hashes'].items())
result = dict(passed=True, mesh_count=1, object_name=ob.name, vertices=len(mesh.vertices),
              triangles=len(mesh.loop_triangles), material_slots=[m.name for m in mesh.materials],
              bounds_ue_cm=bounds, maximum_bounds_roundtrip_error_cm=max_error,
              manifold=True, nondegenerate_faces=True, shared_source_hashes_unchanged=True,
              group_count=2+len(layout['groups']),bay_count=manifest['bay_count'],pane_count=manifest['pane_count'],
              original_corner_preserved=True,door_overlap_volume_m3=manifest['checks']['door_overlap_volume_m3'],
              glass_color_linear=manifest['materials']['Glass']['color_linear'])
(OUT / 'fbx_roundtrip_verification.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
print('GHS_OFFICE_FACADE_FBX_VERIFIED ' + json.dumps(result))
