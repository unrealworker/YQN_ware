"""Publish the reviewed tree and synchronize vehicle exchange materials.

Vehicle geometry and material allocation remain unchanged. Every delivered
FBX is re-read to check geometry, slots and embedded linear base colors.
"""
from pathlib import Path
import sys,json,hashlib
import bpy
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(Path(__file__).parent))
import build_mpr_reference_v4_props as base
OUT=ROOT/'SourceAssets/MPR/reference_v4/props'
manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf8'))
bpy.ops.wm.open_mainfile(filepath=str(OUT/'MPR_ReferenceV4_Props.blend'))
for role,spec in manifest['materials'].items():
 key=role.removeprefix('MPR4_')
 if key in base.PALETTE:
  spec['base_color']=[*base.PALETTE[key],1]
  mat=bpy.data.materials[role];mat.diffuse_color=tuple(spec['base_color'])
  next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED').inputs['Base Color'].default_value=tuple(spec['base_color'])
old=bpy.data.objects['SM_MPR4_Tree_Oak'];bpy.data.objects.remove(old,do_unlink=True)
with bpy.data.libraries.load(str(OUT/'canopy_review/OakCanopy_Review.blend'),link=False) as (src,dst):
 dst.objects=['SM_MPR4_Tree_Oak']
tree=dst.objects[0];bpy.context.scene.collection.objects.link(tree)
tree.name='SM_MPR4_Tree_Oak';tree.data.name=tree.name
indices=[p.material_index for p in tree.data.polygons]
roles=['MPR4_Bark','MPR4_LeafMid','MPR4_LeafLight','MPR4_LeafShade']
tree.data.materials.clear()
for role in roles:tree.data.materials.append(bpy.data.materials[role])
for p,i in zip(tree.data.polygons,indices):p.material_index=i
meta=json.loads((OUT/'canopy_review/metadata.json').read_text(encoding='utf8'))
meta.update(review_status='calibrated_aerial_geometry_reviewed',prototype=False)
row=base.export(tree,meta)
manifest['meshes']=[row if 'Tree' in r['name'] else r for r in manifest['meshes']]
vehicle_count=0
for index,original in enumerate(manifest['meshes']):
 if 'Tree' in original['name']:continue
 ob=bpy.data.objects[original['name']]
 hidden=(ob.hide_get(),ob.hide_render,ob.hide_viewport)
 updated=base.export(ob,dict(original.get('metadata',{})))
 ob.hide_set(hidden[0]);ob.hide_render=hidden[1];ob.hide_viewport=hidden[2]
 for field in ('triangles','vertices','material_roles','material_triangle_counts'):
  assert updated[field]==original[field],(original['name'],'Vehicle geometry changed',field)
 assert max(abs(updated['bounds_m'][i][j]-original['bounds_m'][i][j]) for i in range(3) for j in range(2))<1e-6
 manifest['meshes'][index]=updated;vehicle_count+=1
assert vehicle_count==6,'Expected exactly six current vehicle modules'
manifest['review_status']='calibrated_aerial_geometry_reviewed_pending_UE'
manifest['source_attribution']['modifications']='Native oak scaffold retained and reduced; 220000 individual fine leaves rebuilt into a continuous oval volumetric crown, approximately 12.3m wide and 15.9m high. No solid canopy filler. Muted sage palette.'
checks=[]
for meshrow in manifest['meshes']:
 before=set(bpy.data.objects);bpy.ops.import_scene.fbx(filepath=str(ROOT/meshrow['fbx']))
 imported=[o for o in bpy.data.objects if o not in before and o.type=='MESH'];assert len(imported)==1
 check=imported[0];check.data.calc_loop_triangles()
 error=max(abs(base.bounds(check)[i][j]-meshrow['bounds_m'][i][j]) for i in range(3) for j in range(2))
 assert error<.001 and len(check.data.loop_triangles)==meshrow['triangles'],meshrow['name']
 assert len(check.data.materials)==len(meshrow['material_roles']),meshrow['name']
 colors={};color_error=0.
 for i,role in enumerate(meshrow['material_roles']):
  material=check.data.materials[i]
  assert material.name==role or material.name.startswith(role+'.'),(meshrow['name'],i,role,material.name)
  shader=next(n for n in material.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
  actual=list(shader.inputs['Base Color'].default_value)[:3]
  expected=manifest['materials'][role]['base_color'][:3]
  delta=max(abs(a-b) for a,b in zip(actual,expected));color_error=max(color_error,delta)
  assert delta<1e-6,(meshrow['name'],role,'FBX embedded color mismatch',actual,expected)
  colors[role]=actual
 counts={meshrow['material_roles'][i]:sum(1 for p in check.data.polygons if p.material_index==i) for i in range(len(check.data.materials))}
 assert counts==meshrow['material_triangle_counts'],meshrow['name']
 checks.append(dict(name=meshrow['name'],bounds_error_m=error,triangles=meshrow['triangles'],
  material_allocation_unchanged=True,embedded_base_colors_linear=colors,max_base_color_error=color_error,
  fbx_sha256=hashlib.sha256((ROOT/meshrow['fbx']).read_bytes()).hexdigest()))
 for ob in list(bpy.data.objects):
  if ob not in before:bpy.data.objects.remove(ob,do_unlink=True)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'MPR_ReferenceV4_Props.blend'))
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
(OUT/'SOURCE_ATTRIBUTION.json').write_text(json.dumps(manifest['source_attribution'],ensure_ascii=False,indent=2),encoding='utf8')
validation=json.loads((OUT/'validation.json').read_text(encoding='utf8'))
validation['roundtrips']=checks
validation.update(success=True,vehicle_geometry_unchanged=True,vehicle_modules_materials_synchronized=vehicle_count,
 tree_actual_radius_m=row['metadata']['radial_extent_m'],calibrated_aerial_geometry_reviewed=True,
 reviewed_views=['canopy_review/oak_calibrated_aerial.png','canopy_review/oak_close.png'])
(OUT/'validation.json').write_text(json.dumps(validation,indent=2),encoding='utf8')
print('MPR_REFINED_CANOPY_PUBLISHED',row['triangles'],'vehicle modules',vehicle_count,
 'max embedded color error',max(c['max_base_color_error'] for c in checks),flush=True)
