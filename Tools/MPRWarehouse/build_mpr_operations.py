"""Low-poly CAD-positioned operating equipment, split into reusable HISM modules."""
from pathlib import Path
import sys,json,math,collections,argparse
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).parent))
from mpr_blender_common import Geometry
from mpr_cad_semantics import DRAFTING_SYMBOLS,turn_requires_reflection,reflected_mesh_roles,covered_drive_detail
from mpr_conveyor_detail_geometry import add_cad_detail_meshes
from mpr_cad_feed_geometry import add_feed_meshes
parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'SourceAssets/MPR/operations')
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
OUT=args.output;OUT.mkdir(parents=True,exist_ok=True)
layout=json.loads((ROOT/'SourceAssets/MPR/mpr_cad_layout.json').read_text(encoding='utf8'))
feed_evidence=json.loads((ROOT/'SourceAssets/MPR/operations/cad_loose_feed_geometry.json').read_text(encoding='utf8'))
loose_feeds=feed_evidence['feeds']
evidence={x['block']:x for x in json.loads((ROOT/'SourceAssets/MPR/mpr_cad_operations_lines.json').read_text(encoding='utf8'))} if (ROOT/'SourceAssets/MPR/mpr_cad_operations_lines.json').exists() else {}
g=Geometry();instances=[];omitted=[];merged_drive_units=[]
cad_details=add_cad_detail_meshes(g)
feed_specs=add_feed_meshes(g,feed_evidence)
def box(n,r,p,s):g.box(n,r,p,s)
def legset(n,w,l,z=.87):
 for x in (-w*.4,w*.4):
  for y in (-l*.39,l*.39):
   box(n,'Metal',(x,y,z/2),(.05,.05,z));box(n,'Rubber',(x,y,.025),(.12,.12,.05))
 for y in (-l*.39,l*.39):box(n,'Cobalt',(0,y,.22),(w*.8,.035,.035))
def cylinder_x(n,center,r,length,segments=8):
 vs=[(center[0]+x*length/2,center[1]+r*math.cos(2*math.pi*i/segments),center[2]+r*math.sin(2*math.pi*i/segments)) for x in (-1,1) for i in range(segments)]
 fs=[tuple(range(segments-1,-1,-1)),tuple(range(segments,segments*2))]+[(i,(i+1)%segments,(i+1)%segments+segments,i+segments) for i in range(segments)]
 g.mesh(n,'Metal',vs,fs)
def rollers(n,w,l,z=1):
 for x in (-w/2+.035,w/2-.035):box(n,'Cobalt',(x,0,z-.07),(.07,l,.14))
 count=max(6,round(l/.12))
 for i in range(count):cylinder_x(n,(0,-l/2+.08+(l-.16)*i/(count-1),z),.035,w-.14,6)
 legset(n,w,l,z-.1)
conv='SM_MPR_Conveyor2m';rollers(conv,1,2)
table='SM_MPR_WorkTable';legset(table,1,1.2,.83);box(table,'Porcelain',(0,0,.88),(1,1.2,.1));box(table,'Cobalt',(0,.43,1.12),(.04,.04,.43));box(table,'Charcoal',(0,.43,1.35),(.38,.055,.27));box(table,'SoftBlue',(0,.397,1.35),(.32,.015,.21))
output='SM_MPR_SorterOutput';legset(output,.415,2.38,.76)
box(output,'Metal',(0,0,.82),(.415,2.38,.055));box(output,'Rubber',(0,0,.857),(.35,2.30,.02))
for x in (-.19,.19):box(output,'Cobalt',(x,0,.93),(.035,2.38,.12))
sealer='SM_MPR_CartonSealer';rollers(sealer,1.23211,1.9504,.85)
for x in (-.43,.43):box(sealer,'Cobalt',(x,0,1.25),(.10,.11,.95))
box(sealer,'Porcelain',(0,0,1.64),(.96,.37,.20));box(sealer,'Charcoal',(0,-.02,1.52),(.22,.48,.06));box(sealer,'Cobalt',(.48,.17,1.15),(.19,.24,.30));box(sealer,'SoftBlue',(.585,.17,1.20),(.01,.14,.09))
support='SM_MPR_ConveyorSupport';legset(support,1.295,.2,.9);box(support,'Metal',(0,0,.92),(1.295,.2,.08))
scan='SM_MPR_ScanGate';rollers(scan,.8,1.405,.95)
for x in (-.36,.36):box(scan,'Porcelain',(x,0,1.4),(.065,.065,1.0))
box(scan,'Cobalt',(0,0,1.88),(.8,.13,.12));box(scan,'Charcoal',(0,-.08,1.82),(.13,.1,.08))
def add(mesh,p,yaw=0,scale=(1,1,1),source=None,kind=''):
 instances.append({'mesh':mesh,'position_m':[round(v,5) for v in p],'rotation_deg':round(yaw,6),'scale':[round(v,6) for v in scale],'source_handles':source or [],'kind':kind,'height_basis':'estimated appearance; measured CAD XY footprint preserved','collision':False,'tick':False})
