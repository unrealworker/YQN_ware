"""Clock/cargo continuity and dynamic swept-footprint audit of exported replay."""
import bisect,json,math,hashlib
from pathlib import Path
from replay_audit_sources import verify_sources
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'Saved/OrderReplay'
timeline_path=ROOT/'Content/GHSTwinUI/data/order-replay.json'
timeline_bytes=timeline_path.read_bytes()
timeline_hash=hashlib.sha256(timeline_bytes).hexdigest()
data=json.loads(timeline_bytes);tracks=data['tracks'];duration=data['cycleDuration']
_,source_hashes=verify_sources(ROOT,data)
assets=json.loads((ROOT/'SourceAssets/GHS/OrderReplay/replay_assets.json').read_text(encoding='utf8'))
mesh_bounds={m['name']:m['bounds_m'] for m in assets['meshes']}
times=[[k[0] for k in t['keys']] for t in tracks]
def sample(i,t):
    keys=tracks[i]['keys'];n=max(0,bisect.bisect_right(times[i],t)-1);a=keys[n];b=keys[min(n+1,len(keys)-1)]
    f=(t-a[0])/(b[0]-a[0]) if b[0]>a[0] and a[6]==b[6] else 0
    p=[(x+(y-x)*f)/100 for x,y in zip(a[1],b[1])];yaw=a[2]+math.remainder(b[2]-a[2],360)*f;lift=(a[3]+(b[3]-a[3])*f)/100
    door=a[4]+(b[4]-a[4])*f
    if a[6]>=0:
        parent=sample(a[6],t);r=math.radians(parent[1]);x,y,z=p
        p=[parent[0][0]+math.cos(r)*x-math.sin(r)*y,parent[0][1]+math.sin(r)*x+math.cos(r)*y,parent[0][2]+z+(parent[2] if a[6]<5 else 0)]
        yaw+=parent[1]
    return p,yaw,lift,door,a[5],a[6]
def box_at(position,yaw,x0,x1,y0,y1):
    r=math.radians(yaw); c,s=math.cos(r),math.sin(r)
    x,y=(x0+x1)/2,(y0+y1)/2
    return (position[0]+c*x-s*y,position[1]+s*x+c*y,c,s,(x1-x0)/2,(y1-y0)/2)

def envelope(key,pose,old=None,load=None):
    # Conservative rotational sagitta between the two poses used by the interval hull.
    margin=.002
    if old:
        r=16 if key>=5 else 2.7
        angle=abs(math.remainder(pose[1]-old[1],360))
        margin+=r*(1-math.cos(math.radians(angle)/2))
    p,yaw=pose[:2]
    if key<5:
        x_max,y_abs=2.20,.625
        if load:
            local=[truck_local(v,pose) for v in corners(load[0])]
            x_max=max(x_max,max(x for x,y in local))
            y_abs=max(y_abs,max(abs(y) for x,y in local))
        return box_at(p,yaw,-1.25-margin,x_max+margin,-y_abs-margin,y_abs+margin)
    # Hinged rear doors extend 1.23 m behind the origin when fully opened.
    return box_at(p,yaw,-1.28-margin,14.72+margin,-1.52-margin,1.52+margin)

def truck_local(point,truck):
    p,yaw=truck[:2]
    x,y=point[0]-p[0],point[1]-p[1]
    r=math.radians(yaw); c,s=math.cos(r),math.sin(r)
    return (x*c+y*s,-x*s+y*c)

def cargo_box(i,pose):
    bounds=mesh_bounds[tracks[i]['mesh'].split('/')[-1]]
    sx,sy,sz=tracks[i]['scale']
    return box_at(*pose[:2],bounds[0][0]*sx,bounds[0][1]*sx,bounds[1][0]*sy,bounds[1][1]*sy),pose[0][2]+bounds[2][0]*sz,pose[0][2]+bounds[2][1]*sz

def leaves(truck):
    p,yaw,_,opening=truck[:4]
    rad=math.radians(yaw)
    for side in (-1,1):
        hinge=(p[0]-side*1.22*math.sin(rad),p[1]+side*1.22*math.cos(rad))
        # FBX importer reflects the Blender Y axis. Left closes towards positive local Y.
        yield box_at(hinge,yaw-side*opening*100,-.0125,.0425,0 if side<0 else -1.22,1.22 if side<0 else 0)

