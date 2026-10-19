"""Blend garment junctions and polish the visible worker silhouette."""
import bpy,bmesh,math
from mathutils import Vector
co=bpy.data.collections['05_Driver'];root=bpy.data.objects['MF_Root']
assert not root.get('WorkerV3Polished',False)

for role,color in [('Cloth',(.014,.025,.045)),('Navy',(.013,.022,.041)),('Seam',(.012,.020,.035))]:
    m=bpy.data.materials['M_MF_WorkerV3_'+role]
    p=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    p.inputs['Base Color'].default_value=(*color,1);m.diffuse_color=(*color,1)

def blend_garment(names,name,material,voxel):
    objs=[bpy.data.objects[n] for n in names];verts=[];faces=[]
    for o in objs:
        offset=len(verts);verts.extend([o.matrix_world@v.co for v in o.data.vertices])
        faces.extend([tuple(offset+i for i in p.vertices) for p in o.data.polygons])
    me=bpy.data.meshes.new(name+'_ContinuousMesh');me.from_pydata(verts,[],faces);me.update()
    o=bpy.data.objects.new(name+'_Continuous',me);co.objects.link(o)
    me.materials.append(material)
    mod=o.modifiers.new('Blend sewn garment junctions','REMESH');mod.mode='VOXEL';mod.voxel_size=voxel;mod.adaptivity=.15;mod.use_smooth_shade=True
    sm=o.modifiers.new('Relax cloth surface','SMOOTH');sm.factor=.55;sm.iterations=3
    bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get()
    evaluated=bpy.data.meshes.new_from_object(o.evaluated_get(dg),preserve_all_data_layers=True,depsgraph=dg)
    assert 1000<len(evaluated.vertices)<200000,(name,len(evaluated.vertices))
    o.modifiers.clear();o.data=evaluated
    for p in o.data.polygons:p.use_smooth=True
    for old in objs:bpy.data.objects.remove(old,do_unlink=True)
    o.name=name;o.parent=root;o['GarmentConstruction']='Continuous surface across joints'
    print('GARMENT',name,len(o.data.vertices),len(o.data.polygons))

blend_garment(['DRV_WorkJacket','DRV_RightSleeve','DRV_LeftSleeve'],'DRV_WorkJacket',bpy.data.materials['M_MF_WorkerV3_Cloth'],.003)
blend_garment(['DRV_TrouserSeat','DRV_RightTrouserLeg','DRV_LeftTrouserLeg'],'DRV_Trousers',bpy.data.materials['M_MF_WorkerV3_Navy'],.0032)

# The existing wheel grip stays fixed; smoothing removes polygonal mitten edges.
for o in co.objects:
    if any(w in o.name for w in ['GlovePalm','GloveFinger','GloveThumb']):
        mod=o.modifiers.new('Natural hand contour','SUBSURF');mod.levels=1;mod.render_levels=1
        for p in o.data.polygons:p.use_smooth=True

# Short dark hair peeks out below the hardhat at the nape and temples.
head=bpy.data.objects['DRV_Head']
hair=bpy.data.materials.new('M_MF_WorkerV3_Hair');hair.use_nodes=True
hp=next(n for n in hair.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
hp.inputs['Base Color'].default_value=(.021,.016,.014,1);hp.inputs['Roughness'].default_value=.95
hair.diffuse_color=(.021,.016,.014,1)
head.data.update();vs=[];fs=[];mapping={}
for f in head.data.polygons:
    c=f.center
    keep=(c.z>1.902) or (c.x<-.437 and c.z>1.795) or (abs(c.y)>.069 and c.x<-.384 and c.z>1.844)
    if not keep:continue
    ids=[]
    for idx in f.vertices:
        if idx not in mapping:
            v=head.data.vertices[idx];mapping[idx]=len(vs);vs.append(v.co+v.normal*.0008)
        ids.append(mapping[idx])
    fs.append(tuple(ids))
me=bpy.data.meshes.new('WorkerShortHair');me.from_pydata(vs,[],fs);me.materials.append(hair)
o=bpy.data.objects.new('DRV_V3_ShortHair',me);co.objects.link(o);o.parent=root;o.matrix_world=head.matrix_world.copy()
for p in me.polygons:p.use_smooth=True

# A soft ear concha shadow gives the pinna a readable shape in the close-up.
mat=bpy.data.materials['DRV_FaceV3_SkinShade']
for side in [-1,1]:
    vs=[];fs=[];N=24
    vs.append((-.418,side*.092,1.802))
    for i in range(N):
        a=math.tau*i/N;vs.append((-.418+.007*math.cos(a),side*.091,1.802+.014*math.sin(a)))
    fs=[(0,i+1,(i+1)%N+1) for i in range(N)]
    me=bpy.data.meshes.new('EarConcha');me.from_pydata(vs,[],fs);me.materials.append(mat)
    o=bpy.data.objects.new('DRV_V3_EarConcha_'+str(side),me);co.objects.link(o);o.parent=root
    for p in me.polygons:p.use_smooth=True

root['WorkerV3Polished']=True
for o in co.objects:
    if o.type=='MESH':
        bm=bmesh.new();bm.from_mesh(o.data);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(o.data);bm.free()
bpy.context.view_layer.update()
print('WORKER_POLISHED',len(co.objects))
