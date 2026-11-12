"""Offline, traceable whole-row rack clearance using current native bounds.

Only writes a new plan. Source CAD, existing transforms, meshes and UE remain
untouched. Coordinates in the solver are CAD metres (UE Y is negated once).
"""
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path
import argparse
import gzip
import hashlib
import itertools
import json
import math
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'Scripts/ghs'))
sys.path.insert(0, str(ROOT/'Scripts/_vendor/cad'))
from plan_clearance_fix import corners, overlap
from prepare_rack_spacing_v2 import forbidden_x_shift, merge_intervals, solve_rows
from shapely.geometry import Polygon, LineString, box as shapely_box
import mpr_rack_clearance_evidence_20261112 as evidence

BASE = ROOT/'Saved/MPR/optimization_20261112'
OUT = ROOT/'SourceAssets/MPR/rack_clearance_20261112'
IDENTITY = dict(translation_cm=[0., 0., 0.], rotation_xyzw=[0., 0., 0., 1.], scale=[1., 1., 1.])
EPS = 1.e-7
CLEARANCE = .1
NUMERIC_MARGIN = .0002
GROUP_TOLERANCE = .003


def read(path):
    raw = evidence.read_bytes(path)
    return json.loads((gzip.decompress(raw) if path.suffix=='.gz' else raw).decode('utf-8-sig'))


def sha(path):
    return hashlib.sha256(evidence.read_bytes(path)).hexdigest()


def aabb(rect):
    points = rect.get('polygon_points') or corners(rect)
    return [[min(p[i] for p in points), max(p[i] for p in points)] for i in (0, 1)]


def native_rect(actor, component, index, transform, native):
    assert actor['transform'] == component['transform'] == IDENTITY, actor['label']
    q = transform['rotation_xyzw']
    assert abs(q[0])+abs(q[1]) < 1.e-7 and min(transform['scale']) >= 0
    angle = 2*math.atan2(q[2], q[3])
    b = native[component['mesh']]['bounds_cm']
    scale = transform['scale']
    center = [sum(pair)/2*scale[i] for i, pair in enumerate(b)]
    x = transform['translation_cm'][0]+center[0]*math.cos(angle)-center[1]*math.sin(angle)
    y = transform['translation_cm'][1]+center[0]*math.sin(angle)+center[1]*math.cos(angle)
    z = transform['translation_cm'][2]+center[2]
    size = [(bb[1]-bb[0])*scale[i]/100 for i,bb in enumerate(b)]
    return dict(id=actor['guid']+':'+component['name']+':'+str(index),
        actor_guid=actor['guid'], actor_label=actor['label'], component_name=component['name'],
        instance_index=index, mesh=component['mesh'], position_m=[x/100,-y/100],
        size_m=size[:2], z_range_m=[z/100-size[2]/2,z/100+size[2]/2],
        rotation_deg=-math.degrees(angle))


def from_bounds(id, bounds, category, **extra):
    return dict(id=id, position_m=[sum(v)/2 for v in bounds[:2]],
                size_m=[v[1]-v[0] for v in bounds[:2]], z_range_m=bounds[2],
                rotation_deg=0., category=category, **extra)


def padded(rect, amount):
    result = deepcopy(rect)
    result['size_m'] = [v+2*amount for v in rect['size_m']]
    return result


def vertical_overlap(a,b):
    return min(a['z_range_m'][1],b['z_range_m'][1])-max(a['z_range_m'][0],b['z_range_m'][0]) > EPS


def solid_overlap(a,b,tolerance=.00001):
    """Ignore sub-0.01mm native float noise at an exact CAD contact edge."""
    pa,pb=corners(a),corners(b)
    for rect in (a,b):
        angle=math.radians(rect['rotation_deg'])
        for nx,ny in ((math.cos(angle),math.sin(angle)),(-math.sin(angle),math.cos(angle))):
            aa=[x*nx+y*ny for x,y in pa];bb=[x*nx+y*ny for x,y in pb]
            if min(max(aa),max(bb))-max(min(aa),min(bb))<=tolerance:return False
    return True


class Grid:
    def __init__(self, rectangles, cell=5.):
        self.rectangles=rectangles; self.cell=cell; self.cells=defaultdict(list)
        for i,rectangle in enumerate(rectangles):
            for key in self.keys(aabb(rectangle)):
                self.cells[key].append(i)

    def keys(self, bb):
        return itertools.product(*(range(math.floor(lo/self.cell),math.floor(hi/self.cell)+1) for lo,hi in bb))

    def query(self, bb):
        indices=set()
        for key in self.keys(bb):indices.update(self.cells.get(key,()))
        return (self.rectangles[i] for i in sorted(indices))


