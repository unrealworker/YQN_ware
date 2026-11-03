"""Multiview physical-geometry review; context only, never saves scene assets."""
from pathlib import Path
import bpy,json,math,hashlib
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[2];FOLDER=ROOT/'SourceAssets/MPR/reference_v4/context';OUT=FOLDER/'plan_validation';OUT.mkdir(exist_ok=True)
manifest=json.loads((FOLDER/'manifest.json').read_text(encoding='utf8'));bpy.ops.wm.open_mainfile(filepath=str(FOLDER/'mpr4_reference_context.blend'))
scene=bpy.context.scene
for row in manifest['meshes']:
    if row.get('instance_only'):bpy.data.objects[row['name']].hide_render=True
for ob in list(scene.objects):
    if ob.type in ('LIGHT','CAMERA'):bpy.data.objects.remove(ob,do_unlink=True)
scene.render.engine='CYCLES';scene.cycles.samples=24;scene.cycles.use_denoising=True;scene.cycles.max_bounces=4
preferences=bpy.context.preferences.addons['cycles'].preferences
try:
    preferences.compute_device_type='OPTIX';preferences.get_devices()
    for d in preferences.devices:d.use=d.type=='OPTIX'
    scene.cycles.device='GPU'
except Exception:scene.cycles.device='CPU'
scene.render.resolution_x=1280;scene.render.resolution_y=800;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.view_settings.view_transform='AgX';scene.view_settings.look='AgX - Medium High Contrast';scene.view_settings.exposure=0
world=bpy.data.worlds.new('PlanGeometryReviewWorld');world.use_nodes=True;scene.world=world
background=next(n for n in world.node_tree.nodes if n.type=='BACKGROUND');background.inputs['Color'].default_value=(.68,.76,.86,1);background.inputs['Strength'].default_value=.35
bpy.ops.object.light_add(type='SUN');sun=bpy.context.object;sun.data.energy=2.8;sun.data.angle=math.radians(9);sun.rotation_euler=(math.radians(27),math.radians(-25),math.radians(-35))
bpy.ops.mesh.primitive_plane_add(size=3000,location=(0,0,-1.24));ground=bpy.context.object;mat=bpy.data.materials.new('ReviewGround');mat.use_nodes=True
shader=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED');shader.inputs['Base Color'].default_value=(.29,.33,.28,1);shader.inputs['Roughness'].default_value=.9;ground.data.materials.append(mat)
bpy.ops.object.camera_add();cam=bpy.context.object;scene.camera=cam;cam.data.type='ORTHO';cam.data.clip_end=5000
houses=[r for r in manifest['context_buildings']if r['type']=='house_gable'];house=min(houses,key=lambda x:(x['physical_frame']['center_m'][0]+310)**2+(x['physical_frame']['center_m'][1]-140)**2)
cx,cy=house['physical_frame']['center_m'];target=(cx,cy,2.8)
l=next(r for r in manifest['context_buildings']if r['id']=='northwest_l_office');lx,ly=l['physical_frame']['center_m']
views=[('01-houses-front',target,(-55,-65,48),64),('02-houses-rear',target,(55,65,48),64),('03-houses-low',target,(-50,-68,20),53),
       ('04-neighbor-real-recess',(20,125,4),(-28,-65,25),84),('05-north-l-building',(lx,ly,3),(-95,-110,90),133)]
report=[]
for name,point,offset,scale in views:
    point=Vector(point);cam.location=point+Vector(offset);cam.rotation_euler=(point-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.ortho_scale=scale
    path=OUT/(name+'.png');scene.render.filepath=str(path);bpy.ops.render.render(write_still=True)
    report.append(dict(name=name,path=path.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),camera_position=list(cam.location),camera_target=list(point),orthographic_scale_m=scale))
(OUT/'render_report.json').write_text(json.dumps(dict(success=True,source_blend_sha256=hashlib.sha256((FOLDER/'mpr4_reference_context.blend').read_bytes()).hexdigest(),views=report,
    boundary='Context-only Blender lighting setup for geometric inspection. Does not certify final UE illumination, scene composition or runtime performance.'),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('MPR_CONTEXT_MULTIVIEW_READY',len(report))
