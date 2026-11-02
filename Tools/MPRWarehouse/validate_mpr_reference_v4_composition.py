"""Reopen V4 exterior and verify source identities, catalog placement and camera."""
import bpy,json,math,hashlib,sys
from pathlib import Path
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'SourceAssets/MPR/reference_v4';REV=OUT/'validation_blender'
sys.path.insert(0,str(Path(__file__).parent))
from mpr_reference_catalog import load_catalog
catalog=load_catalog(ROOT,require_final=True)
report=json.loads((REV/'composition_manifest.json').read_text(encoding='utf8'))
for group,source in report['sources'].items():
 for field in ['manifest','blend']:
  assert hashlib.sha256((ROOT/source[field]).read_bytes()).hexdigest()==source[field+'_sha256'],(group,field,'source changed')
calpath=ROOT/report['reference_camera_calibration'];assert hashlib.sha256(calpath.read_bytes()).hexdigest()==report['reference_camera_sha256']
cal=json.loads(calpath.read_text(encoding='utf8'))
bpy.ops.wm.open_mainfile(filepath=str(OUT/'MPR_ReferenceExterior.blend'))
library=bpy.data.collections['MODULE_LIBRARY__HIDDEN'];assert library.hide_render and library.hide_viewport
masters={o.name:o for o in library.objects};owners={row['name']:category for category,row in catalog['rows']}
prefixes={'Architecture':'architecture','Context':'context','Site':'site','Props':'site'}
count=0;maxposition=0
for name,placements in catalog['instances'].items():
 group=prefixes[owners[name]]
 for i,p in enumerate(placements):
  obj=bpy.data.objects[f'{group}_{name}_{i:04}'];assert obj.data==masters[name].data
  assert not obj.hide_render and not obj.hide_viewport
  error=max(abs(obj.location[j]-p['position_m'][j]) for j in range(3));maxposition=max(maxposition,error);assert error<.0002
  assert max(abs(obj.scale[j]-p.get('scale',[1,1,1])[j]) for j in range(3))<.00001
  assert abs((math.degrees(obj.rotation_euler.z)-p.get('rotation_deg',0)+180)%360-180)<.0001
  count+=1
static=[r['name'] for category,r in catalog['rows'] if not r.get('instance_only')]
for name in static:assert bpy.data.objects[name].type=='MESH' and not bpy.data.objects[name].hide_render
assert not any('_Review' in o.name or '_LOD1' in o.name or '_LOD2' in o.name for o in bpy.context.scene.objects)
assert not any('SM_MPR_Floor' in o.name or 'OfficePartitions' in o.name for o in bpy.context.scene.objects)
scene=bpy.context.scene;W,H=cal['image_dimensions_px'];errors=[]
for p in cal['correspondences']:
 q=world_to_camera_view(scene,scene.camera,Vector(p['world_m']));errors.append(math.dist([q.x*W,(1-q.y)*H],p['projected_pixel']))
assert max(errors)<.01
images=[im for im in bpy.data.images if im.source=='FILE'];assert all(im.packed_file for im in images)
result=dict(success=True,sources_unchanged=True,reopened_blend=True,catalog_lod0_meshes=len(catalog['rows']),
 static_partitions=len(static),linked_instances=count,max_position_error_m=maxposition,hidden_modules=len(masters),
 packed_texture_images=len(images),calibrated_camera_max_error_px=max(errors),
 no_temporary_tree_proxies=not report['temporary_tree_proxy'],no_interior_assets=True,
 output_sha256=hashlib.sha256((OUT/'MPR_ReferenceExterior.blend').read_bytes()).hexdigest(),
 validation_boundary='Source/catalog/camera/saved Blender checks only. Does not certify pixel-perfect visual agreement or UE performance.')
(REV/'composition_validation.json').write_text(json.dumps(result,indent=2),encoding='utf8')
print('MPR_V4_COMPOSITION_VALID',json.dumps(result))
