"""Package the inspected UE captures and their exact saved-map provenance."""
import hashlib,json
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(r'D:\UEPro\Test')
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run():
    verification=read(ROOT/'Saved/GHS_CADRackVerification.json');assert verification['success']
    change=read(ROOT/'Saved/GHS_CADRackRevision.json');assert change['success']
    captures=[]
    for style in ['Normal','Blue']:
        report=read(ROOT/f'Saved/GHS_CADRack_{style}_CaptureReport.json')
        refined=read(ROOT/f'Saved/GHS_CADRack_{style}_DockD1_2UpperLevels_CaptureReport.json')
        assert report['success'] and refined['success']
        assert report['map_file_sha256']==refined['map_file_sha256']
        latest={s['view']:s for s in report['screenshots']}
        latest.update({s['view']:s for s in refined['screenshots']})
        assert len(latest)==6
        for view,s in latest.items():
            p=Path(s['path']);assert Image.open(p).size==(1920,1080)
            captures.append(dict(style=style,view=view,path=str(p),sha256=sha(p),camera=s['camera'],
                source_report=f'GHS_CADRack_{style}_'+('DockD1_2UpperLevels_' if view=='DockD1_2UpperLevels' else '')+'CaptureReport.json'))
        for name,path in [('Blue','GHS_CAD_DigitalTwin'),('Normal','GHS_CAD_NormalWarehouse')]:
            assert sha(ROOT/f'Content/Maps/{path}.umap')==report['map_file_sha256'][name]
    for p,s in change['changed_files'].items():assert sha(ROOT/p)==s['after_sha256']
    for p,s in change['new_assets'].items():assert sha(ROOT/p)==s
    canvas=Image.new('RGB',(2400,1460),'#101927');draw=ImageDraw.Draw(canvas)
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',30)
    for row,view in enumerate(['Overview','TypeB_12Levels']):
        for col,style in enumerate(['Normal','Blue']):
            x,y=col*1200,row*730
            draw.text((x+22,y+12),('浅灰场景' if style=='Normal' else '蓝色场景')+' · '+('CAD 全景比例' if row==0 else 'B 型 12 层货架'),font=font,fill='white')
            pic=Image.open(ROOT/f'Saved/GHS_CADRack_{style}_UE_{view}.png').convert('RGB')
            canvas.paste(pic.resize((1200,675),Image.Resampling.LANCZOS),(x,y+55))
    preview=ROOT/'Saved/GHS_CADRack_Comparison.png';canvas.save(preview)
    review=dict(success=True,verification_report='Saved/GHS_CADRackVerification.json',
        verification_sha256=sha(ROOT/'Saved/GHS_CADRackVerification.json'),captures=captures,preview=str(preview),
        reviewed_features=['CAD footprint and scale','A four storage levels','B twelve storage levels',
            'D1 upper two levels and clear loading doors','cross-aisle opening','matching blue and normal geometry'],
        camera_refinement='D1 recaptured from the open staging aisle to remove foreground rack occlusion; saved cameras/maps unchanged',
        assumptions=verification['assumptions'])
    (ROOT/'Saved/GHS_CADRackVisualReview.json').write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(success=True,captures=len(captures),preview=str(preview))))
if __name__=='__main__':run()
