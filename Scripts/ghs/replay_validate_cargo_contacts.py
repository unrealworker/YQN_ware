"""Read-only Blender audit of all ten replay cargo meshes, including source stacks.

Run blender --background --factory-startup --python-exit-code 1 --python this_file.
Uses actual FBX faces at owner transitions, every vehicle key and intermediate poses.
"""
import bisect
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Scripts/ghs'))
from replay_audit_sources import verify_sources

ASSETS = ROOT/'SourceAssets/GHS/OrderReplay'
timeline = ROOT/'Content/GHSTwinUI/data/order-replay.json'
timeline_bytes = timeline.read_bytes()
data = json.loads(timeline_bytes)
_, provenance = verify_sources(ROOT,data)
tracks = data['tracks']
times = [[k[0] for k in t['keys']] for t in tracks]
models = {m['name']:m for m in json.loads((ASSETS/'replay_assets.json').read_bytes())['meshes']}


def state(i,t):
    keys = tracks[i]['keys']
    j = max(0,bisect.bisect_right(times[i],t)-1)
    a,b = keys[j],keys[min(j+1,len(keys)-1)]
    f = (t-a[0])/(b[0]-a[0]) if b[0]>a[0] and a[6]==b[6] else 0.
    return ([((1-f)*x+f*y)/100 for x,y in zip(a[1],b[1])],
            a[2]+f*math.remainder(b[2]-a[2],360), ((1-f)*a[3]+f*b[3])/100,a[5],a[6])


def rotate(x,y,yaw):
    theta = math.radians(yaw)
    c,s = math.cos(theta),math.sin(theta)
    return (c*x-s*y,s*x+c*y)


def sample_scene(t):
    poses=[state(i,t) for i in range(len(tracks))]
    for i in range(8,18):
        p,yaw,lift,on,owner=poses[i]
        if owner>=0:
            carrier,cyaw,clift,visible,_=poses[owner]
            x,y=rotate(p[0],p[1],cyaw)
            poses[i]=([carrier[0]+x,carrier[1]+y,carrier[2]+p[2]+(clift if owner<5 else 0)],
                      yaw+cyaw,lift,on and visible,owner)
    return poses


def contact_samples():
    samples={t for row in times for t in row}
    for t in tracks[:8]:
        for a,b in zip(t['keys'],t['keys'][1:]):
            distance=math.dist(a[1],b[1])
            rotation=abs(math.remainder(b[2]-a[2],360))
            lift=abs(b[3]-a[3])
            precision=2 if a[7] not in ('运送托盘','返回地堆','前往补给月台','补给运回地堆','驶离园区','测试补给车 · 返回园区','倒车入泊') else 15
            if not a[5] or not b[5]:
                continue
            n=max(1,math.ceil(distance/precision),math.ceil(rotation/2),math.ceil(lift/2))
            samples.update(a[0]+step*(b[0]-a[0])/n for step in range(1,n))
    return sorted(samples)


def read_mesh(name):
    file=ASSETS/(name+'.fbx')
    assert hashlib.sha256(file.read_bytes()).hexdigest()==models[name]['sha256']
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(file))
    vertices,faces=[],[]
    for obj in bpy.data.objects:
        if obj.type!='MESH':
            continue
        obj.data.calc_loop_triangles()
        start=len(vertices)
        for v in obj.data.vertices:
            p=obj.matrix_world @ v.co
            vertices.append(Vector((p.x,-p.y,p.z)))
        faces.extend([tuple(i+start for i in t.vertices) for t in obj.data.loop_triangles])
    return vertices,faces


