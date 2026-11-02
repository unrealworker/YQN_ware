"""Scientific same-canvas comparison; does not alter either input image."""
import json
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'SourceAssets/MPR/reference_v4/validation_blender'
REFERENCE=ROOT/'SourceAssets/MPR/reference_v4/references/ChatGPT 图像 2026年11月2日 15_56_24.png'
render=OUT/'Authoritative_Overview.png'
if not render.exists():render=OUT/'Authoritative_Overview_REVIEW.png'
if not render.exists():render=OUT/'Authoritative_Overview_PROXY.png'
a=Image.open(REFERENCE).convert('RGB');b=Image.open(render).convert('RGB');assert a.size==b.size,(a.size,b.size)
w,h=a.size;canvas=Image.new('RGB',(w*2,h+110),'#e9edf2');d=ImageDraw.Draw(canvas)
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',22)
canvas.paste(a,(0,50));canvas.paste(b,(w,50))
d.text((24,14),'AUTHORITATIVE REFERENCE',fill='#183246',font=font)
d.text((w+24,14),'BLENDER V4 - SAME CALIBRATED CAMERA'+(' - TEMPORARY TREES' if 'PROXY' in render.name else ''),fill='#183246',font=font)
regions={'bare_roof':[520,366,690,425],'pond':[350,660,384,681],'grass_south':[646,728,750,770],'solar_dark':[812,481,880,503]}
stats={}
for i,(name,box) in enumerate(regions.items()):
 ra=np.array(a.crop(box));rb=np.array(b.crop(box));ca=np.median(ra.reshape(-1,3),axis=0);cb=np.median(rb.reshape(-1,3),axis=0)
 stats[name]={'pixel_box':box,'reference_median_srgb':ca.tolist(),'render_median_srgb':cb.tolist(),
              'reference_mean_srgb':ra.mean(axis=(0,1)).tolist(),'render_mean_srgb':rb.mean(axis=(0,1)).tolist()}
 x=24+i*430;y=h+66
 d.rectangle((x,y,x+30,y+25),fill=tuple(ca.astype(int)));d.rectangle((x+35,y,x+65,y+25),fill=tuple(cb.astype(int)))
 d.text((x+76,y),name,fill='#183246',font=font)
canvas.save(OUT/'reference_render_comparison.png')
(OUT/'reference_color_samples.json').write_text(json.dumps(dict(reference=str(REFERENCE),render=render.relative_to(ROOT).as_posix(),regions=stats,
 note='Identical pixel boxes, median plus mean RGB. Regions may contain different detail pixels; these are review aids, not a photometric or 1:1 pass certificate.'),indent=2),encoding='utf8')
print(json.dumps(stats,indent=2))
