"""Sample the user's video into timestamped reference frames."""
import sys,subprocess,re,json,hashlib
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(r'D:\UEPro\Test')
sys.path.insert(0,str(ROOT/'Scripts/_vendor/video'))
import imageio_ffmpeg
exe=imageio_ffmpeg.get_ffmpeg_exe()
source=Path(r'D:\DDDownload\normal_video.mp4')
out=ROOT/'SourceAssets/GHS_Normal/Reference';out.mkdir(parents=True,exist_ok=True)
probe=subprocess.run([exe,'-hide_banner','-i',str(source)],capture_output=True,text=True,encoding='utf-8',errors='replace')
metadata=probe.stderr
match=re.search(r'Duration: (\d+):(\d+):(\d+(?:\.\d+)?)',metadata);assert match,metadata
duration=int(match[1])*3600+int(match[2])*60+float(match[3])
times=[duration*(i+.35)/12 for i in range(12)]
frames=[]
for i,t in enumerate(times):
    path=out/f'frame_{i+1:02d}.png'
    subprocess.run([exe,'-hide_banner','-loglevel','error','-y','-ss',str(t),'-i',str(source),'-frames:v','1',str(path)],check=True,capture_output=True)
    frames.append(dict(time_seconds=round(t,3),path=str(path)))
tile_w=480;tile_h=300
sheet=Image.new('RGB',(tile_w*4,tile_h*3),'#17212b');draw=ImageDraw.Draw(sheet)
font=ImageFont.truetype(r'C:\Windows\Fonts\segoeui.ttf',18)
for i,f in enumerate(frames):
    im=Image.open(f['path']).convert('RGB');im.thumbnail((tile_w,tile_h-28))
    x=(i%4)*tile_w;y=(i//4)*tile_h
    sheet.paste(im,(x+(tile_w-im.width)//2,y+28))
    draw.text((x+12,y+4),f"{i+1:02d} | {f['time_seconds']:.2f} sec",font=font,fill='white')
sheet.save(out/'contact_sheet.jpg',quality=95)
report=dict(source=str(source),sha256=hashlib.sha256(source.read_bytes()).hexdigest(),duration_seconds=duration,frames=frames,ffmpeg_metadata=metadata)
(out/'reference.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(dict(duration_seconds=duration,contact_sheet=str(out/'contact_sheet.jpg')),indent=2))
