"""Render the saved solar plan as a readable PNG; ordinary Python + Pillow."""
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'SourceAssets/MPR/rebuild_b50b57/solar'


def main():
    data=json.loads((OUT/'layout.json').read_text(encoding='utf8'))
    cad=json.loads((OUT/'inputs/cad_layout.json').read_text(encoding='utf8'))
    image=Image.new('RGB',(2320,800),'#E7EDF1');draw=ImageDraw.Draw(image)
    fonts=[Path('C:/Windows/Fonts/msyh.ttc'),Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')]
    font_path=next((p for p in fonts if p.exists()),None)
    font=ImageFont.truetype(str(font_path),25)if font_path else ImageFont.load_default(size=25)
    small=ImageFont.truetype(str(font_path),20)if font_path else ImageFont.load_default(size=20)
    for side,title in enumerate(['原布局：航拍像素轮廓','整理后：统一板列、同行设备通道']):
        def tx(q):return (side*1160+565+q[0]*2.75,350-q[1]*2.75)
        def shape(g,color):
            polygons=[g['coordinates']]if g['type']=='Polygon'else g['coordinates']if g['type']=='MultiPolygon'else []
            for rings in polygons:
                draw.polygon([tx(q)for q in rings[0]],fill=color)
                for hole in rings[1:]:draw.polygon([tx(q)for q in hole],fill='#E9EDF0')
        draw.text((side*1160+35,25),title,font=font,fill='#17334B')
        draw.polygon([tx(q)for q in cad['footprint_outline_m']],fill='#E9EDF0',outline='#4F7A96',width=2)
        for field in data['fields']:shape(field['geometry'if side else 'old_geometry'],'#153A60')
        if side:
            for rows in data['blocks'].values():
                for block in rows:
                    x0,y0,x1,y1=block['bounds_m'];ix0,iy0,ix1,iy1=block['grid']
                    for ix in range(ix0+1,ix1):
                        x=data['uv_origin_m'][0]+ix*data['pitch_m'][0]
                        draw.line([tx((x,y0)),tx((x,y1))],fill='#294860',width=1)
                    for iy in range(iy0+1,iy1):
                        y=data['uv_origin_m'][1]+iy*data['pitch_m'][1]
                        draw.line([tx((x0,y)),tx((x1,y))],fill='#294860',width=1)
        for device in data['devices_unchanged']:
            x0,y0,x1,y1=device['bounds_m']
            draw.rectangle([tx((x0,y1)),tx((x1,y0))],fill='#F8FAFC',outline='#8196A6',width=1)
        for field in data['fields']:
            points=field['regular_envelope']['coordinates'][0][:-1]
            center=[sum(p[i]for p in points)/len(points)for i in (0,1)]
            draw.text(tx(center),field['id'].split('_')[-1],fill='#FAAD3B',font=small,stroke_width=1,stroke_fill='#15334B')
    draw.text((35,700),'16 主要分区 / 195 屋顶设备位置不变 / 5 个渲染网格 / 三个 LOD 相同占地',fill='#17334B',font=small)
    draw.text((35,742),f'蓝色为光伏，白色为现有设备；设备净空至少 {data["minimum_device_clearance_m"]:.3f} m，板列模块尺寸 1.12 × 1.95 m。',fill='#17334B',font=small)
    image.save(OUT/'plan_comparison.png')
    print(OUT/'plan_comparison.png')


if __name__=='__main__':main()
