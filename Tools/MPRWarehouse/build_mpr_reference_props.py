"""Build shared MPR reference-v3 props in an isolated single-thread Blender.

Blender --background --factory-startup --threads 1 --python <this file>
Writes only SourceAssets/MPR/reference_v3/props; no UE calls or source mutations.
"""
from pathlib import Path
import hashlib
import json
import math
import sys
import bpy
import bmesh
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'SourceAssets/MPR/reference_v3/props'
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'Tools/MPRWarehouse'))
sys.path.insert(0,str(ROOT/'Scripts/ghs'))
from mpr_reference_props_geometry import PALETTE,foliage,trailer,freight,car,TREE_SPECS


def material_specs():
 specs={}
 for role,color in PALETTE.items():
  specs[role]=dict(base_color=[*color,1.],roughness=.86 if role.startswith(('Leaf','Bark')) else .68,
                   metallic=.72 if role=='VehicleMetal' else .25 if role.startswith('Trailer') else 0.,blend_mode='OPAQUE',two_sided=False)
 specs['VehicleGlass'].update(roughness=.19,metallic=.40)
 specs['VehicleRubber'].update(roughness=.94)
 return specs


def make_materials(specs):
 out={}
 for role,s in specs.items():
  mat=bpy.data.materials.new('M_MPR_RefV3_'+role);mat.diffuse_color=tuple(s['base_color']);mat.use_nodes=True
  node=mat.node_tree.nodes.get('Principled BSDF');node.inputs['Base Color'].default_value=tuple(s['base_color']);node.inputs['Roughness'].default_value=s['roughness'];node.inputs['Metallic'].default_value=s['metallic'];out[role]=mat
 return out


def create_object(name,data,roles,mats,collection,lod):
 used=sorted({i for face in data.faces for i in face});remap={old:i for i,old in enumerate(used)}
 mesh=bpy.data.meshes.new(name);mesh.from_pydata([data.vertices[i] for i in used],[],[tuple(remap[i] for i in f) for f in data.faces]);mesh.update()
 for role in roles:mesh.materials.append(mats[role])
 for face,role,smooth in zip(mesh.polygons,data.roles,data.smooth):face.material_index=roles.index(role);face.use_smooth=smooth
 ob=bpy.data.objects.new(name,mesh);collection.objects.link(ob)
 # Recalculate disjoint primitive normals outward without changing silhouette.
 bm=bmesh.new();bm.from_mesh(ob.data)
 bmesh.ops.triangulate(bm,faces=list(bm.faces))
 degenerate=[f for f in bm.faces if f.calc_area()<1e-12]
 if degenerate:bmesh.ops.delete(bm,geom=degenerate,context='FACES_ONLY')
 unused=[v for v in bm.verts if not v.link_faces]
 if unused:bmesh.ops.delete(bm,geom=unused,context='VERTS')
 bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(ob.data);bm.free();ob.data.update()
 return ob


def bounds(ob):
 return [[min(v.co[i] for v in ob.data.vertices),max(v.co[i] for v in ob.data.vertices)] for i in range(3)]


def export(ob,path):
 bpy.ops.object.select_all(action='DESELECT');ob.hide_set(False);ob.hide_render=False;ob.select_set(True);bpy.context.view_layer.objects.active=ob
 bpy.ops.export_scene.fbx(filepath=str(path),use_selection=True,object_types={'MESH'},axis_forward='-Y',axis_up='Z',apply_unit_scale=True,bake_anim=False,mesh_smooth_type='FACE',add_leaf_bones=False)
 ob.select_set(False)


