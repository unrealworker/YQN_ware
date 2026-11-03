"""V4 reviewed foliage from the bundled CC-BY Blender Studio oak.

Run isolated Blender with --disable-autoexec --threads 1. Never modifies V3.
Exports one detailed tree and roof-colour-correct vehicles. UE uses Nanite with
area preservation and its fallback; no separate geometry LOD is generated.
"""
from pathlib import Path
import hashlib,json,math,random,sys
import bpy,bmesh
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'SourceAssets/MPR/reference_v4/props'
SOURCE=OUT/'source/BlenderStudio_Oak_CC-BY.blend'
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'Tools/MPRWarehouse'))
sys.path.insert(0,str(ROOT/'Scripts/ghs'))
from mpr_reference_props_geometry import trailer,car,freight,PALETTE
PALETTE=dict(PALETTE,LeafMid=(.26,.33,.255),LeafLight=(.35,.40,.32),LeafShade=(.19,.26,.19))


def extract_oak():
 bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
 if bpy.context.window:bpy.context.window.view_layer=bpy.context.scene.view_layers['No_Moss']
 bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get()
 vv=[];ff=[];anchors=[]
 for instance in dg.object_instances:
  ob=instance.object;name=ob.name
  if ob.type!='MESH':continue
  matrix=instance.matrix_world.copy()
  if name.startswith('GEO-leaves-oak.'):
   anchors.append((matrix@Vector((0,0,.13)),(matrix.to_3x3()@Vector((0,0,1))).normalized(),(matrix.to_3x3()@Vector((1,0,0))).normalized()))
  elif name=='GEO-oak.1_trunk' or name.startswith(('GEO-tree_branch_small_','GEO-tree_branch_medium_')):
   off=len(vv);vv.extend(tuple(matrix@v.co) for v in ob.data.vertices);ff.extend(tuple(off+i for i in p.vertices) for p in ob.data.polygons)
 license_text=bpy.data.texts['License'].as_string()
 # Preserve the genuine asymmetric scaffold and measured source leaf sites.
 low=[min(v[i] for v in vv) for i in range(3)];high=[max(v[i] for v in vv) for i in range(3)]
 allxy=[(v[0],v[1]) for v in vv]+[(p.x,p.y) for p,_,_ in anchors]
 span=max(max(p[i] for p in allxy)-min(p[i] for p in allxy) for i in range(2));xy=12.85/span
 zbase=low[2];zmax=max(high[2],max(p.z for p,_,_ in anchors));zs=11.85/(zmax-zbase)
 def tx(p):return Vector((p[0]*xy,p[1]*xy,(p[2]-zbase)*zs))
 branches=[]
 for p in vv:
  q=tx(p);t=min(1.,max(0.,q.z/4.8));factor=.4+.6*t*t*(3-2*t)
  branches.append((q.x*factor,q.y*factor,q.z))
 transformed=[(tx(p),Vector((u.x*xy,u.y*xy,u.z*zs)).normalized(),Vector((v.x*xy,v.y*xy,v.z*zs)).normalized()) for p,u,v in anchors]
 return branches,ff,transformed,license_text,dict(source_leaf_sites=len(anchors),source_branch_vertices=len(vv),source_branch_polygons=len(ff),xy_scale=xy,z_scale=zs)


def mesh_object(name,vv,ff,roles,face_roles,mats,smooth=False):
 me=bpy.data.meshes.new(name);me.from_pydata(vv,[],ff);me.update();ob=bpy.data.objects.new(name,me);bpy.context.scene.collection.objects.link(ob)
 for role in roles:me.materials.append(mats[role])
 for p,role in zip(me.polygons,face_roles):p.material_index=roles.index(role);p.use_smooth=smooth
 return ob


