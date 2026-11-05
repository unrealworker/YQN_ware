"""Run the actual B50B57 transition constraints without Blender or Unreal."""
import argparse,copy,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'Saved/ParkRefinement/python_deps'),str(ROOT/'Tools/MPRWarehouse')]
import numpy as np
from shapely.geometry import LineString,Point,mapping,shape
from mpr_extension_roads import build_extension_roads,OUTER_TERMINALS,SOURCE_SHA256
import mpr_plan_site as plan

def validate(source_path,registration_path,output_dir,protection_path=None):
 source=json.loads(source_path.read_text(encoding='utf8'));registration=json.loads(registration_path.read_text(encoding='utf8'))
 transform=registration.get('transform',registration)
 before=hashlib.sha256(json.dumps(source,sort_keys=True).encode()).hexdigest()
 protection=json.loads(protection_path.read_text(encoding='utf8'))if protection_path else None
 kwargs=dict(existing_buildings=shape(protection['buildings']),existing_tree_clearance=shape(protection['trees']))if protection else {}
 result=build_extension_roads(source,transform,**kwargs);audit=result['audit']
 assert not audit['unresolved'],audit['unresolved']
 assert not audit['transition_crossings'],audit['transition_crossings']
 assert audit['outlet_count']==29 and audit['connected_count']==26 and audit['preserved_outer_count']==3
 assert audit['all_surfaces_valid']
 for field in ['old_frame_overlap_m2','fixed_building_overlap_m2','fixed_rail_overlap_m2','fixed_tree_overlap_m2']:
  assert audit[field]<1e-6,(field,audit[field])
 assert result['extension_roads'].intersection(result['replacement_terminal_roads']).area<1e-6
 oldroads=plan.road_geometry()
 roads=oldroads.union(result['extension_roads']).union(result['replacement_terminal_roads'])
 # 0.1mm numerical tolerance is below mesh float precision at these metre
 # coordinates; the independent distance check below remains below 1mm.
 shared_border=result['replacement_terminal_roads'].boundary.intersection(oldroads.buffer(.0001))
 axes={r['id']:LineString(r['points_m'])for r in result['source_axes']}
 checks=[];ids=[]
 for row in result['connections']:
  ids.append(row['id'])
  if row['status']=='connected':
   assert row['fade_allowed']is False
   # The source sample starts 0.75m inside the frozen crop. Only its exterior
   # path is newly authored; an old irregular roadside inside that crop is not
   # a new pavement gap. Independently check the real shared road mouth below.
   line=LineString(row['path_m']);uncovered=line.difference(result['frame_old']).difference(roads.buffer(.015)).length
   contact=shared_border.intersection(Point(row['origin_m']).buffer(max(3.,row['start_width_m']))).length
   local=Point(row['origin_m']).buffer(max(3.,row['start_width_m']))
   gap=oldroads.intersection(local).distance(result['replacement_terminal_roads'].intersection(local))
   target_error=axes[row['source_axis']].distance(Point(row['target_m']))
   assert uncovered<.025,(row['id'],'pavement gap',uncovered)
   assert target_error<1e-6,(row['id'],'target left source axis',target_error)
   assert contact>.1,(row['id'],'no shared original road mouth',contact)
   assert gap<.001,(row['id'],'original road mouth gap',gap)
   checks.append(dict(id=row['id'],uncovered_centerline_m=uncovered,shared_original_road_mouth_m=contact,mouth_gap_m=gap,target_axis_error_m=target_error))
  else:
   assert int(row['id'][-2:])in OUTER_TERMINALS and row['fade_allowed']is True
 assert len(set(ids))==29
 assert result['mouth_stitches'].intersection(oldroads).area<1e-7
 assert all(r['max_in_frame_m']<=.120001 for r in audit['mouth_stitches'])
 assert before==hashlib.sha256(json.dumps(source,sort_keys=True).encode()).hexdigest()
 wrong=dict(source,sha256='0'*64)
 try:build_extension_roads(wrong,transform)
 except ValueError:source_rejection=True
 else:raise AssertionError('Unreviewed new source was accepted')
 pruned=audit['source_boundary_branch_treatments']
 assert any(r['source_axis']=='TPX_ROADS_AXES_798'and r['kept_length_m']==0 for r in pruned)
 assert not any(r['termination']=='fade'for group in pruned for r in group['trims'])
 output_dir.mkdir(parents=True,exist_ok=True)
 report=dict(status='passed',checks=checks,source_mismatch_rejected=source_rejection,source_input_unchanged=True,audit=audit,
   protection_path=str(protection_path)if protection_path else None,
   module_sha256=hashlib.sha256((ROOT/'Tools/MPRWarehouse/mpr_extension_roads.py').read_bytes()).hexdigest())
 (output_dir/'road_transition_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
 (output_dir/'road_transition_result.json').write_text(json.dumps({k:mapping(v)if hasattr(v,'geom_type')else v for k,v in result.items()},ensure_ascii=False,indent=2),encoding='utf8')
 (output_dir/'road_connections_review.json').write_text(json.dumps(dict(connections=result['connections'],source_boundary_branch_treatments=pruned,outer_reasons=OUTER_TERMINALS),ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps(dict(status='passed',connections=26,preserved_outer=3,source_boundary_treatments=len(pruned),max_pavement_gap_m=max(c['uncovered_centerline_m']for c in checks),module_sha256=report['module_sha256']),indent=2))
 return report

if __name__=='__main__':
 parser=argparse.ArgumentParser();base=ROOT/'Saved/MPR/extension_20261104'
 parser.add_argument('--source',type=Path,default=base/'source_geometry.json')
 parser.add_argument('--registration',type=Path,default=base/'registration_proposal.json')
 parser.add_argument('--output',type=Path,default=base)
 parser.add_argument('--protection',type=Path)
 args=parser.parse_args();validate(args.source,args.registration,args.output,args.protection)
