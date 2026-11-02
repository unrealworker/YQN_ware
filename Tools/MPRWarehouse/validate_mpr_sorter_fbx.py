"""Isolated Blender FBX roundtrip: geometry, origin, slots, bounds and LODs."""
import bpy,json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'SourceAssets/MPR/equipment'
results=[]
for manifest_name in ['sorter_manifest.json','sorter_variants_manifest.json']:
 manifest=json.loads((OUT/manifest_name).read_text(encoding='utf8'))
 for spec in manifest['meshes']:
  bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
  bpy.ops.import_scene.fbx(filepath=spec['fbx'])
  meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
  assert len(meshes)==1,(spec['name'],len(meshes))
  obj=meshes[0];obj.data.calc_loop_triangles()
  actual_triangles=len(obj.data.loop_triangles)
  roles=[m.name.removeprefix('M_Zcool_').split('.')[0] for m in obj.data.materials]
  assert roles==spec['material_roles'],(spec['name'],roles)
  assert actual_triangles==spec['triangles']
  from mathutils import Vector
  pts=[obj.matrix_world@Vector(p) for p in obj.bound_box]
  actual_bounds=[[min(p[i] for p in pts),max(p[i] for p in pts)] for i in range(3)]
  error=max(abs(actual_bounds[i][j]-spec['bounds_m'][i][j]) for i in range(3) for j in range(2))
  assert error<.0001,(spec['name'],error,actual_bounds)
  assert obj.location.length<.0001,(spec['name'],tuple(obj.location))
  assert all(math.isfinite(c) for v in obj.data.vertices for c in v.co)
  results.append({'name':spec['name'],'triangles':actual_triangles,'material_slots':len(roles),'bounds_max_error_m':error,'mesh_objects':1,'status':'passed'})
(OUT/'sorter_fbx_validation.json').write_text(json.dumps({'status':'passed','checks':results},indent=2),encoding='utf8')
print('MPR_SORTER_FBX_ROUNDTRIP_PASSED '+str(len(results)))
