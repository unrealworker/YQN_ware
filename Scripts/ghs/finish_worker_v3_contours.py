"""Final shoulder slope, subtle hairline and garment surface clean-up."""
import bpy,math,bmesh
from mathutils import Vector
co=bpy.data.collections['05_Driver'];root=bpy.data.objects['MF_Root']
assert not root.get('WorkerV3FinalContours',False)
j=bpy.data.objects['DRV_WorkJacket']
for v in j.data.vertices:
    p=v.co;u=max(0,min(1,(abs(p.y)-.115)/.095));u=u*u*(3-2*u)
    envelope=math.exp(-((p.z-1.605)/.068)**2)*u
    p.z-=.053*envelope
    p.y-=math.copysign(.010*envelope,p.y)
j.data.update()
for name in ['DRV_WorkJacket','DRV_Trousers']:
    o=bpy.data.objects[name]
    mod=o.modifiers.new('Soften fabric silhouette','SMOOTH');mod.factor=.65;mod.iterations=14
    bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get()
    me=bpy.data.meshes.new_from_object(o.evaluated_get(dg),preserve_all_data_layers=True,depsgraph=dg)
    o.modifiers.clear();o.data=me
    for p in me.polygons:p.use_smooth=True

old=bpy.data.objects.get('DRV_V3_ShortHair')
if old:bpy.data.objects.remove(old,do_unlink=True)
head=bpy.data.objects['DRV_Head'];N=96;rows=84
assert len(head.data.vertices)==N*rows+2
angles=[-math.pi/2+math.pi*i/72 for i in range(72)]+[math.pi/2+math.pi*i/24 for i in range(24)]
vs=[];layers=18
for j in range(layers+1):
    t=j/layers
    for i,a in enumerate(angles):
        # A continuous rounded hairline, high beneath the front visor, low at the nape.
        low=1.799+.116*(.5+.5*math.cos(a))**1.12
        z=low+(1.932-low)*t
        rr=(z-1.681)/(.255)*(rows-1);k=min(rows-2,int(rr));f=rr-k
        p=head.data.vertices[k*N+i].co.lerp(head.data.vertices[(k+1)*N+i].co,f)
        normal=head.data.vertices[k*N+i].normal.lerp(head.data.vertices[(k+1)*N+i].normal,f).normalized()
        vs.append(p+normal*.0008)
fs=[(j*N+i,j*N+(i+1)%N,(j+1)*N+(i+1)%N,(j+1)*N+i) for j in range(layers) for i in range(N)]
me=bpy.data.meshes.new('WorkerHair_SmoothHairline');me.from_pydata(vs,[],fs);me.materials.append(bpy.data.materials['M_MF_WorkerV3_Hair'])
o=bpy.data.objects.new('DRV_V3_ShortHair',me);co.objects.link(o);o.parent=root;o.matrix_world=head.matrix_world.copy()
for p in me.polygons:p.use_smooth=True

hat=bpy.data.materials['M_MF_WorkerV3_Helmet'];p=next(n for n in hat.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
p.inputs['Base Color'].default_value=(.42,.012,.018,1);p.inputs['Roughness'].default_value=.52
p.inputs['Specular IOR Level'].default_value=.3;hat.diffuse_color=(.42,.012,.018,1)
root['WorkerV3FinalContours']=True
bpy.context.view_layer.update()
print('FINAL_WORKER_CONTOURS_READY')