def contacts(racks, obstacles):
    grid=Grid(obstacles); result=[]
    for rack in racks:
        for obstacle in grid.query(aabb(rack)):
            if obstacle.get('door_line'):
                touching=LineString(obstacle['door_line']).distance(Polygon(corners(rack)))<obstacle['required_distance_m']-.000001
            else:
                touching=(Polygon(corners(rack)).intersection(Polygon(obstacle['polygon_points'])).area>1.e-9
                          if obstacle.get('polygon_points') else solid_overlap(rack,obstacle))
            if vertical_overlap(rack,obstacle) and touching:
                result.append(dict(rack_handle=rack['source_handle'], obstacle_id=obstacle['id'],
                                   obstacle_category=obstacle['category']))
    return result


def load_inputs():
    files=dict(baseline=BASE/'baseline.json.gz', native_bounds=BASE/'native_mesh_bounds.json',
        walls=BASE/'wall_solid_boxes.json',
        placement=ROOT/'SourceAssets/MPR/interior_cad_20261112/racks/placement_manifest.json',
        structure=ROOT/'SourceAssets/MPR/interior_cad_20261112/structure/structural_completion_manifest.json',
        layout=ROOT/'SourceAssets/MPR/mpr_cad_layout.json',
        pedestrian_openings=ROOT/'Saved/MPR/interior_cad_20261112/interior_truth/pedestrian_openings.json')
    data={name:read(path) for name,path in files.items()}
    snapshot,native=data['baseline'],data['native_bounds']
    assert not snapshot['dirty_maps'] and not snapshot['dirty_content']
    assert data['walls']['map_sha256']==snapshot['map_file_sha256']
    source={tuple(round(v,4) for v in r['original_transform']['translation_cm']):r for r in data['placement']['instances']}
    assert len(source)==2867
    racks,physical_columns,bases,fixed=[],[],[],[]
    for actor in snapshot['actors']:
        if actor['hidden']:continue
        for c in actor['components']:
            if not c.get('mesh') or not c.get('visible',True) or c.get('hidden_in_game',False):continue
            relevant=(actor['folder'].startswith(('MPR/Storage','MPR/Operations','MPR/Equipment')) or
                      actor['label'].startswith(('MPR_Columns_','MPR_ColumnBases_')))
            if not relevant:continue
            transforms=c.get('instance_transforms',[IDENTITY])
            for index,tr in enumerate(transforms):
                rect=native_rect(actor,c,index,tr,native)
                if max(rect['size_m'])<.001 or rect['z_range_m'][1]<.005:continue
                if actor['folder']=='MPR/Storage/Racks':
                    key=tuple(round(v,4) for v in tr['translation_cm'])
                    row=source[key]
                    assert c['mesh'].rsplit('.',1)[-1]==row['mesh_name']
                    rect.update(source_handle=row['source_handle'],family=row['family'],
                        passage_variant=row['passage_variant'],width_inches=row['width_inches'],
                        original_transform=deepcopy(tr),category='rack_loaded_envelope')
                    racks.append(rect)
                elif actor['label'].startswith('MPR_ColumnBases_'):
                    rect['category']='column_base';bases.append(rect)
                elif actor['label'].startswith('MPR_Columns_'):
                    rect['category']='column_shaft';physical_columns.append(rect)
                else:
                    rect['category']='fixed_operation_or_floor_storage';fixed.append(rect)
    assert len(racks)==2867 and len({r['source_handle'] for r in racks})==2867
    assert len(bases)==len(physical_columns)==161
    nested_actor=next(a for a in snapshot['actors'] if a['label']=='MPR_CAD_NestedColumns_20261112')
    assert nested_actor['transform']==IDENTITY
    for i,row in enumerate(data['structure']['column_sections']):
        xy=[[row['center_m'][k]-row['size_m'][k]/2,row['center_m'][k]+row['size_m'][k]/2] for k in (0,1)]
        common=dict(actor_guid=nested_actor['guid'],actor_label=nested_actor['label'],source_handles=row['source_handles'])
        physical_columns.append(from_bounds('nested_shaft:'+str(i),xy+[[.26,12.2]],'column_shaft',**common))
        bases.append(from_bounds('nested_base:'+str(i),xy+[[0.,.26]],'column_base',**common))
    assert len(bases)==len(physical_columns)==303
    # The envelope clearance is a deliberate GHS design rule; it is stricter
    # than claiming that every low base intersects an actual shelf at that Z.
    column_clearance=[]
    shaft_by_center={tuple(round(v,5) for v in r['position_m']):r for r in physical_columns}
    assert len(shaft_by_center)==303
    for base in bases:
        shaft=shaft_by_center[tuple(round(v,5) for v in base['position_m'])]
        assert math.dist(base['position_m'],shaft['position_m'])<1.e-5
        rect=padded(base,CLEARANCE+NUMERIC_MARGIN)
        rect.update(id=base['id']+':clearance',category='column_base_plus_100mm',z_range_m=[0.,12.2])
        column_clearance.append(rect)
    for wall in data['walls']['solids']:
        if wall['bounds_m'][2][1]>.005:
            fixed.append(from_bounds('wall:'+wall['id'],wall['bounds_m'],'wall_or_door_solid',
                                     actor_guid=wall['actor_guid'],actor_label=wall['actor_label']))
    # Preserve the nearest existing rack clearance to every actual CAD door
    # opening, capped at the same 2 m GHS aisle policy. A convex buffered LINE
    # protects approach space as well as the door leaf, without inventing a
    # larger zone that the source layout itself cannot satisfy.
    doors=[]
    for door in data['layout']['dock_doors']+data['layout']['drive_in_doors']:
        x,y=door['position_m'];nx,ny=door['outward_normal_xy'];half=door['opening_width_m']/2
        doors.append(dict(id=door['id'],endpoints=[(x-ny*half,y+nx*half),(x+ny*half,y-nx*half)]))
    doors.extend(dict(id=d['id'],endpoints=d['opening_endpoints_m']) for d in data['pedestrian_openings'])
    polygons=[Polygon(corners(r)) for r in racks]
    for door in doors:
        line=LineString(door['endpoints'])
        distance=min(line.distance(poly) for poly in polygons)
        required=min(distance,2.)
        door.update(original_rack_clearance_m=distance,minimum_required_m=required)
        if required<.00001:continue
        poly=line.buffer(required-.000001,quad_segs=16)
        bb=poly.bounds
        fixed.append(dict(id='door_approach:'+door['id'],category='door_approach',
            position_m=[(bb[0]+bb[2])/2,(bb[1]+bb[3])/2],size_m=[bb[2]-bb[0],bb[3]-bb[1]],
            rotation_deg=0.,z_range_m=[0.,2.15],polygon_points=list(poly.exterior.coords)[:-1],
            door_line=door['endpoints'],required_distance_m=required))
    data['door_clearances']=doors
    return files,data,racks,physical_columns,bases,column_clearance,fixed