def make_materials():
 colors={'MPR4_'+key:PALETTE[key]for key in ('LeafMid','LeafLight','LeafShade')}
 colors['MPR4_Bark']=(.17,.145,.105)
 colors.update({'MPR4_'+k:v for k,v in PALETTE.items() if not k.startswith(('Leaf','Bark'))})
 mats={};specs={}
 for role,color in colors.items():
  leaf=role.startswith('MPR4_Leaf');metal=role=='MPR4_VehicleMetal'
  spec=dict(base_color=[*color,1],roughness=.88 if leaf else .95 if role=='MPR4_Bark' else .68,metallic=.65 if metal else 0.,two_sided=leaf,blend_mode='OPAQUE',subsurface=.035 if leaf else 0.)
  mat=bpy.data.materials.new(role);mat.diffuse_color=tuple(spec['base_color']);mat.use_nodes=True;mat.use_backface_culling=not leaf
  bs=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED');bs.inputs['Base Color'].default_value=tuple(spec['base_color']);bs.inputs['Roughness'].default_value=spec['roughness'];bs.inputs['Metallic'].default_value=spec['metallic'];bs.inputs['Subsurface Weight'].default_value=spec['subsurface']
  mats[role]=mat;specs[role]=spec
 return mats,specs


def detailed_tree(vv,ff,anchors,mats):
 branch=mesh_object('OakScaffold',vv,ff,['MPR4_Bark'],['MPR4_Bark']*len(ff),mats,True)
 branch.data.calc_loop_triangles();source_tris=len(branch.data.loop_triangles)
 bpy.context.view_layer.objects.active=branch;branch.select_set(True)
 dec=branch.modifiers.new('Preserve visible scaffold','DECIMATE');dec.ratio=min(1.,70000/source_tris);bpy.ops.object.modifier_apply(modifier=dec.name);branch.select_set(False)
 vertices=[tuple(v.co) for v in branch.data.vertices];faces=[tuple(p.vertices) for p in branch.data.polygons];roles=['MPR4_Bark']*len(faces)
 branch_count=sum(len(f)-2 for f in faces);rng=random.Random(44221);leaf_count=0
 # Sixty small leaves per native site form several short shoots, with no solid canopy
 # fillers. Each real 8-15cm blade is a bent opaque four-triangle surface.
 for center,axis,across in anchors:
  normal=axis.cross(across).normalized()
  for i in range(60):
   angle=rng.uniform(-math.pi,math.pi)
   direction=(axis*math.cos(angle)+across*math.sin(angle)+normal*rng.uniform(-.7,.7)).normalized()
   leaf_normal=(Vector((0,0,1))*.7+normal*.25+Vector((rng.uniform(-.5,.5),rng.uniform(-.5,.5),rng.uniform(-.15,.15)))).normalized()
   lateral=leaf_normal.cross(direction).normalized()
   direction=lateral.cross(leaf_normal).normalized()
   # An ellipsoid is only the sampling envelope: every visible surface is a
   # separate, dimensioned leaf blade, never a closed canopy filler volume.
   jitter=Vector((rng.gauss(0,1),rng.gauss(0,1),rng.gauss(0,1))).normalized()*rng.random()**(1/3)
   p=center+across*jitter.x*.43+axis*jitter.y*.42+normal*jitter.z*.28
   length=rng.uniform(.08,.15);width=length*rng.uniform(.60,.86);off=len(vertices)
   vertices.extend([tuple(p-direction*length*.5),tuple(p-lateral*width*.5),tuple(p+direction*length*.5),tuple(p+lateral*width*.5),tuple(p+leaf_normal*length*.075)])
   faces.extend([(off,off+1,off+4),(off+1,off+2,off+4),(off+2,off+3,off+4),(off+3,off,off+4)])
   role=rng.choices(['MPR4_LeafMid','MPR4_LeafLight','MPR4_LeafShade'],[.50,.32,.18])[0];roles.extend([role]*4);leaf_count+=1
 bpy.data.objects.remove(branch,do_unlink=True)
 ordered=['MPR4_Bark','MPR4_LeafMid','MPR4_LeafLight','MPR4_LeafShade'];ob=mesh_object('SM_MPR4_Tree_Oak',vertices,faces,ordered,roles,mats)
 for p in ob.data.polygons:p.use_smooth=(p.material_index==0)
 return ob,dict(leaf_count=leaf_count,leaf_length_m=[.08,.15],branch_triangles=branch_count,source_branch_triangles=source_tris,
  leaf_geometry='Individual bent 4-triangle opaque blades; no ellipsoid/sphere canopy filler',native_scaffold=True)


