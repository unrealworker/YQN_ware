"""Use closed exact unions and embedded sleeve roots for clean sewn shoulders."""
import bpy,bmesh,sys,importlib
from mathutils import Vector
sys.path.insert(0,r'D:/UEPro/Test/Scripts/ghs')
import build_forklift_driver,refine_forklift_driver_v2
scene=bpy.context.scene;co=bpy.data.collections['05_Driver'];root=bpy.data.objects['MF_Root']
temp=bpy.data.collections.new('Worker_GarmentConstruction');scene.collection.children.link(temp)
mats={key:bpy.data.materials['M_MF_'+key] for key in ['Cloth','Navy','Safety','Reflective','Skin','Rubber','Helmet','Dark','Metal']}
new=build_forklift_driver.build_driver(scene,temp,mats)
keep={'DRV_WorkJacket','DRV_LeftSleeve','DRV_RightSleeve','DRV_TrouserSeat','DRV_LeftTrouserLeg','DRV_RightTrouserLeg'}
for o in list(temp.objects):
    if o.name.split('.')[0] not in keep:bpy.data.objects.remove(o,do_unlink=True)
byname={o.name.split('.')[0]:o for o in temp.objects}
for side,sgn in [('Left',1),('Right',-1)]:
    o=byname['DRV_'+side+'Sleeve']
    # First cross section is entirely inside the torso, avoiding exposed circular end caps.
    c=sum((o.data.vertices[i].co for i in range(16)),Vector())/16
    target=Vector((-.485,sgn*.10,1.52))
    for i in range(16):o.data.vertices[i].co=target+(o.data.vertices[i].co-c)*.80
    for i in range(16,32):o.data.vertices[i].co.z-=.010
refine_forklift_driver_v2.refine_driver(scene,temp,mats)
for o in temp.objects:
    bm=bmesh.new();bm.from_mesh(o.data);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(o.data);bm.free()

def union_group(base,operands,target,role):
    o=byname[base]
    for key in operands:
        mod=o.modifiers.new('Sewn surface union','BOOLEAN');mod.operation='UNION';mod.solver='EXACT';mod.object=byname[key]
    bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get()
    me=bpy.data.meshes.new_from_object(o.evaluated_get(dg),preserve_all_data_layers=True,depsgraph=dg)
    assert len(me.vertices)>500
    # Keep only the final surface in the asset collection.
    old=bpy.data.objects[target];bpy.data.objects.remove(old,do_unlink=True)
    ob=bpy.data.objects.new(target,me);co.objects.link(ob);ob.parent=root
    me.materials.clear();me.materials.append(bpy.data.materials['M_MF_WorkerV3_'+role])
    for p in me.polygons:p.material_index=0;p.use_smooth=True
    sm=ob.modifiers.new('Soft cloth transitions','SMOOTH');sm.factor=.28;sm.iterations=3
    print('CLEAN_GARMENT',target,len(me.vertices),len(me.polygons))

union_group('DRV_WorkJacket',['DRV_LeftSleeve','DRV_RightSleeve'],'DRV_WorkJacket','Cloth')
union_group('DRV_TrouserSeat',['DRV_LeftTrouserLeg','DRV_RightTrouserLeg'],'DRV_Trousers','Navy')
for o in list(temp.objects):bpy.data.objects.remove(o,do_unlink=True)
bpy.data.collections.remove(temp)
bpy.context.view_layer.update()
print('GARMENT_JUNCTIONS_REBUILT')