def group_rows(racks):
    groups=[]
    for axis in (0,1):
        candidates=[]
        for rack in racks:
            angle=rack['rotation_deg']%180
            normal=0 if abs(angle-90)<1.e-5 else 1
            assert normal==0 or min(abs(angle),abs(angle-180))<1.e-5
            if normal==axis:candidates.append(rack)
        for rack in sorted(candidates,key=lambda r:(r['original_transform']['translation_cm'][axis]*(1 if axis==0 else -1),r['source_handle'])):
            center=rack['original_transform']['translation_cm'][axis]/100*(1 if axis==0 else -1)
            if not groups or groups[-1]['axis']!=axis or center-groups[-1]['minimum_anchor_m']>GROUP_TOLERANCE:
                groups.append(dict(id='ROW_'+('X' if axis==0 else 'Y')+'_'+str(len(groups)).zfill(3),
                                   axis=axis,minimum_anchor_m=center,members=[]))
            groups[-1]['members'].append(rack)
    for group in groups:
        members=group['members'];axis=group['axis']
        anchors=[r['original_transform']['translation_cm'][axis]/100*(1 if axis==0 else -1) for r in members]
        group['anchor_m']=sum(anchors)/len(anchors)
        bb=[aabb(r) for r in members]
        group['bounds_m']=[[min(b[k][0] for b in bb),max(b[k][1] for b in bb)] for k in (0,1)]
        for r in members:r['row_id']=group['id']
    assert sum(len(g['members']) for g in groups)==2867
    return groups


