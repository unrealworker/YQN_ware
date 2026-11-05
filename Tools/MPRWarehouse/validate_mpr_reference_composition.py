"""Reopen and verify the complete exterior blend against all frozen manifests."""
from pathlib import Path
import bpy,json,math,hashlib
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'SourceAssets/MPR/reference_v3';REV=OUT/'validation_blender'
report=json.loads((REV/'composition_manifest.json').read_text(encoding='utf8'))
manifests={}
for key,source in report['sources'].items():
 for field in ['manifest','blend']:
  assert hashlib.sha256((ROOT/source[field]).read_bytes()).hexdigest()==source[field+'_sha256'],(key,field,'source changed since composition')
 manifests[key]=json.loads((ROOT/source['manifest']).read_text(encoding='utf8'))
bpy.ops.wm.open_mainfile(filepath=str(OUT/'MPR_ReferenceExterior.blend'))
scene=bpy.context.scene;library=bpy.data.collections['MODULE_LIBRARY__HIDDEN']
assert library.hide_render and library.hide_viewport
masters={o.name:o for o in library.objects};instances=0;max_position_error=0
for group in ['architecture','site']:
 for name,placements in manifests[group].get('instances',{}).items():
  for i,p in enumerate(placements):
   ob=bpy.data.objects[f'{group}_{name}_{i:04}']
   assert ob.data==masters[name].data,(ob.name,'non-shared geometry')
   assert not ob.hide_render,(ob.name,'hidden instance')
   error=max(abs(ob.location[j]-p['position_m'][j]) for j in range(3));assert error<.0001
   max_position_error=max(max_position_error,error)
   assert max(abs(ob.scale[j]-p.get('scale',[1,1,1])[j]) for j in range(3))<.00001
   delta=(math.degrees(ob.rotation_euler.z)-p.get('rotation_deg',0)+180)%360-180
   assert abs(delta)<.0001,(ob.name,delta)
   instances+=1
assert instances==report['total_manifest_instances']
expected_static={r['name'] for m in manifests.values() for r in m['meshes'] if not r.get('instance_only',False)}
assert len(expected_static)==110
for name in expected_static:
 ob=bpy.data.objects[name];assert ob.type=='MESH' and not ob.hide_render
 assert all(abs(c)<1e-8 for c in ob.location)
assert not [o.name for o in scene.objects if '_Review' in o.name or o.name.startswith('Review') or '_LOD1' in o.name or '_LOD2' in o.name]
assert not [o.name for o in scene.objects if o.type=='MESH' and any(p in o.name for p in ['SM_MPR_Floor','StructureColumn','OfficePartitions'])]
assert len([o for o in scene.objects if o.type=='CAMERA'])==3
textures=[im for im in bpy.data.images if im.source=='FILE'];assert all(im.packed_file for im in textures)
result=dict(success=True,reopened_blend=True,sources_hash_unchanged=True,static_partitions=len(expected_static),
 linked_instances=instances,max_position_error_m=max_position_error,packed_texture_images=len(textures),
 hidden_module_count=len(masters),no_props_review_objects=True,no_interior_assets=True,only_lod0=True,
 output_sha256=hashlib.sha256((OUT/'MPR_ReferenceExterior.blend').read_bytes()).hexdigest(),
 validation_boundary='Saved Blender composition only; source render comparison and UE validation remain separate.')
(REV/'composition_validation.json').write_text(json.dumps(result,indent=2),encoding='utf8')
print('MPR_REFERENCE_COMPOSITION_VALID',json.dumps(result))
