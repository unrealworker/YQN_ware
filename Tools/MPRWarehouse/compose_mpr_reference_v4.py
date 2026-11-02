"""V4 reference-camera exterior composition; source libraries remain read-only.

Until final foliage is supplied, --proxy-trees places V3 modules at V4 traced
crown positions/radii and explicitly reports those as temporary proxies.
Run: blender -b -t 1 --python this.py -- --render --proxy-trees
"""
from pathlib import Path
import sys,json,math
import bpy
from mathutils import Matrix,Vector
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).parent))
import compose_mpr_reference_scene as core
core.OUT=ROOT/'SourceAssets/MPR/reference_v4'
core.REV=core.OUT/'validation_blender';core.REV.mkdir(parents=True,exist_ok=True)
V3=ROOT/'SourceAssets/MPR/reference_v3'
CAL=V3/'calibration/camera_calibration.json'
core.FILES={
 'architecture':(V3/'architecture/reference_shell_manifest.json',V3/'architecture/mpr_reference_shell.blend'),
 'site':(core.OUT/'site/manifest.json',core.OUT/'site/MPR_ReferenceSite.blend'),
 'context':(core.OUT/'context/manifest.json',core.OUT/'context/mpr4_reference_context.blend'),
 'props':(V3/'props/manifest.json',V3/'props/MPR_Reference_Props.blend')}
architecture4=core.OUT/'architecture/reference_shell_manifest.json'
if architecture4.exists():core.FILES['architecture']=(architecture4,core.OUT/'architecture/mpr_reference_shell.blend')
props4=core.OUT/'props/manifest.json'
if props4.exists():
 candidates=list((core.OUT/'props').glob('*.blend'))
 preferred=[core.OUT/'props'/n for n in ['MPR_ReferenceV4_Props.blend','MPR_ReferenceV4_PropsPrototype.blend'] if (core.OUT/'props'/n).exists()]
 if preferred:candidates=preferred[:1]
 if len(candidates)==1:
  core.FILES['props']=(props4,candidates[0])
  if '--proxy-trees' in sys.argv:core.FILES['proxy_foliage']=(V3/'props/manifest.json',V3/'props/MPR_Reference_Props.blend')
core.INSTANCE_GROUPS=['architecture','site','context']

def augment(manifests,masters):
 import hashlib
 trees=manifests['site'].get('planting',{}).get('tree_positions',[])
 props=manifests.get('proxy_foliage',manifests['props']);byname={r['name']:r for r in props['meshes']}
 proxy='--proxy-trees' in sys.argv;placed=0
 fallback=[]
 for name in manifests['site'].get('instances',{}):
  if name not in masters and name.replace('SM_MPR4_','SM_MPR3_') in masters:
   masters[name]=masters[name.replace('SM_MPR4_','SM_MPR3_')];fallback.append(name)
 if not proxy:
  from mpr_reference_catalog import load_catalog
  catalog=load_catalog(ROOT,require_final='--review-models' not in sys.argv)
  groups={'Architecture':'architecture','Context':'context','Props':'site','Site':'site'}
  owners={row['name']:groups[category] for category,row in catalog['rows']}
  for group in core.INSTANCE_GROUPS:manifests[group]['instances']={}
  for name,placements in catalog['instances'].items():manifests[owners[name]]['instances'][name]=placements
 for i,row in enumerate(trees if proxy else []):
  name='SM_MPR3_Tree_'+str(i%3)
  if name not in masters:
   raise RuntimeError('Temporary tree library is missing '+name)
  radius=byname[name]['metadata']['crown_radius_m'];scale=float(row['crown_radius_m'])/radius
  height_scale=12.0/byname[name]['metadata']['height_m']
  manifests['site'].setdefault('instances',{}).setdefault(name,[]).append(dict(position_m=row['position_m'],
      rotation_deg=row.get('rotation_deg',0),scale=[scale,scale,height_scale],temporary_proxy=True,requested_crown_radius_m=row['crown_radius_m']))
  placed+=1
 # Store composition-expanded placements without mutating the root site source.
 (core.REV/'composition_instances.json').write_text(json.dumps({k:manifests[k].get('instances',{}) for k in core.INSTANCE_GROUPS},ensure_ascii=False,indent=2),encoding='utf8')
 return dict(reference_version=4,reference_camera_calibration=CAL.relative_to(ROOT).as_posix(),
  reference_camera_sha256=hashlib.sha256(CAL.read_bytes()).hexdigest(),temporary_tree_proxy=proxy,temporary_proxy_tree_count=placed,
  source_models_pending_visual_review='--review-models' in sys.argv,
  temporary_vehicle_proxy_names=fallback,
  tree_scale_contract='mpr_reference_catalog.load_catalog; geometry/scale identical for review and final' if not proxy else 'V3 proxy XY crown radius; 12m estimated proxy height',
  interim_components=(['V3 main shell appearance retained pending V4 details'] if not architecture4.exists() else [])+(['V3 foliage scaled to V4 crown radii; layout check only, not final tree appearance'] if proxy else []))

