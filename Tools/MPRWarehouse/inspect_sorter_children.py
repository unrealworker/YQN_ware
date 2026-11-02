"""Read CAD assembly child footprints without touching the source drawing."""
import json,sys,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Scripts/_vendor/cad'))
import ezdxf
from ezdxf.math import Matrix44
from ezdxf import bbox
doc=ezdxf.readfile(r'D:\Data\仓库数据\MPR\平面布局图_MPR规划图V1.1_ALL-IN-ONE_0921.dxf')
result={}
def descendants(parent,mt,depth=0):
 rows=[]
 for e in doc.blocks.get(parent.dxf.name):
  if e.dxftype()!='INSERT':continue
  bound=bbox.extents([e]);corners=list(mt.transform_vertices(bound.rect_vertices()))
  mn=[min(p[i] for p in corners) for i in range(2)];mx=[max(p[i] for p in corners) for i in range(2)]
  lo=[(mn[0]-12800)*.0254,(mn[1]-8000)*.0254];hi=[(mx[0]-12800)*.0254,(mx[1]-8000)*.0254]
  size=[hi[i]-lo[i] for i in range(2)]
  if 2.3<size[0]<3.7 and 1.4<size[1]<2.4:
   rows.append({'name':e.dxf.name,'handle':e.dxf.handle,'min':lo,'max':hi,'size':size,'depth':depth})
  elif depth<5 and 2.3<size[0]<4 and 8<size[1]<20:
   rows.extend(descendants(e,Matrix44.chain(e.matrix44(),mt),depth+1))
 return rows
for handle in ['2C9AE5','2D41B7']:
 parent=doc.entitydb[handle];rows=[]
 for e in doc.blocks.get(parent.dxf.name):
  if e.dxftype()!='INSERT':continue
  bound=bbox.extents([e]);corners=list(parent.matrix44().transform_vertices(bound.rect_vertices()))
  mn=[min(p[i] for p in corners) for i in range(2)];mx=[max(p[i] for p in corners) for i in range(2)]
  lo=[(mn[0]-12800)*.0254,(mn[1]-8000)*.0254];hi=[(mx[0]-12800)*.0254,(mx[1]-8000)*.0254]
  rows.append({'name':e.dxf.name,'handle':e.dxf.handle,'min':lo,'max':hi,'size':[hi[i]-lo[i] for i in range(2)]})
 result[handle]=rows
(ROOT/'SourceAssets/MPR/equipment/sorter_child_bounds.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(result,ensure_ascii=False,indent=2))