def fromcad(v,mesh,native):
 add(mesh,[*v['position_m'],0],v['rotation_deg'],(v['size_m'][0]/native[0],v['size_m'][1]/native[1],1),v['source_handles'],v['kind'])
# Straight conveyors are divided into <=2m segments, preserving endpoints and orientation.
def conveyor(v):
 w,l=v['size_m'];yaw=v['rotation_deg'];x,y=v['position_m']
 if w>l:w,l=l,w;yaw-=90
 count=math.ceil(l/2);length=l/count;rad=math.radians(yaw)
 for i in range(count):
  offset=-l/2+(i+.5)*length
  add(conv,[x-math.sin(rad)*offset,y+math.cos(rad)*offset,0],yaw,(w,length/2,1),v['source_handles'],'conveyor_run')
for v in layout['conveyor_runs']:conveyor(v)
for v in layout['equipment']:
 k=v['kind'];w,l=v['size_m'];n=v['block']
 if n in DRAFTING_SYMBOLS:continue
 drive=covered_drive_detail(v,layout['conveyor_runs'])
 if drive:
  merged_drive_units.append(drive);continue
 if n in cad_details:
  detail=cad_details[n];fromcad(v,detail['mesh'],detail['native_size_m'])
 elif k=='workstation':fromcad(v,table,(1,1.2))
 elif k=='sorter_output':fromcad(v,output,(.415,2.38))
 elif k=='carton_sealer':fromcad(v,sealer,(1.23211,1.9504))
 elif k=='machine_support' and min(w,l)<.3:
  vv=dict(v);vv['size_m']=[max(w,l),min(w,l)];vv['rotation_deg']=v['rotation_deg']+(90 if l>w else 0);fromcad(vv,support,(1.295,.2))
 elif n.startswith('*U13') and abs(w-.55)<.02 and abs(l-1.1)<.02:
  spec=feed_specs['__terminal__'];fromcad(v,spec['mesh'],spec['native_size_m'])
  instances[-1]['height_basis']='H:1500 feed-line continuation; endpoint assignment is display interpretation'
 elif n=='扫码1200':fromcad(v,scan,(.8,1.405))
 elif n=='GIE2':fromcad(v,table,(1,1.2))
 elif n in ('*U951','*U953','*U949','*U950'):fromcad(v,table,(1,1.2))
 elif n in ('*U1656','*U258','*U259','*U1198','物流猫摆轮分拣机M5A10','BAILUN 202506040917'):
  conveyor(v)
 elif n in ('*U1368','*U1369'):fromcad(v,scan,(.8,1.405))
 elif n=='自动开箱机':fromcad(v,sealer,(1.23211,1.9504))
 else:omitted.append({'id':v['id'],'block':n,'kind':k,'reason':'Complex/multi-part equipment preserved as CAD trace; no invented solid bounding-box machine','position_m':v['position_m'],'size_m':v['size_m']})
