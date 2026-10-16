"""Prepare presentation-only vertical hierarchy; never mutate authoritative registry."""
import json,math,copy,hashlib,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];SRC=ROOT/'SourceAssets/GHS';baseline=SRC/'ue_scene_registry.json';raw=baseline.read_bytes();reg=json.loads(raw);groups={g['actor']:g for g in reg['groups']};cargo=groups['GHS_CAD_PalletCargo']['instances']
# Cluster original CAD slots (including blocked positions) so column holes cannot
# break a contiguous storage block into random height islands.
cad=json.loads((SRC/'cad_layout.json').read_text(encoding='utf8'));slots=cad['storage'];parent=list(range(len(slots)));grid=collections.defaultdict(list)
def find(i):
 while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
 return i
def union(i,j):parent[find(j)]=find(i)
for i,e in enumerate(slots):
 x,y=e['position_m'];cell=(math.floor(x/1.5),math.floor(y/1.5))
 for dx in [-1,0,1]:
  for dy in [-1,0,1]:
   for j in grid[cell[0]+dx,cell[1]+dy]:
    a,b=slots[j]['position_m'];dist=math.hypot(x-a,y-b)
    if dist<1.5 and (abs(x-a)<.03 or abs(y-b)<.03):union(i,j)
 grid[cell].append(i)
clusters=collections.defaultdict(list)
for i,e in enumerate(slots):clusters[find(i)].append(e)
active={r['id']:r for r in cargo};blocks=[]
for rows in clusters.values():
 ids=[r['id'] for r in rows if r['id'] in active]
 if not ids:continue
 blocks.append({'slot_ids':ids,'all_cad_slot_count':len(rows),'center_m':[sum(r['position_m'][k] for r in rows)/len(rows) for k in (0,1)]})
# Assign whole blocks in contiguous north/south bands, balancing 25/50/25
# independently in each of three broad west/east floor-storage sectors.
xs=[b['center_m'][0] for b in blocks];xmin,xmax=min(xs),max(xs);assign={};stats=[]
for zone in range(3):
 bs=[b for b in blocks if min(2,int(3*(b['center_m'][0]-xmin)/(xmax-xmin+1e-9)))==zone];bs.sort(key=lambda b:(b['center_m'][1],b['center_m'][0]));total=sum(len(b['slot_ids']) for b in bs);done=0;counts=collections.Counter()
 for b in bs:
  n=len(b['slot_ids']);q=(done+n/2)/total;variant='Low' if q<.25 else 'High' if q>=.75 else 'Mid';done+=n;block_id='FloorBlock_%03d'%blocks.index(b);b.update(id=block_id,zone=zone,variant=variant)
  for id in b['slot_ids']:assign[id]=(variant,block_id)
  counts[variant]+=n
 stats.append({'zone':zone,'active_slots':total,'variant_counts':dict(counts)})
out=copy.deepcopy(reg);newgroups=[];modified=['GHS_CAD_Racks','GHS_CAD_PalletCargo','GHS_CAD_PalletCargoLow','GHS_CAD_PalletCargoHigh','GHS_CAD_Columns','GHS_ColumnEdgeOutlines'];height={'Low':1.376,'Mid':1.976,'High':2.576}
for g in out['groups']:
 label=g['actor']
 if label=='GHS_CAD_PalletCargo':
  for variant in ['Mid','Low','High']:
   v=copy.deepcopy(g);v['actor']=label+('' if variant=='Mid' else variant);v['mesh']='SM_GHS_Presentation_Cargo'+variant;v['instances']=[copy.deepcopy(r) for r in g['instances'] if assign[r['id']][0]==variant]
   for r in v['instances']:r.update(presentation_variant=variant,presentation_height_m=height[variant],presentation_block_id=assign[r['id']][1])
   v['count']=len(v['instances']);newgroups.append(v)
 elif label=='GHS_CAD_Racks':
  g['mesh']='SM_GHS_Presentation_RackTall'
  for r in g['instances']:r['presentation_height_m']=4.8
  newgroups.append(g)
 elif label=='GHS_CAD_Columns':
  for r in g['instances']:
   bottom=r['position_m'][2]-r['scale'][2]/2;r['position_m'][2]=bottom+2.8;r['scale'][2]=5.6;r['presentation_height_m']=5.6
  newgroups.append(g)
 else:newgroups.append(g)
