"""Rebuild measured operating-equipment evidence from stable source CAD handles."""
import argparse,runpy,json,math,pathlib
from PIL import Image,ImageDraw,ImageFont
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=pathlib.Path,help='Optional evidence directory for isolated reproduction checks')
args=parser.parse_args()
g=runpy.run_path(__file__.replace('mpr_cad_operations_detail.py','mpr_cad_extract.py'))
doc=g['doc'];OUT=g['OUT'];points=g['points'];Matrix44=g['Matrix44']
if args.output:OUT=args.output;OUT.mkdir(parents=True,exist_ok=True)
# The completed instances manifest has no unmodeled rows. Candidate selection
# must remain independent of that output or a second extraction erases evidence.
# One representative INSERT per audited block, in the original contact-sheet order.
handles=('2C93C9','2C958F','2C9590','2C95B3','2C95D6','2C9831','2C9869',
 '2C98A3','2C99CA','2C9A01','2C9A2B','2CA61A','2CB2DE','2CCF62','2CCFA1',
 '2CCFEE','2CCFFC','2CD0A3','2CD0A4','2CD0A5','2D4056','2D4095','2D40BC',
 '2D419C','2D4318','2D432D','2D4354','2D457E','2D4633','2D4DEB','2D4E7B',
 '2D4E90','2D4EA5','2D540A','2E710D','2E7339','2E735B','2E7F0F','2E7F10',
 '2E886D','2E8A03','2E90D0','2E9165','2E916F')
entities=[doc.entitydb[handle] for handle in handles]
assert all(e.dxftype()=='INSERT' for e in entities)
assert len(set(e.dxf.name for e in entities))==len(handles)
font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',18)
sheet=Image.new('RGB',(2200,math.ceil(len(entities)/4)*390),(13,23,37));dr=ImageDraw.Draw(sheet)
evidence=[]
for idx,e in enumerate(entities):
 name=e.dxf.name
 it=g['item'](e);bb=it['bounds_dxf'];ratio=480/max(bb[1][i]-bb[0][i] for i in (0,1));x0=idx%4*550;y0=idx//4*390
 ratio=min(ratio,300/max(.001,bb[1][1]-bb[0][1]));long=[];arcs=[];polys=[]
 def p(v):return (x0+25+(v[0]-bb[0][0])*ratio,y0+350-(v[1]-bb[0][1])*ratio)
 def walk(entities,mt,depth=0):
  for ee in entities:
   if ee.dxftype()=='INSERT' and depth<10:walk(doc.blocks.get(ee.dxf.name),Matrix44.chain(ee.matrix44(),mt),depth+1)
   else:
    try:
     ps=list(mt.transform_vertices(points(ee)))
     if len(ps)>1:
      dr.line([p(v) for v in ps],fill=(164,192,214),width=1)
      if ee.dxftype()=='ARC' and ee.dxf.radius*mt.transform_direction((1,0,0)).magnitude*.0254>.4:
       arcs.append({'center':g['xy'](mt.transform(ee.dxf.center)),'points':[g['xy'](v) for v in ps],'radius_m':ee.dxf.radius*mt.transform_direction((1,0,0)).magnitude*.0254})
      if ee.dxftype()=='LWPOLYLINE' and ee.closed and len(ps)<7:polys.append([g['xy'](v) for v in ps])
      if ee.dxftype() in ('LINE','LWPOLYLINE'):
       for a,b in zip(ps,ps[1:]):
        if math.dist(a,b)*.0254>1.8:long.append({'a':g['xy'](a),'b':g['xy'](b)})
    except Exception:pass
 walk(doc.blocks.get(e.dxf.name),e.matrix44())
 dr.text((x0+15,y0+5),name,font=font,fill='white');dr.text((x0+15,y0+28),str(it['size_m'])+' m',font=font,fill='#90bede')
 evidence.append({'block':name,'placement':it,'long_lines':long,'arcs':arcs,'rectangles':polys})
sheet.save(OUT/'mpr_cad_operations_detail.png')
(OUT/'mpr_cad_operations_lines.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf8')
print('OPERATION_DETAILS',len(evidence))
