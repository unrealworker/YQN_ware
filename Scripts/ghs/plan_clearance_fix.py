"""Plan traceable column clearances without mutating source CAD or Unreal assets."""
import json, math, copy, collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'SourceAssets/GHS'
TOL=1e-7
FOOT_EXTRA=.10
CLEARANCE=.10
MIN_SEGMENT=.75

def corners(e):
 x,y=e['position_m'][:2];sx,sy=e['size_m'];a=math.radians(e.get('rotation_deg',0));c,s=math.cos(a),math.sin(a)
 return [(x+u*c-v*s,y+u*s+v*c) for u,v in [(-sx/2,-sy/2),(sx/2,-sy/2),(sx/2,sy/2),(-sx/2,sy/2)]]

def overlap(a,b):
 pa,pb=corners(a),corners(b)
 for e in (a,b):
  r=math.radians(e.get('rotation_deg',0))
  for n in [(math.cos(r),math.sin(r)),(-math.sin(r),math.cos(r))]:
   aa=[p[0]*n[0]+p[1]*n[1] for p in pa];bb=[p[0]*n[0]+p[1]*n[1] for p in pb]
   if min(max(aa),max(bb))-max(min(aa),min(bb))<=TOL:return False
 return True

def collision_pairs(groups):
 # Spatial hashing covers all OBB AABBs, avoiding quadratic all-warehouse comparisons.
 entries=[(cat,e) for cat,items in groups.items() for e in items];grid=collections.defaultdict(list);seen=set();pairs=[];cell=5.
 for i,(cat,e) in enumerate(entries):
  ps=corners(e);lo=[math.floor(min(p[k] for p in ps)/cell) for k in (0,1)];hi=[math.floor(max(p[k] for p in ps)/cell) for k in (0,1)]
  cells=[(x,y) for x in range(lo[0],hi[0]+1) for y in range(lo[1],hi[1]+1)]
  for key in cells:
   for j in grid[key]:
    if (j,i) in seen:continue
    seen.add((j,i));other,b=entries[j]
    if overlap(e,b):pairs.append({'a_category':other,'a_id':b['id'],'b_category':cat,'b_id':e['id']})
   grid[key].append(i)
 return pairs

def trim_shared_end_frames(groups):
 # Resolve physical overlap at adjacent collinear CAD bays by sharing the end frame,
 # with a 20 mm visible seam. Preserve the original CAD anchor separately.
 entries={e['id']:e for rows in groups.values() for e in rows};limits={};changes=[]
 for e in entries.values():
  axis=int(e['size_m'][1]>e['size_m'][0]);half=e['size_m'][axis]/2
  limits[e['id']]=[-half,half]
 pairs=collision_pairs(groups)
 unresolved=[]
 for pair in pairs:
  a,b=entries[pair['a_id']],entries[pair['b_id']]
  ax=int(a['size_m'][1]>a['size_m'][0]);bx=int(b['size_m'][1]>b['size_m'][0]);ra=math.radians(a.get('rotation_deg',0))+ax*math.pi/2;rb=math.radians(b.get('rotation_deg',0))+bx*math.pi/2
  u=(math.cos(ra),math.sin(ra));v=(-u[1],u[0]);dot=math.cos(ra-rb);delta=[b['position_m'][k]-a['position_m'][k] for k in (0,1)];along=sum(delta[k]*u[k] for k in (0,1));cross=sum(delta[k]*v[k] for k in (0,1))
  if abs(abs(dot)-1)>.0001 or abs(cross)>.03 or abs(along)<.01:
   unresolved.append(pair);continue
  seam=along/2;gap=.01
  # Convert seam point into each object's signed local long axis.
  if along>0:limits[a['id']][1]=min(limits[a['id']][1],seam-gap)
  else:limits[a['id']][0]=max(limits[a['id']][0],seam+gap)
  bseam=-along/2*dot
  if bseam>0:limits[b['id']][1]=min(limits[b['id']][1],bseam-gap)
  else:limits[b['id']][0]=max(limits[b['id']][0],bseam+gap)
  changes.append(dict(action='shared_end_frame_trim',a_id=a['id'],b_id=b['id'],gap_m=.02,reason='Adjacent CAD rack symbols share 3-inch end frames; render each side to midpoint with 20mm seam. Original CAD anchors retained.'))
 for e in entries.values():
  axis=int(e['size_m'][1]>e['size_m'][0]);lo,hi=limits[e['id']];old=e['size_m'][axis]
  if hi-lo<old-1e-8:
   e['nominal_size_m']=list(e['size_m']);e['cad_anchor_position_m']=list(e['position_m']);e['parent_cad_id']=e['id'];angle=math.radians(e.get('rotation_deg',0))+axis*math.pi/2
   e['position_m']=[e['position_m'][0]+math.cos(angle)*(lo+hi)/2,e['position_m'][1]+math.sin(angle)*(lo+hi)/2];e['size_m'][axis]=hi-lo;e['trimmed_geometry_size_m']=list(e['size_m']);e['design_adjustment']='Shared-frame geometry trimmed in place; no aisle or CAD anchor relocation.'
 return changes,unresolved

