"""Read the V2 exported FBX files back into a separate background Blender."""
from pathlib import Path
import hashlib
import json
import math
import bpy

OUT = Path(__file__).resolve().parent
data = json.loads((OUT / 'refined_rack_cargo.json').read_text(encoding='utf-8'))
results = []
for record in data['meshes']:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    fbx = Path(record['fbx'])
    assert hashlib.sha256(fbx.read_bytes()).hexdigest() == record['fbx_sha256']
    bpy.ops.import_scene.fbx(filepath=str(fbx))
    objects = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
    assert len(objects) == 1, (record['name'], len(objects))
    obj = objects[0]
    assert obj.matrix_world.determinant() > 0
    points = [obj.matrix_world @ v.co for v in obj.data.vertices]
    bounds = [[min(p[i] for p in points), max(p[i] for p in points)] for i in range(3)]
    maximum_error = max(abs(a - b) for axis, expected in zip(bounds, record['bounds_m']) for a, b in zip(axis, expected))
    assert maximum_error < .00002, (record['name'], bounds, record['bounds_m'])
    assert len(obj.data.materials) == 7
    roles = [m.name.replace('M_GHS_CADRack_', '') for m in obj.data.materials]
    assert roles == record['slot_roles'], (record['name'], roles)
    assert all(math.isfinite(x) for p in points for x in p)
    obj.data.calc_loop_triangles()
    assert len(obj.data.loop_triangles) == record['triangles']
    assert obj.location.length < .00002
    results.append(dict(name=record['name'], bounds_m=bounds, maximum_bounds_error_m=maximum_error,
                        material_roles=roles, triangles=len(obj.data.loop_triangles),
                        positive_transform_determinant=True, origin_floor_center=True,
                        sha256_verified=True))
report = dict(passed=True, checked_fbx_count=len(results), checks=results)
(OUT / 'fbx_roundtrip_validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print('V2_FBX_ROUNDTRIP_PASS', len(results), max(r['maximum_bounds_error_m'] for r in results), flush=True)
