"""Traffic and context extensions share the same CAD paths as park_site.py.

All geometry is in site UV metres. Exported runtime points are UE centimetres.
No scene files, ground materials or existing parked vehicles are modified.
"""
from pathlib import Path
import json
import math
import sys
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'Saved/ParkRefinement/python_deps'))
from shapely.geometry import LineString, Point, box
from shapely.ops import unary_union, linemerge
from park_curves import rounded_path, offset_path, sample_along

ORIGIN = (239.33385, 60.24019)
GLEN = {'13a3','1460','1633','149c','1673','17c8','1f42','20d4'}
SYCAMORE = {'15ee','140d','16e0','1f7f','17a8','13d0','166f'}


def _parts(geometry):
    if geometry.geom_type == 'LineString': return [geometry]
    return [p for g in geometry.geoms for p in _parts(g)]


def _extend(points, start, end):
    path = [tuple(p) for p in points]
    if start:
        a,b=path[:2];d=math.dist(a,b)
        path.insert(0,(a[0]+65*(a[0]-b[0])/d,a[1]+65*(a[1]-b[1])/d))
    if end:
        a,b=path[-2:];d=math.dist(a,b)
        path.append((b[0]+65*(b[0]-a[0])/d,b[1]+65*(b[1]-a[1])/d))
    return path


def build_routes():
    cad=json.loads((ROOT/'SourceAssets/GHS/Park/cad_layout.json').read_text(encoding='utf8'))
    scope=box(-175,-195,725,570).buffer(22,quad_segs=16)
    paths={}
    for row in cad['roads']:
        if row['handle'] not in GLEN|SYCAMORE and row['layer']!='highways':continue
        controls=list(LineString(row['points_uv_m']).simplify(.18,preserve_topology=True).coords)
        path=rounded_path(controls,55 if row['layer']=='highways' else 22,max_step=1.)
        paths[row['handle']]=LineString(path).intersection(scope)
    glen=linemerge(unary_union([paths[h] for h in GLEN]))
    assert glen.geom_type=='LineString'
    glen=list(glen.coords)
    if glen[0][0]>glen[-1][0]:glen.reverse()
    highway=_parts(linemerge(unary_union([paths[h] for h in ['16ec','16ff','1853','1f50']])))
    assert len(highway)==2
    highway.sort(key=lambda p:p.interpolate(.5,normalized=True).y)
    inbound=linemerge(unary_union([paths[h] for h in ['17a8','1f7f','140d']]))
    assert inbound.geom_type=='LineString'
    inbound=list(inbound.coords)
    if inbound[0][1]<inbound[-1][1]:inbound.reverse()
    specs=[('glen','GlenHelen',glen,19.,True,True),
           ('sycamore_south','Sycamore',list(paths['15ee'].coords),6.6,False,True),
           ('sycamore_north','Sycamore',inbound,6.6,True,False)]
    for n,line in enumerate(highway):
        path=list(line.coords)
        if (n==0 and path[0][0]<path[-1][0]) or (n==1 and path[0][0]>path[-1][0]):path.reverse()
        specs.append(('i15_'+str(n),'I15_'+str(n),path,14.,True,True))
    sycamore=unary_union([paths[h] for h in SYCAMORE])
    roads=[];routes=[]
    for name,corridor,path,width,start,end in specs:
        original=LineString(path)
        intersection=original.intersection(sycamore) if corridor.startswith('I15') else None
        crossing=original.project(intersection.centroid) if intersection is not None and not intersection.is_empty else None

        def height(p):
            if crossing is None:return .015
            delta=abs(original.project(Point(p))-crossing)
            q=max(0.,min(1.,(100.-delta)/64.))
            return .03+6.1*q*q*(3-2*q)

        extended=_extend(path,start,end)
        road=dict(id=name,corridor=corridor,width_m=width,path_uv_m=path,
                  heights_m=[height(p) for p in path],extended_path_uv_m=extended,
                  extended_heights_m=[height(p) for p in extended],
                  extend_start=start,extend_end=end)
        roads.append(road)
        # Glen Helen is a two-way four-lane road; each highway already is a
        # directional carriageway. Sycamore's two CAD paths need no offset.
        lanes=[(6.9,False),(-6.9,True)] if corridor=='GlenHelen' else [(0.,False)]
        for offset,reverse in lanes:
            lane=offset_path(extended,offset)
            if reverse:lane.reverse()
            line=LineString(lane)
            # Keep whole vehicles inside the pavement at the spawn/despawn
            # edges and clear of Sycamore's northern junction with Glen Helen.
            samples=[p for p,_,_ in sample_along(lane,3.,start=18.) if line.project(Point(p))<line.length-18.]
            if corridor=='Sycamore':
                # The source's two carriageways meet at one CAD endpoint far
                # south of the campus. Their visual context tails continue
                # beyond it, but straight tangent extensions cross there.
                # End/start the active lanes 18m before/after that terminal
                # join, keeping an entire 15m truck out of the shared point.
                if name=='sycamore_south':
                    samples=[p for p in samples if original.project(Point(p))<original.length-18.]
                else:
                    samples=[p for p in samples if original.project(Point(p))>18.]
            points=[(p[0],p[1],height(p)+.025) for p in samples]
            routes.append(dict(id=name+('_reverse' if reverse else '_forward'),road_id=name,corridor=corridor,
                length_m=LineString(samples).length,max_speed_cm_s=1800 if corridor.startswith('I15') else 950,
                terminal_join_exclusion_m=18. if corridor=='Sycamore' else 0.,
                points_uvz_m=points,points_cm=[[(p[0]-ORIGIN[0])*100,(p[1]-ORIGIN[1])*100,p[2]*100] for p in points]))
    return dict(version=1,origin_uv_m=ORIGIN,extension_m=65,roads=roads,routes=routes)


def main():
    result=build_routes()
    out=ROOT/'SourceAssets/GHS/Traffic';out.mkdir(parents=True,exist_ok=True)
    (out/'routes.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    runtime={'version':1,'routes':[{k:v for k,v in route.items() if k!='points_uvz_m'} for route in result['routes']]}
    for route in runtime['routes']:
        route['points_cm']=[[round(v,3) for v in point] for point in route['points_cm']]
    (ROOT/'Content/GHSTwinUI/data/campus-traffic-routes.json').write_text(json.dumps(runtime,separators=(',',':')),encoding='utf8')
    print(json.dumps({'roads':len(result['roads']),'routes':len(result['routes']),'points':sum(len(r['points_cm']) for r in result['routes'])}))


if __name__=='__main__':main()
