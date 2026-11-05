"""Validate Blender projection and render the main shell at the calibrated camera."""
import bpy,json,math,sys
from pathlib import Path
from mathutils import Matrix,Vector
from bpy_extras.object_utils import world_to_camera_view
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'SourceAssets/MPR/reference_v3/calibration'
cal=json.loads((OUT/'camera_calibration.json').read_text(encoding='utf8'))
source=ROOT/'SourceAssets/MPR/reference_v3/architecture/mpr_reference_shell.blend'
bpy.ops.wm.open_mainfile(filepath=str(source));scene=bpy.context.scene
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=24;scene.cycles.use_denoising=True;scene.cycles.max_bounces=4
scene.render.threads_mode='FIXED';scene.render.threads=1
scene.render.resolution_x,scene.render.resolution_y=cal['image_dimensions_px'];scene.render.resolution_percentage=100
scene.render.pixel_aspect_x=scene.render.pixel_aspect_y=1
scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGBA';scene.render.film_transparent=True
scene.view_settings.view_transform='AgX';scene.view_settings.look='AgX - Medium High Contrast';scene.view_settings.exposure=.25
world=bpy.data.worlds.new('CalibrationWorld');world.use_nodes=True;scene.world=world
bg=next(n for n in world.node_tree.nodes if n.type=='BACKGROUND');bg.inputs['Color'].default_value=(.70,.80,.92,1);bg.inputs['Strength'].default_value=.3
bpy.ops.object.light_add(type='SUN');sun=bpy.context.object;sun.data.energy=2.8;sun.data.angle=math.radians(12)
sun.rotation_euler=(math.radians(25),math.radians(-26),math.radians(-28))
bpy.ops.object.camera_add();camera=bpy.context.object;camera.name='MPR_Authoritative_Reference_Camera';scene.camera=camera
spec=cal['blender_camera'];camera.matrix_world=Matrix(spec['matrix_world']);camera.data.type='PERSP'
camera.data.lens=spec['lens_mm'];camera.data.sensor_width=spec['sensor_width_mm'];camera.data.sensor_fit=spec['sensor_fit']
camera.data.shift_x=spec['shift_x'];camera.data.shift_y=spec['shift_y'];camera.data.clip_start=.1;camera.data.clip_end=10000
bpy.context.view_layer.update()
rows=[];W,H=cal['image_dimensions_px']
for point in cal['correspondences']:
 uv=world_to_camera_view(scene,camera,Vector(point['world_m']));pixel=[uv.x*W,(1-uv.y)*H]
 error=math.dist(pixel,point['projected_pixel']);rows.append(dict(id=point['id'],blender_pixel=pixel,analytic_pixel=point['projected_pixel'],difference_px=error))
maximum=max(row['difference_px'] for row in rows);assert maximum<.01,('Camera shift/convention mismatch',maximum)
(OUT/'blender_camera_validation.json').write_text(json.dumps(dict(success=True,maximum_analytic_vs_blender_difference_px=maximum,points=rows),indent=2),encoding='utf8')
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'MPR_CalibratedShell.blend'))
scene.render.filepath=str(OUT/'calibrated_main_shell.png');bpy.ops.render.render(write_still=True)
print('MPR_CAMERA_RENDER_COMPLETE',maximum)