# Quarter turns from actual CAD arcs; reuse one local mesh for each CAD block.
def make_turn(n):
 ev=evidence[n];it=ev['placement'];arcs=ev['arcs'];clusters=collections.defaultdict(list)
 for a in arcs:clusters[tuple(round(v,2) for v in a['center'])].append(a)
 if not clusters:return None
 group=max(clusters.values(),key=len);radii=[a['radius_m'] for a in group];r0,r1=min(radii),max(radii)
 if r1-r0<.25:return None
 arc=group[0]
 cx,cy=arc['center'];base=it['position_m'];yaw=math.radians(-it['rotation_deg']);cc,ss=math.cos(yaw),math.sin(yaw)
 if n in ('*U255','*U74','*U256'):r0,r1=1.07,2.33
 # CAD turns are fragmented into 15/30-degree arcs. Merge angular coverage;
 # taking only the longest primitive would leave gaps in the 90-degree turn.
 angles=sorted(set(round(math.atan2(p[1]-cy,p[0]-cx)%(2*math.pi),7) for a in group for p in a['points']))
 gaps=[((angles[(i+1)%len(angles)]-angles[i])%(2*math.pi),i) for i in range(len(angles))]
 gap,index=max(gaps);start=angles[(index+1)%len(angles)];span=2*math.pi-gap
 assert 1.45<span<1.70,(n,span)
 def local(p):
  dx,dy=p[0]-base[0],p[1]-base[1];return (cc*dx-ss*dy,ss*dx+cc*dy)
 rim=[]
 for i in range(17):
  angle=start+span*i/16;dx,dy=math.cos(angle),math.sin(angle)
  rim.append((local((cx+dx*r0,cy+dy*r0)),local((cx+dx*r1,cy+dy*r1))))
 mesh='SM_MPR_Turn_'+''.join(c if c.isalnum() else '_' for c in n)
 for (a,b),(c,d) in zip(rim,rim[1:]):
  g.mesh(mesh,'Rubber',[(a[0],a[1],1),(b[0],b[1],1),(d[0],d[1],1),(c[0],c[1],1)],[(0,1,2,3)])
  g.segment(mesh,'Cobalt',a,c,.055,.99,.18);g.segment(mesh,'Cobalt',b,d,.055,.99,.18)
 for i in (0,len(rim)//2,len(rim)-1):
  for p in rim[i]:box(mesh,'Metal',(p[0],p[1],.45),(.06,.06,.9))
 return mesh
handled=set();curves={}
for row in list(omitted):
 n=row['block']
 if n not in ('*U255','*U74','*U256','*U33','e3'):continue
 if n not in curves:curves[n]=make_turn(n)
 if curves[n]:
  v=next(x for x in layout['equipment'] if x['id']==row['id'])
  reference=next(x for x in layout['equipment'] if x['id']==evidence[n]['placement']['id'])
  if n=='*U33':assert 'planar_handedness' in reference and 'planar_handedness' in v,'U33 CAD reflection evidence is required'
  mesh=curves[n]
  if turn_requires_reflection(reference,v):
   mesh=curves[n]+'_Reflected'
   if mesh not in g.data:g.data[mesh]=reflected_mesh_roles(g.data[curves[n]])
  add(mesh,[*v['position_m'],0],v['rotation_deg'],source=v['source_handles'],kind='cad_arc_conveyor');handled.add(row['id'])
# Empty CAD rectangles are operating-zone reservations, not solid machinery.
zone_names={'*U1073','*U1072','*U1294','*U1295','*U1324','*U1114','*U1115','*U1116','*U1117','*U1528','*U1326'}
zones=[];additional_pallets=[];merged_supports=[]
for v in layout['equipment']:
 n=v['block'];ev=evidence.get(n)
 if n in zone_names:
  zones.append({'source_handles':v['source_handles'],'position_m':v['position_m'],'size_m':v['size_m'],'classification':'CAD unfilled operating/parking zone; keep clear'});handled.add(v['id'])
 if n in ('*U1328','*U1337','*U1339','*U1341') and ev:
  # 3x4 crossed rectangles are individual pallet positions, not an equipment cage.
  for ps in ev['rectangles']:
   lo=[min(p[i] for p in ps) for i in (0,1)];hi=[max(p[i] for p in ps) for i in (0,1)]
   if .7<hi[0]-lo[0]<1.5 and .7<hi[1]-lo[1]<1.6:
    additional_pallets.append({'position_m':[(lo[0]+hi[0])/2,(lo[1]+hi[1])/2],'rotation_deg':0,'source_handles':v['source_handles']})
  handled.add(v['id'])
 if n in ('*U952','*U372','*U1348','*U1523','*U1527'):
  # Open packing stations, seat group outlines; only actual worktable modules.
  if n=='*U1348':
   for off in (-3.7,0,3.7):add(table,[v['position_m'][0]+off,v['position_m'][1],0],source=v['source_handles'],kind='pack_worktable')
  elif n in ('*U952','*U372'):fromcad(v,table,(1,1.2))
  handled.add(v['id'])
 if n in ('供包爬坡','供包爬坡机'):
  # Reuse the GHS inclined conveyor; adjust measured run footprint, retaining its slope.
  add('/Game/GHSDigitalTwin/Meshes/SM_GHS_Shared_Conveyor',[*v['position_m'],.021],v['rotation_deg'],(v['size_m'][0]/1.054911,v['size_m'][1]/3.026911,1),v['source_handles'],'reused_inclined_conveyor');handled.add(v['id'])
 if n in ('0.0393700787401575','13131'):
  zones.append({'source_handles':v['source_handles'],'classification':'Four-view equipment illustration; not four physical machines'});handled.add(v['id'])
 if n=='作业工人':handled.add(v['id'])
 if n=='zw$9FA9':
  merged_supports.append({'source_handles':v['source_handles'],'reason':'Three angled turn-support frames are represented by the legs of the coincident CAD arc-conveyor module; prevent duplicate support meshes'});handled.add(v['id'])
# Measured complex feeder layout: pair long parallel belt edges, preserving open floor.
for n in ('dsefasd','入库摆轮05'):
 ev=evidence.get(n)
 if not ev:continue
 v=next(x for x in layout['equipment'] if x['block']==n);segs=[]
 for line in ev['long_lines']:
  a,b=line['a'],line['b'];axis=0 if abs(a[1]-b[1])<.01 else 1 if abs(a[0]-b[0])<.01 else None
  if axis is not None:segs.append((axis,(a[1-axis]+b[1-axis])/2,min(a[axis],b[axis]),max(a[axis],b[axis])))
 candidates=[]
 for i,s in enumerate(segs):
  for t in segs[i+1:]:
   if s[0]!=t[0]:continue
   width=abs(s[1]-t[1]);lo=max(s[2],t[2]);hi=min(s[3],t[3])
   if .55<=width<=1.32 and hi-lo>1.8:candidates.append((hi-lo,s[0],(s[1]+t[1])/2,lo,hi,width))
 accepted=[]
 for length,axis,fixed,lo,hi,width in sorted(candidates,reverse=True):
  if any(axis==s[1] and abs(fixed-s[2])<.65 and min(hi,s[4])-max(lo,s[3])>.5 for s in accepted):continue
  accepted.append((length,axis,fixed,lo,hi,width))
  pos=[(lo+hi)/2,fixed] if axis==0 else [fixed,(lo+hi)/2]
  conveyor({'position_m':pos,'size_m':[width,length],'rotation_deg':-90 if axis==0 else 0,'source_handles':v['source_handles']})
 if accepted:handled.add(v['id'])
# Main feeds of the three inspected sorter groups (the branch modules are separate).
for n,x,y,length,width in [('14234123',-104.30,-13.00301,36.1,1.26),('480',-111.52,16.36737,8.1,1.06)]:
 v=next(x for x in layout['equipment'] if x['block']==n)
 conveyor({'position_m':[x,y],'size_m':[width,length],'rotation_deg':0,'source_handles':v['source_handles']})
 handled.add(v['id'])
for n in ('小黄人','PW_TG_96C_IN'):
 for v in layout['equipment']:
  if v['block']==n:
   if n=='PW_TG_96C_IN':fromcad(v,table,(1,1.2))
   handled.add(v['id'])
platform='SM_MPR_SorterPlatform'
box(platform,'PaleGray',(0,0,.015),(2.5999948,38.999922,.03))
for y in [i*.65-19.499961 for i in range(61)]:box(platform,'Metal',(0,y,.033),(2.5999948,.012,.006))
for x in (-1.2999974,-.6499974,0,.6500026,1.2999974):box(platform,'Metal',(x,0,.033),(.012,38.999922,.006))
add(platform,[-108.4858347,-54.387945,0],source=['2D41B7'],kind='CAD sorter floor grid; floor level')
for feed in loose_feeds:
 spec=feed_specs[feed['id']];fromcad(feed,spec['mesh'],spec['native_size_m'])
 instances[-1]['height_basis']=feed['height_policy']
omitted=[v for v in omitted if v['id'] not in handled]
deduplicated={}
for row in instances:
 key=(row['mesh'],tuple(round(v,3) for v in row['position_m']),round(row['rotation_deg'],3),tuple(round(v,3) for v in row['scale']))
 if key in deduplicated:deduplicated[key]['source_handles']=list(dict.fromkeys(deduplicated[key]['source_handles']+row['source_handles']))
 else:deduplicated[key]=row
instances=list(deduplicated.values())
manifest=g.export(OUT,'mpr_operations',{'purpose':'CAD positioned modular basic equipment; GHS material roles reused','triangle_budget_per_mesh':1800,'assumptions':['Conveyor elevation1.0m,worktop.88m,sealer1.74m estimated where no plan elevation exists.','Frame and machine geometry simplify exact CAD footprint with explicit open structure; no whole-complex bbox cuboids.','GHS shared conveyor is a fixed inclined3m unit and cannot tile measured level runs without steps; new2m straight module uses same material roles.','Complex feeder line positions are paired from measured source edges; heights and narrow internal mechanical details are simplified.']})
for row in manifest['meshes']:row['instance_only']=True
(OUT/'mpr_operations.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
assert all(x['triangles']<1800 for x in manifest['meshes'])
(OUT/'instances.json').write_text(json.dumps({'schema_version':1,'coordinate_system':'CAD local metres; UE apply X*100,Y*-100,Z*100,yaw*-1 once','instances':instances,'additional_pallet_positions':additional_pallets,'reserved_zones':zones,'merged_supports':merged_supports,'merged_drive_units':merged_drive_units,'recovered_loose_feeds':loose_feeds,'unmodeled_components':omitted,'drafting_symbols':layout.get('drafting_symbols',[]),'counts_by_mesh':dict(collections.Counter(v['mesh'] for v in instances))},ensure_ascii=False,indent=2),encoding='utf8')
print('MPR_OPERATIONS_INSTANCES',len(instances),'REVIEW',len(omitted))
