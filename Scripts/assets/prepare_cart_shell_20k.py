"""Keep complete CAD patches visible from outside, including through openings.

Run in Blender background. Nothing is sampled from or changed in the live scene.
The result keeps original assembly coordinates, CAD patch IDs and material colors.
"""
import json,math
from pathlib import Path
from collections import defaultdict
from mathutils import Vector
from mathutils.bvhtree import BVHTree
ROOT=Path(__file__).resolve().parents[2]
TEMP=ROOT/'Saved/CartShell1026'
data=json.loads((TEMP/'assembly_mesh.json').read_text(encoding='utf8'))
vertices=[];triangles=[];surface_owners=[]
for part in data['parts']:
    offset=len(vertices)
    vertices.extend([tuple(v/1000 for v in p) for p in part['vertices_mm']])
    triangles.extend([tuple(v+offset for v in f) for f in part['triangles']])
    surface_owners.extend((part['index'],fid,j) for j,fid in enumerate(part['face_ids']))
bvh=BVHTree.FromPolygons(vertices,triangles,all_triangles=True)
lo,hi=data['bounds_mm']
origin=Vector(((lo[0]+hi[0])/2000,(lo[1]+hi[1])/2000,lo[2]/1000))
inspection_cameras=[origin+Vector(p) for p in ((.68,-.85,.68),(-.65,.85,.6),(.8,.1,.45),(-.8,.1,.45))]
# Probe from the exterior as well as from face centres. A large internal face
# may only be visible at one corner through a small opening.
camera_visible=defaultdict(set)
camera_triangles=defaultdict(set)
target=origin+Vector((0,0,.09))
for camera in inspection_cameras:
    direction=(target-camera).normalized()
    right=direction.cross(Vector((0,0,1))).normalized()
    up=right.cross(direction).normalized()
    for row in range(420):
        for col in range(420):
            start=camera+right*((col/419-.5)*.72)+up*((row/419-.5)*.72)
            hit=bvh.ray_cast(start,direction,3)
            if hit[2] is not None:
                index,fid,triangle_index=surface_owners[hit[2]]
                camera_visible[index].add(fid)
                camera_triangles[index].add(triangle_index)
directions=[Vector((x,y,z)).normalized() for x,y,z in [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)]]
for i in range(64):
    z=1-2*(i+.5)/64;theta=i*math.pi*(3-math.sqrt(5));r=math.sqrt(1-z*z)
    directions.append(Vector((r*math.cos(theta),r*math.sin(theta),z)))
results=[]
for part in data['parts']:
    vv=[Vector(tuple(v/1000 for v in p)) for p in part['vertices_mm']]
    groups=defaultdict(list)
    for i,faceid in enumerate(part['face_ids']):groups[faceid].append(i)
    kept=set();inspection_visible=set(camera_visible[part['index']])
    for faceid,indices in groups.items():
        visible=False
        if part['index'] in (2,3,4,5):
            for idx in indices:
                a,b,c=(vv[v] for v in part['triangles'][idx]);normal=(b-a).cross(c-a).normalized();center=(a+b+c)/3
                for camera in inspection_cameras:
                    vector=camera-center;direction=vector.normalized()
                    if direction.dot(normal)>.001 and bvh.ray_cast(center+direction*.000005,direction,vector.length)[0] is None:
                        inspection_visible.add(faceid);break
                if faceid in inspection_visible:break
        for idx in indices:
            a,b,c=(vv[v] for v in part['triangles'][idx]);normal=(b-a).cross(c-a).normalized();center=(a+b+c)/3
            for direction in [normal]+[d for d in directions if d.dot(normal)>.05]:
                if bvh.ray_cast(center+direction*.000005,direction,2)[0] is None:
                    visible=True;break
            if visible:break
        if visible:kept.add(faceid)
    kept.update(inspection_visible)
    indices=[i for i,fid in enumerate(part['face_ids']) if fid in kept]
    p={**part,'triangles':[part['triangles'][i] for i in indices],
       'colors':[part['colors'][i] for i in indices], 'face_ids':[part['face_ids'][i] for i in indices],
       'input_triangles':len(part['triangles']), 'visible_cad_patches':sorted(kept),
       'source_triangle_indices':indices,
       'inspection_visible_triangles':sorted(camera_triangles[part['index']]),
       'inspection_visible_patches':sorted(inspection_visible)}
    results.append(p)
    print('VISIBLE',part['index'],len(indices),'of',len(part['triangles']),len(kept),'CAD patches',flush=True)
(TEMP/'visible_parts_20k.json').write_text(json.dumps({**data,'parts':results},ensure_ascii=False),encoding='utf8')
print('TOTAL',sum(len(p['triangles']) for p in results),flush=True)
