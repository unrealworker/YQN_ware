"""Render the geometry-only plan as PNG with Pillow; reference photos unchanged."""
import json
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
out=Path(__file__).resolve().parent
layout=json.loads((out/'roof_layout_reference.json').read_text(encoding='utf8'))
cad=json.loads((out.parent/'mpr_cad_layout.json').read_text(encoding='utf8'))
image=Image.new('RGB',(1560,900),'#e8eef3');draw=ImageDraw.Draw(image)
sx=lambda x:75+(x+190)*3.7
sy=lambda y:105+(95-y)*3.7
font=lambda s:ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',s)
draw.text((75,20),'MPR 屋顶光伏 / 天窗 — 照片标定平面预览',font=font(26),fill='#19354b')
draw.text((75,60),'照片读数估计（约 2–5 m）；CAD 轮廓固定。+X：阶梯端；−Y：南侧装卸场。非光伏施工图。',font=font(17),fill='#43596a')
draw.polygon([(sx(x),sy(y)) for x,y in cad['footprint_outline_m']],fill='#fbfcfd',outline='#42596c',width=2)
for t in layout['continuous_strips']:
    draw.rectangle((sx(t['x']-t['width']/2),sy(t['y1']),sx(t['x']+t['width']/2),sy(t['y0'])),fill='#24465d')
for x,y in layout['skylight_centers_m']:
    draw.rectangle((sx(x)-2.5,sy(y)-1.7,sx(x)+2.5,sy(y)+1.7),fill='#95b3cb',outline='#49657c')
for x in range(-150,181,50):draw.text((sx(x)-30,796),f'X {x} m',font=font(15),fill='#43596a')
draw.line((75,853,260,853),fill='#19354b',width=3);draw.text((140,863),'50 m',font=font(16),fill='#19354b')
draw.text((325,842),f"{len(layout['continuous_strips'])} 条合并板带 · {layout['solar_module_cells']} 个视觉模块 · {len(layout['skylight_centers_m'])} 处可识别天窗",font=font(17),fill='#43596a')
image.save(out/'roof_layout_preview.png')
