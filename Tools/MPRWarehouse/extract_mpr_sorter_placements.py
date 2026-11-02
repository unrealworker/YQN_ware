"""Extract side-machine extents from the actual CAD linework occupancy.

Uses non-central X bands of each drawn assembly, detects connected Y runs at
20mm pitch, and preserves CAD-to-world transformation. This is geometry grouping,
not identification of a surveyed machine model or vertical capacity.
"""
import json,sys,math,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Scripts/_vendor/cad'))
import ezdxf
from ezdxf.math import Matrix44
OUT=ROOT/'SourceAssets/MPR/equipment';OUT.mkdir(parents=True,exist_ok=True)
details=json.loads((ROOT/'SourceAssets/MPR/mpr_cad_equipment_details.json').read_text(encoding='utf8'))
details={r['block']:r['placement'] for r in details}
doc=ezdxf.readfile(str(Path(r'D:\Data\仓库数据\MPR\平面布局图_MPR规划图V1.1_ALL-IN-ONE_0921.dxf')))

def pts(e):
 t=e.dxftype()
 if t=='LINE':return [e.dxf.start,e.dxf.end]
 if t=='LWPOLYLINE':return [(p[0],p[1],0) for p in e.get_points()]
 if t=='CIRCLE':return [(e.dxf.center.x+e.dxf.radius*math.cos(a*math.pi/4),e.dxf.center.y+e.dxf.radius*math.sin(a*math.pi/4),0) for a in range(8)]
 if t=='ARC':
  a=e.dxf.start_angle;b=e.dxf.end_angle
  if b<a:b+=360
  return [(e.dxf.center.x+e.dxf.radius*math.cos(math.radians(a+(b-a)*i/4)),e.dxf.center.y+e.dxf.radius*math.sin(math.radians(a+(b-a)*i/4)),0) for i in range(5)]
 if t=='SPLINE':return list(e.control_points)
 return []

def walk(entities,mt,depth=0):
 for e in entities:
  if e.dxftype()=='INSERT' and depth<8:yield from walk(doc.blocks.get(e.dxf.name),Matrix44.chain(e.matrix44(),mt),depth+1)
  else:
   for p in mt.transform_vertices(pts(e)):yield [(p.x-12800)*.0254,(p.y-8000)*.0254]

def runs(rows,cx,side,margin,step=.02):
 selected=[p for p in rows if (p[0]-cx)*side>margin]
 hist=collections.Counter(math.floor(p[1]/step) for p in selected)
 occupied=sorted(k for k,v in hist.items() if v>2)
 groups=[]
 for k in occupied:
  if not groups or k-groups[-1][-1]>12:groups.append([k])
  else:groups[-1].append(k)
 result=[]
 for group in groups:
  lo=group[0]*step;hi=(group[-1]+1)*step
  subset=[p for p in selected if lo<=p[1]<=hi]
  if hi-lo<.7:continue
  result.append({'min':[min(p[0] for p in subset),min(p[1] for p in subset)],'max':[max(p[0] for p in subset),max(p[1] for p in subset)],'points':len(subset)})
 return result

reports=[]
for name,margin in [('14234123',1.30),('480',.90),('小黄人',1.4)]:
 d=details[name];e=doc.entitydb[d['source_handles'][0]]
 rows=list(walk(doc.blocks.get(e.dxf.name),e.matrix44()))
 cx=d['position_m'][0]
 if name=='14234123':cx-=.06
 if name=='480':cx+=.06
 if name=='小黄人':cx-=.65
 side_rows={str(side):runs(rows,cx,side,margin) for side in (-1,1)}
 reports.append({'block':name,'source_handle':e.dxf.handle,'assembly':d,'points':len(rows),'core_x_m':cx,'side_groups':side_rows})
(OUT/'sorter_cad_groups.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(reports,ensure_ascii=False,indent=2))
