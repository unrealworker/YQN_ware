"""Extract reference frames using Blender's installed video decoder."""
import bpy
import json
import sys
from pathlib import Path

source=Path(r'D:\WinAPP\WechatData\xwechat_files\wxid_9l6pu9lrlmbm12_cd7f\msg\video\2026-10\6dc2988787ab4c342c807e37633a086d_raw.mp4')
out=Path(r'D:\UEPro\Test\SourceAssets\VideoReference\Frames')
out.mkdir(parents=True,exist_ok=True)
clip=bpy.data.movieclips.load(str(source))
fps=clip.fps
duration=clip.frame_duration/fps
scene=bpy.context.scene
sequence=scene.sequence_editor_create()
movie=sequence.strips.new_movie('Reference',str(source),channel=1,frame_start=1)
scene.render.fps=round(fps)
scene.render.resolution_x=1920
scene.render.resolution_y=1080
args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
scene.render.resolution_percentage=100 if args else 50
scene.render.image_settings.file_format='PNG'
scene.render.use_sequencer=True
scene.view_settings.view_transform='Standard'
scene.view_settings.look='None'
frames=[]
for t in ([int(a) for a in args] if args else list(range(0,76,5))):
    f=min(clip.frame_duration,round(t*fps)+1)
    scene.frame_set(f)
    path=out/('frame_%03ds.png'%t)
    scene.render.filepath=str(path)
    bpy.ops.render.render(write_still=True)
    frames.append(dict(seconds=t,frame=f,file=str(path)))
(out.parent/'video_metadata.json').write_text(json.dumps(dict(source=str(source),fps=fps,duration_seconds=duration,size=list(clip.size),frames=frames),indent=2),encoding='utf-8')
print('VIDEO_FRAMES_EXTRACTED',duration,len(frames))
