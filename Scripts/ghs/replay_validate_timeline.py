"""Clock/cargo continuity and dynamic swept-footprint audit of exported replay."""
import bisect,json,math,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'Saved/OrderReplay'
data=json.loads((ROOT/'Content/GHSTwinUI/data/order-replay.json').read_text(encoding='utf8'));tracks=data['tracks'];duration=data['cycleDuration']
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
def obb(p,yaw,i):
    r=math.radians(yaw);c,s=math.cos(r),math.sin(r)
    # Loaded pallet reaches 2.5388m forward; include 2cm around the full body/load envelope.
    center=.65 if i<5 else 7.25425;hx=1.91 if i<5 else 7.45175;hy=.64 if i<5 else 1.515
    return (p[0]+center*c,p[1]+center*s,c,s,hx,hy)
def overlap(a,b):
    dx=b[0]-a[0];dy=b[1]-a[1]
    for ux,uy in [(a[2],a[3]),(-a[3],a[2]),(b[2],b[3]),(-b[3],b[2])]:
        ra=a[4]*abs(ux*a[2]+uy*a[3])+a[5]*abs(-ux*a[3]+uy*a[2]);rb=b[4]*abs(ux*b[2]+uy*b[3])+b[5]*abs(-ux*b[3]+uy*b[2])
        if abs(dx*ux+dy*uy)>=ra+rb:return False
    return True
def authorized_insertion(i,j,poses):
    if i>=5 or j!=5+[0,0,1,2,2][i]:return False
    p,yaw,_,door,_,_=poses[j];q=poses[i][0];r=math.radians(yaw)
    local_x=(q[0]-p[0])*math.cos(r)+(q[1]-p[1])*math.sin(r)
    # Chassis stays behind the rear door; only raised tines/cargo enter the open box.
    return door>.99 and local_x<=-1.235 and poses[i][2]>=1.14
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
failures=[];groups={};step=.1;previous=None;checked_pairs=0
for n in range(math.ceil(duration/step)):
    t=n*step;poses=[sample(i,t) for i in range(8)];boxes=[obb(p[0],p[1],i) for i,p in enumerate(poses)]
    sweep=[hull(corners(b)+(corners(previous[1][i]) if previous and poses[i][4] and previous[0][i][4] else [])) for i,b in enumerate(boxes)]
    for i in range(8):
        if not poses[i][4]:continue
        for j in range(i+1,8):
            if not poses[j][4] or (authorized_insertion(i,j,poses) and (not previous or authorized_insertion(i,j,previous[0]))):continue
            if math.hypot(boxes[i][0]-boxes[j][0],boxes[i][1]-boxes[j][1])>boxes[i][4]+boxes[j][4]+2:continue
            checked_pairs+=1
            if polygons_overlap(sweep[i],sweep[j]):
                k=(i,j);g=groups.setdefault(k,dict(pair=[tracks[i]['id'],tracks[j]['id']],first=t,last=t,samples=0));g['last']=t;g['samples']+=1
                if len(failures)<30:failures.append(dict(time=round(t,2),pair=g['pair'],positions=[poses[i][0],poses[j][0]]))
    previous=(poses,boxes)
continuity=[]
for i in range(8,18):
    for k in tracks[i]['keys'][1:-1]:
        before=sample(i,max(0,k[0]-1e-5));after=sample(i,k[0]);distance=math.dist(before[0],after[0]);angle=abs(math.remainder(after[1]-before[1],180))
        if distance>.002 or angle>.02:continuity.append(dict(id=tracks[i]['id'],time=k[0],distance=distance,angle=angle))
report=dict(success=not groups and not continuity,timeline_sha256=hashlib.sha256((ROOT/'Content/GHSTwinUI/data/order-replay.json').read_bytes()).hexdigest(),step_s=step,duration=duration,dynamic_collisions=list(groups.values()),first_collisions=failures,cargo_discontinuities=continuity,
            fixed_entities=len(tracks),cargo_entities=10,events=len(data['events']),continuous_interval_hulls=True,nearby_pair_sweeps_checked=checked_pairs,
            scope='All eight vehicle rigid envelopes, including carried cargo reach; 0.1s hulls with padded footprint. Own raised fork insertion into its open truck is intentionally allowed.')
(OUT/'timeline_validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in report.items() if k!='first_collisions'},ensure_ascii=False))
assert report['success'],'Inspect Saved/OrderReplay/timeline_validation.json'
