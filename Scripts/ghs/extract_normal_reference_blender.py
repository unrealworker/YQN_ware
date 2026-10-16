"""Use Blender's bundled video decoder for read-only reference extraction."""
import bpy,json,hashlib
from pathlib import Path
source=Path(r'D:\DDDownload\normal_video.mp4')
out=Path(r'D:\UEPro\Test\SourceAssets\GHS_Normal\Reference');out.mkdir(parents=True,exist_ok=True)
scene=bpy.context.scene
clip=bpy.data.movieclips.load(str(source))
width,height=clip.size;fps=clip.fps;count=clip.frame_duration
scene.render.engine='BLENDER_WORKBENCH';scene.render.resolution_x=width;scene.render.resolution_y=height;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGB'
scene.render.fps=round(fps);scene.render.fps_base=round(fps)/fps
scene.view_settings.view_transform='Standard';scene.view_settings.look='None';scene.view_settings.exposure=0;scene.view_settings.gamma=1
seq=scene.sequence_editor_create()
seq.strips.new_movie('ReferenceVideo',str(source),channel=1,frame_start=1)
scene.render.use_sequencer=True;scene.render.use_compositing=False
frames=[]
for i in range(12):
    frame=max(1,min(count,int(count*(i+.35)/12)))
    path=out/f'frame_{i+1:02d}.png';scene.frame_set(frame);scene.render.filepath=str(path)
    bpy.ops.render.render(write_still=True)
    frames.append(dict(time_seconds=round((frame-1)/fps,3),frame=frame,path=str(path)))
(out/'reference.json').write_text(json.dumps(dict(source=str(source),sha256=hashlib.sha256(source.read_bytes()).hexdigest(),duration_seconds=count/fps,fps=fps,size=[width,height],frames=frames),indent=2),encoding='utf-8')
print('NORMAL_REFERENCE_EXTRACTED',count/fps,width,height)