def forklift_parts(i,pose,loads):
    p,yaw,lift=pose[:3]
    yield 'chassis',box_at(p,yaw,-1.25,1.02,-.625,.625),p[2],p[2]+2.337
    yield 'forks',box_at(p,yaw,1.02,2.20,-.363,.363),p[2]+lift+.043,p[2]+lift+.12
    if i in loads:
        yield ('load',*loads[i])

def truck_collision(i,j,now,before,loads,old_loads):
    truck,old_truck=now[j],before[j]
    # Only authorized docking allows fork tines and the pallet to cross the rear plane.
    # All other encounters use the closed body envelope and both moving hinges.
    same_truck=j==5+[0,0,1,2,2][i]
    docked=(same_truck and abs(math.remainder(truck[1]-old_truck[1],360))<.01 and math.dist(truck[0],old_truck[0])<.001
            and min(truck[3],old_truck[3])>.999)
    body=swept_box(box_at(truck[0],truck[1],-.198,14.706,-1.50,1.50),box_at(old_truck[0],old_truck[1],-.198,14.706,-1.50,1.50))
    doors=[swept_box(a,b) for a,b in zip(leaves(truck),leaves(old_truck))]
    old_parts={kind:(rect,lo,hi) for kind,rect,lo,hi in forklift_parts(i,before[i],old_loads)}
    for kind,rect,lo,hi in forklift_parts(i,now[i],loads):
        old_rect,old_lo,old_hi=old_parts.get(kind,(rect,lo,hi))
        vertices=swept_box(rect,old_rect)
        if max(hi,old_hi)>truck[0][2]+1.145 and min(lo,old_lo)<truck[0][2]+3.615:
            if any(polygons_overlap(vertices,door) for door in doors):return 'hinged door/'+kind
        if not polygons_overlap(vertices,body):continue
        if kind=='chassis' or not docked:return 'truck body/'+kind
        local=[truck_local(v,truck) for v in vertices]
        if max(x for x,y in local)<-.05 and min(lo,old_lo)>=truck[0][2]+1.13:continue
        if (max(abs(y) for x,y in local)>1.165 or max(x for x,y in local)>11.92 or
            min(lo,old_lo)<truck[0][2]+1.12999 or max(hi,old_hi)>truck[0][2]+3.62):
            return 'rear aperture/'+kind
    return None

def corners(b):
    x,y,c,s,hx,hy=b
    return [(x+c*dx-s*dy,y+s*dx+c*dy) for dx,dy in [(-hx,-hy),(hx,-hy),(hx,hy),(-hx,hy)]]
def hull(points):
    points=sorted(set(points))
    def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    low=[];high=[]
    for p in points:
        while len(low)>1 and cross(low[-2],low[-1],p)<=0:low.pop()
        low.append(p)
    for p in reversed(points):
        while len(high)>1 and cross(high[-2],high[-1],p)<=0:high.pop()
        high.append(p)
    return low[:-1]+high[:-1]
def polygons_overlap(a,b):
    for poly in [a,b]:
        for n,q in enumerate(poly):
            p=poly[n-1];ux,uy=p[1]-q[1],q[0]-p[0]
            aa=[x*ux+y*uy for x,y in a];bb=[x*ux+y*uy for x,y in b]
            if max(aa)<=min(bb) or max(bb)<=min(aa):return False
    return True
def swept_box(a,b):
    # The chord between rotated corners misses the arc by its sagitta. Sixteen metres
    # covers the longest corner-to-pivot distance in the truck, hinged panels and loads.
    cosine=max(-1.,min(1.,a[2]*b[2]+a[3]*b[3]))
    sagitta=16*(1-math.sqrt((1+cosine)/2))
    padded_a=(*a[:4],a[4]+sagitta,a[5]+sagitta)
    padded_b=(*b[:4],b[4]+sagitta,b[5]+sagitta)
    return hull(corners(padded_a)+corners(padded_b))

def check_aperture_examples():
    checks={}
    for name,lateral,bottom,opening,expected in (
        ('centered_open',0,1.14,1,None),
        ('side_intrusion',1.05,1.14,1,'hinged door/chassis'),
        ('fork_below_bed',0,.55,1,'rear aperture/forks'),
        ('closed_doors',0,1.14,0,'hinged door/forks'),
        ('above_opening',0,3.56,1,'rear aperture/forks')):
        fork=([-1.25,lateral,0],0,bottom,0,True,-1)
        truck=([0,0,0],0,0,opening,True,-1)
        poses=[fork]*5+[truck]*3
        loads={0:(box_at([.68,lateral],0,-.60,.60,-.51,.51),bottom,bottom+.988)}
        reason=truck_collision(0,5,poses,poses,loads,loads)
        assert reason==expected,(name,reason,expected)
        checks[name]=reason or 'clear'
    return checks

