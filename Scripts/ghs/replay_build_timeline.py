"""Deterministic full outbound + visible replenishment cycle for 5/3/10 entities."""
import argparse,json,math,hashlib,bisect
from pathlib import Path
from replay_motion_profile import build_route_profile
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'Saved/OrderReplay'
plan=json.loads((OUT/'routes_plan.json').read_text());truck_plan=json.loads((OUT/'truck_routes.json').read_text())
assert plan['success'] and truck_plan['success']
probe_hash = hashlib.sha256((OUT/'scene_probe.json').read_bytes()).hexdigest()
assert plan['source_probe_sha256'] == truck_plan['sources']['Saved/OrderReplay/scene_probe.json'] == probe_hash
assert plan['sceneBindingsSha256'] == hashlib.sha256((ROOT/'Content/GHSTwinUI/data/scene-bindings.json').read_bytes()).hexdigest()
ASSET='/Game/GHSOrderReplay/Meshes/SM_Replay_'
CARRY_X=1.93;CARRY_Z=-.0204;GROUND_Z=.005
# The four-way blue floor pallet and the original wooden rack pallet have different fork pockets.
RACK_CARRY_Z=.006
cargo_tops={m['name']:m['bounds_m'][2][1] for m in json.loads(
    (ROOT/'SourceAssets/GHS/OrderReplay/replay_assets.json').read_bytes())['meshes']}
events=[];tracks=[]
def cm(p):return [round(x*100,6) for x in p]
def event(t,i,kind,title):events.append(dict(id='EV-%03d'%len(events),time=round(t,6),deviceId=tracks[i]['id'],kind=kind,type=kind,text=title,title=title))
def key(t,pos,yaw,lift=0,door=0,visible=True,owner=-1,status='待命'):
    return [round(t,6),cm(pos),round(yaw,6),round(lift*100,6),door,visible,owner,status,'','']
