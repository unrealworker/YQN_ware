"""Plan against a fresh read-only map snapshot; centimetres on export."""
import sys,json,math,heapq,hashlib,zlib,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'Saved/ParkRefinement/python_deps'))
sys.path.insert(0,str(ROOT/'Scripts/ghs'))
import numpy as np
import shapely
from shapely.geometry import box,Polygon,Point,LineString
from shapely.ops import unary_union
from park_curves import rounded_path
OUT=ROOT/'Saved/OrderReplay';p=json.loads((OUT/'scene_probe.json').read_text())
by={r['label']:r for r in p['items']}
choices=[('High',1896,75),('Low',1567,75),('Mid',1616,51),('High',127,20),('Low',1291,20)]
selected=[];exclude=set()
for n,(kind,index,dock) in enumerate(choices):
    label='GHS_CAD_PalletCargo'+('' if kind=='Mid' else kind);r=by[label];i=r['instances'][index]
    pos=[v/100 for v in i['transform']['position_cm']];yaw=90 if kind in ('High','Mid') else -90
    half={'High':1.288015365,'Mid':.98801559,'Low':.68801559}[kind]
    truck=by['GHS_DockTruck_%03d'%dock]['instances'][0]['transform']
    selected.append(dict(id='REPLAY-FORK-%02d'%(n+1),kind=kind,actor=r['actor'],component=r['component'],index=index,label=label,
        position_m=pos,scale=i['transform']['scale'],yaw=yaw,tier_height_m=half,dock=dock,
        truck_position_m=[v/100 for v in truck['position_cm']],truck_yaw=truck['rotation_deg'][1]))
    exclude.add((label,index))
obstacles=[];metadata=[]
for r in p['items']:
    label=r['label']
    if not (label.startswith(('GHS_CAD_PalletCargo','GHS_V2_Rack','GHS_CAD_Columns','GHS_ColumnBases','GHS_ChargingSupport'))):continue
    for i in r['instances']:
        if (label,i['index']) in exclude:continue
        a,b,c,d,e,f=[v/100 for v in i['bounds_cm']]
        if f<.03 or c>2.4:continue
        obstacles.append(box(a,b,d,e));metadata.append([label,i['index'],a,b,d,e])
for label,ts in p['triangles_cm'].items():
    if 'Wall' not in label:continue
    for tri in ts:
        if min(v[2] for v in tri)>240 or max(v[2] for v in tri)<3:continue
        geom=Polygon([(v[0]/100,v[1]/100) for v in tri])
        if geom.area<1e-8:geom=LineString([(v[0]/100,v[1]/100) for v in tri]).buffer(.01)
        else:geom=geom.buffer(0)
        if not geom.is_empty:obstacles.append(geom)
solid=unary_union(obstacles)
floor=unary_union([Polygon([(v[0]/100,v[1]/100) for v in t]) for t in p['triangles_cm']['GHS_CAD_ExactFootprint'] if all(abs(v[2])<.01 for v in t)])
# Travel planning includes the existing concrete dock apron through real apertures.
domain=floor.union(box(-189,58,200,82));blocked=solid.buffer(1.84,quad_segs=8)
step=.5;x0=-195;y0=-60;nx=850;ny=285
xs=np.arange(nx)*step+x0;ys=np.arange(ny)*step+y0
xx,yy=np.meshgrid(xs,ys);points=shapely.points(xx,yy)
free=shapely.contains(domain,points)&~shapely.intersects(blocked,points)

