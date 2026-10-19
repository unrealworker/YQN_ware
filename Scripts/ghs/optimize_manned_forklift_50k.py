"""Silhouette-conscious, per-part optimization. Run on the preserved worker v3 source."""
import bpy, bmesh, math, json
from mathutils import Vector
from pathlib import Path
OUT=Path(r'D:/UEPro/Test/SourceAssets/GHS_Normal/MannedForklift')
asset=bpy.data.collections['MannedForklift_Editable']
assert bpy.context.scene.name=='GHS_MannedForklift_Studio'
root=bpy.data.objects['MF_Root']
assert not root.get('optimization_50k_stage1'), 'Already optimized; reload original before repeating.'
bpy.context.view_layer.objects.active=None
for o in bpy.context.selected_objects:o.select_set(False)

def count(o):
    dg=bpy.context.evaluated_depsgraph_get(); e=o.evaluated_get(dg); m=e.to_mesh()
    m.calc_loop_triangles(); n=len(m.loop_triangles);e.to_mesh_clear();return n

def remake(o,vs,fs,smooth=True):
    materials=list(o.data.materials)
    m=bpy.data.meshes.new(o.name+'_Optimized');m.from_pydata(vs,[],fs);m.update()
    for mat in materials:m.materials.append(mat)
    bm=bmesh.new();bm.from_mesh(m);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(m);bm.free()
    for p in m.polygons:p.use_smooth=smooth
    o.modifiers.clear();o.data=m

removed=[]
for o in list(asset.all_objects):
    if o and o.name.startswith(('MF_LiftChainLink','MF_ChainPin')):
        removed.append(o.name);bpy.data.objects.remove(o,do_unlink=True)

# Two side-labelled axles in each wheel pair occupy exactly the same volume.
for front in ['Front','Rear']:
    a=bpy.data.objects.get('MF_V2_'+front+'_R_Axle');b=bpy.data.objects.get('MF_V2_'+front+'_L_Axle')
    if a and b:
        av=sorted(tuple(round(c,7) for c in a.matrix_world@v.co) for v in a.data.vertices)
        bv=sorted(tuple(round(c,7) for c in b.matrix_world@v.co) for v in b.data.vertices)
        if av==bv:removed.append(b.name);bpy.data.objects.remove(b,do_unlink=True)

for o in list(asset.all_objects):
    if not o or o.type!='MESH':continue
    n=o.name
    if 'RoundedSolidTyre' in n:
        old=[v.co.copy() for v in o.data.vertices];assert len(old)==15*96
        step=2 if 'Front' in n else 3;N=96//step;R=15
        vs=[old[j*96+i*step] for j in range(R) for i in range(N)]
        fs=[(j*N+i,j*N+(i+1)%N,((j+1)%R)*N+(i+1)%N,((j+1)%R)*N+i) for j in range(R) for i in range(N)]
        remake(o,vs,fs)
    elif 'SidewallBead' in n or 'RimSeat' in n:
        old=[v.co.copy() for v in o.data.vertices];assert len(old)==640
        vs=[];N=32;K=4
        for j in range(N):
            pts=old[j*20:j*20+10];c=sum(pts,Vector())/10
            u=pts[0]-c;v=(pts[2]-c-u*math.cos(math.tau*2/10))/math.sin(math.tau*2/10)
            for k in range(K):
                a=math.tau*k/K;vs.append(c+u*math.cos(a)+v*math.sin(a))
        fs=[(j*K+k,j*K+(k+1)%K,((j+1)%N)*K+(k+1)%K,((j+1)%N)*K+k) for j in range(N) for k in range(K)]
        remake(o,vs,fs)
    elif 'MouldedTreadGroove' in n:
        old=[v.co.copy() for v in o.data.vertices];assert len(old)==60
        centers=[sum(old[i*10:i*10+10],Vector())/10 for i in range(6)]
        x,r=(.53,.315) if 'Front' in n else (-.92,.215)
        vs=[]
        for i,p in enumerate(centers):
            radial=Vector((p.x-x,0,p.z-r)).normalized()
            tangent=(centers[min(i+1,5)]-centers[max(i-1,0)]).normalized()
            across=tangent.cross(radial).normalized();c=p+radial*.0017
            for s in [-1,1]:
                q=c+across*(s*.0022);q.z=max(0,q.z);vs.append(q)
        fs=[]
        for i in range(5):
            face=(2*i,2*i+1,2*i+3,2*i+2)
            normal=(vs[face[1]]-vs[face[0]]).cross(vs[face[2]]-vs[face[0]])
            p=centers[i];radial=Vector((p.x-x,0,p.z-r))
            if normal.dot(radial)<0:face=tuple(reversed(face))
            fs.append(face)
        remake(o,vs,fs,False)
    elif 'StepGrip' in n:
        for m in list(o.modifiers):
            if m.type in {'BEVEL','WEIGHTED_NORMAL'}:o.modifiers.remove(m)
    else:
        for m in o.modifiers:
            if m.type=='BEVEL':
                # Retain more curvature on the large body and soft seating surfaces.
                broad=any(t in n for t in ('Chassis','SeatBase','BatteryAccess','SeatCushion','SeatBack','Bolster','Armrest','ShapedRoofRail','ArchedWheelGuard','TaperedForgedFork'))
                m.segments=min(m.segments,2 if broad else 1)
    if o.type=='MESH':
        o['optimization']='Retained appearance; reduced tessellation and fine bevel subdivisions'

# Bake evaluated shape, so the later budget exactly includes all render modifiers.
for o in list(asset.all_objects):
    if not o or o.type not in {'MESH','FONT','CURVE'}:continue
    if o.type=='MESH' and not o.modifiers:continue
    bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get()
    if o.type!='MESH':
        bpy.context.view_layer.objects.active=o;o.select_set(True);bpy.ops.object.convert(target='MESH');o.select_set(False)
    else:
        m=bpy.data.meshes.new_from_object(o.evaluated_get(dg),preserve_all_data_layers=True,depsgraph=dg)
        o.modifiers.clear();o.data=m

root['optimization_50k_stage1']=True
root['optimization_removed_chain_objects']=len([n for n in removed if 'Chain' in n])
report=[];groups={}
for c in asset.children:
    for o in c.all_objects:
        if o and o.type=='MESH':
            nt=count(o);groups[c.name]=groups.get(c.name,0)+nt
            report.append({'name':o.name,'collection':c.name,'triangles':nt})
(OUT/'optimization_stage1.json').write_text(json.dumps({'groups':groups,'objects':report,'removed':removed},indent=2),encoding='utf-8')
print('STAGE1',sum(groups.values()),json.dumps(groups), 'removed',len(removed))
