"""Build clean display shells from the CAD exterior patches and top plate.

The sub-millimetre manufacturing fillets/hidden ribs are replaced by clean rim
strips. The original top surface (all 53 openings), side silhouette and wheel
cutouts remain in CAD coordinates.
"""
from pathlib import Path
from collections import Counter
import json,math,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Saved/StepTools'))
import numpy as np
import pymeshlab
TEMP=ROOT/'Saved/CartShell1026'
data=json.loads((TEMP/'assembly_mesh.json').read_text(encoding='utf8'))
low,high=data['bounds_mm']
origin=np.array([(low[0]+high[0])/2,(low[1]+high[1])/2,low[2]])

def side_distance(p):
    return math.hypot(max(abs(p[0])-90,0),max(abs(p[1])-150,0))-100

def outward(p):
    n=np.array([math.copysign(max(abs(p[0])-90,0),p[0]),math.copysign(max(abs(p[1])-150,0),p[1]),0.])
    return n/max(np.linalg.norm(n),1e-10)

def patch(verts,faces,kind):
    points=[];tris=[];index={}
    for face in faces:
        f=[]
        for old in face:
            p=verts[old];key=tuple(round(x,4) for x in p)
            if key not in index:
                index[key]=len(points);points.append(p.tolist())
            f.append(index[key])
        if len(set(f))==3:tris.append(f)
    counts=Counter(tuple(sorted((f[k],f[(k+1)%3]))) for f in tris for k in range(3))
    boundary=[(f[k],f[(k+1)%3]) for f in tris for k in range(3) if counts[tuple(sorted((f[k],f[(k+1)%3])))]==1]
    opening_vertices=set()
    if kind=='top':
        adjacent={}
        for a,b in boundary:
            adjacent.setdefault(a,set()).add(b);adjacent.setdefault(b,set()).add(a)
        remaining=set(adjacent)
        while remaining:
            stack=[next(iter(remaining))];component=set()
            while stack:
                v=stack.pop()
                if v in component:continue
                component.add(v);stack.extend(adjacent[v]-component)
            remaining-=component
            coords=np.array([points[v] for v in component]);size=np.ptp(coords,axis=0)
            if 70<size[0]<200 and 70<size[1]<200:
                opening_vertices.update(component)
    extruded={}
    for a,b in boundary:
        if a in opening_vertices and b in opening_vertices:
            continue
        for v in (a,b):
            if v in extruded:continue
            p=np.array(points[v]);q=p.copy()
            if kind=='top':
                q[2]-=2.768
                if side_distance(p)>-3.1:
                    q+=outward(p)*2.768
            else:
                q-=outward(p)*2.5
            extruded[v]=len(points);points.append(q.tolist())
        aa,bb=extruded[a],extruded[b]
        tris.extend([[b,a,aa],[b,aa,bb]])
    return points,tris

outputs=[]
for part in data['parts'][:2]:
    i=part['index'];vertices=np.array(part['vertices_mm'])-origin
    outer=[];top=[];collar=[]
    collar_ids=set(range(1141,1159))|{154}|set(range(498,505))|set(range(510,520))
    for fi,face in enumerate(part['triangles']):
        a,b,c=vertices[face];center=(a+b+c)/3
        normal=np.cross(b-a,c-a);normal/=max(np.linalg.norm(normal),1e-12)
        if i==1 and part['face_ids'][fi]==175:
            top.append(face)
        elif i==1 and part['face_ids'][fi] in collar_ids:
            collar.append(face)
        elif center[2] < (192.74 if i==1 else 107) and -1.5 < side_distance(center)<.1 and np.dot(normal,outward(center))>.15:
            outer.append(face)
    points,faces=patch(vertices,outer,'side')
    if top:
        pv,pf=patch(vertices,top,'top');offset=len(points)
        points.extend(pv);faces.extend([[n+offset for n in f] for f in pf])
    if collar:
        offset=len(points);points.extend(vertices.tolist())
        faces.extend([[n+offset for n in f] for f in collar])
    print('EXTERIOR',i,len(faces),flush=True)
    ms=pymeshlab.MeshSet()
    ms.add_mesh(pymeshlab.Mesh(vertex_matrix=np.array(points)/1000,face_matrix=np.array(faces,dtype=np.int32)))
    ms.meshing_remove_duplicate_vertices()
    ms.meshing_remove_duplicate_faces()
    ms.meshing_remove_null_faces()
    ms.meshing_remove_unreferenced_vertices()
    target=2200 if i==0 else 4500
    if ms.current_mesh().face_number()>target:
        ms.meshing_decimation_quadric_edge_collapse(targetfacenum=target,qualitythr=.4,
            preserveboundary=True,boundaryweight=100,preservenormal=True,preservetopology=True,
            optimalplacement=False,planarquadric=True,planarweight=.05,autoclean=True)
    m=ms.current_mesh()
    outputs.append(dict(index=i,vertices_mm=(m.vertex_matrix()*1000+origin).tolist(),triangles=m.face_matrix().tolist()))
    print('RETOPOLOGIZED',i,m.face_number(),flush=True)
(TEMP/'optimized_shells.json').write_text(json.dumps(outputs),encoding='utf8')
