"""Reduce the original visible CAD geometry while retaining its holes and parts."""
from pathlib import Path
from collections import defaultdict
import sys,json
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Saved/StepTools'))
import numpy as np
import pymeshlab
TEMP=ROOT/'Saved/CartShell1026'
data=json.loads((TEMP/'visible_parts_20k.json').read_text(encoding='utf8'))
low,high=data['bounds_mm']
origin=np.array([(low[0]+high[0])/2,(low[1]+high[1])/2,low[2]])
results=[]
def protected_patches(part):
    i=part['index']
    if i not in (0,1,2,3,4,5):return set()
    v=np.array(part['vertices_mm'])-origin
    f=np.array(part['triangles']);ids=np.array(part['face_ids'])
    pts=v[f];center=pts.mean(axis=1)
    cross=np.cross(pts[:,1]-pts[:,0],pts[:,2]-pts[:,0])
    normals=cross/np.maximum(np.linalg.norm(cross,axis=1)[:,None],1e-15)
    radial=np.maximum(abs(center[:,:2])-np.array([90,150]),0)*np.sign(center[:,:2])
    dist=np.linalg.norm(radial,axis=1);radial/=np.maximum(dist[:,None],1e-15)
    exterior=(dist>99.2)&(dist<100.2)&((radial*normals[:,:2]).sum(axis=1)>.5)
    base=set(ids[exterior]) if i<2 else set(ids[np.abs(center[:,0])>157]) if i in (2,4) else set()
    if i==1:base.add(175)
    bypoint=defaultdict(set)
    for fid,face in zip(ids,f):
        for x in face:bypoint[tuple(np.round(v[x],4))].add(fid)
    adjacent=set(base)
    for fid,face in zip(ids,f):
        if fid in base:
            for x in face:adjacent.update(bypoint[tuple(np.round(v[x],4))])
    if i==1:adjacent.update(set(range(1141,1159))|{154}|set(range(498,505))|set(range(510,520)))
    if i in (2,3,4,5):
        area=np.linalg.norm(cross,axis=1)/2
        for fid in set(ids):
            selected=np.flatnonzero(ids==fid);valid=selected[area[selected]>1e-8]
            planar=len(valid) and np.min(normals[valid]@normals[valid[0]])>.99999
            if planar and ((i in (2,4) and area[selected].sum()>2000) or
                           (i in (3,5) and area[selected].sum()>25 and normals[valid[0],2]>-.1)):
                adjacent.add(fid)
    if i!=0:adjacent.update(part.get('inspection_visible_patches',[]))
    return adjacent

for part in data['parts']:
    i=part['index']
    if not part['triangles']:
        results.append(dict(index=i,vertices_mm=[],triangles=[],target=0));continue
    target=6000 if i==0 else 6500 if i==1 else 2200 if i in (2,4) else 600 if i in (3,5) else 400 if i in (6,17,28,39) else 30
    points=(np.array(part['vertices_mm'])-origin)/1000
    weights=np.ones(len(points))
    if i in (0,1):
        dist=np.hypot(np.maximum(np.abs(points[:,0])-.09,0),np.maximum(np.abs(points[:,1])-.15,0))
        weights=np.where(dist>.095,12.,.5)
        if i==1:weights=np.where(points[:,2]>.19,5.,weights)
    ms=pymeshlab.MeshSet()
    protected=protected_patches(part)
    triangles=np.array(part['triangles'],dtype=np.int32)
    ids=np.array(part['face_ids'])
    source_indices=np.array(part['source_triangle_indices'])
    if i==1:
        q=points[triangles];cr=np.cross(q[:,1]-q[:,0],q[:,2]-q[:,0])
        normals=cr/np.maximum(np.linalg.norm(cr,axis=1)[:,None],1e-15)
        # The underside of the enclosed lid is hidden. Remove it as a complete
        # inward-facing patch, instead of collapsing it across the visible holes.
        inward=(normals[:,2]<-.99)&(q.mean(axis=1)[:,2]>.185)&(~np.isin(ids,list(protected)))
        removed=set(ids[inward])
        keep=~np.isin(ids,list(removed))
        triangles=triangles[keep];ids=ids[keep];source_indices=source_indices[keep]
    visible_triangles=set(part.get('inspection_visible_triangles',[])) if i==0 else set()
    mask=np.array([float(fid in protected or src in visible_triangles) for fid,src in zip(ids,source_indices)])
    ms.add_mesh(pymeshlab.Mesh(vertex_matrix=points,face_matrix=triangles,
                              v_scalar_array=weights,f_scalar_array=mask))
    ms.meshing_remove_duplicate_vertices()
    ms.meshing_remove_duplicate_faces()
    ms.meshing_remove_null_faces()
    ms.meshing_remove_unreferenced_vertices()
    before=ms.current_mesh().face_number()
    protected_count=int(np.sum(ms.current_mesh().face_scalar_array()>.5))
    if before>target:
        current=ms.current_mesh()
        frozen=current.face_scalar_array()>.5
        locked_vertices=current.vertex_matrix().copy()
        locked_faces=current.face_matrix()[frozen].copy()
        # Reduce the hidden remainder separately: otherwise shared border
        # vertices force thousands of invisible slivers to survive the budget.
        free=pymeshlab.MeshSet()
        free.add_mesh(pymeshlab.Mesh(vertex_matrix=locked_vertices,
                                    face_matrix=current.face_matrix()[~frozen],
                                    v_scalar_array=current.vertex_scalar_array()))
        free.meshing_remove_unreferenced_vertices()
        free.meshing_decimation_quadric_edge_collapse(targetfacenum=max(4,target-protected_count),qualitythr=.3,
            preserveboundary=False,boundaryweight=10,preservenormal=True,preservetopology=False,
            optimalplacement=False,planarquadric=True,planarweight=.01,qualityweight=True,autoclean=True)
        reduced=free.current_mesh()
        merged=pymeshlab.Mesh(vertex_matrix=np.vstack((locked_vertices,reduced.vertex_matrix())),
                             face_matrix=np.vstack((locked_faces,reduced.face_matrix()+len(locked_vertices))))
        ms=pymeshlab.MeshSet();ms.add_mesh(merged)
        ms.meshing_remove_duplicate_vertices()
        ms.meshing_remove_unreferenced_vertices()
    mesh=ms.current_mesh()
    results.append(dict(index=i,vertices_mm=(mesh.vertex_matrix()*1000+origin).tolist(),
                        triangles=mesh.face_matrix().tolist(),target=target,protected_cad_patches=sorted(int(n) for n in protected),
                        protected_source_triangles=sorted(visible_triangles),protected_triangles=protected_count))
    print('REDUCED',i,before,'to',mesh.face_number(),'target',target,'protected',protected_count,flush=True)
(TEMP/'optimized_parts_20k.json').write_text(json.dumps(results),encoding='utf8')
print('TOTAL',sum(len(p['triangles']) for p in results),flush=True)