def main():
 cad=json.loads((SOURCE/'cad_layout.json').read_text(encoding='utf8'));physical=json.loads((SOURCE/'physical_bounds_proposed.json').read_text(encoding='utf8'))
 cols=[copy.deepcopy(e) for e in cad['columns'] if e['block']!='PILLAR'];excluded=[]
 for e in cad['columns']:
  if e['block']!='PILLAR':continue
  near=min(cols,key=lambda c:math.dist(e['position_m'],c['position_m']));dist=math.dist(e['position_m'],near['position_m']);v=copy.deepcopy(e)
  v.update(exclusion_reason='duplicate_column_redraw' if dist<.15 else 'unconfirmed_off_grid_candidate',nearest_authoritative_column=near['id'],nearest_distance_m=dist);excluded.append(v)
 obstacles=[]
 for c in cols:
  v=copy.deepcopy(c);v['size_m']=[s+FOOT_EXTRA+2*CLEARANCE for s in c['size_m']];obstacles.append(v)
 out={'schema_version':1,'origin_dxf_xy':cad['origin_dxf_xy'],'units_to_m':cad['units_to_m'],'bounds_m':cad['bounds_m'],'footprint_outline_m':cad['footprint_outline_m'],'columns':cols,'storage':[],'racks':[],'equipment':[],'excluded_candidates':excluded,'blocked_storage':[],'removed_rack_segments':[],'conveyors':[],'policy':{'column_base_total_width_extra_m':FOOT_EXTRA,'clearance_from_base_each_side_m':CLEARANCE,'minimum_rack_segment_length_m':MIN_SEGMENT,'unchanged_slot_positions':True,'height_changes':False,'note':'Design clearance correction, not an assertion that original CAD specifies these exclusions.'}}
 adjustments=[]
 physical=copy.deepcopy(physical)
 equipment=copy.deepcopy(cad['equipment'])
 original_before=collision_pairs({'columns_with_base_clearance':obstacles,'storage':physical['storage'],'racks':physical['racks'],'equipment':equipment})
 shared_changes,unresolved_shared=trim_shared_end_frames({'racks':physical['racks'],'equipment':equipment})
 adjustments.extend(shared_changes)
 for e in physical['storage']:
  hits=[c for c in obstacles if overlap(e,c)];v=copy.deepcopy(e)
  if hits:
   v.update(reason='Column base plus 0.10m clearance occupies this CAD slot; entire load omitted, slot retained as blocked.',blocking_column_ids=[c['id'] for c in hits],blocking_column_source_handles=[c['source_handles'] for c in hits]);out['blocked_storage'].append(v);adjustments.append({'id':e['id'],'action':'leave_entire_storage_slot_empty','reason':v['reason'],'column_ids':v['blocking_column_ids']})
  else:out['storage'].append(v)
 for cat,items in [('racks',physical['racks']),('equipment',equipment)]:
  for e in items:
   hits=[c for c in obstacles if overlap(e,c)]
   if not hits:out[cat].append(copy.deepcopy(e));continue
   axis=1 if cat=='racks' else int(e['size_m'][1]>e['size_m'][0]);ang=math.radians(e.get('rotation_deg',0))+axis*math.pi/2;u=(math.cos(ang),math.sin(ang));half=e['size_m'][axis]/2
   intervals=[]
   for c in hits:
    proj=[(p[0]-e['position_m'][0])*u[0]+(p[1]-e['position_m'][1])*u[1] for p in corners(c)];intervals.append([max(-half,min(proj)-.001),min(half,max(proj)+.001)])
   intervals.sort();merged=[]
   for lo,hi in intervals:
    if merged and lo<=merged[-1][1]:merged[-1][1]=max(hi,merged[-1][1])
    else:merged.append([lo,hi])
   remaining=[];cursor=-half
   for lo,hi in merged:
    if lo>cursor:remaining.append([cursor,lo])
    cursor=max(cursor,hi)
   if cursor<half:remaining.append([cursor,half])
   kept=[]
   for idx,(lo,hi) in enumerate(remaining):
    v=copy.deepcopy(e);v.update(id=e['id']+'_ClearanceSeg_'+str(idx+1),parent_cad_id=e['id'],design_adjustment='Local long-axis split around column base and 0.10m clearance; CAD parent center not moved.',blocking_column_ids=[c['id'] for c in hits],segment_interval_m=[lo,hi]);v['position_m']=[e['position_m'][k]+u[k]*(lo+hi)/2 for k in range(2)];v['size_m'][axis]=hi-lo;v['trimmed_geometry_size_m']=list(v['size_m']);v.setdefault('nominal_size_m',list(e['size_m']))
    if hi-lo+TOL>=MIN_SEGMENT:out[cat].append(v);kept.append(v['id'])
    else:v['reason']='Remainder shorter than 0.75m minimum display segment';out['removed_rack_segments'].append(v)
   adjustments.append({'id':e['id'],'category':cat,'action':'split_in_place','column_ids':[c['id'] for c in hits],'removed_intervals_m':merged,'kept_segment_ids':kept,'reason':'Avoid authoritative column base plus required clearance; no row or other slot translation.'})
 before=original_before
 after=collision_pairs({'columns_with_base_clearance':obstacles,'storage':out['storage'],'racks':out['racks'],'equipment':out['equipment']})
 def counts(pairs):return dict(collections.Counter('_'.join(sorted([p['a_category'],p['b_category']])) for p in pairs))
 col_after=[p for p in after if 'columns_with_base_clearance' in [p['a_category'],p['b_category']] and p['a_category']!=p['b_category']]
 report={'status':'planned','source_cad_unchanged':True,'policy':out['policy'],'counts':{k:len(out[k]) for k in ['columns','storage','blocked_storage','racks','equipment','excluded_candidates','removed_rack_segments']},'exclusion_counts':dict(collections.Counter(e['exclusion_reason'] for e in excluded)),'before_collision_counts':counts(before),'after_collision_counts':counts(after),'checked_pair_categories':['storage_storage','racks_racks','equipment_equipment','racks_storage','equipment_storage','equipment_racks','columns_with_base_clearance_storage','columns_with_base_clearance_racks','columns_with_base_clearance_equipment','columns_with_base_clearance_columns_with_base_clearance'],'after_column_clearance_collision_count':len(col_after),'before_collision_pairs':before,'after_collision_pairs':after,'adjustments':adjustments,'shared_frame_unresolved_pairs':unresolved_shared,'limitations':['2D OBB assessment assumes mesh physical XY bounds match nominal model dimensions and centered pivots.','Object-object contacts are reported, not suppressed or automatically changed.','Empty slots and shortened rack segments are design corrections, not original surveyed CAD geometry.']}
 assert len(cols)==170 and len(excluded)==36
 assert len(out['storage'])+len(out['blocked_storage'])==7530
 assert not col_after, 'Residual column clearance overlaps'
 assert not after, 'Residual object-object overlaps: inspect report logic'
 (SOURCE/'clearance_layout.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8');(ROOT/'Saved/GHS_ClearancePlan.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps({k:report[k] for k in ['counts','exclusion_counts','before_collision_counts','after_collision_counts','after_column_clearance_collision_count']},indent=2))
if __name__=='__main__':main()
