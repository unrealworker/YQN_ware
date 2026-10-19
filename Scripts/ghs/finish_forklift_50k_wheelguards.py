import bpy,bmesh
from pathlib import Path
names=['MF_V2_ArchedWheelGuard','MF_V2_ArchedWheelGuard.001']
with bpy.data.libraries.load(r'D:/UEPro/Test/Saved/Backups/GHS_Forklift_50k_20261019/before_optimization.blend',link=False) as (a,b):b.objects=list(names)
for n,source in zip(names,b.objects):
    o=bpy.data.objects[n];mats=list(o.data.materials)
    vs=[source.data.vertices[j*41+i*2].co.copy() for j in range(4) for i in range(21)]
    N=21;fs=[]
    for i in range(20):
        for a,c in [(0,N),(N,3*N),(3*N,2*N),(2*N,0)]:fs.append((a+i,a+i+1,c+i+1,c+i))
    fs.extend([(0,N,3*N,2*N),(N-1,2*N-1,4*N-1,3*N-1)])
    m=bpy.data.meshes.new(n+'_RegularArc');m.from_pydata(vs,[],fs);m.update()
    for mat in mats:m.materials.append(mat)
    bm=bmesh.new();bm.from_mesh(m);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(m);bm.free()
    for p in m.polygons:p.use_smooth=True
    o.modifiers.clear();o.data=m
    mod=o.modifiers.new('Preserved corner highlight','BEVEL');mod.width=.004;mod.segments=1
    mod=o.modifiers.new('Face normals','WEIGHTED_NORMAL');mod.keep_sharp=True
    bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get()
    baked=bpy.data.meshes.new_from_object(o.evaluated_get(dg),preserve_all_data_layers=True,depsgraph=dg)
    o.modifiers.clear();o.data=baked
    bpy.data.objects.remove(source,do_unlink=True)
asset=bpy.data.collections['MannedForklift_Editable'];total=0
for o in asset.all_objects:
    if o and o.type=='MESH':o.data.calc_loop_triangles();total+=len(o.data.loop_triangles)
print('REFINED_TOTAL',total)
assert total<=50000
bpy.context.scene.render.filepath=r'D:/UEPro/Test/SourceAssets/GHS_Normal/MannedForklift/manned_forklift_50k_preview.png'
bpy.ops.render.render(write_still=True)
