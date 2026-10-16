"""Arrange original UE captures without changing their visual content."""
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
root=Path(r'D:\UEPro\Test');saved=root/'Saved'
canvas=Image.new('RGB',(2400,1435),'#09121c')
draw=ImageDraw.Draw(canvas);font=ImageFont.truetype(r'C:\Windows\Fonts\msyh.ttc',32)
draw.text((26,18),'调整前：低矮、灰白、面间明暗弱',font=font,fill='#c6d5e4')
draw.text((1226,18),'调整后：分级高度、深蓝材质、单主光投影',font=font,fill='#81d7f2')
for row,view in enumerate(['FloorStorage','RackAisles']):
    for col,phase in enumerate(['Before','Reload']):
        im=Image.open(saved/f'GHS_Presentation{phase}_UE_{view}.png').convert('RGB')
        assert im.size==(2400,1350)
        im=im.resize((1200,675),Image.Resampling.LANCZOS)
        canvas.paste(im,(col*1200,70+row*690))
canvas.save(saved/'GHS_PresentationComparison.jpg',quality=95)
print(saved/'GHS_PresentationComparison.jpg')
