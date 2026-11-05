"""Read supplied Blender geometry without saving or modifying its source."""
import bpy,json,hashlib
from pathlib import Path
from collections import Counter
from mathutils import Vector
ROOT=Path('D:/UEPro/Test');OUT=ROOT/'Saved/MPR/extension_20261104';OUT.mkdir(parents=True,exist_ok=True)
src=Path('D:/CodexTemp/2026-11-04/topoexport-B50B57/topoexport-B50B57.blend')
bpy.ops.wm.open_mainfile(filepath=str(src),load_ui=False,use_scripts=False)
rows=[]
for scene in bpy.data.scenes:
 for o in scene.objects:
  r=dict(name=o.name,type=o.type,scene=scene.name,layer=o.get('dxf_layer'),matrix=[list(x)for x in o.matrix_world],props={k:o[k]for k in o.keys()if isinstance(o[k],(str,int,float))})
  if o.type=='MESH':
   r['vertices']=[list(o.matrix_world@v.co)for v in o.data.vertices];r['faces']=[list(p.vertices)for p in o.data.polygons]
  elif o.type=='CURVE':r['splines']=[dict(points=[list(o.matrix_world@Vector(p.co[:3]))for p in s.points],closed=s.use_cyclic_u)for s in o.data.splines]
  elif o.type=='FONT':r['text']=o.data.body;r['position']=list(o.matrix_world.translation)
  elif o.instance_collection:r['instance']=o.instance_collection.name;r['position']=list(o.matrix_world.translation)
  rows.append(r)
data=dict(source=str(src),sha256=hashlib.sha256(src.read_bytes()).hexdigest(),scenes=[dict(name=s.name,props={k:s[k]for k in s.keys()if isinstance(s[k],(str,int,float))})for s in bpy.data.scenes],objects=rows)
(OUT/'source_geometry.json').write_text(json.dumps(data,ensure_ascii=False),encoding='utf8')
summary=dict(scenes=[s.name for s in bpy.data.scenes],objects=len(rows),layers=dict(Counter(str(r['layer'])+' / '+r['type']for r in rows)))
(OUT/'source_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(summary,ensure_ascii=False))