class Motion:
    def __init__(self,i,position,yaw):self.i=i;self.t=0;self.p=list(position);self.yaw=yaw;self.lift=0;self.door=0;self.visible=True;self.status='待命';self.emit()
    def emit(self):
        row=key(self.t,self.p,self.yaw,self.lift,self.door,self.visible,status=self.status);keys=tracks[self.i]['keys']
        if keys and abs(keys[-1][0]-self.t)<1e-5:keys[-1]=row
        else:keys.append(row)
    def wait(self,d,status=None):
        if status:self.status=status;self.emit()
        self.t+=max(0,d);self.emit()
    def until(self,t,status=None):self.wait(max(0,t-self.t),status)
    def tween(self,d,position=None,yaw=None,lift=None,door=None,status=None):
        if status:self.status=status;self.emit()
        a=list(self.p);b=list(position if position is not None else a);ay=self.yaw;by=ay+math.remainder((yaw if yaw is not None else ay)-ay,360);al=self.lift;bl=lift if lift is not None else al;ad=self.door;bd=door if door is not None else ad
        n=max(2,math.ceil(d*6));t=self.t
        for k in range(1,n+1):
            q=k/n;v=q*q*(3-2*q);self.t=t+d*q;self.p=[x+(y-x)*v for x,y in zip(a,b)];self.yaw=ay+(by-ay)*v;self.lift=al+(bl-al)*v;self.door=ad+(bd-ad)*v;self.emit()
    def route(self,path,speed=2.6,fault=False,status='运送托盘',carrying=False):
        if carrying:
            # The route guides the loaded vehicle envelope. Retain axle clearance at bends;
            # taper the offset over the straight four-metre pickup/dock approaches.
            distances=[0.]
            for a,b in zip(path,path[1:]):distances.append(distances[-1]+math.dist(a[:3],b[:3]))
            adjusted=[]
            for j,p in enumerate(path):
                a,b=path[max(0,j-1)],path[min(len(path)-1,j+1)];yaw=math.atan2(b[1]-a[1],b[0]-a[0]);offset=.35*min(1.,distances[j]/4.,(distances[-1]-distances[j])/4.)
                adjusted.append([p[0]-math.cos(yaw)*offset,p[1]-math.sin(yaw)*offset,p[2],math.degrees(yaw)])
            path=adjusted
        self.status=status;self.emit()
        if self.i<5:
            # Bake continuous steering at the original constant driving speed.
            # Absolute keys keep playback, scrubbing and reverse seeks deterministic.
            directed=[]
            for j,p in enumerate(path):
                a,b=path[max(0,j-1)],path[min(len(path)-1,j+1)]
                yaw=p[3] if len(p)>3 else math.degrees(math.atan2(b[1]-a[1],b[0]-a[0]))
                directed.append([*p[:3],yaw])
            split=len(directed)//3 if fault else len(directed)-1
            parts=[directed[:split+1]]+([directed[split:]] if fault else [])
            self.tween(3,yaw=directed[0][3],status=status)
            for part_index,part in enumerate(parts):
                frames=build_route_profile(part,speed);start=self.t
                for elapsed,position,yaw in frames[1:]:
                    self.t=start+elapsed;self.p=list(position);self.yaw=yaw;self.emit()
                if fault and part_index==0:
                    event(self.t,self.i,'fault','人工叉车 03 · 电机过热，暂停作业')
                    self.wait(45,'故障停机')
                    event(self.t,self.i,'recovery','人工叉车 03 · 故障排除，恢复作业')
                    self.status=status;self.emit()
            return
        for j,p in enumerate(path):
            if len(p)>3:yaw=p[3]
            else:
                a,b=path[max(0,j-1)],path[min(len(path)-1,j+1)];yaw=math.degrees(math.atan2(b[1]-a[1],b[0]-a[0]))
            if j==0:
                self.tween(3,yaw=yaw,status=status)
                continue
            dist=math.dist(self.p,p[:3]);self.t+=max(.001,dist/speed);self.p=list(p[:3]);self.yaw=yaw;self.emit()
            if fault and j==len(path)//3:
                event(self.t,self.i,'fault','人工叉车 03 · 电机过热，暂停作业');self.wait(45,'故障停机');event(self.t,self.i,'recovery','人工叉车 03 · 故障排除，恢复作业');self.status=status;self.emit()

for n,r in enumerate(plan['forklifts']):tracks.append(dict(id=r['id'],name='人工叉车 %02d'%(n+1),kind='forklift',mesh=ASSET+'ForkliftBody',scale=[1,1,1],keys=[],route=[cm(x) for x in r['route_m']]))
for t in truck_plan['trucks']:tracks.append(dict(id=t['id'],name='装卸卡车 '+t['id'][-1],kind='truck',mesh=ASSET+'TruckBody',scale=[1,1,1],keys=[],route=[cm(x[:3]) for x in t['points_m'][::8]]))
for n,r in enumerate(plan['forklifts']):
    for load in r['loads']:
        tracks.append(dict(id='REPLAY-CARGO-%02d'%(len(tracks)-7),name=load['source_name']+'托盘',
            kind='cargo',mesh=ASSET+load['mesh'],scale=load['scale'],
            keys=[key(0,load['position_m'],load['source_yaw'])],route=[]))
forks=[Motion(i,r['staging_m'],r['yaw']) for i,r in enumerate(plan['forklifts'])]
trucks=[Motion(5+i,t['points_m'][0][:3],t['points_m'][0][3]) for i,t in enumerate(truck_plan['trucks'])]
for m in trucks:m.door=1;m.status='等待装车';m.emit()
fork_truck=[0,0,1,2,2]
cargo_frames={};drop_times={}

def ownership(cargo,t,owner,pos,yaw):
    tracks[cargo]['keys'].append(key(t,pos,yaw,owner=owner,status='已装载' if owner>=0 else '已落托'))

