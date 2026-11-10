"""Export the saved, baked Manny forklift source with stable material slots.
Run in background Blender; no dependency on temporary pose files.
"""
import bpy,json,hashlib
from pathlib import Path
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'SourceAssets/GHS_Normal/MannedForklift';TMP=ROOT/'Saved/MannyForklift'
source=OUT/'manned_forklift_50k.blend'
bpy.ops.wm.open_mainfile(filepath=str(source))
def signatures():
 result={}
 for o in bpy.data.objects:
  if o.type=='MESH' and not o.name.startswith('DRV_'):
   result[o.name]=hashlib.sha256(repr((list(map(tuple,o.matrix_world)),[tuple(v.co)for v in o.data.vertices],[tuple(p.vertices) for p in o.data.polygons],[p.material_index for p in o.data.polygons],[m.name if m else None for m in o.data.materials])).encode()).hexdigest()
 return result
before=signatures()
driver=bpy.data.objects['DRV_Manny_Seated'];assert driver.parent is None
assert len([o for o in bpy.data.objects if o.name.startswith('DRV_')])==1
# Bake meshes using original world coordinates and retain source UVs/split normals.
audit=json.loads((OUT/'manny_driver_import_baseline.json').read_text());report={'driver_source':'/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple','driver_materials':['MI_Manny_01_New','MI_Manny_02_New'],'removed_driver_parts':94,'protected_mesh_count':len(before),'protected_mesh_signatures':before,'outputs':[]}
def export(name,objects,target,key):
 slots=[s['name']for s in audit['meshes'][key]['slots']]+['MI_Manny_01_New','MI_Manny_02_New'];verts=[];faces=[];mats=[];uvs=[];normals=[]
 deps=bpy.context.evaluated_depsgraph_get()
 for o in objects:
  ev=o.evaluated_get(deps);me=ev.to_mesh();off=len(verts);w=o.matrix_world;normal_matrix=w.to_3x3().inverted().transposed()
  verts.extend(tuple(w@v.co)for v in me.vertices)
  for p in me.polygons:
   faces.append(tuple(off+i for i in p.vertices));mat=me.materials[p.material_index];assert mat.name in slots,mat.name;mats.append(slots.index(mat.name))
   for li in p.loop_indices:
    uvs.append(tuple(me.uv_layers.active.data[li].uv)if me.uv_layers.active else (0,0));normals.append(tuple((normal_matrix@me.corner_normals[li].vector).normalized()))
  ev.to_mesh_clear()
 me=bpy.data.meshes.new(name);me.from_pydata(verts,[],faces);me.update()
 for n in slots:me.materials.append(bpy.data.materials.get(n)or bpy.data.materials.new(n))
 for p,mi in zip(me.polygons,mats):p.material_index=mi;p.use_smooth=True
 uv=me.uv_layers.new(name='UVMap')
 for loop,v in zip(uv.data,uvs):loop.uv=v
 me.normals_split_custom_set(normals)
 ob=bpy.data.objects.new(name,me);bpy.context.scene.collection.objects.link(ob)
 bpy.ops.object.select_all(action='DESELECT');ob.select_set(True);bpy.context.view_layer.objects.active=ob
 expected=audit['meshes'][key]['boundsCm'];bounds=[min(v[i]for v in verts)*100 for i in range(3)]+[max(v[i]for v in verts)*100 for i in range(3)];assert all(abs(a-b)<.03 for a,b in zip(bounds,expected)),(bounds,expected)
 bpy.ops.export_scene.fbx(filepath=str(target),use_selection=True,object_types={'MESH'},axis_forward='-Y',axis_up='Z',apply_unit_scale=True,bake_space_transform=False,add_leaf_bones=False,use_mesh_modifiers=True,path_mode='STRIP',mesh_smooth_type='FACE')
 me.calc_loop_triangles();report['outputs'].append({'name':name,'triangles':len(me.loop_triangles),'slots':slots,'source_parts':len(objects),'bounds_m':[[min(v[i]for v in verts),max(v[i]for v in verts)]for i in range(3)],'fbx':str(target)})
 bpy.data.objects.remove(ob,do_unlink=True)
objects=[o for o in bpy.data.objects if o.type=='MESH' and (o.name.startswith('MF_')or o==driver)]
export('SM_GHN_MannedForklift50k',objects,OUT/'manned_forklift_50k.fbx','/Game/GHSNormalWarehouse/MannedForklift/Meshes/SM_GHN_MannedForklift50k')
excluded=('MF_Carriage','MF_LoadBackrest','MF_Fork','MF_V2_TaperedForgedFork','MF_V2_ForkCarriageHook','MF_InnerMastRail','MF_LiftRamChrome')
export('SM_Replay_ForkliftBody',[o for o in objects if not o.name.startswith(excluded)],ROOT/'SourceAssets/GHS/OrderReplay/SM_Replay_ForkliftBody.fbx','/Game/GHSOrderReplay/Meshes/SM_Replay_ForkliftBody')
assert signatures()==before
report['success']=True;(OUT/'manny_driver_validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print('MANNY_EXPORT',[(r['name'],r['triangles'])for r in report['outputs']])
