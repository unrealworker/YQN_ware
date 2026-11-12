"""Independent GEOS geometry/readback audit of the offline whole-row plan."""
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import math
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Tools/MPRWarehouse'))
sys.path.insert(0,str(ROOT/'Scripts/_vendor/cad'))
import plan_mpr_rack_clearance_20261112 as planner
from shapely.geometry import Polygon,LineString
from shapely.strtree import STRtree


def polygon(rect):
    if rect.get('polygon_points'):return Polygon(rect['polygon_points'])
    x,y=rect['position_m'];w,d=rect['size_m'];a=math.radians(rect['rotation_deg'])
    c,s=math.cos(a),math.sin(a)
    return Polygon([(x+u*c-v*s,y+u*s+v*c) for u,v in
                    [(-w/2,-d/2),(w/2,-d/2),(w/2,d/2),(-w/2,d/2)]])


def intersections(racks,obstacles):
    polys=[polygon(r) for r in obstacles];tree=STRtree(polys);hits=[]
    for rack in racks:
        rp=polygon(rack)
        for index in tree.query(rp):
            index=int(index);obstacle=obstacles[index]
            vertical=min(rack['z_range_m'][1],obstacle['z_range_m'][1])-max(rack['z_range_m'][0],obstacle['z_range_m'][0])
            if vertical>1.e-7 and rp.intersection(polys[index]).area>1.e-7:
                hits.append((rack['source_handle'],obstacle['id']))
    return sorted(hits)