def change_pallet_entry(i, cargo, outbound):
    """Set the pallet down while the forklift travels to an adjacent entry face."""
    vehicle = forks[i]
    south = plan['forklifts'][i]['route_m'][-1][:3]
    pad = [south[0], south[1]+4.5, .012]
    west = [pad[0]-4.5, pad[1], GROUND_Z]
    corner = [west[0], south[1], GROUND_Z]
    working_lift = pad[2]-GROUND_Z-CARRY_Z

    def go_around(start_at_south):
        heading, next_heading, end, end_heading = (180,90,west,0) if start_at_south else (-90,0,south,90)
        for yaw, point in ((heading,corner),(next_heading,end)):
            vehicle.tween(2,yaw=yaw,status='调整叉取方向')
            vehicle.tween(3,position=point,status='绕行至托盘侧面')
        vehicle.tween(2,yaw=end_heading,status='对准托盘叉孔')

    def transfer(pickup, heading):
        stage = west if heading == 0 else south
        reach = [pad[0]-CARRY_X if heading==0 else pad[0],
                 pad[1] if heading==0 else pad[1]-CARRY_X,GROUND_Z]
        vehicle.tween(2,yaw=heading,lift=working_lift if pickup else working_lift+.12,status='中转区对位')
        vehicle.tween(3,position=reach,status='侧面插叉' if pickup else '中转区送托')
        if pickup:
            ownership(cargo,vehicle.t,i,[CARRY_X,0,CARRY_Z],-heading)
            event(vehicle.t,i,'transfer',tracks[i]['name']+' · 从转运位重新插叉取托')
            vehicle.tween(2,lift=working_lift+.12,status='叉起中转托盘')
        else:
            vehicle.tween(2,lift=working_lift,status='中转区暂放托盘')
            ownership(cargo,vehicle.t,-1,pad,0)
            event(vehicle.t,i,'transfer',tracks[i]['name']+' · 托盘暂放转运位')
        vehicle.tween(3,position=stage,status='退出中转托位')

    if not outbound:
        go_around(True)
    transfer(False,90 if outbound else 0)
    go_around(outbound)
    transfer(True,0 if outbound else 90)
    if outbound:
        go_around(False)
    vehicle.tween(2,lift=.25,status='降低运输高度')

def truck_slot(i,j):
    # Pallets enter lengthwise after regripping to fit two across the rear door.
    height=1.13
    if i in (1,4):
        base_load=plan['forklifts'][0 if i==1 else 3]['loads'][j]
        height+=cargo_tops['SM_Replay_'+base_load['mesh']]*base_load['scale'][2]
    return [.68,(-.54 if j==0 else .54),height]

def approach(i,j):
    r=plan['forklifts'][i];tx,ty,tz=r['truck_position_m'];slot=truck_slot(i,j)
    return [tx-slot[1],ty-2.85,GROUND_Z],[tx-slot[1],ty+slot[0]-CARRY_X,GROUND_Z]

def outbound(i,start):
    r=plan['forklifts'][i];m=forks[i];m.until(start,'等待作业');truck=fork_truck[i]
    for j,load in enumerate(r['loads']):
        cyaw=load['source_yaw']-r['yaw']
        place='货架' if load['kind']=='rack' else '地堆'
        carry_z=RACK_CARRY_Z if load['kind']=='rack' else CARRY_Z
        if i==3 and j==1:m.wait(75,'交叉通道让行')
        if i==4 and j==1:m.wait(60,'交叉通道让行')
        cargo=8+i*2+j;sourcebase=load['position_m'][2];m.tween(3,yaw=r['yaw'],lift=sourcebase-GROUND_Z-carry_z,status='对位取货')
        m.tween(3,position=load['pickup_origin_m'],status='货叉插入'+place+'托盘');ownership(cargo,m.t,i,[CARRY_X,0,carry_z],cyaw)
        m.tween(2,lift=sourcebase-GROUND_Z-carry_z+.12,status='抬升托盘');event(m.t,i,'pickup',tracks[i]['name']+' · '+load['source_name']+' · 取货完成')
        m.tween(4,position=load['staging_m'],status='倒车退出'+place);m.tween(3,lift=.25,status='降低运输高度')
        m.route(load['route_m'],fault=(i==2 and j==0),carrying=True)
        if load['kind']=='floor':change_pallet_entry(i,cargo,True)
        pre,truck_reach=approach(i,j);m.tween(3,yaw=90,status='月台对位')
        m.tween(4,position=pre,status='驶入装卸位');slot=truck_slot(i,j);lift=r['truck_position_m'][2]+slot[2]-GROUND_Z-carry_z
        m.tween(4,lift=lift+.12,status='抬叉至车厢');m.tween(3,position=truck_reach,status='送入车厢');m.tween(2,lift=lift,status='平稳落托')
        ownership(cargo,m.t,5+truck,slot,0);drop_times[(i,j)]=m.t;event(m.t,i,'dropoff',tracks[i]['name']+' · 放货完成，装卸卡车 '+chr(65+truck))
        m.tween(4,position=pre,status='倒车退出车厢');m.tween(3,lift=.15,status='回收货叉')
        if i==4 and j==1:m.until(out_ends[1]+12,'交叉通道让行')
        m.tween(4,position=r['route_m'][-1],status='退出月台')
        m.route(list(reversed(r['loads'][1-j]['route_m'])),3.2,status='返回'+place);m.tween(3,yaw=r['yaw'],status='等待下一托')
    return m.t