def build():
 OUT.mkdir(parents=True,exist_ok=True)
 bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
 scene=bpy.context.scene;scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1
 scene.render.threads_mode='FIXED';scene.render.threads=1
 specs=material_specs();mats=make_materials(specs)
 builders=[]
 for v,(name,*_) in enumerate(TREE_SPECS):builders.append(('SM_MPR3_Tree_'+str(v),lambda lod,v=v:foliage(v,lod)))
 for v,name in enumerate(('LowMound','MixedCluster')):builders.append(('SM_MPR3_Bush_'+str(v),lambda lod,v=v:foliage(v,lod,True)))
 for color in ('White','Blue','Coral'):builders.append(('SM_MPR3_Trailer_'+color,lambda lod,color=color:trailer(color,lod)))
 builders.extend([('SM_MPR3_Car_0',lambda lod:car(0,lod)),('SM_MPR3_Car_1',lambda lod:car(1,lod)),('SM_MPR3_FreightBoxcar',freight)])
 rows=[];detail=[];baseobjects={}
 for name,builder in builders:
  collection=bpy.data.collections.new(name);scene.collection.children.link(collection)
  generated=[builder(lod) for lod in range(3)]
  roles=sorted({r for data,_ in generated for r in data.roles});assetlods=[]
  for lod,(data,meta) in enumerate(generated):
   lodname=name+('_LOD'+str(lod) if lod else '');ob=create_object(lodname,data,roles,mats,collection,lod)
   ob['asset_role']=meta['kind'];ob['lod']=lod;ob['source_reference']='multiview/01,04,06';ob['units']='metres'
   ob.data.calc_loop_triangles();fbx=OUT/(lodname+'.fbx');export(ob,fbx)
   row=dict(name=lodname,fbx=fbx.relative_to(ROOT).as_posix(),lod=lod,material_roles=roles,bounds_m=bounds(ob),triangles=len(ob.data.loop_triangles),vertices=len(ob.data.vertices),sha256=hashlib.sha256(fbx.read_bytes()).hexdigest())
   assetlods.append(row);detail.append(row);ob.hide_render=True;ob.hide_set(True)
   if lod==0:baseobjects[name]=ob
  row=assetlods[0].copy();row.update(instance_only=True,collision=False,metadata=generated[0][1],origin_m=[0,0,0],mesh_long_x=not ('Tree_' in name or 'Shrub_' in name),
    lod_files=[r['fbx'] for r in assetlods[1:]],lod_triangles=[r['triangles'] for r in assetlods],lod_screen_sizes=[1.,.18,.045])
  rows.append(row)
  print('MPR_PROP '+name+' '+str(row['lod_triangles']),flush=True)
 manifest=dict(schema_version=1,units='metres',coordinate_frame='Local ground-centred origin, CAD +Y, vehicle front +X / rear doors -X, FBX forward -Y/up Z; UE reflects Y',
  meshes=rows,lod_details=detail,materials=specs,optimization=dict(shared_static_assets=len(rows),lod_count=3,opaque_foliage=True,alpha_cards=False,wind_tick=False,all_instances_expected=True,collision=False),
  references=['D:/CodexTemp/output/imagegen/industrial-saas/multiview/01-front-left-aerial.png','D:/CodexTemp/output/imagegen/industrial-saas/multiview/04-loading-dock-closeup.png','D:/CodexTemp/output/imagegen/industrial-saas/multiview/06-yard-corner-closeup.png'],
  assumptions=['Vehicles and trees reconstruct the supplied art reference, not surveyed fleet models or botanical species.','53ft dry-van box dimensions are visual nominal dimensions. No tractor cab is present.','Railway boxcar is approximately 20m including couplers.'])
 assert len(rows)==11
 assert all(r['lod_triangles'][0]>r['lod_triangles'][1]>r['lod_triangles'][2] for r in rows),[(r['name'],r['lod_triangles']) for r in rows]
 for row in rows:
  if '_Tree_' in row['name']:assert 8000<=row['triangles']<=18000 and 300<=row['lod_triangles'][2]<=800,row
 # Compact editable library: each collection holds all three source LODs.
 bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'MPR_Reference_Props.blend'))
 (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
 # Verify the actual interchange artifacts and the importer material contract.
 checks=[]
 for row in detail:
  bpy.ops.object.select_all(action='DESELECT');existing=set(bpy.data.objects)
  bpy.ops.import_scene.fbx(filepath=str(ROOT/row['fbx']))
  new=[ob for ob in bpy.data.objects if ob not in existing and ob.type=='MESH'];assert len(new)==1
  ob=new[0];actual=bounds(ob);error=max(abs(actual[i][j]-row['bounds_m'][i][j]) for i in range(3) for j in range(2))
  assert error<.001 and len(ob.data.materials)==len(row['material_roles']),(row['name'],error)
  assert all(math.isfinite(c) for v in ob.data.vertices for c in v.co)
  ob.data.calc_loop_triangles();assert len(ob.data.loop_triangles)==row['triangles'],(row['name'],len(ob.data.loop_triangles),row['triangles'])
  checks.append(dict(name=row['name'],bounds_error_m=error,triangles=row['triangles'],material_slots=len(ob.data.materials)))
  for newob in list(bpy.data.objects):
   if newob not in existing:bpy.data.objects.remove(newob,do_unlink=True)
 validation=dict(success=True,fbx_roundtrips=len(checks),max_bounds_error_m=max(c['bounds_error_m'] for c in checks),meshes=checks,
   source_assets_saved=True,unreal_import_tested=False,triangle_decrease_all_lods=True)
 (OUT/'validation.json').write_text(json.dumps(validation,indent=2),encoding='utf-8')
 render_reviews(baseobjects,mats)
 print('MPR_REFERENCE_PROPS_COMPLETE '+json.dumps(dict(assets=len(rows),fbx=len(detail),validation=True)),flush=True)


def render_reviews(objects,mats):
 scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=12;scene.cycles.use_denoising=True
 scene.render.threads_mode='FIXED';scene.render.threads=1
 scene.render.resolution_x=1600;scene.render.resolution_y=1100;scene.render.resolution_percentage=100
 scene.world.use_nodes=True;bg=scene.world.node_tree.nodes.get('Background');bg.inputs['Color'].default_value=(.76,.82,.88,1);bg.inputs['Strength'].default_value=.65
 sun=bpy.data.lights.new('ReviewSun','SUN');sun.energy=2.5;sun.angle=.12;ob=bpy.data.objects.new('ReviewSun',sun);scene.collection.objects.link(ob);ob.rotation_euler=(.55,-.4,-.5)
 bpy.ops.mesh.primitive_plane_add(size=240,location=(0,0,-.015));ground=bpy.context.object;ground.name='ReviewGround';ground.data.materials.append(mats['TrailerWhite'])
 camera=bpy.data.cameras.new('ReviewCamera');ob=bpy.data.objects.new('ReviewCamera',camera);scene.collection.objects.link(ob);scene.camera=ob;camera.type='ORTHO';camera.clip_end=1000
 shown=[]
 def use(name,position):
  base=objects[name];o=bpy.data.objects.new(name+'_Review',base.data);scene.collection.objects.link(o);o.location=position;shown.append(o);return o
 def shot(name,position,target,size):
  ob.location=position;ob.rotation_euler=(Vector(target)-ob.location).to_track_quat('-Z','Y').to_euler();camera.ortho_scale=size
  scene.render.image_settings.file_format='PNG';scene.render.filepath=str(OUT/name);bpy.ops.render.render(write_still=True)
 use('SM_MPR3_Tree_0',(-8,1,0));use('SM_MPR3_Tree_1',(0,3,0));use('SM_MPR3_Tree_2',(8,1,0))
 use('SM_MPR3_Bush_0',(-3,-4,0));use('SM_MPR3_Bush_1',(3,-4,0))
 shot('foliage_close.png',(21,-31,16),(0,0,4.6),27)
 if '--foliage-only' in sys.argv:return
 for item in shown:bpy.data.objects.remove(item,do_unlink=True)
 shown.clear()
 for i,color in enumerate(('White','Blue','Coral')):use('SM_MPR3_Trailer_'+color,(0,i*4,0))
 use('SM_MPR3_Car_0',(6,-5,0));use('SM_MPR3_Car_1',(-1,-5,0))
 shot('vehicles_close.png',(-25,-30,15),(0,2,1.6),29)
 for item in shown:bpy.data.objects.remove(item,do_unlink=True)
 shown.clear();use('SM_MPR3_FreightBoxcar',(0,0,0))
 shot('rail_boxcar_close.png',(-25,-30,15),(0,0,2),25)


if __name__=='__main__':build()
