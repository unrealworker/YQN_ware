import json,math
from PIL import Image,ImageDraw,ImageFont
d=json.load(open('SourceAssets/GHS/cad_layout.json',encoding='utf8'));q=json.load(open('SourceAssets/GHS/physical_bounds_proposed.json',encoding='utf8'));im=Image.new('RGB',(1800,820),(15,22,33));dr=ImageDraw.Draw(im);font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',22)
def pt(p):return (70+(p[0]+70)*58,730-(p[1]-18)*58)
def box(e,col,width):
 x,y=e['position_m'];sx,sy=e['size_m'];a=math.radians(e['rotation_deg']);c,s=math.cos(a),math.sin(a);ps=[pt((x+dx*c-dy*s,y+dx*s+dy*c)) for dx,dy in [(-sx/2,-sy/2),(sx/2,-sy/2),(sx/2,sy/2),(-sx/2,sy/2)]];dr.polygon(ps,outline=col,width=width)
for e in d['storage']:
 if -70<e['position_m'][0]<-43 and 18<e['position_m'][1]<29:box(e,(85,92,108),1)
for e in q['storage']:
 if -70<e['position_m'][0]<-43 and 18<e['position_m'][1]<29:box(e,(230,180,65),2)
for e in d['columns']:
 if -70<e['position_m'][0]<-43 and 18<e['position_m'][1]<29:box(e,(255,72,72),5);dr.text(pt((e['position_m'][0],e['position_m'][1]+.5)),e['id'],font=font,fill='white')
dr.text((30,20),'Floor storage: gray = old 50in bbox; gold = actual 40in pallet; RED = 10in architectural column',font=font,fill='white');dr.text((30,55),'Even after removing the dashed 5in margins, source CAD pallet rectangles overlap structural columns.',font=font,fill='white');im.save('SourceAssets/GHS/CAD_column_overlap_detail.png')