# Shared dock resources are serialized. Independent long-distance tasks overlap.
out_ends={}
for i,start in [(0,0),(2,24),(3,66)]:out_ends[i]=outbound(i,start)
out_ends[1]=outbound(1,out_ends[0]+8)
out_ends[4]=outbound(4,out_ends[3]+70)
ready=[]
for ti,(m,r) in enumerate(zip(trucks,truck_plan['trucks'])):
    complete=max(out_ends[i] for i in range(5) if fork_truck[i]==ti)+8
    m.until(complete,'等待叉车退出');m.tween(3,door=0,status='关闭车门');event(m.t,5+ti,'departure',tracks[5+ti]['name']+' · 装满离场')
    m.route(r['points_m'],5.0,status='驶离园区');m.visible=False;m.emit();m.wait(20,'场外换班 · 测试补给车')
    # The inactive pool slot is repositioned only while outside the visible scene.
    arrival=r['arrival'];m.p=list(arrival['points_m'][0][:3]);m.yaw=arrival['points_m'][0][3];m.emit();m.wait(.01);m.visible=True;m.status='测试补给车 · 返回园区';m.emit()
    reverse=arrival['reverse_start_distance_m'];paused=False
    for j,p in enumerate(arrival['points_m']):
        if j==0:continue
        reversing=arrival['distances_m'][j]>=reverse
        if reversing and not paused:m.wait(3,'停车换向');paused=True
        m.t+=max(.001,math.dist(m.p,p[:3])/(1.8 if reversing else 5.0));m.p=list(p[:3]);m.yaw=p[3];m.status='倒车入泊' if reversing else '测试补给车 · 返回园区';m.emit()
    m.tween(3,door=1,status='开启车门');ready.append(m.t);event(m.t,5+ti,'replenishment',tracks[5+ti]['name']+' · 补给到位，开始卸回原库位')

