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
 fade_audit=None
 if row.get('vertex_color_fade'):
  colors=ob.data.color_attributes.get('EdgeFade') or ob.data.color_attributes.active_color
  assert colors and len(colors.data)>0,(row['name'],'Missing EdgeFade after FBX roundtrip')
  values=[tuple(c.color) for c in colors.data]
  assert all(all(math.isfinite(v) and -.0001<=v<=1.0001 for v in c) for c in values)
  lo=min(c[0] for c in values);hi=max(c[0] for c in values)
  assert lo<.005 and hi>.99,(row['name'],'Fade must include both road and grass endpoints',lo,hi)
  assert max(max(c[:3])-min(c[:3]) for c in values)<.005,(row['name'],'RGB fade channel mismatch')
  fade_audit=dict(attribute=colors.name,domain=colors.domain,color_count=len(values),range=[lo,hi],intermediate_color_count=sum(.005<c[0]<.99 for c in values))
 checks.append(dict(name=row['name'],triangles=len(ob.data.loop_triangles),source_triangles=row['triangles'],triangle_match=triangle_match,
                    material_slots=len(row['material_roles']),bounds_error_m=error,minimum_triangle_area_m2=min(t.area for t in ob.data.loop_triangles),vertex_color_fade=fade_audit))
out=OUT/'validation_blender';out.mkdir(parents=True,exist_ok=True)
(out/'site_fbx_validation.json').write_text(json.dumps(dict(success=all(r['triangle_match'] for r in checks),mesh_count=len(checks),checks=checks,
 source_manifest_sha256=hashlib.sha256((OUT/'site/manifest.json').read_bytes()).hexdigest(),max_bounds_error_m=max(r['bounds_error_m'] for r in checks),
 validation_boundary='Offline FBX geometry/material/unit/UV verification only, not UE or visual acceptance.'),indent=2),encoding='utf8')
print('MPR_REFERENCE_SITE_FBX_RESULT',len(checks),sum(r['triangles'] for r in checks),max(r['bounds_error_m'] for r in checks),[r for r in checks if not r['triangle_match']])
