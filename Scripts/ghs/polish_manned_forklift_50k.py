import bpy,bmesh,math,json
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from pathlib import Path
OUT=Path(r'D:/UEPro/Test/SourceAssets/GHS_Normal/MannedForklift')
asset=bpy.data.collections['MannedForklift_Editable'];root=bpy.data.objects['MF_Root']
assert root.get('optimization_50k_stage2') and not root.get('optimization_50k_polished')

def count(o):
    o.data.calc_loop_triangles();return len(o.data.loop_triangles)
def reduce(o,target):
    n=count(o)
    if n<=target:return
    m=o.modifiers.new('Small detail optimization','DECIMATE');m.ratio=target/n;m.use_collapse_triangulate=True
    bpy.context.view_layer.objects.active=o;o.select_set(True);bpy.ops.object.modifier_apply(modifier=m.name);o.select_set(False)

for o in list(asset.all_objects):
    if not o or o.type!='MESH':continue
    if 'ArchedWheelGuard' in o.name:reduce(o,400)
    elif o.name=='MF_SteeringWheel':reduce(o,320)
    elif 'BeaconLensRing' in o.name:reduce(o,128)
    elif 'ModelMark' in o.name:reduce(o,480)

# Rebuild reflective strips as orderly surface ribbons, not collapsed thin solids.
# This preserves their outline and prevents the yellow/silver layers intersecting.
names=[o.name for o in asset.children['05_Driver'].all_objects if o and 'Tape' in o.name]
original={}
with bpy.data.libraries.load(r'D:/UEPro/Test/Saved/Backups/GHS_Forklift_50k_20261019/before_optimization.blend',link=False) as (src,dst):
    dst.objects=list(names)
for name,loaded in zip(names,dst.objects):
    assert loaded and loaded.type=='MESH'
    original[name]=[v.co.copy() for v in loaded.data.vertices]
    bpy.data.objects.remove(loaded,do_unlink=True)
jacket=bpy.data.objects['DRV_WorkJacket']
bvh=BVHTree.FromPolygons([jacket.matrix_world@v.co for v in jacket.data.vertices],[tuple(p.vertices) for p in jacket.data.polygons])
for name in names:
    o=bpy.data.objects[name];old=original[name];core='Core' in name
    if 'Sleeve' in name:
        assert len(old)==224
        N=32;rowids=[0,3,6];vs=[]
        for j in rowids:
            for i in range(N):
                p=old[j*N+i];hit,normal,idx,dist=bvh.find_nearest(p)
                assert hit is not None and dist<.015,(name,dist)
                vs.append(hit+normal*(.0038 if core else .0018))
        fs=[(j*N+i,j*N+(i+1)%N,(j+1)*N+(i+1)%N,(j+1)*N+i) for j in range(2) for i in range(N)]
    else:
        assert len(old)==91
        N=13;rowids=[0,6];vs=[]
        for j in rowids:
            for i in range(N):
                p=old[j*N+i];hit,normal,idx,dist=bvh.ray_cast(Vector((.2,p.y,p.z)),Vector((-1,0,0)),2)
                assert hit is not None
                vs.append(Vector((hit.x+(.0042 if core else .002),p.y,p.z)))
        fs=[(i,i+1,N+i+1,N+i) for i in range(N-1)]
    mats=list(o.data.materials);m=bpy.data.meshes.new(name+'_LowPolyRibbon');m.from_pydata(vs,[],fs);m.update()
    for mat in mats:m.materials.append(mat)
    bm=bmesh.new();bm.from_mesh(m);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(m);bm.free()
    for p in m.polygons:p.use_smooth=True
    o.modifiers.clear();o.data=m

bpy.context.view_layer.update();root['optimization_50k_polished']=True
groups={}
for c in asset.children:
    groups[c.name]=sum(count(o) for o in c.all_objects if o and o.type=='MESH')
print('POLISHED',sum(groups.values()),json.dumps(groups))
bpy.context.scene.render.filepath=str(OUT/'manned_forklift_50k_preview.png')
bpy.ops.render.render(write_still=True)
