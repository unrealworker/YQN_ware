"""Validate every forklift action against the unchanged scene's solid geometry."""
import sys,json,math,bisect,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'Saved/OrderReplay'
sys.path.insert(0,str(ROOT/'Scripts/_vendor/cad'))
from collections import Counter
from shapely.affinity import affine_transform
from shapely.geometry import Polygon,LineString,box
from shapely.ops import unary_union
from shapely.prepared import prep
from replay_audit_sources import verify_sources, timeline_path as replay_timeline_path
plan=json.loads((OUT/'routes_plan.json').read_text(encoding='utf8'))
path=replay_timeline_path(ROOT);data=json.loads(path.read_text(encoding='utf8'));tracks=data['tracks']
probe,source_hashes=verify_sources(ROOT,data)
assert plan['source_probe_sha256']==source_hashes['source_probe_sha256']
excluded={(s['actor'],s['component'],s['index']) for s in data['sourceInstances'] if s['role'] in ('cargo','door')}
# These three bays are audited as actual 3D geometry in replay_validate_cargo_contacts.
rack_sources={(s['actor'],s['component'],s['index']) for s in data['sourceInstances'] if s['role']=='rackSlot'}
assert len(excluded)+len(rack_sources)>0
source_bays_seen=set()
resolved=set()
obstacles=[];coverage=Counter()
pass_shapes={}
for name,triangles in probe['rack_footprints_local_cm'].items():
    planes=[]
    for points in triangles:
        vertices=[(x/100,y/100) for x,y,z in points]
        tri=Polygon(vertices)
        planes.append(tri if tri.area>1e-10 else LineString(vertices).buffer(.001))
    pass_shapes[name]=unary_union(planes)
for item in probe['items']:
    if not item['label'].startswith(('GHS_CAD_PalletCargo','GHS_Rack_CAD24_','GHS_CAD_Columns','GHS_ColumnBases','GHS_ChargingSupport','GHS_CAD_DockDoors')):continue
    for inst in item['instances']:
        target=(item['actor'],item['component'],inst['index'])
        if target in excluded:
            resolved.add(target)
            continue
        coverage[item['label']]+=1
        if target in rack_sources:
            source_bays_seen.add(target)
            continue
        if '_PASS' in item['label'] or item['label'].endswith('_D1'):
            tr=inst['transform'];yaw=math.radians(tr['rotation_deg'][1]);c,s=math.cos(yaw),math.sin(yaw)
            sx,sy,sz=tr['scale'];px,py,pz=tr['position_cm']
            assert abs(pz)<.1 and abs(sz-1)<.0001
            obstacles.append(affine_transform(pass_shapes[item['mesh']], [c*sx,-s*sy,s*sx,c*sy,px/100,py/100]))
            continue
        a,b,c,d,e,f=[v/100 for v in inst['bounds_cm']]
        if f>=.03 and c<=3.9:obstacles.append(box(a,b,d,e))
assert source_bays_seen==rack_sources
assert resolved==excluded, 'Source exclusion does not resolve in the scene'
registry=json.loads((ROOT/'Content/GHSTwinUI/data/scene-bindings.json').read_bytes())
for g in registry['groups']:
    if g['actor'].startswith('GHS_Rack_CAD24_'):
        assert coverage[g['actor']]==g['count'],g['actor']
# The merged office facade spans the warehouse in its overall bounds. The
# source contains the exact cuboid for each glazed pane, sill and mullion.
facade_path=ROOT/'SourceAssets/GHS/OfficeFacade/facade_manifest.json'
facade=json.loads(facade_path.read_bytes())
facade_component=next(row for row in probe['items'] if row['label']=='GHS_OfficeGlassFacade')
[facade_instance]=facade_component['instances']
assert facade_component['mesh'].split('.')[-1]==facade['mesh']['name']
assert facade_instance['transform']=={'position_cm':[0,0,0],'rotation_deg':[0,0,0],'scale':[1,1,1]}
source_bounds=facade['mesh']['bounds_ue_cm']
assert max(abs(v-w) for v,w in zip(facade_instance['bounds_cm'],source_bounds['min']+source_bounds['max'])) < .01
for part in facade['parts']:
    bottom,top=part['z_range_m']
    if top>=.03 and bottom<=3.9:
        u,v,U,V=part['bounds_uv_m']
        obstacles.append(box(u-239.33385,v-60.24019,U-239.33385,V-60.24019))
        coverage['office_facade_parts']+=1
for label,triangles in probe['triangles_cm'].items():
    if 'Wall' not in label and label!='GHS_OfficeGlassFacade':continue
    for tri in triangles:
        if min(v[2] for v in tri)>390 or max(v[2] for v in tri)<3:continue
        geom=Polygon([(v[0]/100,v[1]/100) for v in tri])
        geom=LineString([(v[0]/100,v[1]/100) for v in tri]).buffer(.01) if geom.area<1e-8 else geom.buffer(0)
        if not geom.is_empty:obstacles.append(geom)
