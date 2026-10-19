"""Portrait framing for review; the caller controls collection visibility."""
import bpy
from pathlib import Path
from mathutils import Vector
s=bpy.context.scene;cam=s.camera
out=Path(r'D:/UEPro/Test/SourceAssets/GHS_Normal/MannedForklift')
old=(cam.matrix_world.copy(),cam.data.ortho_scale,s.render.resolution_x,s.render.resolution_y,s.render.filepath)
try:
    cam.location=(2.1,-2.9,2.04)
    cam.rotation_euler=(Vector((-.29,0,1.57))-cam.location).to_track_quat('-Z','Y').to_euler()
    cam.data.ortho_scale=1.12
    s.render.resolution_x=1050;s.render.resolution_y=1200;s.render.resolution_percentage=100
    s.render.filepath=str(out/'worker_v3_detail.png')
    bpy.ops.render.render(write_still=True)
finally:
    cam.matrix_world=old[0];cam.data.ortho_scale=old[1]
    s.render.resolution_x=old[2];s.render.resolution_y=old[3];s.render.filepath=old[4]
    bpy.context.view_layer.update()
print('WORKER_DETAIL_RENDER',str(out/'worker_v3_detail.png'))