def remap_axis(rect,axis):
    if axis==0:return rect
    result=dict(rect)
    result['position_m']=[rect['position_m'][1],rect['position_m'][0]]
    result['rotation_deg']=90-rect['rotation_deg']
    if rect.get('polygon_points'):result['polygon_points']=[[p[1],p[0]] for p in rect['polygon_points']]
    if rect.get('door_line'):result['door_line']=[[p[1],p[0]] for p in rect['door_line']]
    return result


def forbidden_shift(moving,fixed):
    if fixed.get('door_line'):
        # Exact Euclidean distance between an axis-aligned moving rectangle
        # and an axis-aligned door opening. Avoid polygon-buffer chord error
        # at corners, which can silently narrow an original door gap.
        bb=aabb(moving);line=fixed['door_line'];required=fixed['required_distance_m']
        lo=[min(p[k] for p in line) for k in (0,1)];hi=[max(p[k] for p in line) for k in (0,1)]
        assert min(hi[0]-lo[0],hi[1]-lo[1])<.000001
        perpendicular=max(lo[1]-bb[1][1],bb[1][0]-hi[1],0.)
        if perpendicular>=required-1.e-9:return None
        reach=math.sqrt(max(0.,required*required-perpendicular*perpendicular))
        return lo[0]-bb[0][1]-reach,hi[0]-bb[0][0]+reach
    if not fixed.get('polygon_points'):return forbidden_x_shift(moving,fixed)
    pa,pb=corners(moving),fixed['polygon_points'];lo,hi=-math.inf,math.inf
    for polygon in (pa,pb):
        for a,b in zip(polygon,polygon[1:]+polygon[:1]):
            nx,ny=-(b[1]-a[1]),b[0]-a[0]
            length=math.hypot(nx,ny)
            if length<1.e-10:continue
            nx,ny=nx/length,ny/length
            aa=[x*nx+y*ny for x,y in pa];bb=[x*nx+y*ny for x,y in pb]
            lower,upper=min(bb)-max(aa),max(bb)-min(aa)
            if abs(nx)<1.e-10:
                if lower>=-1.e-8 or upper<=1.e-8:return None
            else:
                a,b=sorted([lower/nx,upper/nx]);lo,hi=max(lo,a),min(hi,b)
                if lo>=hi-1.e-8:return None
    return lo,hi


def building_limits(group,polygon,max_shift):
    bounds=group['bounds_m'];axis=group['axis']
    def inside(shift):
        bb=deepcopy(bounds);bb[axis]=[v+shift for v in bb[axis]]
        return polygon.covers(shapely_box(bb[0][0],bb[1][0],bb[0][1],bb[1][1]))
    assert inside(0),('Original full row crosses building outline',group['id'],bounds)
    result=[]
    for sign in (-1,1):
        lo,hi=0.,max_shift
        if not inside(sign*hi):
            for _ in range(45):
                mid=(lo+hi)/2
                if inside(sign*mid):lo=mid
                else:hi=mid
        else:lo=hi
        result.append(sign*lo)
    return result


