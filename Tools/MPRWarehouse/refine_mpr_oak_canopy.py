"""Review an oval, continuous fine-leaf canopy under the reference ground ray.

Reads the approved V4 library; writes only props/canopy_review until accepted.
No vehicles, UE assets, placements or shared scene sources are modified.
"""
from pathlib import Path
import bpy,math,random,json,sys
from mathutils import Vector,Matrix
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).parent))
import build_mpr_reference_v4_props as base
OUT=ROOT/'SourceAssets/MPR/reference_v4/props/canopy_review'


def build():
 OUT.mkdir(parents=True,exist_ok=True)
 bpy.ops.wm.open_mainfile(filepath=str(base.OUT/'MPR_ReferenceV4_Props.blend'))
 old=bpy.data.objects['SM_MPR4_Tree_Oak'];used=sorted({i for p in old.data.polygons if p.material_index==0 for i in p.vertices});index={n:i for i,n in enumerate(used)}
 vv=[(old.data.vertices[i].co.x*.80,old.data.vertices[i].co.y*.80,old.data.vertices[i].co.z*1.25) for i in used]
 ff=[tuple(index[i] for i in p.vertices) for p in old.data.polygons if p.material_index==0];roles=['MPR4_Bark']*len(ff)
 bpy.ops.wm.read_factory_settings(use_empty=True)
 bpy.context.scene.world=bpy.data.worlds.new('CanopyReviewWorld')
 bpy.context.scene.unit_settings.system='METRIC';bpy.context.scene.unit_settings.scale_length=1
 mats,specs=base.make_materials();rng=random.Random(90426);N=220000
 # Every canopy surface is a real 8-15cm leaf. Most leaves occupy a thin but
 # volumetric outer layer, with 25% filling the crown interior. Several smooth
 # low-frequency bulges make the envelope layered rather than a perfect egg.
 for i in range(N):
  az=rng.random()*math.tau;uz=rng.uniform(-1,1);rad=math.sqrt(1-uz*uz)
  wave=1+.055*math.sin(az*5+uz*3.1)*rad+.032*math.cos(az*9-uz*5.7)*rad+.025*math.sin(uz*14+az*3)
  r=rng.uniform(.86,1) if i%4 else rng.random()**(1/3)*.87
  # The upper crown tapers gently. The lower half is broad and rounded, with
  # a clear trunk beneath its Z=3.8m underside.
  taper=1-.12*max(uz,0)
  p=Vector((5.75*rad*math.cos(az)*wave*r*taper,5.55*rad*math.sin(az)*wave*r*taper,9.8+5.9*uz*wave*r))
  p+=Vector((rng.uniform(-.045,.045),rng.uniform(-.045,.045),rng.uniform(-.045,.045)))
  normal=(Vector((rad*math.cos(az),rad*math.sin(az),uz))*.45+Vector((0,0,.65))+Vector((rng.uniform(-.6,.6),rng.uniform(-.6,.6),rng.uniform(-.4,.4)))).normalized()
  axis=normal.cross(Vector((1,0,.01))).normalized();across=normal.cross(axis).normalized();turn=rng.random()*math.tau
  d=axis*math.cos(turn)+across*math.sin(turn);side=normal.cross(d)
  length=rng.uniform(.08,.15);width=length*rng.uniform(.68,.88);off=len(vv)
  vv.extend([tuple(p-d*length*.5),tuple(p-side*width*.5),tuple(p+d*length*.5),tuple(p+side*width*.5),tuple(p+normal*length*.075)])
  ff.extend([(off,off+1,off+4),(off+1,off+2,off+4),(off+2,off+3,off+4),(off+3,off,off+4)])
  role=rng.choices(['MPR4_LeafMid','MPR4_LeafLight','MPR4_LeafShade'],[.5,.32,.18])[0];roles.extend([role]*4)
 tree=base.mesh_object('SM_MPR4_Tree_Oak',vv,ff,['MPR4_Bark','MPR4_LeafMid','MPR4_LeafLight','MPR4_LeafShade'],roles,mats)
 for p in tree.data.polygons:p.use_smooth=p.material_index==0
 tree.data.calc_loop_triangles();b=base.bounds(tree)
 metadata=dict(triangles=len(tree.data.loop_triangles),leaf_count=N,bounds_m=b,crown_radius_m=max(b[0][1]-b[0][0],b[1][1]-b[1][0])/2,height_m=b[2][1],geometry='Native oak scaffold, individual bent fine leaves in a volumetric oval canopy; no solid filler',review_status='pending_calibrated_aerial_review')
 (OUT/'metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf8')
 bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'OakCanopy_Review.blend'))
 print('CANOPY_REVIEW_GEOMETRY_READY',json.dumps(metadata),flush=True)
 render(tree)


