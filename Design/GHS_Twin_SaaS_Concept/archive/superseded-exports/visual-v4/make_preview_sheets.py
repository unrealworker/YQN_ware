from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import json, shutil
base=Path(__file__).parent
pages=json.loads((base.parent/'business-v3/index.json').read_text(encoding='utf-8'))
for p in pages:
    im=Image.open(base/(p['id']+'.png'))
    assert im.size==(1920,1080)
    shutil.copyfile(base/(p['id']+'.png'),base/p['file'])
(base/'index.json').write_text(json.dumps(pages,ensure_ascii=False,indent=2),encoding='utf-8')
font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',24)
small=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',17)
def panels(items,name,cols):
    pw,ph,pad,head,th=480,1016,24,96,42
    out=Image.new('RGB',(pad+cols*(pw+pad),head+((len(items)+cols-1)//cols)*(ph+th+pad)),'#EEF2F7')
    d=ImageDraw.Draw(out)
    d.text((pad,22),'GHS 仓储数字孪生 · 图片与图表改版',font=font,fill='#25364B')
    d.text((pad,58),'Pencil 静态设计 · 项目设备模型预览 · 演示数据',font=small,fill='#5B6C82')
    for i,(idx,label) in enumerate(items):
        x=pad+i%cols*(pw+pad); y=head+i//cols*(ph+th+pad)
        im=Image.open(base/pages[idx]['file']).convert('RGB').crop((1440,64,1920,1080))
        d.text((x,y),label,font=font,fill='#25364B');out.paste(im,(x,y+th))
    out.save(base/name)
panels([(1,'总览 · 指标与统计图'),(2,'设备 · 图片与仪表'),(11,'库存 · 货位分布')],'visual-highlights.png',3)
panels([(1,'运营总览'),(11,'库存与货位'),(12,'出入库订单'),(13,'设备监控'),(14,'告警中心'),(15,'物料追溯'),(16,'场景设置'),(2,'设备详情')],'sidebar-contents.png',4)
out=Image.new('RGB',(1584,1028),'#EEF2F7');d=ImageDraw.Draw(out)
for i,idx in enumerate([1,2,11,7]):
    x=24+(i%2)*780;y=24+(i//2)*502
    d.text((x,y),pages[idx]['title'],font=font,fill='#25364B')
    im=Image.open(base/pages[idx]['file']).convert('RGB').resize((756,425),Image.Resampling.LANCZOS)
    out.paste(im,(x,y+42))
out.save(base/'scene-and-equipment.png')
data={'snapshot':'2026-10-20 14:20:08','kind':'demonstration','sourceTotals':'../business-demo-data.json','completedOrderTrend':{'times':['06:00:00','08:00:00','10:00:00','12:00:00','14:00:00','14:20:08'],'inbound':[0,12,38,66,92,96],'outbound':[0,18,48,78,112,118],'axisMax':150},'rackA03':{'kind':'demonstration distribution, not CAD coordinates','total':48,'freeBins':[13,20,27,34,41,42,43,44],'lockedBins':[15,30,45,48],'selectedBin':12}}
assert data['completedOrderTrend']['inbound'][-1]==96
assert data['completedOrderTrend']['outbound'][-1]==118
for k in ['inbound','outbound']:
    vals=data['completedOrderTrend'][k]
    assert all(a<=b for a,b in zip(vals,vals[1:]))
free=set(data['rackA03']['freeBins']);locked=set(data['rackA03']['lockedBins'])
assert not free & locked and 48-len(free)-len(locked)==36
assert 12 not in free|locked and 13 in free and 15 in locked
(base.parent.parent/'visual-demo-data.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print('23 screens exported; 3 overview sheets rendered; demo trend and 48-bin distribution verified.')