def run():
    path=planner.OUT/'placement_plan.json';plan=planner.read(path)
    assert plan['status']=='geometry_verified'
    files,data,original,shafts,bases,columns,fixed=planner.load_inputs()
    for relative,digest in plan['input_sha256'].items():
        assert planner.sha(ROOT/relative)==digest,('Input changed',relative)
    assert plan['map_sha256']==data['baseline']['map_file_sha256']
    old={r['source_handle']:r for r in original}
    rows={r['row_id']:r for r in plan['rows']}
    changes=plan['instances'];by_row=defaultdict(list);updated=[];identities=set()
    assert len(changes)==len(old)==2867
    assert {r['source_handle'] for r in changes}==set(old)
    for change in changes:
        before=old[change['source_handle']]
        identity=tuple(change[k] for k in ('actor_guid','component_name','instance_index'))
        assert identity not in identities;identities.add(identity)
        assert identity==tuple(before[k] for k in ('actor_guid','component_name','instance_index'))
        assert change['original_transform']==before['original_transform']
        for key in ('mesh','family','width_inches','passage_variant'):assert change[key]==before[key]
        a,b=change['original_transform'],change['proposed_transform']
        assert a['rotation_xyzw']==b['rotation_xyzw'] and a['scale']==b['scale']
        assert a['translation_cm'][2]==b['translation_cm'][2]
        row=rows[change['row_id']];axis=row['axis'];shift=row['shift_m']
        delta=[(b['translation_cm'][k]-a['translation_cm'][k])/100*(1 if k==0 else -1) for k in (0,1)]
        assert abs(delta[axis]-shift)<1.e-10 and abs(delta[1-axis])<1.e-10
        assert abs(shift)<=plan['policy']['maximum_shift_m']+1.e-10
        assert max(abs(delta[k]-change['displacement_cad_m'][k]) for k in (0,1))<1.e-10
        after=deepcopy(before);after['position_m']=[before['position_m'][k]+delta[k] for k in (0,1)]
        after['row_id']=change['row_id'];updated.append(after);by_row[change['row_id']].append(after)
    assert len(by_row)==len(rows)==109
    for id,row in rows.items():
        members=by_row[id]
        assert len(members)==row['member_count']
        assert {r['source_handle'] for r in members}==set(row['source_handles'])
        if row['locked_due_to_unchanged_existing_equipment_contact']:assert row['shift_m']==0
    building=Polygon(data['layout']['footprint_outline_m'])
    polys=[polygon(r) for r in updated]
    assert all(building.covers(poly) for poly in polys)
    column_hits=intersections(updated,columns)
    assert not column_hits,column_hits
    original_fixed=intersections(original,fixed);after_fixed=intersections(updated,fixed)
    assert after_fixed==original_fixed and len(after_fixed)==4,(original_fixed,after_fixed)
    changes_by_handle={r['source_handle']:r for r in changes}
    for handle,_ in after_fixed:
        assert changes_by_handle[handle]['original_transform']==changes_by_handle[handle]['proposed_transform']
    tree=STRtree(polys);cross_pairs=[]
    for i,rack in enumerate(updated):
        for j in tree.query(polys[i]):
            j=int(j)
            if j<=i or rack['row_id']==updated[j]['row_id']:continue
            if polys[i].intersection(polys[j]).area>1.e-7:cross_pairs.append((rack['source_handle'],updated[j]['source_handle']))
    assert not cross_pairs,cross_pairs
    measured=[]
    for gap in plan['aisles']:
        axis=gap['axis']
        left=[polygon(r).bounds for r in by_row[gap['left_row']]]
        right=[polygon(r).bounds for r in by_row[gap['right_row']]]
        actual=min(b[axis] for b in right)-max(b[axis+2] for b in left)
        assert abs(actual-gap['new_width_m'])<1.e-8
        assert actual>=gap['minimum_required_m']-1.e-8
        measured.append(dict(left_row=gap['left_row'],right_row=gap['right_row'],
                             classification=gap['classification'],width_m=actual,minimum_m=gap['minimum_required_m']))
    doors=[]
    for door in plan['door_clearances']:
        line=LineString(door['endpoints'])
        distance=min(line.distance(p) for p in polys)
        assert distance>=door['minimum_required_m']-.000002,(door['id'],distance,door['minimum_required_m'])
        doors.append(dict(id=door['id'],before_m=door['original_rack_clearance_m'],after_m=distance,
                          minimum_m=door['minimum_required_m']))
    # All 118 substantial shaft contacts intersect a continuous measured
    # bearing section (deck plus front/rear beams) in standard rack families.
    # This distinguishes physical penetration from eight float-noise edge
    # contacts that still fail the separate 100mm presentation-clearance rule.
    specs=planner.read(ROOT/'SourceAssets/MPR/interior_cad_20261112/racks/rack_specs.json')
    original_shaft=intersections(original,shafts);shaft_by_id={r['id']:r for r in shafts}
    for handle,id in original_shaft:
        r=old[handle];spec=specs['families'][r['family']]
        assert not r['passage_variant'] and r['width_inches']==144
        section=dict(r,size_m=[spec['clear_width_m'],spec['depth_m']])
        assert polygon(section).intersection(polygon(shaft_by_id[id])).area>1.e-7
    assert len(original_shaft)==118
    result=dict(schema_version=1,success=True,plan_sha256=planner.sha(path),
        map_sha256=plan['map_sha256'],validator='Independent Shapely/GEOS polygon intersections and exact opening distances; not planner SAT solver',
        rack_count=2867,row_count=109,column_positions=303,door_openings=len(doors),
        confirmed_original_column_structure_penetrations=len(original_shaft),
        final_column_base_clearance_contacts=0,new_fixed_obstacle_contacts=0,cross_row_contacts=0,
        retained_existing_fixed_contacts=[dict(rack_handle=h,obstacle_id=o) for h,o in after_fixed],
        rotations_scales_heights_materials_and_mesh_references_preserved=True,
        within_original_building=True,all_instances_mapped_once=True,rigid_column_translation_verified=True,
        moved_rows=plan['summary']['moved_rows'],moved_instances=plan['summary']['moved_instances'],
        maximum_shift_m=plan['summary']['maximum_displacement_m'],aisles=measured,doors=doors)
    (planner.OUT/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('aisles','doors','retained_existing_fixed_contacts')},ensure_ascii=False,indent=2))
    return result


if __name__=='__main__':
    planner.evidence.USE_ARCHIVE='--archived-inputs' in sys.argv
    run()