def render(tree):
 scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=16;scene.cycles.use_denoising=True
 prefs=bpy.context.preferences.addons['cycles'].preferences;prefs.compute_device_type='OPTIX';prefs.get_devices()
 for device in prefs.devices:device.use=device.type=='OPTIX'
 scene.cycles.device='GPU'
 scene.render.threads_mode='FIXED';scene.render.threads=1;scene.render.resolution_x=1600;scene.render.resolution_y=1000
 scene.view_settings.view_transform='AgX';scene.view_settings.look='AgX - Medium High Contrast';scene.view_settings.exposure=1
 bg=next(n for n in scene.world.node_tree.nodes if n.type=='BACKGROUND');bg.inputs['Color'].default_value=(.70,.80,.92,1);bg.inputs['Strength'].default_value=.4
 sun=bpy.data.lights.new('ReferenceSun','SUN');sun.energy=2.8;sun.angle=math.radians(16);so=bpy.data.objects.new('ReferenceSun',sun);scene.collection.objects.link(so);so.rotation_euler=(math.radians(25),math.radians(-26),math.radians(-28))
 mat=bpy.data.materials.new('ReferenceGround');mat.use_nodes=True;next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED').inputs['Base Color'].default_value=(.37,.43,.31,1)
 bpy.ops.mesh.primitive_plane_add(size=500,location=(0,0,-.01));bpy.context.object.data.materials.append(mat)
 cam=bpy.data.cameras.new('ReferenceRayCamera');co=bpy.data.objects.new('ReferenceRayCamera',cam);scene.collection.objects.link(co);scene.camera=co;cam.type='ORTHO';cam.ortho_scale=48;cam.clip_end=1000
 cal=json.loads((ROOT/'SourceAssets/MPR/reference_v3/calibration/camera_calibration.json').read_text());ray=(Vector(cal['camera_location_m'])-Vector((0,-200,8))).normalized()
 target=Vector((0,2,7));co.location=target+ray*100;co.rotation_euler=(target-co.location).to_track_quat('-Z','Y').to_euler()
 for j,(x,y,scale) in enumerate([(-17,7,.90),(17,7,1.02)]):
  ob=bpy.data.objects.new('CanopyGroup_'+str(j),tree.data);scene.collection.objects.link(ob);ob.location=(x,y,0);ob.scale=(scale,)*3;ob.rotation_euler.z=2.1*j+.9
 scene.render.image_settings.file_format='PNG';scene.render.filepath=str(OUT/'oak_calibrated_aerial.png');bpy.ops.render.render(write_still=True)
 # A second view preserves near-shape evidence with exactly the same geometry.
 cam.ortho_scale=38;target=Vector((0,0,8));co.location=(23,-35,19);co.rotation_euler=(target-co.location).to_track_quat('-Z','Y').to_euler()
 for ob in scene.objects:
  if ob.name.startswith('CanopyGroup_'):ob.hide_render=True
 scene.render.filepath=str(OUT/'oak_close.png');bpy.ops.render.render(write_still=True)
 print('CANOPY_REVIEW_RENDERS_READY',flush=True)


if __name__=='__main__':build()