def configure():
 cal=json.loads(CAL.read_text(encoding='utf8'));spec=cal['blender_camera'];scene=bpy.context.scene
 scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=96;scene.cycles.use_denoising=True;scene.cycles.max_bounces=4
 try:
  prefs=bpy.context.preferences.addons['cycles'].preferences;prefs.compute_device_type='OPTIX';prefs.get_devices()
  gpu=[d for d in prefs.devices if d.type=='OPTIX']
  for d in prefs.devices:d.use=d in gpu
  if gpu:scene.cycles.device='GPU';print('MPR4_RENDER_DEVICE',[d.name for d in gpu],flush=True)
 except Exception as error:print('MPR4_RENDER_CPU_FALLBACK',str(error),flush=True)
 scene.render.threads_mode='FIXED';scene.render.threads=1;scene.render.resolution_x,scene.render.resolution_y=cal['image_dimensions_px']
 scene.render.resolution_percentage=100;scene.render.pixel_aspect_x=scene.render.pixel_aspect_y=1
 scene.render.image_settings.file_format='PNG';scene.view_settings.view_transform='AgX';scene.view_settings.look='AgX - Medium High Contrast';scene.view_settings.exposure=1.0
 world=bpy.data.worlds.new('MPR4_ReferenceDaylight');world.use_nodes=True;scene.world=world
 bg=next(n for n in world.node_tree.nodes if n.type=='BACKGROUND');bg.inputs['Color'].default_value=(.70,.80,.92,1);bg.inputs['Strength'].default_value=.40
 lights=core.collection('V4_REFERENCE_CAMERAS_LIGHTS');sun=bpy.data.lights.new('MPR4_Sun','SUN');sun.energy=2.8;sun.angle=math.radians(16)
 ob=bpy.data.objects.new('MPR4_Sun',sun);lights.objects.link(ob);ob.rotation_euler=Vector((-.50,-.35,-.79)).to_track_quat('-Z','Y').to_euler()
 data=bpy.data.cameras.new('MPR4_AuthoritativeReference');data.type='PERSP';data.lens=spec['lens_mm'];data.sensor_width=36;data.sensor_fit='HORIZONTAL'
 data.shift_x=spec['shift_x'];data.shift_y=spec['shift_y'];data.clip_start=.1;data.clip_end=10000
 camera=bpy.data.objects.new('MPR4_AuthoritativeReference',data);lights.objects.link(camera);camera.matrix_world=Matrix(spec['matrix_world'])
 label='Authoritative_Overview_PROXY' if '--proxy-trees' in sys.argv else 'Authoritative_Overview_REVIEW' if '--review-models' in sys.argv else 'Authoritative_Overview'
 scene.camera=camera;return [(label,camera)]

core.augment_manifests=augment
core.configure_preview=configure
if __name__=='__main__':core.build()
