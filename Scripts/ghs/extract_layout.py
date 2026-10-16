import sys,json,math,collections,logging
sys.path.insert(0,r'D:\UEPro\Test\Scripts\_vendor\cad')
import ezdxf
from ezdxf.math import Matrix44
from ezdxf import bbox
from PIL import Image,ImageDraw,ImageFont
logging.disable(logging.WARNING)
d=ezdxf.read(open(r'D:\EdgeDownload\平面布局图_GHS_0.23_20260710现状.dxf',encoding='utf8',errors='replace'));m=d.modelspace()
origin=[6917380.,1902500.];scale=.0254
out={'origin_dxf_xy':origin,'units_to_m':scale,'units':'inches','walls':[],'columns':[],'racks':[],'equipment':[],'storage':[],'conveyors':[],'agvs':[],'chargers':[],'zones':[],'texts':[],'geometry':[],'doors':[],'candidates':[]}
def xy(p):return [round((p[i]-origin[i])*scale,5) for i in range(2)]
def points(e):
 t=e.dxftype()
 if t=='LINE':return [list(e.dxf.start)[:2],list(e.dxf.end)[:2]]
 if t=='LWPOLYLINE':
  ps=[list(p)[:2] for p in e.vertices_in_wcs()]
  if e.closed:ps.append(ps[0])
  return ps
 if t=='POLYLINE':return [list(p)[:2] for p in e.points()]
 if t in ('CIRCLE','ARC'):
  a=0 if t=='CIRCLE' else e.dxf.start_angle;b=360 if t=='CIRCLE' else e.dxf.end_angle
  if b<=a:b+=360
  return [[e.dxf.center.x+e.dxf.radius*math.cos(math.radians(a+(b-a)*i/32)),e.dxf.center.y+e.dxf.radius*math.sin(math.radians(a+(b-a)*i/32))] for i in range(33)]
 return []
raw=[];inserts=[]
def recurse(entities,mat,chain,inherit='0',depth=0):
 for e in entities:
  lay=e.dxf.layer if e.dxf.layer!='0' else inherit;h=e.dxf.handle or '?';ch=chain+[h]
  if e.dxftype()=='INSERT':
   mt=Matrix44.chain(e.matrix44(),mat)
   inserts.append((e,mt,ch,lay))
   if depth<8:recurse(d.blocks.get(e.dxf.name),mt,ch,lay,depth+1)
  elif e.dxftype() not in ('DIMENSION','HATCH'):
   try:
    c=e.copy();c.transform(mat);ps=points(c)
    if ps:raw.append({'layer':lay,'source_handles':ch,'points':ps,'type':e.dxftype()})
    elif c.dxftype() in ('TEXT','MTEXT'):out['texts'].append({'text':c.dxf.text if c.dxftype()=='TEXT' else c.plain_text(),'position_m':xy(c.dxf.insert),'layer':lay,'source_handles':ch})
   except Exception:pass
recurse(m,Matrix44(),[])
json.dump({'raw':raw,'insert_count':len(inserts)},open('SourceAssets/GHS/cad_raw.json','w',encoding='utf8'),ensure_ascii=False)
# View authoritative main plan, excluding separate old layouts and rack elevations below it.
clip=[6907000,1898500,6927800,1905800]
def inside(ps):return any(clip[0]<=p[0]<=clip[2] and clip[1]<=p[1]<=clip[3] for p in ps)
for g in raw:
 if inside(g['points']):out['geometry'].append({'layer':g['layer'],'source_handles':g['source_handles'],'points_m':[xy(p) for p in g['points']],'type':g['type']})
cache={}
for e,mat,ch,lay in inserts:
 n=e.dxf.name
 if n not in cache:cache[n]=bbox.extents(d.blocks.get(n),fast=True)
 bb=cache[n]
 if not bb.has_data:continue
 ps=[mat.transform((x,y,0)) for x in (bb.extmin.x,bb.extmax.x) for y in (bb.extmin.y,bb.extmax.y)]
 if not inside(ps):continue
 center=mat.transform(((bb.extmin.x+bb.extmax.x)/2,(bb.extmin.y+bb.extmax.y)/2,0))
 a=mat.transform_direction((1,0,0));b=mat.transform_direction((0,1,0))
 item={'id':'CAD_'+'_'.join(ch),'block':n,'position_m':xy(center),'size_m':[(bb.extmax.x-bb.extmin.x)*a.magnitude*scale,(bb.extmax.y-bb.extmin.y)*b.magnitude*scale],'rotation_deg':math.degrees(math.atan2(a.y,a.x)),'layer':lay,'source_handles':ch,'confidence':1.0}
 if lay=='W_STORAGE':out['storage'].append(item)
 elif lay=='W_RACK_OVERSIZE_WR':out['racks'].append(item)
 elif n=='PILLAR' or lay.lower().endswith('$col'):out['columns'].append(item)
 elif 'DOOR' in lay:out['doors'].append(item)
 elif lay=='W_DOCK':item['kind']='dock_rack';item['height_m']=2.8;out['equipment'].append(item)
 elif len(ch)==1 and n.startswith('*U') and item['size_m'][0]<20 and item['size_m'][1]<40:out['candidates'].append(item)
# Architectural lines retained as measured surfaces: small thickness is visual extrusion, not measured wall thickness.
for g in out['geometry']:
 l=g['layer'].upper()
 if l.endswith('$BUILD') or l.endswith('$1-INT-WALL') or l.endswith('$1-INTWALL'):
  for a,b in zip(g['points_m'],g['points_m'][1:]):
   if math.dist(a,b)>.35:out['walls'].append({'id':'W_'+'_'.join(g['source_handles'])+'_'+str(len(out['walls'])),'points_m':[a,b],'thickness_m':.15,'height_m':4.5,'layer':g['layer'],'source_handles':g['source_handles'],'confidence':.85,'note':'CAD wall-face line; extrusion thickness and height estimated'})
out['bounds_m']=[xy(clip[:2]),xy(clip[2:])]
font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',20)
def render(name,box,width=3000):
 ratio=(width-100)/(box[2]-box[0]);height=int((box[3]-box[1])*ratio)+160
 im=Image.new('RGB',(width,height),(10,18,30));dr=ImageDraw.Draw(im)
 def p(v):return (50+(v[0]-box[0])*ratio,height-70-(v[1]-box[1])*ratio)
 for g in raw:
  if not any(box[0]<=q[0]<=box[2] and box[1]<=q[1]<=box[3] for q in g['points']):continue
  l=g['layer'];color=(72,100,115)
  if 'STORAGE' in l:color=(240,179,64)
  elif 'RACK' in l:color=(73,210,212)
  elif 'BUILD' in l or 'WALL' in l:color=(220,228,240)
  elif 'col' in l:color=(255,130,100)
  elif 'DOCK' in l:color=(150,180,255)
  dr.line([p(q) for q in g['points']],fill=color,width=1)
 dr.text((30,20),name+' | CAD right-handed XY | inch x 0.0254 = m',font=font,fill='white')
 im.save('SourceAssets/GHS/'+name+'.png')
render('CAD_main_plan',clip)
render('CAD_racks_detail',[6907600,1900500,6914600,1905000],2500)
render('CAD_east_charging',[6922000,1903600,6927000,1905100],2500)
json.dump(out,open('SourceAssets/GHS/cad_layout.json','w',encoding='utf8'),ensure_ascii=False,indent=2)
print({k:len(v) for k,v in out.items() if isinstance(v,list)});print('CANDIDATES',out['candidates'])
