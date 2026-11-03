"""FBX roundtrip verification of the site partition meshes, no source mutations."""
import bpy,json,math,hashlib
from pathlib import Path
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'SourceAssets/MPR/reference_v4'
m=json.loads((OUT/'site/manifest.json').read_text(encoding='utf8'));checks=[]
for row in m['meshes']:
 bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
 for material in list(bpy.data.materials):bpy.data.materials.remove(material)
 path=ROOT/row['fbx']
 if row.get('sha256'):assert hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256'],row['name']
 bpy.ops.import_scene.fbx(filepath=str(path))
 objects=[o for o in bpy.context.scene.objects if o.type=='MESH'];assert len(objects)==1,(row['name'],len(objects))
 ob=objects[0];ob.data.calc_loop_triangles()
 triangle_match=len(ob.data.loop_triangles)==row['triangles']
 assert [a.name for a in ob.data.materials]==row['material_roles'],(row['name'],[a.name for a in ob.data.materials])
 points=[ob.matrix_world@Vector(p) for p in ob.bound_box]
 error=max(abs([min(v[i] for v in points),max(v[i] for v in points)][j]-row['bounds_m'][i][j]) for i in range(3) for j in range(2))
 assert error<.0003,(row['name'],error)
 assert len(ob.data.uv_layers)==1,row['name']
 assert all(math.isfinite(c) for v in ob.data.vertices for c in v.co)
 checks.append(dict(name=row['name'],triangles=len(ob.data.loop_triangles),source_triangles=row['triangles'],triangle_match=triangle_match,
                    material_slots=len(row['material_roles']),bounds_error_m=error,minimum_triangle_area_m2=min(t.area for t in ob.data.loop_triangles)))
out=OUT/'validation_blender';out.mkdir(parents=True,exist_ok=True)
(out/'site_fbx_validation.json').write_text(json.dumps(dict(success=all(r['triangle_match'] for r in checks),mesh_count=len(checks),checks=checks,
 source_manifest_sha256=hashlib.sha256((OUT/'site/manifest.json').read_bytes()).hexdigest(),max_bounds_error_m=max(r['bounds_error_m'] for r in checks),
 validation_boundary='Offline FBX geometry/material/unit/UV verification only, not UE or visual acceptance.'),indent=2),encoding='utf8')
print('MPR_REFERENCE_SITE_FBX_RESULT',len(checks),sum(r['triangles'] for r in checks),max(r['bounds_error_m'] for r in checks),[r for r in checks if not r['triangle_match']])