def inbound(i,start):
    r=plan['forklifts'][i];m=forks[i];m.until(start,'等待补给车辆');truck=fork_truck[i]
    departure=r['loads'][0]['route_m']
    for j in [1,0]:
        load=r['loads'][j];place='货架' if load['kind']=='rack' else '地堆'
        carry_z=RACK_CARRY_Z if load['kind']=='rack' else CARRY_Z
        cargo=8+i*2+j;m.route(departure,3.2,status='前往补给月台');pre,truck_reach=approach(i,j);m.tween(3,yaw=90,status='补给车对位')
        m.tween(4,position=pre,status='驶入装卸位');slot=truck_slot(i,j);lift=r['truck_position_m'][2]+slot[2]-GROUND_Z-carry_z
        m.tween(4,lift=lift,status='货叉对准托盘');m.tween(3,position=truck_reach,status='插入补给托盘');ownership(cargo,m.t,i,[CARRY_X,0,carry_z],0)
        m.tween(2,lift=lift+.12,status='抬起补给托盘');event(m.t,i,'pickup',tracks[i]['name']+' · 补给取货完成')
        m.tween(4,position=pre,status='倒车退出车厢');m.tween(3,lift=.25,status='降低运输高度');m.tween(4,position=r['route_m'][-1],status='退出月台')
        if load['kind']=='floor':change_pallet_entry(i,cargo,False)
        m.route(list(reversed(load['route_m'])),2.6,status='补给运回'+place,carrying=True);m.tween(3,yaw=r['yaw'],status='原货位对位')
        z=load['position_m'][2];m.tween(3,lift=z-GROUND_Z-carry_z+.12,status='对准原托位高度');m.tween(3,position=load['pickup_origin_m'],status='送入原'+place)
        m.tween(2,lift=z-GROUND_Z-carry_z,status='平稳落托');ownership(cargo,m.t,-1,load['position_m'],load['source_yaw']);event(m.t,i,'dropoff',tracks[i]['name']+' · '+load['source_name']+' · 托盘补给完成')
        m.tween(4,position=load['staging_m'],status='倒车退出'+place);m.tween(3,lift=0,status='等待下一循环')
        departure=load['route_m']
    return m.t

# Unload stacked upper pallets first, then base pallets. No cargo ever appears by reset.
base=max(max(out_ends.values()),max(ready))+12
in_ends={2:inbound(2,base+24),1:inbound(1,base),4:inbound(4,base+48)}
in_ends[0]=inbound(0,in_ends[1]+8);in_ends[3]=inbound(3,max(in_ends[4],in_ends[2])+8)
duration=math.ceil(max(in_ends.values())+20)
for i,m in enumerate(forks):
    m.until(duration-3,'循环完成');m.tween(3,yaw=plan['forklifts'][i]['yaw'],lift=0,status='待命')
    m.yaw=plan['forklifts'][i]['yaw'];m.emit()
for i,m in enumerate(trucks):
    m.until(duration-3,'补给卸货完成');m.tween(3,door=1,status='等待装车')
for t in tracks[8:]:
    first=t['keys'][0];last=list(first);last[0]=duration;t['keys'].append(last)
for t in tracks:
    assert all(a[0]<b[0] for a,b in zip(t['keys'],t['keys'][1:])),t['id']
    assert t['keys'][0][1:7]==t['keys'][-1][1:7],(t['id'],t['keys'][0],t['keys'][-1])
events.sort(key=lambda e:e['time'])
data=dict(version=2,testData=True,cycleDuration=duration,tracks=tracks,events=events,sourceInstances=plan['source_instances'],
    doors=[dict(position=d['transform']['position_cm'],yaw=d['transform']['rotation_deg'][1]) for d in plan['doors']],
    provenance=dict(sceneProbe=plan['source_probe_sha256'],sceneBindingsSha256=plan['sceneBindingsSha256'],
                    mapSha256=plan['mapSha256'],inventoryBindingsSha256=plan['inventoryBindingsSha256'],
                    inventoryIndexSha256=plan['inventoryIndexSha256'],truckRoutes=hashlib.sha256((OUT/'truck_routes.json').read_bytes()).hexdigest()),
    notes=['Fixed 5 forklifts + 3 trucks + 6 floor pallets + 4 occupied rack slots','Cargo returns visibly on test replenishment trucks, no visible cycle reset'])
parser=argparse.ArgumentParser()
parser.add_argument('--output',type=Path,default=ROOT/'Content/GHSTwinUI/data/order-replay.json')
dest=parser.parse_args().output
dest.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf8')
(OUT/'timeline_summary.json').write_text(json.dumps(dict(cycleDuration=duration,outboundEnd=out_ends,truckReady=ready,inboundEnd=in_ends,events=len(events),keys={t['id']:len(t['keys']) for t in tracks},fileBytes=dest.stat().st_size),indent=2),encoding='utf8')
print(json.dumps(dict(duration=duration,events=len(events),outboundEnd=out_ends,truckReady=ready,inboundEnd=in_ends,bytes=dest.stat().st_size)))