def prepare(a,b,t,queries):
    # Pose tuple: mesh, scale, world position, yaw, owner label.
    am,asc,ap,ay,aid=a
    bm,bsc,bp,by,bid=b
    dx,dy=rotate(bp[0]-ap[0],bp[1]-ap[1],-ay)
    dz=bp[2]-ap[2]
    ba,bb=models[am]['bounds_m'],models[bm]['bounds_m']
    if min(ba[2][1]*asc[2],dz+bb[2][1]*bsc[2])-max(ba[2][0]*asc[2],dz+bb[2][0]*bsc[2])<.0001:
        return
    delta=math.remainder(by-ay,360)
    if abs(abs(delta)-180)<.000001:delta=180.
    theta=math.radians(delta)
    hx=max(abs(v) for v in bb[0])*bsc[0]
    hy=max(abs(v) for v in bb[1])*bsc[1]
    ex=abs(math.cos(theta))*hx+abs(math.sin(theta))*hy
    ey=abs(math.sin(theta))*hx+abs(math.cos(theta))*hy
    if (dx+ex<ba[0][0]*asc[0] or dx-ex>ba[0][1]*asc[0]
            or dy+ey< -ba[1][1]*asc[1] or dy-ey> -ba[1][0]*asc[1]):
        return
    key=(am,asc,bm,bsc,round(dx,5),round(dy,5),round(dz,5),round(delta,5))
    queries.setdefault(key,dict(first_time_s=t,objects=[aid,bid]))


def audit():
    queries={}
    samples=contact_samples()
    for t in samples:
        poses=sample_scene(t)
        cargos=[]
        for i in range(8,18):
            p,yaw,_,on,_=poses[i]
            if on:
                track=tracks[i]
                cargos.append((track['mesh'].split('/')[-1],tuple(track['scale']),p,yaw,track['id']))
        for j,cargo in enumerate(cargos):
            for other in cargos[j+1:]:
                if math.dist(cargo[2][:2],other[2][:2])<2:
                    prepare(cargo,other,t,queries)
            for i,(p,yaw,lift,on,_) in enumerate(poses[:5]):
                if not on or math.dist(p[:2],cargo[2][:2])>3.2:
                    continue
                for part,z in [('Body',0),('Carriage',lift),('Mast',max(0,lift-.7)*.5)]:
                    a=('SM_Replay_Forklift'+part,(1,1,1),[p[0],p[1],p[2]+z],yaw,tracks[i]['id'])
                    prepare(a,cargo,t,queries)
    meshes={}
    for name in sorted({q[i] for q in queries for i in (0,2)}):
        meshes[name]=read_mesh(name)
    fixed={}
    hits=[]
    for key,witness in queries.items():
        a,asc,b,bsc,x,y,z,yaw=key
        if (a,asc) not in fixed:
            vs,fs=meshes[a]
            transform=Matrix.Diagonal(asc)
            fixed[a,asc]=BVHTree.FromPolygons([transform@v for v in vs],fs,all_triangles=True)
        vs,fs=meshes[b]
        transform=Matrix.Rotation(math.radians(yaw),3,'Z') @ Matrix.Diagonal(bsc)
        offset=Vector((x,y,z))
        moving=BVHTree.FromPolygons([transform@v+offset for v in vs],fs,all_triangles=True)
        pairs=fixed[a,asc].overlap(moving)
        if pairs:
            hits.append(dict(**witness,first_mesh=a,second_mesh=b,relative=[x,y,z,yaw],
                             triangle_pair=pairs[0],intersecting_triangle_pairs=len(pairs)))
    classes=Counter(h['first_mesh']+' / '+h['second_mesh'] for h in hits)
    witnesses={}
    for hit in hits:
        witnesses.setdefault(hit['first_mesh']+' / '+hit['second_mesh'],hit)
    report=dict(**provenance,success=not hits,timeline_sha256=hashlib.sha256(timeline_bytes).hexdigest(),
                poses=len(samples),distinct_narrow_phase_pairs=len(queries),intersection_count=len(hits),
                verified_fbx_sha256={name:models[name]['sha256'] for name in meshes},
                intersections_by_mesh_pair=classes,examples_by_mesh_pair=witnesses,
                first_intersections=hits[:80],scope='All ten cargoes including adjacent stacked, carried and truck-owned pallets versus each other and five actual fork body, carriage and mast FBX meshes; substeps at <=2cm lift/precision positioning, <=15 cm travel and <=2 degrees yaw. Vertical contacts below 0.1mm are treated as touching.')
    dest=ROOT/'Saved/OrderReplay/cargo_contacts_validation.json'
    dest.write_text(json.dumps(report,indent=2),encoding='utf8')
    print('CARGO_CONTACTS',len(samples),len(queries),len(hits),flush=True)
    if hits:
        raise RuntimeError(f'{len(hits)} cargo contacts; see {dest}')


if __name__=='__main__':
    audit()