out['groups']=newgroups;ng={g['actor']:g for g in newgroups};edge=.012;rows=[]
for col in ng['GHS_CAD_Columns']['instances']:
 w,d,h=col['scale'];x,y,z=col['position_m'];angle=col['rotation_deg'];t=math.radians(angle);parts=[]
 for level,sign in [('Bottom',-1),('Top',1)]:
  cz=sign*(h-edge)/2
  for side in [-1,1]:parts.extend([(level+'_X_'+str(side),(0,side*(d-edge)/2,cz),(w,edge,edge)),(level+'_Y_'+str(side),(side*(w-edge)/2,0,cz),(edge,d-2*edge,edge))])
 for sx in [-1,1]:
  for sy in [-1,1]:parts.append(('Vertical_'+str(sx)+'_'+str(sy),(sx*(w-edge)/2,sy*(d-edge)/2,0),(edge,edge,h-2*edge)))
 for name,(ox,oy,oz),scale in parts:rows.append(dict(id=col['id']+'_Outline_'+name,parent_column_id=col['id'],edge_name=name,position_m=[x+ox*math.cos(t)-oy*math.sin(t),y+ox*math.sin(t)+oy*math.cos(t),z+oz],rotation_deg=angle,scale=list(scale),source_handles=col['source_handles']))
ng['GHS_ColumnEdgeOutlines']['instances']=rows;ng['GHS_ColumnEdgeOutlines']['count']=len(rows)
# Exact registry values are preserved: no XY recentering or hidden scale changes.
newcargo={r['id']:r for g in newgroups if g['actor'].startswith('GHS_CAD_PalletCargo') for r in g['instances']}
assert set(newcargo)==set(active)
for id,old in active.items():
 new=newcargo[id]
 for k in ['position_m','rotation_deg','scale','source_handles']:assert new[k]==old[k],(id,k)
for g in newgroups:
 if g['actor'] not in modified:assert g==groups[g['actor']]
assert out['individuals']==reg['individuals']
assert len(newgroups)==18 and sum(g['count'] for g in newgroups)==14116 and len(rows)==2040
out['presentation']={'source_baseline_path':str(baseline),'source_baseline_sha256':hashlib.sha256(raw).hexdigest(),'modified_labels':modified,'expected_actor_count':227,'expected_hism_group_count':18,'expected_instance_count':14116,'cargo_count':len(newcargo),'cargo_blocks':blocks,'zone_variant_statistics':stats,'cargo_height_m':height,'rack_height_m':4.8,'column_height_m':5.6,'assumptions':['All presentation heights are artistic estimates, not surveyed CAD heights.','Cargo geometry stays inside old approved XY bounds; registry XY scale and transform are copied byte-for-value.','Tall rack mesh stays inside old approved XY bounds; dock mesh remains original 2.8m.','One whole CAD contiguous block receives one height class; blocked slots participate in clustering but stay empty.','Column footprints and bottom elevation unchanged; only vertical extent and 12-edge closure increase.'],'verification_design':['Check baseline SHA before apply; refuse stale baseline.','Compare every cargo ID/XY/yaw/XYscale/source handle with baseline; only group/mesh and approved metadata differ.','Check new mesh XY bounds against original mesh bounds before apply, not only nominal dimensions.','Re-run actual mesh OBB clearance, 122 blocked slots, 170 authority columns, joined-wall mesh and FX regression.','Whitelist changed group labels in historical comparisons, retaining all XY and lineage constraints.','Confirm 18 HISM groups, 14116 instances, 227 actors; 34 AGVs/56 chargers/40 effects/6 cameras unchanged.']}
from wall_height_profile import synchronize_registry
synchronize_registry(out)  # Architectural walls participate in the same height refinement.
path=SRC/'Presentation/visual_layout.json';path.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8');assert baseline.read_bytes()==raw
print(json.dumps({'path':str(path),'blocks':len(blocks),'variants':{v:sum(assign[id][0]==v for id in active) for v in height},'zones':stats,'groups':len(newgroups),'instances':sum(g['count'] for g in newgroups)},indent=2))