# At adjacent floor positions separated by exactly 48 inches, float32 mesh
# bounds overlap by ~0.08 micrometres. Require a penetration of one micrometre.
coordinate_tolerance_m=.000001
solid=unary_union(obstacles).buffer(-coordinate_tolerance_m);prepared=prep(solid)
def polygon(pos,yaw,coords):
    r=math.radians(yaw);c,s=math.cos(r),math.sin(r)
    return Polygon([(pos[0]+c*x-s*y,pos[1]+s*x+c*y) for x,y in coords])
mesh_bounds={m['name']:m['bounds_m'] for m in json.loads((ROOT/'SourceAssets/GHS/OrderReplay/replay_assets.json').read_bytes())['meshes']}
def cargo_corners(track):
    sx,sy,_=track['scale']
    bx,by,_=mesh_bounds[track['mesh'].split('/')[-1]]
    return [(x*sx,-y*sy) for x,y in ((bx[0],by[0]),(bx[1],by[0]),(bx[1],by[1]),(bx[0],by[1]))]

def parts(pos,yaw,load):
    # Split narrow tines from chassis rather than an unrealistically full-width front box.
    pieces=[polygon(pos,yaw,[(-1.25,-.625),(1.10,-.625),(1.10,.625),(-1.25,.625)]),polygon(pos,yaw,[(1.10,-.363),(2.2,-.363),(2.2,.363),(1.10,.363)])]
    if load:
        cargo,key=load
        pivot=polygon([v/100 for v in key[1]],key[2],cargo_corners(cargo))
        pieces.append(polygon(pos,yaw,list(pivot.exterior.coords)))
    return pieces
ownership_times=[[k[0] for k in track['keys']] for track in tracks[8:]]
def carries(i,t):
    for cargo,times in zip(tracks[8:],ownership_times):
        key=cargo['keys'][max(0,bisect.bisect_right(times,t)-1)]
        if key[6]==i:
            return cargo,key
    return None
hits=[];checked=0;unique=set();pose_times=[]
for i,track in enumerate(tracks[:5]):
    previous=None;previous_token=None
    for a,b in zip(track['keys'],track['keys'][1:]):
        distance=math.dist(a[1],b[1])/100;angle=math.remainder(b[2]-a[2],360)
        n=max(1,math.ceil(distance/.20),math.ceil(abs(angle)/2))
        for k in range(n+1):
            f=k/n;pos=[(x+(y-x)*f)/100 for x,y in zip(a[1],b[1])];yaw=a[2]+angle*f;t=a[0]+(b[0]-a[0])*f
            loaded=carries(i,t)
            load_key=(loaded[0]['id'],tuple(loaded[1][1]),loaded[1][2]) if loaded else None
            pose_token=(*[round(v,6) for v in [*pos,yaw]],load_key);token=(previous_token,pose_token)
            rotation_step=abs(math.remainder(pose_token[3]-previous_token[3],360)) if previous_token else 0;previous_token=pose_token
            current=parts(pos,yaw,loaded)
            if token in unique:previous=current;continue
            unique.add(token);checked+=1
            swept=[piece.union(previous[n]).convex_hull if previous and n<len(previous) else piece for n,piece in enumerate(current)]
            footprint=unary_union(swept)
            if rotation_step>1e-5:footprint=footprint.buffer(.003,quad_segs=2)
            previous=current
            if prepared.intersects(footprint):
                overlap=solid.intersection(footprint).area
                if overlap>1e-7:hits.append(dict(id=track['id'],time=round(t,4),position_m=pos,yaw=yaw,area_m2=overlap,status=a[7]))
report=dict(success=not hits,**source_hashes,coverage=coverage,timeline_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    facade_manifest_sha256=hashlib.sha256(facade_path.read_bytes()).hexdigest(),
    coordinate_tolerance_m=coordinate_tolerance_m,
    maximum_translation_step_m=.20,maximum_yaw_step_degrees=2,unique_forklift_poses_checked=checked,solid_geometry_count=len(obstacles),
    source_bays_with_separate_fbx_audit=len(source_bays_seen),continuous_part_hulls=True,rotation_sweep_padding_m=.003,collision_count=len(hits),collisions=hits[:60],scope='Chassis, tines and carried pallet swept against current CAD 2.4 rack, ground load, column, charging support, closed dock door and wall geometry. Passage and dock rack footprints use actual LOD0 faces intersecting the 0.03–3.90m height band. Replacement floor stacks and open doors are excluded. Exact source bay geometry, including every steel member and all neighboring slots, is tested by replay_validate_cargo_contacts.')
(OUT/'static_actions_validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in report.items() if k!='collisions'}))
assert report['success'],'Inspect Saved/OrderReplay/static_actions_validation.json'
