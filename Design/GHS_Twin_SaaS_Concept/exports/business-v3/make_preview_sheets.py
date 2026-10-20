from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import json, shutil
base = Path(__file__).parent
pages = json.loads((base / 'index.json').read_text(encoding='utf-8'))
font_path = 'C:/Windows/Fonts/msyh.ttc'
font = ImageFont.truetype(font_path, 27)
small = ImageFont.truetype(font_path, 19)
for p in pages:
    image = Image.open(base / (p['id'] + '.png'))
    assert image.size == (1920, 1080), (p['id'], image.size)
    shutil.copyfile(base / (p['id'] + '.png'), base / p['file'])

def sheet(items, file, cols, thumb=(768,432)):
    pad, title_h, head_h = 28, 46, 100
    rows = (len(items) + cols - 1) // cols
    w = pad + cols*(thumb[0]+pad)
    h = head_h + rows*(thumb[1]+title_h+pad)
    out = Image.new('RGB',(w,h),'#EEF2F7')
    d = ImageDraw.Draw(out)
    d.text((pad,24),'GHS 仓储数字孪生 · 业务界面设计',font=font,fill='#25364B')
    d.text((pad,63),'Pencil 静态设计 / 1920 × 1080 / 演示数据',font=small,fill='#5B6C82')
    for j,idx in enumerate(items):
        p=pages[idx]
        im=Image.open(base / p['file']).convert('RGB').resize(thumb,Image.Resampling.LANCZOS)
        x=pad+(j%cols)*(thumb[0]+pad)
        y=head_h+(j//cols)*(thumb[1]+title_h+pad)
        d.text((x,y),p['title'],font=font,fill='#25364B')
        out.paste(im,(x,y+title_h))
    out.save(base/file)
sheet([1,11,12,13,14,15,16,17],'business-overview.png',2)
sheet([11,17,18,15],'material-workflow.png',2)
items=[1,11,12,13,14,15,16,17]
pad, head_h, title_h=24,100,50
cols, pw,ph=4,480,1016
out=Image.new('RGB',(pad+cols*(pw+pad),head_h+2*(ph+title_h+pad)),'#EEF2F7')
d=ImageDraw.Draw(out)
d.text((pad,24),'GHS 仓储数字孪生 · 七个侧栏页面与物料详情',font=font,fill='#25364B')
d.text((pad,63),'总览 → 库存 / 订单 / 设备 / 告警 / 追溯 / 场景；选中货架物料进入详情',font=small,fill='#5B6C82')
for j,idx in enumerate(items):
    p=pages[idx]
    im=Image.open(base / p['file']).convert('RGB').crop((1440,64,1920,1080))
    x=pad+(j%cols)*(pw+pad)
    y=head_h+(j//cols)*(ph+title_h+pad)
    d.text((x,y),p['title'],font=font,fill='#25364B')
    out.paste(im,(x,y+title_h))
out.save(base/'sidebar-contents.png')
print('23 full-size screens and 3 review sheets created.')
