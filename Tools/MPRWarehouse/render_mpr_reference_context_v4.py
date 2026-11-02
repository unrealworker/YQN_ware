"""Assemble reference-placed context instances and render overview/dock proof."""
import bpy,json,math
from pathlib import Path
from mathutils import Matrix,Vector

ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'SourceAssets/MPR/reference_v4/context'
manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
cal=json.loads((ROOT/'SourceAssets/MPR/reference_v3/calibration/camera_calibration.json').read_text(encoding='utf-8'))
bpy.ops.wm.open_mainfile(filepath=str(OUT/'mpr4_reference_context.blend'))
scene=bpy.context.scene;templates={o.name:o for o in scene.objects if o.type=='MESH'}
for row in manifest['meshes']:
    ob=templates[row['name']]
    if row.get('instance_only'):
        ob.hide_render=True;ob.hide_viewport=True
for name,rows in manifest['instances'].items():
    for i,row in enumerate(rows):
        ob=bpy.data.objects.new(name+'_instance_%03d'%i,templates[name].data);scene.collection.objects.link(ob)
        ob.location=row['position_m'];ob.rotation_euler.z=math.radians(row['rotation_deg']);ob.scale=row['scale']
scene.render.engine='CYCLES';scene.cycles.samples=24;scene.cycles.use_denoising=True;scene.cycles.max_bounces=4
scene.render.resolution_x,scene.render.resolution_y=cal['image_dimensions_px'];scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGBA';scene.render.film_transparent=True
scene.view_settings.view_transform='AgX';scene.view_settings.look='AgX - Medium High Contrast';scene.view_settings.exposure=.25
world=bpy.data.worlds.new('ContextReviewWorld');world.use_nodes=True;scene.world=world
bg=next(n for n in world.node_tree.nodes if n.type=='BACKGROUND');bg.inputs['Color'].default_value=(.70,.80,.92,1);bg.inputs['Strength'].default_value=.3
bpy.ops.object.light_add(type='SUN');sun=bpy.context.object;sun.data.energy=2.8;sun.data.angle=math.radians(12)
sun.rotation_euler=(math.radians(25),math.radians(-26),math.radians(-28))
bpy.ops.object.camera_add();cam=bpy.context.object;cam.name='ContextReferenceCamera';scene.camera=cam
spec=cal['blender_camera'];cam.matrix_world=Matrix(spec['matrix_world']);cam.data.type='PERSP'
cam.data.lens=spec['lens_mm'];cam.data.sensor_width=spec['sensor_width_mm'];cam.data.sensor_fit=spec['sensor_fit']
cam.data.shift_x=spec['shift_x'];cam.data.shift_y=spec['shift_y'];cam.data.clip_start=.1;cam.data.clip_end=10000
scene.render.filepath=str(OUT/'context_reference_camera.png');bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'MPR_ReferenceContext_V4.blend'))
building=next(r for r in manifest['context_buildings'] if r['id']=='neighbor_warehouse');points=building['footprint_m']
front=sorted(points,key=lambda p:p[1])[:2];target=Vector((sum(p[0] for p in front)/2,sum(p[1] for p in front)/2,5.0))
cam.location=target+Vector((-42,-92,33));cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.type='ORTHO';cam.data.ortho_scale=110;cam.data.shift_x=cam.data.shift_y=0
scene.render.resolution_x=1320;scene.render.resolution_y=800;scene.render.filepath=str(OUT/'neighbor_deep_docks.png');bpy.ops.render.render(write_still=True)
print('MPR4_CONTEXT_RENDERED',sum(len(v) for v in manifest['instances'].values()))
