"""Plan against a fresh read-only map snapshot; centimetres on export."""
import sys,json,math,heapq,hashlib,zlib,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'Scripts/_vendor/cad'))
sys.path.insert(0,str(ROOT/'Scripts/ghs'))
import numpy as np
import shapely
from shapely.geometry import box,Polygon,Point,LineString
from shapely.ops import unary_union
from shapely.affinity import affine_transform
from park_curves import rounded_path
OUT=ROOT/'Saved/OrderReplay';p=json.loads((OUT/'scene_probe.json').read_text())
by={r['label']:r for r in p['items']}
registry_path=ROOT/'Content/GHSTwinUI/data/scene-bindings.json'
registry={g['actor']:g for g in json.loads(registry_path.read_bytes())['groups']}
assert p['registry_sha256']==hashlib.sha256(registry_path.read_bytes()).hexdigest()
assert p['map_sha256']==hashlib.sha256((ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap').read_bytes()).hexdigest()
# Per-lift assignments use floor CAD IDs and individual rack bay/level/column keys.
choices = [
    (75, 'CAD_24_41852B'), (75, 'CAD_24_418DCB'),
    (51, [('CAD_24_3FD654',2,2),('CAD_24_3FD654',1,2)]),
    (22, [('CAD_24_3FDB82',1,3),('CAD_24_3FDB9E',1,3)]),
    (22, 'CAD_24_419C2B')]
selected=[];exclude=set()
data_dir=registry_path.parent
bindings_path=data_dir/'inventory-bindings.json'
inventory_path=data_dir/'inventory/index.json'
capacity=json.loads((data_dir/'storage-capacity.json').read_bytes())
meshes={m['name']:m for m in capacity['meshes']}
bindings={(r['cadId'],r['level'],r['column']):r for r in json.loads(bindings_path.read_bytes())['bindings']}
inventory={row['id']:row for row in json.loads(inventory_path.read_bytes())['locations']}

def source_instance(label, cad_id, role):
    records=registry[label]['instances']
    [record]=[row for row in records if row['id']==cad_id]
    x,y,*z=record['position_m']
    expected=[x*100,-y*100,(z or [0])[0]*100]
    component=by[label]
    [item]=[i for i in component['instances'] if math.dist(i['transform']['position_cm'],expected)<.1]
    tr=item['transform']
    return dict(cadId=cad_id,role=role,actor=component['actor'],component=component['component'],
                index=item['index'],position=tr['position_cm'],yaw=tr['rotation_deg'][1],scale=tr['scale'])

sources=[]
for n,(dock,assignment) in enumerate(choices):
    truck=by['GHS_DockTruck_%03d'%dock]['instances'][0]['transform']
    loads=[]
    if isinstance(assignment,str):
        label='GHS_CAD_PalletCargo'
        source=source_instance(label,assignment,'cargo')
        sources.append(source)
        floor_instance=by[label]['instances'][source['index']]
        height=(floor_instance['bounds_cm'][5]-floor_instance['bounds_cm'][2])/200
        exclude.add((label,source['index']))
        for layer in (1,0):
            position=[v/100 for v in source['position']]
            position[2]+=layer*height
            loads.append(dict(kind='floor',mesh='CargoMid',position_m=position,scale=source['scale'],
                              height_m=height,source_yaw=source['yaw'],source_name='地堆'+('上层' if layer else '下层')))
    else:
        for j,slot_key in enumerate(assignment):
            bind=bindings[slot_key]
            stock=inventory[bind['locationId']]
            assert stock['code']==bind['locationCode'] and stock['availableQuantity']>0
            mesh=meshes[bind['expectedMesh']]
            label=next(g['actor'] for g in capacity['groups'] if g['mesh']==mesh['name'])
            source=source_instance(label,bind['cadId'],'rackSlot')
            level,column=slot_key[1:]
            slot=next(c for c in mesh['cargo_stacks'] if (c['level'],c['column'])==(level,column))
            assert source['scale']==[1,1,1] and abs(source['yaw'])<.001 and label.endswith('_A1')
            position=[v/100 for v in source['position']]
            position[0]+=slot['pallet_center_x_m'];position[2]+=slot['base_z_m']
            source.update(level=level,column=column,locationId=bind['locationId'],locationCode=stock['code'],
                          palletPosition=[v*100 for v in position],cargoId='REPLAY-CARGO-%02d'%(2*n+j+1))
            sources.append(source)
            loads.append(dict(kind='rack',mesh='CargoRack_A1_L%d_C%d'%(level,column),position_m=position,
                              height_m=slot['stack_top_z_m']-slot['base_z_m'],scale=[1,1,1],source_yaw=-90,
                              source_name='货架 '+stock['code'],available_quantity=stock['availableQuantity'],
                              rackActor=label,rackIndex=source['index'],level=level,column=column))
    selected.append(dict(id='REPLAY-FORK-%02d'%(n+1),dock=dock,yaw=-90,loads=loads,
                         truck_position_m=[v/100 for v in truck['position_cm']],truck_yaw=truck['rotation_deg'][1]))
obstacles=[];metadata=[]
pass_shapes={}
for mesh,triangles in p['rack_footprints_local_cm'].items():
    shapes=[]
    for tri in triangles:
        poly=Polygon([(x/100,y/100) for x,y,z in tri])
        shapes.append(poly if poly.area>1e-9 else poly.boundary.buffer(.001))
    pass_shapes[mesh]=unary_union(shapes)
for r in p['items']:
    label=r['label']
    if not (label.startswith(('GHS_CAD_PalletCargo','GHS_Rack_CAD24_','GHS_CAD_Columns','GHS_ColumnBases','GHS_ChargingSupport'))):continue
    for i in r['instances']:
        if (label,i['index']) in exclude:continue
        a,b,c,d,e,f=[v/100 for v in i['bounds_cm']]
        if f<.03 or c>3.9:continue
        shape=box(a,b,d,e)
        if r['mesh'] in pass_shapes:
            tr=i['transform']; theta=math.radians(tr['rotation_deg'][1]);cs,sn=math.cos(theta),math.sin(theta)
            sx,sy,_=tr['scale'];tx,ty,_=tr['position_cm']
            shape=affine_transform(pass_shapes[r['mesh']],[cs*sx,-sn*sy,sn*sx,cs*sy,tx/100,ty/100])
        obstacles.append(shape);metadata.append([label,i['index'],a,b,d,e])
for label,ts in p['triangles_cm'].items():
    if 'Wall' not in label:continue
    for tri in ts:
        if min(v[2] for v in tri)>390 or max(v[2] for v in tri)<3:continue
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
def astar(start,end,waypoints=False):
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
    if waypoints:return result
    # A broader tangent arc turns naturally at the unchanged driving speed.
    # Keep exact corridor clearance and finely sample the curve geometry.
    curve=rounded_path(result,1.50,max_step=.10)
    assert all(clear(a,b,1.70) for a,b in zip(curve,curve[1:])),('unsafe rounded route',result)
    return curve

def footprint(pos,yaw):
    a=math.radians(yaw);c,s=math.cos(a),math.sin(a)
    return unary_union([Polygon([(pos[0]+c*x-s*y,pos[1]+s*x+c*y) for x,y in coords]) for coords in [[(-1.25,-.625),(1.02,-.625),(1.02,.625),(-1.25,.625)],[(1.02,-.363),(2.20,-.363),(2.20,.363),(1.02,.363)]]])
routes=[]
for r in selected:
    for load in r['loads']:
        x,y,z=load['position_m']
        pickup=(x,y+1.93);staging=(x,y+4.05)
        tx,ty,tz=r['truck_position_m'];end=(tx,47.0)
        if load['kind']=='floor':
            # Leave the closely spaced floor staging positions on parallel headings.
            lead=(x,staging[1]+6.)
            curve=rounded_path([staging,lead,*astar(lead,end)[1:]],1.5,max_step=.10)
            insertion_solid=solid
        else:
            if r['dock']==51:
                # Longitudinal aisle to the dock apron; turn beyond the stationary
                # forklifts at the adjacent floor-picking positions.
                cross=(-42.,29.)
                nodes=astar(staging,cross,True)+astar(cross,end,True)[1:]
                curve=rounded_path(nodes,1.50,max_step=.10)
                assert all(clear(a,b,1.70) for a,b in zip(curve,curve[1:]))
            else:
                curve=astar(staging,end)
            # The vehicle remains in front of the bay. Its tines enter only the
            # selected slot. Detailed beam/slot contact is tested on actual geometry.
            hit_index=next(i for i,m in enumerate(metadata) if m[:2]==[load['rackActor'],load['rackIndex']])
            assert solid.intersection(footprint(pickup,-90)).difference(obstacles[hit_index]).area<1e-8
            insertion_solid=solid.difference(obstacles[hit_index])
        for k in range(31):
            pos=(x,pickup[1]+(staging[1]-pickup[1])*k/30)
            assert not insertion_solid.intersects(footprint(pos,-90)),('pickup collision',r['id'],pos)
        load.update(pickup_origin_m=[*pickup,.005],staging_m=[*staging,.005],
                    route_m=[[a,b,.005] for a,b in curve],route_length_m=LineString(curve).length)
    r['staging_m']=r['loads'][0]['staging_m']
    r['route_m']=r['loads'][0]['route_m']
    routes.append(r)
door=by['GHS_CAD_DockDoors'];doors=[]
for dock in sorted({r['dock'] for r in selected}):
    [record]=[row for row in registry[door['label']]['instances'] if int(row['dock_number'])==dock]
    source=source_instance(door['label'],record['id'],'door');sources.append(source)
    i=door['instances'][source['index']]
    doors.append(dict(index=source['index'],transform=i['transform']))
report=dict(success=True,source_probe_sha256=hashlib.sha256((OUT/'scene_probe.json').read_bytes()).hexdigest(),
    sceneBindingsSha256=p['registry_sha256'],mapSha256=p['map_sha256'],
    inventoryBindingsSha256=hashlib.sha256(bindings_path.read_bytes()).hexdigest(),
    inventoryIndexSha256=hashlib.sha256(inventory_path.read_bytes()).hexdigest(),
    source_instances=sources,doors=doors,forklifts=routes,obstacle_instances=metadata,units='m',
    validation=dict(solid_polygons=len(obstacles),route_clearance_radius_m=1.70,rotation_envelope_radius_m=1.84,pickup_obb_checked=True,
        truck_routes_report='Saved/OrderReplay/truck_routes.json',complete_actions_report='Saved/OrderReplay/static_actions_validation.json'))
# Keep a conservative actual-shape check separate from the path-centre search.
hits=[]
for r in routes:
    for load in r['loads']:
        path=load['route_m']
        for j,q in enumerate(path):
            a,b=path[max(0,j-1)],path[min(len(path)-1,j+1)]
            yaw=math.degrees(math.atan2(b[1]-a[1],b[0]-a[0]))
            overlap=solid.intersection(footprint(q,yaw)).area
            if overlap>1e-6:hits.append(dict(id=r['id'],point=j,position=q,yaw=yaw,overlap=overlap))
(OUT/'forklift_route_shape_audit.json').write_text(json.dumps(dict(success=not hits,hits=hits[:100],hit_count=len(hits)),indent=2))
assert not hits,('actual footprint route collision',hits[:3])
(OUT/'routes_plan.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps([dict(id=r['id'],length=[round(load['route_length_m'],1) for load in r['loads']],staging=r['staging_m']) for r in routes]))
