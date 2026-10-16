"""Encode a GIF from actual foreground UE viewport captures, preserving timing."""
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageChops, ImageStat

ROOT=Path(r'D:\UEPro\Test')
capture=json.loads((ROOT/'Saved/AGVFX_LiveFrames/capture.json').read_text())
records=capture['frames']
raw=[Image.open(item['path']).convert('RGB') for item in records]
assert len(raw)==32 and len({hashlib.sha256(im.tobytes()).hexdigest() for im in raw})>=24
crop=(190,230,660,555)
frames=[im.crop(crop) for im in raw]
atlas=Image.new('RGB',(frames[0].width*4,frames[0].height))
for j,i in enumerate([0,8,16,24]):atlas.paste(frames[i],(j*frames[0].width,0))
palette=atlas.quantize(colors=256)
indexed=[im.quantize(palette=palette,dither=Image.Dither.NONE) for im in frames]
durations=[max(20,round((records[i+1]['elapsed_ms']-records[i]['elapsed_ms'])/10)*10) for i in range(len(records)-1)]
durations.append(durations[-1])
out=ROOT/'Saved/AGVFX_ActualAnimation.gif'
indexed[0].save(out,save_all=True,append_images=indexed[1:],duration=durations,loop=0,disposal=2,optimize=False)
frames[8].save(ROOT/'Saved/AGVFX_ActualAnimation_Poster.png')
atlas.save(ROOT/'Saved/AGVFX_AnimationComparison.png')
regions={'radar_sweep':(425,275,640,410),'ground_diffusion':(250,470,490,530)}
motion={name:ImageStat.Stat(ImageChops.difference(raw[0].crop(rect),raw[8].crop(rect))).mean
        for name,rect in regions.items()}
assert all(sum(value)>1 for value in motion.values()),motion
report=dict(success=True,source=capture['mode'],frame_count=len(frames),duration_ms=sum(durations),
            gif=str(out),crop=list(crop),motion_difference_rgb=motion,
            processing='Crop and GIF palette conversion only; recorded material time and screen content unchanged')
(ROOT/'Saved/AGVFX_AnimationProof.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