def finish_mesh(ob):
 bm=bmesh.new();bm.from_mesh(ob.data);bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.0001);bmesh.ops.triangulate(bm,faces=list(bm.faces));bad=[f for f in bm.faces if f.calc_area()<1e-8 or any(e.calc_length()<.0001 for e in f.edges)]
 if bad:bmesh.ops.delete(bm,geom=bad,context='FACES_ONLY')
 loose=[v for v in bm.verts if not v.link_faces]
 if loose:bmesh.ops.delete(bm,geom=loose,context='VERTS')
 bm.to_mesh(ob.data);bm.free();ob.data.update();ob.data.calc_loop_triangles()
 if 'Tree_' in ob.name:
  minimum=min(v.co.z for v in ob.data.vertices)
  for v in ob.data.vertices:v.co.z-=minimum


def bounds(ob):return [[min(v.co[i] for v in ob.data.vertices),max(v.co[i] for v in ob.data.vertices)] for i in range(3)]


def export(ob,metadata):
 finish_mesh(ob)
 if 'Tree_' in ob.name:
  diameter=max(bounds(ob)[i][1]-bounds(ob)[i][0] for i in (0,1))
  metadata.update(crown_radius_m=diameter/2,radial_extent_m=max(math.hypot(v.co.x,v.co.y) for v in ob.data.vertices),height_m=max(v.co.z for v in ob.data.vertices),crown_diameter_xy_m=diameter)
 path=OUT/(ob.name+'.fbx');bpy.ops.object.select_all(action='DESELECT');ob.hide_set(False);ob.select_set(True);bpy.context.view_layer.objects.active=ob
 bpy.ops.export_scene.fbx(filepath=str(path),use_selection=True,object_types={'MESH'},axis_forward='-Y',axis_up='Z',apply_unit_scale=True,bake_anim=False,mesh_smooth_type='FACE',add_leaf_bones=False)
 ob.select_set(False)
 if 'Tree_' in ob.name:
  # Blender's FBX reader removes a few collapsed legacy scaffold triangles.
  # Make that readback the saved prototype source too, so manifest/blend/FBX
  # all describe the same delivered geometry instead of hiding the delta.
  original_triangles=len(ob.data.loop_triangles);original_materials=list(ob.data.materials);existing=set(bpy.data.objects)
  bpy.ops.import_scene.fbx(filepath=str(path));new=[o for o in bpy.data.objects if o not in existing and o.type=='MESH'];assert len(new)==1
  canonical=new[0];ob.data=canonical.data.copy();indices=[p.material_index for p in ob.data.polygons];ob.data.materials.clear()
  for material in original_materials:ob.data.materials.append(material)
  for polygon,index in zip(ob.data.polygons,indices):polygon.material_index=index
  ob.data.calc_loop_triangles();metadata['legacy_scaffold_collapsed_triangles_removed_by_fbx']=original_triangles-len(ob.data.loop_triangles)
  for item in list(bpy.data.objects):
   if item not in existing:bpy.data.objects.remove(item,do_unlink=True)
 return dict(name=ob.name,fbx=path.relative_to(ROOT).as_posix(),material_roles=[m.name for m in ob.data.materials],material_triangle_counts={m.name:sum(1 for p in ob.data.polygons if p.material_index==i) for i,m in enumerate(ob.data.materials)},bounds_m=bounds(ob),triangles=len(ob.data.loop_triangles),vertices=len(ob.data.vertices),
  sha256=hashlib.sha256(path.read_bytes()).hexdigest(),metadata=metadata,origin_m=[0,0,0],instance_only=True,collision=False)


