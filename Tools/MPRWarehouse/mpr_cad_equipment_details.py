"""Inspect source linework for complex assemblies rather than box-substituting them."""
import runpy,json,math
from PIL import Image,ImageDraw,ImageFont
g=runpy.run_path(__file__.replace('mpr_cad_equipment_details.py','mpr_cad_extract.py'))
doc=g['doc'];OUT=g['OUT'];points=g['points'];Matrix44=g['Matrix44']
font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',23)
selected=['14234123','480','PW_TG_96C_IN','321321','小黄人']
manifest=[]
for name in selected:
 candidates=[e for e in doc.modelspace().query('INSERT') if e.dxf.name==name]
 if not candidates:continue
 e=candidates[0];item=g['item'](e);box=item['bounds_dxf'];ratio=2900/max(box[1][0]-box[0][0],box[1][1]-box[0][1]);width=int((box[1][0]-box[0][0])*ratio)+100;height=int((box[1][1]-box[0][1])*ratio)+130
 im=Image.new('RGB',(width,height),(13,23,37));draw=ImageDraw.Draw(im)
 def p(v):return (50+(v[0]-box[0][0])*ratio,height-50-(v[1]-box[0][1])*ratio)
 def walk(entities,mt,depth=0):
  for ee in entities:
   if ee.dxftype()=='INSERT' and depth<10:walk(doc.blocks.get(ee.dxf.name),Matrix44.chain(ee.matrix44(),mt),depth+1)
   else:
    try:
     ps=list(mt.transform_vertices(points(ee)))
     if len(ps)>1:draw.line([p(v) for v in ps],fill=(164,192,214),width=1)
    except Exception:pass
 walk(doc.blocks.get(e.dxf.name),e.matrix44())
 draw.text((20,15),name+' | actual CAD linework | '+str(item['size_m'])+' m',font=font,fill='white')
 filename='mpr_cad_equipment_'+e.dxf.handle+'.png';im.save(OUT/filename)
 manifest.append({'block':name,'handle':e.dxf.handle,'preview':filename,'placement':item})
(OUT/'mpr_cad_equipment_details.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
print('EQUIPMENT_DETAIL_PREVIEWS',[x['preview'] for x in manifest])
