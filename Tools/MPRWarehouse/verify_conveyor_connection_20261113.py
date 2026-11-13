"""Offline CAD topology regression: detect the former gap and verify source ports.

Uses actual exported mesh surface polygons and prior instance footprints, not
the new generator's branching logic. It performs no UE or scene writes.
"""
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'SourceAssets/MPR/conveyor_connection_20261113'


def read(name):
    return json.loads((SRC/name).read_text(encoding='utf-8-sig'))


def cross(a,b,c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def distance(p,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1]
    t=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy)))
    return math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy)


def inside(p,poly):
    result=False
    for a,b in zip(poly,poly[1:]+poly[:1]):
        if distance(p,a,b)<1e-7:return True
        if (a[1]>p[1])!=(b[1]>p[1]) and p[0]<(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0]:
            result=not result
    return result


def connected(a,b):
    if any(inside(p,b) for p in a) or any(inside(p,a) for p in b):return True
    for p,q in zip(a,a[1:]+a[:1]):
        for r,s in zip(b,b[1:]+b[:1]):
            if cross(p,q,r)*cross(p,q,s)<0 and cross(r,s,p)*cross(r,s,q)<0:return True
            if min(distance(p,r,s),distance(q,r,s),distance(r,p,q),distance(s,p,q))<1e-5:return True
    return False


def components(polys):
    pending=set(range(len(polys)));groups=[]
    while pending:
        group={pending.pop()};queue=list(group)
        while queue:
            i=queue.pop()
            neighbors={j for j in pending if connected(polys[i],polys[j])}
            pending-=neighbors;group|=neighbors;queue.extend(neighbors)
        groups.append(sorted(group))
    return groups


def main():
    evidence=read('cad_evidence.json');manifest=read('MPR_ConveyorConnection_20261113.json')
    old=[]
    for row in read('replacement_targets.json'):
        x,y,_=row['position_m'];sx,sy,_=row['scale'];a=math.radians(row['rotation_deg'])
        old.append([[x+math.cos(a)*dx-math.sin(a)*dy,y+math.sin(a)*dx+math.cos(a)*dy]
                    for dx,dy in [(-sx/2,-sy),(sx/2,-sy),(sx/2,sy),(-sx/2,sy)]])
    actual=[s['points'] for s in manifest['surface_polygons']]
    before=components(old);after=components(actual)
    assert len(before)>1,'The regression fixture must expose the disconnected original mesh layout'
    assert len(after)==1,after
    assert len([s for s in manifest['surface_polygons'] if s['kind'].startswith('branch_')])==10
    assert len([s for s in manifest['surface_polygons'] if s['kind'].startswith('outfeed_')])==10
    spine=evidence['spine'];cx=spine['center_x'];ya,yb=spine['y_range']
    samples=[[cx,ya+(yb-ya)*i/1000] for i in range(1001)]
    missing_before=sum(not any(inside(p,q) for q in old) for p in samples)
    assert missing_before>0
    assert all(any(inside(p,q) for q in actual) for p in samples)
    # Check source-measured branch exit endpoints, including reflected left side.
    port_checks=[]
    for branch in evidence['branches']:
        source=branch['source_outer_edge']['points_cad_m']
        points=source if branch['side']==1 else [[2*cx-x,y] for x,y in source]
        assert all(any(inside(p,q) for q in actual) for p in points)
        port_checks.append(dict(index=branch['index'],side=branch['side'],source_handles=branch['source_outer_edge']['source_handles']))
    # The existing infeed ends at -65.86867m, inside the corrected main spine.
    feed_end=[-17.49353,-74.25619+16.77504/2]
    assert inside(feed_end,actual[0])
    assert manifest['source_handle']=='2D457E'
    assert len(manifest['meshes'])==1 and manifest['meshes'][0]['triangles']<25000
    assert evidence['independent_parallel_lines']==['2D4587','2D45D9']
    report=dict(success=True,source_handle='2D457E',old_connected_components=len(before),
        new_connected_components=len(after),old_missing_center_samples=missing_before,
        new_center_samples_covered=1001,branch_ports_verified=port_checks,
        infeed_endpoint_connected=feed_end,geometry=manifest['meshes'][0],
        scope='Replace only twelve instances of source 2D457E with one private mesh instance')
    (SRC/'topology_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('branch_ports_verified','geometry')},ensure_ascii=False))


if __name__=='__main__':main()