def render(tree):
 scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=16;scene.cycles.use_denoising=True;scene.render.threads_mode='FIXED';scene.render.threads=1
 scene.render.resolution_x=1500;scene.render.resolution_y=1000;scene.render.resolution_percentage=100
 scene.world.use_nodes=True;bg=next(n for n in scene.world.node_tree.nodes if n.type=='BACKGROUND');bg.inputs['Color'].default_value=(.72,.80,.88,1);bg.inputs['Strength'].default_value=.75
 sun=bpy.data.lights.new('PrototypeSun','SUN');sun.energy=2.3;sun.angle=.14;ob=bpy.data.objects.new('PrototypeSun',sun);scene.collection.objects.link(ob);ob.rotation_euler=(.6,-.4,-.5)
 groundmat=bpy.data.materials.new('PrototypeGround');groundmat.diffuse_color=(.40,.46,.36,1);groundmat.use_nodes=True;bs=next(n for n in groundmat.node_tree.nodes if n.type=='BSDF_PRINCIPLED');bs.inputs['Base Color'].default_value=(.40,.46,.36,1);bs.inputs['Roughness'].default_value=.95
 bpy.ops.mesh.primitive_plane_add(size=1000,location=(0,0,-.03));bpy.context.object.data.materials.append(groundmat)
 cam=bpy.data.cameras.new('PrototypeCamera');co=bpy.data.objects.new('PrototypeCamera',cam);scene.collection.objects.link(co);scene.camera=co;cam.lens=55;cam.clip_end=2000
 def shot(name,pos,target):
  co.location=pos;co.rotation_euler=(Vector(target)-co.location).to_track_quat('-Z','Y').to_euler();scene.render.image_settings.file_format='PNG';scene.render.filepath=str(OUT/name);bpy.ops.render.render(write_still=True)
 shot('oak_prototype_near.png',(21,-26,17),(0,0,6))
 for i,(x,y,s) in enumerate([(-13,4,.90),(13,5,1.02),(-6,18,.96),(8,22,1.08)]):
  ob=bpy.data.objects.new('PrototypeGroup_'+str(i),tree.data);scene.collection.objects.link(ob);ob.location=(x,y,0);ob.scale=(s,s,s);ob.rotation_euler.z=i*1.77
 shot('oak_group_30m.png',(15,-26,13),(0,6,6))
 shot('oak_group_100m.png',(35,-93.675,31),(0,7,6))


