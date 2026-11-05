"""Read-only geometry diagnostics for site export / shell tangent warnings."""
import bpy,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'SourceAssets/MPR/reference_v3'
result={}
for path,names in [(OUT/'site/MPR_ReferenceSite.blend',['SM_MPR3_Site_Near_Lawns']),
                   (OUT/'architecture/mpr_reference_shell.blend',None)]:
 with bpy.data.libraries.load(str(path),link=False) as (source,target):
  target.objects=names or [n for n in source.objects if n.startswith('SM_MPR3_RoofEdge_')]
 for ob in target.objects:
  data=ob.data;data.calc_loop_triangles();uv=data.uv_layers[0]
  areas=[];ratios=[]
  for t in data.loop_triangles:
   ps=[uv.data[i].uv for i in t.loops]
   area=abs((ps[1].x-ps[0].x)*(ps[2].y-ps[0].y)-(ps[1].y-ps[0].y)*(ps[2].x-ps[0].x))*.5
   areas.append(area)
   if t.area>1e-18:ratios.append(area/t.area)
  ordered=sorted(data.loop_triangles,key=lambda t:t.area)
  result[ob.name]={'triangles':len(data.loop_triangles),'min_world_area_m2':ordered[0].area,
   'world_degenerate_count':sum(t.area<1e-12 for t in data.loop_triangles),'min_uv_area':min(areas),
   'uv_degenerate_count':sum(a<1e-12 for a in areas),'min_uv_to_world_area_ratio':min(ratios),
   'max_uv_to_world_area_ratio':max(ratios),
   'smallest_world_triangles':[{'area':t.area,'vertices':[list(data.vertices[i].co) for i in t.vertices]} for t in ordered[:2]]}
out=OUT/'validation_blender';out.mkdir(exist_ok=True)
(out/'geometry_audit.json').write_text(json.dumps(result,indent=2),encoding='utf8')
print(json.dumps(result,indent=2))
