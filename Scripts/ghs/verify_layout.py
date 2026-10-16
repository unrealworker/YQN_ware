import json,math
from PIL import Image,ImageDraw,ImageFont
d=json.load(open('SourceAssets/GHS/cad_layout.json',encoding='utf8'));W=3200;H=1320;im=Image.new('RGB',(W,H),(9,17,30));dr=ImageDraw.Draw(im);font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',25)
def p(a):return (80+(a[0]+245)*6.5,1120-(a[1]+80)*6.5)
dr.polygon([p(a) for a in d['footprint_outline_m']],fill=(16,31,47),outline=(255,255,255),width=3)
for cat,col in [('storage',(218,164,56)),('racks',(48,199,210)),('equipment',(110,135,220)),('columns',(245,113,83)),('chargers',(238,100,210))]:
 for e in d[cat]:
  x,y=e['position_m'];sx,sy=e['size_m'];r=math.radians(e['rotation_deg']);co=math.cos(r);si=math.sin(r);pts=[p([x+dx*co-dy*si,y+dx*si+dy*co]) for dx,dy in [(-sx/2,-sy/2),(sx/2,-sy/2),(sx/2,sy/2),(-sx/2,sy/2)]];dr.polygon(pts,outline=col,width=1)
for w in d['walls']:dr.line([p(a) for a in w['points_m']],fill=(225,230,241),width=max(1,round(w['thickness_m']*6.5)))
dr.text((65,25),'GHS 0710 | Extracted physical layout | 465.7344 m x 137.16 m | 56,116.10 m2',font=font,fill='white')
dr.text((65,65),'Cyan: 1607 rack blocks   Gold: 7530 pallet positions   Magenta: 56 charging bays   Orange: 206 columns',font=font,fill='white')
for txt,loc in [('Rack storage / 大件货架区',[-230,65]),('Floor pallet storage / 地堆区',[-40,65]),('Charging bays / 充电位',[141,65]),('Dock racking / 装卸货架',[-120,-68])]:dr.text(p(loc),txt,font=font,fill='white')
dr.line([p([-230,-100]),p([-180,-100])],fill='white',width=4);dr.text(p([-230,-104]),'50 m',font=font,fill='white')
im.save('SourceAssets/GHS/CAD_verified_layout.png')
# Basic geometric count and dimension validations.
assert len(d['storage'])==7530 and len(d['chargers'])==56 and len(d['racks'])==1607
assert all(0.06<=w['thickness_m']<=.5 for w in d['walls'])
assert all(math.isfinite(v) for cat in ['storage','racks','columns','chargers'] for e in d[cat] for v in e['position_m']+e['size_m'])
print('PASS: counts, measured wall thicknesses, finite positions and sizes; scaled overview written.')

