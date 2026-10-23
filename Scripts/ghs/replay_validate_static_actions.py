"""Validate every forklift action against the unchanged scene's solid geometry."""
import sys,json,math,bisect,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'Saved/OrderReplay'
sys.path.insert(0,str(ROOT/'Saved/ParkRefinement/python_deps'))
from shapely.geometry import Polygon,LineString,box
from shapely.ops import unary_union
from shapely.prepared import prep
probe=json.loads((OUT/'scene_probe.json').read_text(encoding='utf8'))
plan=json.loads((OUT/'routes_plan.json').read_text(encoding='utf8'))
path=ROOT/'Content/GHSTwinUI/data/order-replay.json';data=json.loads(path.read_text(encoding='utf8'));tracks=data['tracks']
excluded={(s['actor'],s['component'],s['index']) for s in data['sourceInstances']}
models=json.loads((ROOT/'SourceAssets/GHS/RefinementV2/Racks/refined_rack_cargo.json').read_text(encoding='utf8'))
rack_models={m['name']:m for m in models['meshes']}
obstacles=[]
for item in probe['items']:
    if not item['label'].startswith(('GHS_CAD_PalletCargo','GHS_V2_Rack','GHS_CAD_Columns','GHS_ColumnBases','GHS_ChargingSupport')):continue
    for inst in item['instances']:
        if (item['actor'],item['component'],inst['index']) in excluded:continue
        if item['label'].startswith('GHS_V2_Rack_D1'):
            name=item['mesh'].split('/')[-1].split('.')[0].removesuffix('_Capacity');model=rack_models[name]
            assert model['clear_under_beam_m']>=4.47
            tr=inst['transform'];pos=[v/100 for v in tr['position_cm']];yaw=math.radians(tr['rotation_deg'][1]);c,s=math.cos(yaw),math.sin(yaw)
            for part in model['solid_boxes']:
                x,y,z=part['center_m'];dx,dy,dz=[v/2 for v in part['size_m']]
                if z-dz>3.9 or z+dz<.03:continue
                # Narrow phase uses physical upright/brace parts, not the hollow D1 envelope.
                coords=[(x-dx,-y-dy),(x+dx,-y-dy),(x+dx,-y+dy),(x-dx,-y+dy)]
                obstacles.append(Polygon([(pos[0]+c*a-s*b,pos[1]+s*a+c*b) for a,b in coords]))
            continue
        a,b,c,d,e,f=[v/100 for v in inst['bounds_cm']]
        if f>=.03 and c<=3.8:obstacles.append(box(a,b,d,e))
for label,triangles in probe['triangles_cm'].items():
    if 'Wall' not in label:continue
    for tri in triangles:
        if min(v[2] for v in tri)>380 or max(v[2] for v in tri)<3:continue
        geom=Polygon([(v[0]/100,v[1]/100) for v in tri])
        geom=LineString([(v[0]/100,v[1]/100) for v in tri]).buffer(.01) if geom.area<1e-8 else geom.buffer(0)
        if not geom.is_empty:obstacles.append(geom)
solid=unary_union(obstacles);prepared=prep(solid)
def polygon(pos,yaw,coords):
    r=math.radians(yaw);c,s=math.cos(r),math.sin(r)
    return Polygon([(pos[0]+c*x-s*y,pos[1]+s*x+c*y) for x,y in coords])
def parts(pos,yaw,loaded=False):
    # Split narrow tines from chassis rather than an unrealistically full-width front box.
    pieces=[polygon(pos,yaw,[(-1.25,-.625),(1.02,-.625),(1.02,.625),(-1.25,.625)]),polygon(pos,yaw,[(1.02,-.363),(2.2,-.363),(2.2,.363),(1.02,.363)])]
    if loaded:pieces.append(polygon(pos,yaw,[(1.321205,-.5076),(2.538795,-.5076),(2.538795,.5076),(1.321205,.5076)]))
    return pieces
ownership_times=[[k[0] for k in track['keys']] for track in tracks[8:]]
def carries(i,t):
    return any(track['keys'][max(0,bisect.bisect_right(times,t)-1)][6]==i for track,times in zip(tracks[8:],ownership_times))
hits=[];checked=0;unique=set();pose_times=[]
for i,track in enumerate(tracks[:5]):
    previous=None;previous_token=None
    for a,b in zip(track['keys'],track['keys'][1:]):
        distance=math.dist(a[1],b[1])/100;angle=math.remainder(b[2]-a[2],360)
        n=max(1,math.ceil(distance/.20),math.ceil(abs(angle)/2))
        for k in range(n+1):
            f=k/n;pos=[(x+(y-x)*f)/100 for x,y in zip(a[1],b[1])];yaw=a[2]+angle*f;t=a[0]+(b[0]-a[0])*f
            loaded=carries(i,t);pose_token=tuple(round(v,4) for v in [*pos,yaw,loaded]);token=(previous_token,pose_token)
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
report=dict(success=not hits,source_probe_sha256=hashlib.sha256((OUT/'scene_probe.json').read_bytes()).hexdigest(),timeline_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    maximum_translation_step_m=.20,maximum_yaw_step_degrees=2,unique_forklift_poses_checked=checked,solid_geometry_count=len(obstacles),
    continuous_part_hulls=True,rotation_sweep_padding_m=.003,collision_count=len(hits),collisions=hits[:60],scope='Split chassis, carriage/tines and carried pallet swept footprints versus original rack/cargo/columns/charging/wall solids. Straight sweeps are exact; rotating sweeps include 3mm arc padding. Hollow D1 uses physical upright/brace parts below 3.9m; selected five replacement stacks excluded.')
(OUT/'static_actions_validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in report.items() if k!='collisions'}))
assert report['success'],'Inspect Saved/OrderReplay/static_actions_validation.json'
