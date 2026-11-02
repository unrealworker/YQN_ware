"""Offline asset-board render; does not modify the exported asset library."""
import bpy,sys,pathlib,json
from mathutils import Vector
ROOT=pathlib.Path(__file__).resolve().parents[2];OUT=ROOT/'SourceAssets/MPR/operations'
bpy.ops.wm.open_mainfile(filepath=str(OUT/'mpr_operations.blend'))
objs=[o for o in bpy.context.scene.objects if o.type=='MESH' and o.name!='SM_MPR_SorterPlatform']
for o in bpy.context.scene.objects:
 if o.name=='SM_MPR_SorterPlatform':o.hide_render=True
for i,o in enumerate(objs):o.location=((i%4)*3,(i//4)*3,0)
scene=bpy.context.scene
scene.render.engine='CYCLES';scene.cycles.samples=16;scene.cycles.use_denoising=True
scene.render.resolution_x=1500;scene.render.resolution_y=900;scene.render.resolution_percentage=100
bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,-.05));plane=bpy.context.object
mat=bpy.data.materials.new('PreviewFloor');mat.use_nodes=True
next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED').inputs['Base Color'].default_value=(.24,.31,.40,1);plane.data.materials.append(mat)
scene.world.color=(.2,.2,.2)
for loc,power,size in [((4,-3,10),1800,7),((0,5,9),1200,7)]:
 bpy.ops.object.light_add(type='AREA',location=loc);light=bpy.context.object;light.data.energy=power;light.data.shape='DISK';light.data.size=size;light.rotation_euler=(Vector((4,1.5,0))-light.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(16,-14,15));cam=bpy.context.object;cam.rotation_euler=(Vector((4.3,2.7,.5))-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.type='ORTHO';cam.data.ortho_scale=15.5;scene.camera=cam
scene.render.image_settings.file_format='PNG';scene.render.filepath=str(OUT/'mpr_operations_preview.png');bpy.ops.render.render(write_still=True)
