"""Render deterministic CAD-coordinate before/after clearance closeups."""
import json
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from plan_clearance_fix import corners

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'SourceAssets/GHS'
OUT=SOURCE/'RefinementV2/Layout'


def render():
    plan=json.loads((OUT/'rack_spacing.json').read_text(encoding='utf8'))
    old=json.loads((SOURCE/'RackSpecs/cad_plan_mapping.json').read_text(encoding='utf8'))
    layout=json.loads((SOURCE/'clearance_layout.json').read_text(encoding='utf8'))
    old_racks=old['assignments']+old['additional_pass_racks']
    img=Image.new('RGB',(1800,1320),(13,22,33));draw=ImageDraw.Draw(img)
    title=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',30)
    regular=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',23)
    small=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',19)
    draw.text((40,24),'CAD V2 | Full bays and floor slots restored inside protected circulation',font=title,fill='white')
    draw.text((40,70),'Racks: 70 original bays restored | max shift 0.964 m | minimum longitudinal aisle 2.0002 m',font=regular,fill=(139,204,234))
    draw.text((40,102),'Floor: 122 / 122 slots restored | max shift 0.754 m | every original block boundary retained',font=regular,fill=(139,204,234))
    def panel(rect,bounds,title_text,racks,ground,blocked,after):
        x0,y0,x1,y1=rect;xlo,xhi,ylo,yhi=bounds
        draw.rounded_rectangle(rect,12,fill=(20,32,46),outline=(70,88,110),width=2)
        draw.text((x0+18,y0+12),title_text,font=regular,fill='white')
        sx=(x1-x0-50)/(xhi-xlo);sy=(y1-y0-75)/(yhi-ylo);scale=min(sx,sy)
        ox=(x0+x1-(xhi-xlo)*scale)/2;oy=y1-20
        def pt(p):return (ox+(p[0]-xlo)*scale,oy-(p[1]-ylo)*scale)
        def box(e,fill,outline=None,width=1):
            ps=corners(e)
            if any(p[0]<xlo-.05 or p[0]>xhi+.05 or p[1]<ylo-.05 or p[1]>yhi+.05 for p in ps):return
            draw.polygon([pt(p) for p in ps],fill=fill,outline=outline,width=width)
        for r in racks:
            e=dict(position_m=r['position_m'],size_m=[max(1.2192,r['physical_depth_m']),r['physical_span_m']],rotation_deg=r['rotation_deg'])
            color=(215,159,66) if r['spec_type']=='A' else (163,113,207)
            if after and r.get('restored_column_split'):color=(54,208,155)
            box(e,color,(220,225,225),1)
        for g in ground:
            color=(54,208,155) if g.get('was_blocked') else ((56,154,183) if g.get('displacement_distance_m',0)>.0001 else (76,96,116))
            box(g,color,(135,163,183),1)
        for g in blocked:box(g,None,(226,86,96),3)
        for c in layout['columns']:
            base=dict(c,size_m=[v+.3 for v in c['size_m']]);box(base,None,(255,160,85),2)
            base=dict(c,size_m=[v+.1 for v in c['size_m']]);box(base,(133,143,153))
            box(c,(240,244,249))
    rackbounds=(-229.5,-219,16,28)
    floorbounds=(-40.9,-28.2,16.3,24.65)
    panel((30,155,885,735),rackbounds,'Before | local cut segments around column',old_racks,[],[],False)
    panel((915,155,1770,735),rackbounds,'After | full bays, complete row shifted 0.507 m',plan['racks'],[],[],True)
    panel((30,765,885,1240),floorbounds,'Before | two blocked floor cells (red outline)',[],layout['storage'],layout['blocked_storage'],False)
    panel((915,765,1770,1240),floorbounds,'After | full loads restored inside original block',[],plan['groundcargo'],[],True)
    draw.text((40,1267),'Green = restored bay or load   Cyan = moved existing load   White = fixed CAD column   Orange outline = base + 100 mm clearance',font=small,fill=(209,222,233))
    img.save(OUT/'rack_spacing_before_after.png')
    print(OUT/'rack_spacing_before_after.png')


if __name__=='__main__':render()
