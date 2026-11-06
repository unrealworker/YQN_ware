"""Extract measured MPR plan geometry; source remains read only."""
import sys,json,math,collections,pathlib,logging,time,io
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Scripts/_vendor/cad'))
import ezdxf
from ezdxf.math import Matrix44,BoundingBox
from PIL import Image,ImageDraw,ImageFont
from mpr_cad_semantics import planar_handedness
logging.disable(logging.WARNING)
SOURCE=pathlib.Path(r'D:\Data\仓库数据\MPR\平面布局图_MPR规划图V1.1_ALL-IN-ONE_0921.dxf')
OUT=ROOT/'SourceAssets/MPR';OUT.mkdir(parents=True,exist_ok=True)
class MixedDxfStream:
 def __init__(self,path):self.file=open(path,'rb')
 def readline(self):
  data=self.file.readline().replace(b'\r\n',b'\n')
  try:return data.decode('utf8')
  except UnicodeDecodeError:return data.decode('gb18030',errors='replace')
doc=ezdxf.read(MixedDxfStream(SOURCE));ms=doc.modelspace()
scale=.0254
origin=[12800.,8000.]
clip=[5400,4200,20200,11400]
def xy(p):return [round((p[i]-origin[i])*scale,5) for i in range(2)]
def inside(p):return clip[0]<=p[0]<=clip[2] and clip[1]<=p[1]<=clip[3]
def points(e,curves=True):
 t=e.dxftype()
 if t=='LINE':return [e.dxf.start,e.dxf.end]
 if t=='LWPOLYLINE':
  ps=list(e.vertices_in_wcs())
  return ps+[ps[0]] if e.closed and ps else ps
 if t=='POLYLINE':return list(e.points())
 if t in ('CIRCLE','ARC'):
  a=0 if t=='CIRCLE' else e.dxf.start_angle;b=360 if t=='CIRCLE' else e.dxf.end_angle
  if b<=a:b+=360
  return [(e.dxf.center.x+e.dxf.radius*math.cos(math.radians(a+(b-a)*i/32)),e.dxf.center.y+e.dxf.radius*math.sin(math.radians(a+(b-a)*i/32)),e.dxf.center.z) for i in range(33)]
 if t=='SPLINE':return list(e.control_points)
 if t=='ELLIPSE':return list(e.flattening(3,4))
 return []
cache={}
def bounds(name,anc=()):
 if name in cache:return cache[name]
 if name in anc:return BoundingBox()
 box=BoundingBox()
 for e in doc.blocks.get(name):
  if e.dxftype()=='INSERT':
   bb=bounds(e.dxf.name,anc+(name,))
   if bb.has_data:box.extend(e.matrix44().transform_vertices(bb.cube_vertices()))
  else:
   try:box.extend(points(e,False))
   except Exception:pass
 cache[name]=box
 return box
def item(e,mat=None,chain=(),layer=None):
 mt=mat or e.matrix44();bb=bounds(e.dxf.name)
 if not bb.has_data:return None
 center=mt.transform(bb.center);a=mt.transform_direction((1,0,0));b=mt.transform_direction((0,1,0))
 world=BoundingBox(mt.transform_vertices(bb.cube_vertices()))
 return {'id':'CAD_'+'_'.join(chain+(e.dxf.handle,)),'block':e.dxf.name,'position_m':xy(center),'center_dxf':[center.x,center.y],'size_m':[round(bb.size.x*a.magnitude*scale,5),round(bb.size.y*b.magnitude*scale,5)],'rotation_deg':round(math.degrees(math.atan2(a.y,a.x)),6),'planar_handedness':planar_handedness(a,b),'layer':layer or e.dxf.layer,'source_handles':list(chain+(e.dxf.handle,)),'bounds_dxf':[list(world.extmin)[:2],list(world.extmax)[:2]],'local_bounds_dxf':[list(bb.extmin),list(bb.extmax)]}
out={'source':str(SOURCE),'header_units':doc.units,'units':'inches (physical scale verified against rack nominal sizes and 50ft column spacing; DXF header says mm)','units_to_m':scale,'origin_dxf_xy':origin,'clip_dxf':clip,'racks':[],'columns':[],'equipment':[],'doors':[],'architecture':[],'texts':[],'all_insert_groups':[],'base_inserts':[]}
def recurse(entities,mat,chain,inherit='0',depth=0):
 for e in entities:
  lay=e.dxf.layer if e.dxf.layer!='0' else inherit
  ch=chain+(e.dxf.handle or '?',)
  if e.dxftype()=='INSERT':
   mt=Matrix44.chain(e.matrix44(),mat)
   if 'DOOR' in lay.upper():
    val=item(e,mt,chain,lay)
    if val and inside(val['center_dxf']):out['doors'].append(val)
   if depth<8:recurse(doc.blocks.get(e.dxf.name),mt,ch,lay,depth+1)
  else:
   try:
    ps=list(mat.transform_vertices(points(e)))
    if ps and any(inside(p) for p in ps):out['architecture'].append({'type':e.dxftype(),'layer':lay,'source_handles':list(ch),'points_m':[xy(p) for p in ps],'closed':getattr(e,'closed',False)})
   except Exception:pass
for e in ms:
 t=e.dxftype();lay=e.dxf.layer
 if t=='INSERT':
  if lay not in ('A_WALL','A_BASE','W_RACK','W_EQUIPMENT','E_CHARGE'):continue
  val=item(e)
  if not val:continue
  out['all_insert_groups'].append(val)
  if lay in ('A_WALL','A_BASE') and e.dxf.name!='PILLAR':
   out['base_inserts'].append(val)
   if lay=='A_WALL':recurse(doc.blocks.get(e.dxf.name),e.matrix44(),(e.dxf.handle,),lay)
  elif inside(val['center_dxf']):
   key='columns' if e.dxf.name=='PILLAR' else 'racks' if lay=='W_RACK' else 'equipment'
   out[key].append(val)
 elif t in ('TEXT','MTEXT') and inside(e.dxf.insert):out['texts'].append({'text':e.dxf.text if t=='TEXT' else e.plain_text(),'position_m':xy(e.dxf.insert),'layer':lay,'handle':e.dxf.handle})
 elif lay in ('W_EQUIPMENT','E_CHARGE','W_RACK'):
  ps=points(e)
  if ps and any(inside(p) for p in ps):out.setdefault('loose_geometry',[]).append({'type':t,'layer':lay,'source_handles':[e.dxf.handle],'points_m':[xy(p) for p in ps],'closed':getattr(e,'closed',False)})
(OUT/'mpr_cad_extracted.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
print('COUNTS', {k:len(v) for k,v in out.items() if isinstance(v,list)})
print('BASES',json.dumps(out['base_inserts'],ensure_ascii=False))
print('ARCH',dict(collections.Counter(g['layer'] for g in out['architecture'])))
print('RACKS',dict(collections.Counter(g['block'] for g in out['racks'])))
print('EQUIPMENT',dict(collections.Counter(g['block'] for g in out['equipment'])))
