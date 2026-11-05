"""Render isolated source-model overview/dock/roof previews, one CPU thread."""
import bpy,math,sys
from pathlib import Path
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'SourceAssets/MPR/reference_v3/architecture'
bpy.ops.wm.open_mainfile(filepath=str(OUT/'mpr_reference_shell.blend'))
scene=bpy.context.scene
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=16;scene.cycles.use_denoising=True
scene.cycles.max_bounces=4;scene.render.threads_mode='FIXED';scene.render.threads=1
scene.render.resolution_x=1280;scene.render.resolution_y=800;scene.render.resolution_percentage=100
scene.view_settings.view_transform='AgX';scene.view_settings.exposure=.65
world=bpy.data.worlds.new('PreviewWorld');world.use_nodes=True
world.node_tree.nodes['Background'].inputs[0].default_value=(.73,.80,.89,1)
world.node_tree.nodes['Background'].inputs[1].default_value=.7;scene.world=world
bpy.ops.mesh.primitive_plane_add(size=1200,location=(0,0,-1.23));ground=bpy.context.object
mat=bpy.data.materials.new('PreviewGround');mat.diffuse_color=(.31,.35,.39,1);mat.use_nodes=True
bs=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
bs.inputs['Base Color'].default_value=(.31,.35,.39,1)
bs.inputs['Roughness'].default_value=.85;ground.data.materials.append(mat)
bpy.ops.object.light_add(type='SUN',location=(0,-100,200));sun=bpy.context.object
sun.data.energy=2.0;sun.data.angle=math.radians(18);sun.rotation_euler=(math.radians(25),math.radians(-28),math.radians(-40))
bpy.ops.object.camera_add();camera=bpy.context.object;scene.camera=camera
views=[('overview',(180,-430,310),(-5,-5,5),465),('dock',(-145,-102,5.4),(-136,-83.8,2.2),None),('roof',(95,-70,15.3),(88,-60,13.4),None)]
args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
if args:views=[v for v in views if v[0] in args]
for name,p,t,ortho in views:
 camera.location=p;camera.rotation_euler=(Vector(t)-camera.location).to_track_quat('-Z','Y').to_euler()
 camera.data.type='ORTHO' if ortho else 'PERSP';camera.data.lens=42
 if ortho:camera.data.ortho_scale=ortho
 camera.data.clip_end=2000;scene.render.filepath=str(OUT/('preview_'+name+'.png'))
 bpy.ops.render.render(write_still=True)