def node(p):return (int(round((p[0]-x0)/step)),int(round((p[1]-y0)/step)))
def xy(n):return (n[0]*step+x0,n[1]*step+y0)
def clear(a,b,radius=1.84):return not solid.intersects(LineString([a,b]).buffer(radius,cap_style=1))
def astar(start,end):
    sn,en=node(start),node(end)
    # Narrow door approaches are final straight segments, not rotational corridors.
    assert free[sn[1],sn[0]],('blocked start',start)
    assert free[en[1],en[0]],('blocked end',end)
    q=[(math.dist(sn,en),0,sn)];cost={sn:0};came={}
    while q:
        _,g,n=heapq.heappop(q)
        if g>cost[n]+1e-7:continue
        if n==en:break
        for dx,dy in [(1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)]:
            nn=(n[0]+dx,n[1]+dy)
            if not(0<=nn[0]<nx and 0<=nn[1]<ny and free[nn[1],nn[0]]):continue
            if dx and dy and not(free[n[1],nn[0]] and free[nn[1],n[0]]):continue
            ng=g+math.hypot(dx,dy)
            if ng<cost.get(nn,1e99):cost[nn]=ng;came[nn]=n;heapq.heappush(q,(ng+math.dist(nn,en),ng,nn))
    assert en in cost,('no route',start,end)
    chain=[en]
    while chain[-1]!=sn:chain.append(came[chain[-1]])
    chain=[start]+[xy(n) for n in chain[::-1]][1:-1]+[end]
    # Exact buffered line-of-sight reduction leaves clearance for rounded corners.
    result=[chain[0]];i=0
    while i<len(chain)-1:
        j=len(chain)-1
        while j>i+1 and not clear(chain[i],chain[j]):j-=1
        result.append(chain[j]);i=j
    curve=rounded_path(result,.85,max_step=.35)
    assert all(clear(a,b,1.70) for a,b in zip(curve,curve[1:])),('unsafe rounded route',result)
    return curve

def footprint(pos,yaw):
    a=math.radians(yaw);c,s=math.cos(a),math.sin(a)
    return unary_union([Polygon([(pos[0]+c*x-s*y,pos[1]+s*x+c*y) for x,y in coords]) for coords in [[(-1.25,-.625),(1.02,-.625),(1.02,.625),(-1.25,.625)],[(1.02,-.363),(2.20,-.363),(2.20,.363),(1.02,.363)]]])
routes=[]
for r in selected:
    x,y,z=r['position_m'];yaw=r['yaw'];sign=1 if yaw==90 else -1
    # Contact-reviewed pallet centre is 1.93m ahead of the axle origin.
    pickup=(x,y-sign*1.93);staging=(x,y-sign*4.05)
    tx,ty,tz=r['truck_position_m'];end=(tx,53.0)
    curve=astar(staging,end)
    r.update(pickup_origin_m=[*pickup,.005],staging_m=[*staging,.005],route_m=[[a,b,.005] for a,b in curve],route_length_m=LineString(curve).length)
    # Ignore only selected target during straight fork insertion; all other stacks stay solid.
    for k in range(31):
        q=(pickup[0],pickup[1]+(staging[1]-pickup[1])*k/30)
        assert not solid.intersects(footprint(q,yaw)),('pickup collision',r['id'],q)
    routes.append(r)
sources=[dict(actor=r['actor'],component=r['component'],index=r['index'],role='cargo') for r in selected]
door=by['GHS_CAD_DockDoors'];doors=[]
for dock in sorted({r['dock'] for r in selected}):
    i=door['instances'][dock-1]
    sources.append(dict(actor=door['actor'],component=door['component'],index=dock-1,role='door'))
    doors.append(dict(index=dock-1,transform=i['transform']))
report=dict(success=True,source_probe_sha256=hashlib.sha256((OUT/'scene_probe.json').read_bytes()).hexdigest(),
    source_instances=sources,doors=doors,forklifts=routes,obstacle_instances=metadata,units='m',
    validation=dict(solid_polygons=len(obstacles),route_clearance_radius_m=1.70,rotation_envelope_radius_m=1.84,pickup_obb_checked=True,
        truck_routes_report='Saved/OrderReplay/truck_routes_qa.json',complete_actions_report='Saved/OrderReplay/static_actions_validation.json'))
# Keep a conservative actual-shape check separate from the path-centre search.
hits=[]
for r in routes:
    path=r['route_m']
    for j,q in enumerate(path):
        a,b=path[max(0,j-1)],path[min(len(path)-1,j+1)]
        yaw=math.degrees(math.atan2(b[1]-a[1],b[0]-a[0]))
        overlap=solid.intersection(footprint(q,yaw)).area
        if overlap>1e-6:hits.append(dict(id=r['id'],point=j,position=q,yaw=yaw,overlap=overlap))
(OUT/'forklift_route_shape_audit.json').write_text(json.dumps(dict(success=not hits,hits=hits[:100],hit_count=len(hits)),indent=2))
assert not hits,('actual footprint route collision',hits[:3])
(OUT/'routes_plan.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps([dict(id=r['id'],index=r['index'],length=round(r['route_length_m'],1),staging=r['staging_m']) for r in routes]))
