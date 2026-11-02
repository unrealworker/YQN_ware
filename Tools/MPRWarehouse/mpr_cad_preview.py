"""Render the extracted physical CAD plan without loading the 256 MB DXF again."""
import pathlib,json,math,collections
from PIL import Image,ImageDraw,ImageFont
ROOT=pathlib.Path(__file__).resolve().parents[2];OUT=ROOT/'SourceAssets/MPR'
d=json.loads((OUT/'mpr_cad_extracted.json').read_text(encoding='utf8'))
font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',23)
def render(name,box,width=3000):
 ratio=(width-100)/(box[2]-box[0]);height=int((box[3]-box[1])*ratio)+130
 im=Image.new('RGB',(width,height),(13,23,37));draw=ImageDraw.Draw(im)
 def p(v):return (50+(v[0]-box[0])*ratio,height-50-(v[1]-box[1])*ratio)
 for g in d['architecture']:
  col=(190,206,220) if 'WALL' in g['layer'] else (60,78,95)
  if len(g['points_m'])>1:draw.line([p(v) for v in g['points_m']],fill=col,width=1)
 for g in d.get('loose_geometry',[]):
  col=(200,150,65) if g['layer']=='W_EQUIPMENT' else (155,180,88)
  if len(g['points_m'])>1:draw.line([p(v) for v in g['points_m']],fill=col,width=1)
 for key,col in [('racks',(51,174,221)),('equipment',(235,167,58)),('columns',(255,100,100)),('doors',(185,180,255))]:
  for g in d[key]:
   x,y=g['position_m'];w,h=g['size_m'];a=math.radians(g['rotation_deg'])
   pts=[[x+i*w/2*math.cos(a)-j*h/2*math.sin(a),y+i*w/2*math.sin(a)+j*h/2*math.cos(a)] for i,j in [(-1,-1),(1,-1),(1,1),(-1,1),(-1,-1)]]
   draw.line([p(v) for v in pts],fill=col,width=2 if key=='columns' else 1)
 draw.text((25,15),name+' | CAD +Y up | metres | blue:racks amber:equipment red:columns',font=font,fill='white')
 im.save(OUT/(name+'.png'))
render('mpr_cad_plan',[-188,-90,190,85])
render('mpr_cad_operations',[-188,-90,-38,85],2400)
print('PREVIEWS_WRITTEN')
