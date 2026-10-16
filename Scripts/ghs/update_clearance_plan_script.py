from pathlib import Path
p=Path('Scripts/ghs/plan_clearance_fix.py');s=p.read_text();marker='def main():\n';helper='''def trim_shared_end_frames(groups):
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

''';s=s.replace(marker,helper+marker)
s=s.replace("adjustments=[]\n for e in physical['storage']:","adjustments=[]\n physical=copy.deepcopy(physical)\n equipment=copy.deepcopy(cad['equipment'])\n shared_changes,unresolved_shared=trim_shared_end_frames({'racks':physical['racks'],'equipment':equipment})\n adjustments.extend(shared_changes)\n for e in physical['storage']:")
s=s.replace("('equipment',cad['equipment'])]","('equipment',equipment)]")
s=s.replace("v['size_m'][axis]=hi-lo\n    if", "v['size_m'][axis]=hi-lo;v['trimmed_geometry_size_m']=list(v['size_m']);v.setdefault('nominal_size_m',list(e['size_m']))\n    if")
s=s.replace("'adjustments':adjustments,'limitations'", "'adjustments':adjustments,'shared_frame_unresolved_pairs':unresolved_shared,'limitations'")
s=s.replace("assert not col_after, 'Residual column clearance overlaps'", "assert not col_after, 'Residual column clearance overlaps'\n assert not after, 'Residual object-object overlaps: inspect report logic'")
p.write_text(s,encoding='utf8')