aperture_examples=check_aperture_examples()
failures=[];groups={};step=.1;previous=None;checked_pairs=0
truck_load_errors=[]
# Include every emitted key so ownership changes and hinged-door endpoints are checked exactly.
samples=sorted(set(min(n*step,duration) for n in range(math.ceil(duration/step)+1)).union(*times))
for t in samples:
    poses=[sample(i,t) for i in range(8)]
    old_poses=previous[0] if previous else poses
    loads={}
    for c in range(8,18):
        state=sample(c,t); owner=state[5]
        if 0<=owner<5:loads[owner]=cargo_box(c,state)
        elif owner>=5 and poses[owner][4]:
            rect,z0,z1=cargo_box(c,state)
            xy=[truck_local(v,poses[owner]) for v in corners(rect)]
            # Clearance and top surfaces use the authored 12m truck interior, in metres.
            if (min(x for x,y in xy)<-.00001 or max(x for x,y in xy)>11.92 or max(abs(y) for x,y in xy)>1.185
                or z0<poses[owner][0][2]+1.12999 or z1>poses[owner][0][2]+3.645):
                if len(truck_load_errors)<30:truck_load_errors.append(dict(id=tracks[c]['id'],time=t,owner=owner))
    boxes=[envelope(i,p,old_poses[i],loads.get(i)) for i,p in enumerate(poses)]
    old_loads=previous[2] if previous else loads
    sweep=[swept_box(b,previous[1][i]) if previous and poses[i][4] and old_poses[i][4] else corners(b) for i,b in enumerate(boxes)]
    for i in range(8):
        if not poses[i][4]:continue
        for j in range(i+1,8):
            if not poses[j][4]:continue
            if math.hypot(boxes[i][0]-boxes[j][0],boxes[i][1]-boxes[j][1])>boxes[i][4]+boxes[j][4]+2:continue
            checked_pairs+=1
            if not polygons_overlap(sweep[i],sweep[j]):continue
            reason='vehicle envelopes'
            if i<5<=j:
                reason=truck_collision(i,j,poses,old_poses,loads,old_loads)
                if reason is None:continue
            k=(i,j);g=groups.setdefault(k,dict(pair=[tracks[i]['id'],tracks[j]['id']],first=t,last=t,samples=0));g['last']=t;g['samples']+=1
            if len(failures)<30:failures.append(dict(time=round(t,2),pair=g['pair'],reason=reason,positions=[poses[i][0],poses[j][0]]))
    previous=poses,boxes,loads
continuity=[]
for i in range(8,18):
    for k in tracks[i]['keys'][1:-1]:
        before=sample(i,max(0,k[0]-1e-5));after=sample(i,k[0]);distance=math.dist(before[0],after[0]);angle=abs(math.remainder(after[1]-before[1],360))
        if distance>.002 or angle>.02:continuity.append(dict(id=tracks[i]['id'],time=k[0],distance=distance,angle=angle))
assert hashlib.sha256(timeline_path.read_bytes()).hexdigest()==timeline_hash, 'Timeline changed during audit'
report=dict(success=not groups and not continuity and not truck_load_errors,**source_hashes,truck_load_errors=truck_load_errors,timeline_sha256=timeline_hash,evaluated_times=len(samples),negativeChecks=aperture_examples,step_s=step,duration=duration,dynamic_collisions=list(groups.values()),first_collisions=failures,cargo_discontinuities=continuity,
            fixed_entities=len(tracks),cargo_entities=10,events=len(data['events']),continuous_interval_hulls=True,nearby_pair_sweeps_checked=checked_pairs,
            scope='All eight vehicle rigid envelopes, including carried cargo reach; 0.1s hulls with padded footprint. Forks and attached cargo are tested against both hinged doors, truck floor, sides, rear aperture and roof.')
(OUT/'timeline_validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in report.items() if k!='first_collisions'},ensure_ascii=False))
assert report['success'],'Inspect Saved/OrderReplay/timeline_validation.json'