def solve(groups,columns,fixed,polygon,max_shift,existing_fixed):
    shifts={};details=[];gaps=[]
    retained_pairs={(r['rack_handle'],r['obstacle_id']) for r in existing_fixed}
    fixed_handles={r['rack_handle'] for r in existing_fixed}
    column_handles={r['rack_handle'] for r in contacts([r for g in groups for r in g['members']],columns)}
    for axis in (1,0):
        selected=sorted((g for g in groups if g['axis']==axis),key=lambda g:g['anchor_m'])
        other=[]
        for g in groups:
            if g['axis']==axis:continue
            for member in g['members']:
                r=deepcopy(member);r['position_m'][g['axis']]+=shifts.get(g['id'],0.);other.append(r)
        obstacles=columns+fixed+other;grid=Grid(obstacles)
        forbidden=[]
        for group in selected:
            blocked=[];causes=defaultdict(set)
            locked=bool({r['source_handle'] for r in group['members']} & fixed_handles)
            if locked:
                assert not ({r['source_handle'] for r in group['members']} & column_handles), 'Existing equipment overlap shares a column-conflicting row; requires explicit joint plan'
            for member in group['members']:
                bb=aabb(member);bb[axis]=[bb[axis][0]-max_shift,bb[axis][1]+max_shift]
                moving=remap_axis(member,axis)
                for obstacle in grid.query(bb):
                    if (member['source_handle'],obstacle['id']) in retained_pairs:
                        assert locked
                        continue
                    if not vertical_overlap(member,obstacle):continue
                    interval=forbidden_shift(moving,remap_axis(obstacle,axis))
                    if interval and interval[0]<max_shift and interval[1]>-max_shift:
                        blocked.append(interval);causes[obstacle['category']].add(obstacle['id'])
            limits=building_limits(group,polygon,max_shift)
            if locked:limits=[0.,0.]
            blocked.extend([(-math.inf,limits[0]),(limits[1],math.inf)])
            intervals=merge_intervals(blocked);forbidden.append(intervals)
            details.append(dict(row_id=group['id'],axis=axis,anchor_m=group['anchor_m'],
                member_count=len(group['members']),source_handles=[r['source_handle'] for r in group['members']],
                locked_due_to_unchanged_existing_equipment_contact=locked,
                building_allowed_shift_m=limits,
                forbidden_intervals_m=[[None if not math.isfinite(x) else x for x in pair] for pair in intervals],
                obstacle_counts={k:len(v) for k,v in causes.items()}))
        xs=[g['anchor_m'] for g in selected];separations=[]
        for i,(left,right) in enumerate(zip(selected,selected[1:])):
            old=right['bounds_m'][axis][0]-left['bounds_m'][axis][1]
            along=1-axis
            overlap_along=min(left['bounds_m'][along][1],right['bounds_m'][along][1])-max(left['bounds_m'][along][0],right['bounds_m'][along][0])>EPS
            required=min(old,2.) if overlap_along else 0.
            assert old>=-EPS,(left['id'],right['id'],'Different columns overlap')
            separations.append(xs[i+1]-xs[i]-old+required)
            gaps.append(dict(left_row=left['id'],right_row=right['id'],axis=axis,original_width_m=old,
                minimum_required_m=required,classification=('back_to_back_gap' if old<1. else 'longitudinal_aisle') if overlap_along else 'separate_longitudinal_ranges'))
        chosen=solve_rows(xs,forbidden,separations,step=.001,max_shift=max_shift)
        for group,shift in zip(selected,chosen):shifts[group['id']]=shift
    return shifts,details,gaps