def main():
 OUT.mkdir(parents=True,exist_ok=True)
 vv,ff,anchors,license_text,source_stats=extract_oak()
 bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene;scene.world=bpy.data.worlds.new('PrototypeWorld');scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1
 mats,specs=make_materials();tree,meta=detailed_tree(vv,ff,anchors,mats);rows=[export(tree,meta)];objects=[tree]
 for color in ('White','Blue','Coral'):
  data,metadata=trailer(color,0);target='Trailer'+color
  data.roles=[target if r=='TrailerWhite' and color!='White' else r for r in data.roles]
  roles=sorted({'MPR4_'+r for r in data.roles});ob=mesh_object('SM_MPR4_Trailer_'+color,data.vertices,data.faces,roles,['MPR4_'+r for r in data.roles],mats)
  for p,smooth in zip(ob.data.polygons,data.smooth):p.use_smooth=smooth
  metadata['roof_matches_body_color']=True;rows.append(export(ob,metadata));objects.append(ob)
 for name,builder in [('SM_MPR4_Car_0',lambda:car(0,0)),('SM_MPR4_Car_1',lambda:car(1,0)),('SM_MPR4_FreightBoxcar',lambda:freight(0))]:
  data,metadata=builder();roles=sorted({'MPR4_'+r for r in data.roles});ob=mesh_object(name,data.vertices,data.faces,roles,['MPR4_'+r for r in data.roles],mats)
  for p,smooth in zip(ob.data.polygons,data.smooth):p.use_smooth=smooth
  rows.append(export(ob,metadata));objects.append(ob)
 for ob in objects:ob.hide_render=ob!=tree;ob.hide_set(ob!=tree)
 bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'MPR_ReferenceV4_Props.blend'))
 provenance=dict(author='Simon Thommes',licensor='Blender Studio',license='CC-BY',source_url='https://cloud.blender.org/',source_file=str(SOURCE),source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),license_text=license_text,
  modifications='Native oak branch structure and leaf instance sites retained; twig mesh reduced, individual 8-15cm leaf shoots rebuilt, canopy scaled to approximately 13m diameter/12m high, muted MPR material palette.',source_stats=source_stats)
 (OUT/'SOURCE_ATTRIBUTION.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2),encoding='utf-8');(OUT/'LICENSE-BlenderStudio.txt').write_text(license_text,encoding='utf-8')
 manifest=dict(schema_version=1,review_status='geometry_reviewed_pending_scene_lighting',units='metres',coordinate_frame='Local ground origin; CAD +Y; vehicle +X front/-X rear; FBX -Y forward Z up',meshes=rows,instances={},materials=specs,source_attribution=provenance,tree_lods='UE Nanite area preservation and automatic fallback; explicit LOD meshes intentionally omitted')
 (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
 checks=[]
 for row in rows:
  existing=set(bpy.data.objects);bpy.ops.import_scene.fbx(filepath=str(ROOT/row['fbx']));new=[o for o in bpy.data.objects if o not in existing and o.type=='MESH'];assert len(new)==1
  ob=new[0];error=max(abs(bounds(ob)[i][j]-row['bounds_m'][i][j]) for i in range(3) for j in range(2));ob.data.calc_loop_triangles()
  assert error<.001 and len(ob.data.loop_triangles)==row['triangles'] and len(ob.data.materials)==len(row['material_roles']),(row['name'],error,len(ob.data.loop_triangles),row['triangles'],len(ob.data.materials),len(row['material_roles']))
  counts={row['material_roles'][i]:sum(1 for p in ob.data.polygons if p.material_index==i) for i in range(len(ob.data.materials))}
  assert counts==row['material_triangle_counts'],(row['name'],'material assignment mismatch',counts,row['material_triangle_counts'])
  checks.append(dict(name=row['name'],bounds_error_m=error,triangles=row['triangles']))
  for o in list(bpy.data.objects):
   if o not in existing:bpy.data.objects.remove(o,do_unlink=True)
 (OUT/'validation.json').write_text(json.dumps(dict(success=True,roundtrips=checks,tree_actual_radius_m=max(math.hypot(v.co.x,v.co.y) for v in tree.data.vertices),visual_review_complete=False),indent=2),encoding='utf-8')
 print('V4_PROTOTYPE_GEOMETRY_READY '+json.dumps(rows[0]),flush=True);render(tree)
 print('V4_PROTOTYPE_RENDERS_READY',flush=True)


def finalize_reviewed():
 """Apply the approved name/palette to already reviewed, immutable geometry."""
 manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
 source=OUT/'MPR_ReferenceV4_PropsPrototype.blend'
 if not source.exists():source=OUT/'MPR_ReferenceV4_Props.blend'
 bpy.ops.wm.open_mainfile(filepath=str(source));new_mats,specs=make_materials()
 oldname='SM_MPR4_Tree_OakPrototype';tree=bpy.data.objects.get(oldname) or bpy.data.objects['SM_MPR4_Tree_Oak']
 tree.name='SM_MPR4_Tree_Oak';tree.data.name=tree.name
 for role,spec in specs.items():
  for mat in bpy.data.materials:
   if mat.name==role or mat.name.startswith(role+'.'):
    mat.diffuse_color=tuple(spec['base_color'])
    next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED').inputs['Base Color'].default_value=tuple(spec['base_color'])
 for row in manifest['meshes']:
  if row['name']==oldname or row['name']==tree.name:
   row['metadata'].pop('prototype',None);updated=export(tree,row['metadata'])
   assert updated['triangles']==row['triangles'] and updated['material_triangle_counts']==row['material_triangle_counts'],'Finalization changed geometry/material allocation'
   row.clear();row.update(updated)
 bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'MPR_ReferenceV4_Props.blend'))
 manifest['review_status']='geometry_reviewed_pending_scene_lighting';manifest['materials']=specs
 manifest['tree_lods']='UE Nanite area preservation and automatic fallback; explicit LOD meshes intentionally omitted'
 manifest['source_attribution']['source_file']=str(SOURCE)
 (OUT/'SOURCE_ATTRIBUTION.json').write_text(json.dumps(manifest['source_attribution'],ensure_ascii=False,indent=2),encoding='utf-8')
 (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
 validation=json.loads((OUT/'validation.json').read_text(encoding='utf-8'))
 for row in validation['roundtrips']:
  if row['name']==oldname:row['name']=tree.name
 validation.update(geometry_review_complete=True,scene_lighting_review_complete=False,reviewed_views=['oak_prototype_near.png','oak_group_30m.png','oak_group_100m.png'])
 (OUT/'validation.json').write_text(json.dumps(validation,indent=2),encoding='utf-8')
 print('V4_REVIEWED_GEOMETRY_FROZEN',flush=True);render(tree);print('V4_REVIEWED_PALETTE_RENDERS_READY',flush=True)


def rebuild_vehicles_only():
 """Replace vehicle modules in the reviewed library without rebuilding foliage."""
 from mpr_transport_v6_geometry import tractor,connected_boxcar,locomotive
 manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf8'))
 tree_row=next(r for r in manifest['meshes'] if r['name']=='SM_MPR4_Tree_Oak')
 tree_hash=hashlib.sha256((ROOT/tree_row['fbx']).read_bytes()).hexdigest()
 bpy.ops.wm.open_mainfile(filepath=str(OUT/'MPR_ReferenceV4_Props.blend'))
 tree=bpy.data.objects['SM_MPR4_Tree_Oak'];tree_vertices=[tuple(v.co) for v in tree.data.vertices]
 mats={role:bpy.data.materials[role] for role in manifest['materials']}
 builders=[('SM_MPR4_Trailer_'+color,lambda color=color:trailer(color,1,coupled=True)) for color in ('White','Blue','Coral')]
 builders += [('SM_MPR4_Tractor',tractor),('SM_MPR4_FreightBoxcar',connected_boxcar),('SM_MPR4_Locomotive',locomotive)]
 changes=[]
 for name,builder in builders:
  old=bpy.data.objects.get(name)
  if old:bpy.data.objects.remove(old,do_unlink=True)
  data,meta=builder()
  if 'Trailer_' in name:
   target=name.rsplit('_',1)[-1];data.roles=['Trailer'+target if role=='TrailerWhite' else role for role in data.roles]
   meta['roof_matches_body_color']=True
  roles=sorted({'MPR4_'+r for r in data.roles})
  ob=mesh_object(name,data.vertices,data.faces,roles,['MPR4_'+r for r in data.roles],mats)
  for polygon,smooth in zip(ob.data.polygons,data.smooth):polygon.use_smooth=smooth
  row=export(ob,meta);ob.hide_render=True;ob.hide_set(True)
  manifest['meshes']=[r for r in manifest['meshes'] if r['name']!=name]+[row];changes.append(row)
 checks=[]
 for row in changes:
  before=set(bpy.data.objects);bpy.ops.import_scene.fbx(filepath=str(ROOT/row['fbx']))
  imported=[ob for ob in bpy.data.objects if ob not in before and ob.type=='MESH'];assert len(imported)==1
  check=imported[0];check.data.calc_loop_triangles();actual=bounds(check)
  err=max(abs(actual[i][j]-row['bounds_m'][i][j]) for i in range(3) for j in range(2))
  assert err<.001 and len(check.data.loop_triangles)==row['triangles'],name
  assert abs(actual[2][0])<.001,('Wheel-contact origin',row['name'],actual[2])
  assert row['triangles']<24000,('Vehicle triangle budget',row['name'],row['triangles'])
  checks.append(dict(name=row['name'],triangles=row['triangles'],bounds_error_m=err,minimum_z_m=actual[2][0],sha256=row['sha256']))
  for ob in list(bpy.data.objects):
   if ob not in before:bpy.data.objects.remove(ob,do_unlink=True)
 assert [tuple(v.co) for v in tree.data.vertices]==tree_vertices,'Reviewed tree vertices changed'
 assert hashlib.sha256((ROOT/tree_row['fbx']).read_bytes()).hexdigest()==tree_hash,'Reviewed tree FBX changed'
 bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'MPR_ReferenceV4_Props.blend'))
 manifest['transport_revision']='v6_grounded_tractor_and_continuous_consists'
 manifest['transport_validation']=dict(source_checks=checks,reviewed_tree_unchanged=True,tree_fbx_sha256=tree_hash,visual_review_complete=False)
 (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
 (OUT/'transport_validation.json').write_text(json.dumps(manifest['transport_validation'],ensure_ascii=False,indent=2),encoding='utf8')
 validation=json.loads((OUT/'validation.json').read_text(encoding='utf8'))
 prior={r['name']:r for r in validation['roundtrips']}
 for row in checks:prior[row['name']]=row
 validation.update(success=True,roundtrips=list(prior.values()),vehicle_geometry_unchanged=False,transport_revision=manifest['transport_revision'])
 (OUT/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2),encoding='utf8')
 print('MPR_TRANSPORT_V6_SOURCE_READY '+json.dumps(checks),flush=True)


if __name__=='__main__':
 if '--vehicles-only' in sys.argv:rebuild_vehicles_only()
 elif '--finalize-existing' in sys.argv:finalize_reviewed()
 else:main()