def run(max_shift=2.,audit_only=False):
    files,data,racks,shafts,bases,columns,fixed=load_inputs();groups=group_rows(racks)
    initial=dict(shaft_envelope_contacts=contacts(racks,shafts),
                 column_clearance_contacts=contacts(racks,columns),fixed_contacts=contacts(racks,fixed))
    summary=dict(rack_instances=len(racks),whole_rows=len(groups),row_axes=dict(Counter(g['axis'] for g in groups)),
        column_positions=len(columns),fixed_obstacles=len(fixed),
        before_shaft_envelope_contacts=len(initial['shaft_envelope_contacts']),
        before_column_clearance_contacts=len(initial['column_clearance_contacts']),
        before_fixed_contacts=len(initial['fixed_contacts']))
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    OUT.mkdir(parents=True,exist_ok=True)
    input_hashes={path.relative_to(ROOT).as_posix():sha(path) for path in files.values()}
    if audit_only:
        (OUT/'initial_contacts.json').write_text(json.dumps(dict(summary=summary,contacts=initial),ensure_ascii=False,indent=2),encoding='utf8')
        return
    polygon=Polygon(data['layout']['footprint_outline_m'])
    assert polygon.is_valid
    shifts,details,gaps=solve(groups,columns,fixed,polygon,max_shift,initial['fixed_contacts'])
    updated=[];placements=[]
    for group in groups:
        delta=shifts[group['id']];axis=group['axis']
        for original in group['members']:
            r=deepcopy(original);r['position_m'][axis]+=delta;updated.append(r)
            transform=deepcopy(original['original_transform'])
            transform['translation_cm'][axis]+=delta*100*(1 if axis==0 else -1)
            placements.append(dict(source_handle=r['source_handle'],row_id=group['id'],actor_guid=r['actor_guid'],
                actor_label=r['actor_label'],component_name=r['component_name'],instance_index=r['instance_index'],
                mesh=r['mesh'],family=r['family'],passage_variant=r['passage_variant'],width_inches=r['width_inches'],
                original_transform=original['original_transform'],proposed_transform=transform,
                displacement_cad_m=[delta if axis==k else 0. for k in (0,1)],
                original_bounds_cad_m=aabb(original),proposed_bounds_cad_m=aabb(r)))
    after_columns=contacts(updated,columns);after_fixed=contacts(updated,fixed)
    before_fixed_keys={(r['rack_handle'],r['obstacle_id']) for r in initial['fixed_contacts']}
    new_fixed=[r for r in after_fixed if (r['rack_handle'],r['obstacle_id']) not in before_fixed_keys]
    placement_by_handle={r['source_handle']:r for r in placements}
    assert all(placement_by_handle[r['rack_handle']]['original_transform']==placement_by_handle[r['rack_handle']]['proposed_transform'] for r in after_fixed)
    for gap in gaps:
        gap['new_width_m']=gap['original_width_m']+shifts[gap['right_row']]-shifts[gap['left_row']]
        assert gap['new_width_m']+EPS>=gap['minimum_required_m']
    for row in details:row['shift_m']=shifts[row['row_id']]
    # Independently inspect cross-row rack pairs; shared end frames in the same
    # rigid column are an existing CAD construction relation, not new overlaps.
    grid=Grid(updated);pairs=[];seen=set()
    for rack in updated:
        assert polygon.covers(Polygon(corners(rack))),rack['source_handle']
        for other in grid.query(aabb(rack)):
            key=tuple(sorted([rack['source_handle'],other['source_handle']]))
            if key in seen or rack['row_id']==other['row_id']:continue
            seen.add(key)
            if overlap(rack,other):pairs.append(key)
    summary.update(moved_rows=sum(abs(x)>EPS for x in shifts.values()),
        moved_instances=sum(any(abs(x)>EPS for x in r['displacement_cad_m']) for r in placements),
        maximum_displacement_m=max(map(abs,shifts.values())),total_row_displacement_m=sum(map(abs,shifts.values())),
        after_column_clearance_contacts=len(after_columns),after_fixed_contacts=len(after_fixed),new_fixed_contacts=len(new_fixed),cross_row_rack_contacts=len(pairs))
    result=dict(schema_version=1,map=data['baseline']['map'],map_sha256=data['baseline']['map_file_sha256'],
        status='geometry_verified' if not after_columns and not new_fixed and not pairs else 'blocked',
        input_sha256=input_hashes,source_cad_sha256=data['placement']['source_sha256'],summary=summary,
        policy=dict(whole_row_translation_only=True,source_cad_unchanged=True,retain_2867_instances=True,
            fixed_columns_and_operations=True,rotation_scale_height_unchanged=True,geometry_materials_unchanged=True,
            maximum_shift_m=max_shift,solver_grid_m=.001,objective='Sum(abs(row_shift)+0.05*row_shift^2), GHS prefix-minimum dynamic program',
            column_base_clearance_m=CLEARANCE,numeric_margin_m=NUMERIC_MARGIN,
            aisle_rule='Preserve original width if below 2m; retain at least 2m otherwise. Back-to-back gaps never shrink.',
            grouping_tolerance_m=GROUP_TOLERANCE),
        rows=details,aisles=gaps,door_clearances=data['door_clearances'],instances=placements,before=initial,
        after=dict(column_clearance_contacts=after_columns,fixed_contacts=after_fixed,new_fixed_contacts=new_fixed,cross_row_rack_contacts=pairs),
        limitations=['Loaded mesh XY envelopes conservatively contain cargo and frames; shaft contacts are envelope contacts, not a triangle intersection claim.',
            'The GHS 100mm column-base margin is a visualization clearance policy, not a certified operating or fire-code clearance.',
            'Current native equipment bounds are conservative solids; all source wall boxes retain door/window voids.',
            'Four pre-existing southern rack/conveyor envelope contacts are retained exactly with the entire affected non-column-conflicting row locked at its original pose; no new or deepened contact is allowed.',
            'Integration must match every original actor/component/instance transform before applying and independently verify unchanged scene scope.'])
    (OUT/'placement_plan.json').write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')),encoding='utf8')
    (OUT/'summary.json').write_text(json.dumps(dict(status=result['status'],summary=summary,rows=details,aisles=gaps),ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    assert result['status']=='geometry_verified',result['after']
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--max-shift',type=float,default=2.)
    parser.add_argument('--audit-only',action='store_true')
    parser.add_argument('--archived-inputs',action='store_true',help='Reproduce from the checked-in native JSON evidence')
    args=parser.parse_args()
    evidence.USE_ARCHIVE=args.archived_inputs
    run(args.max_shift,args.audit_only)
