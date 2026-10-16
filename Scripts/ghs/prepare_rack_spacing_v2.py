"""Independent CAD rack restoration and constrained X spacing plan.

Does not modify the source CAD, old mapping, mesh manifest, registry, or reports.
CAD local X is rack depth and local Y is bay span; all output uses CAD XY metres.
"""
import bisect
import collections
import copy
import hashlib
import json
import math
from pathlib import Path

from plan_clearance_fix import corners, overlap, trim_shared_end_frames, collision_pairs

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'SourceAssets/GHS'
OUT = SOURCE / 'RefinementV2/Layout'
EPS = 1e-8
MAX_SHIFT = .999
PALLET_DEPTH = 1.2192
COLUMN_BASE_CLEARANCE = .1
NUMERIC_MARGIN = .0002


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def forbidden_x_shift(moving, fixed):
    """Exact open displacement interval in which two 2D OBBs penetrate.

    Their orientation and Y stay fixed, only the moving rectangle's X changes.
    Derived by intersecting overlap inequalities on every SAT separating axis.
    """
    pa, pb = corners(moving), corners(fixed)
    lo, hi = -math.inf, math.inf
    for e in (moving, fixed):
        a = math.radians(e.get('rotation_deg', 0))
        for nx, ny in ((math.cos(a), math.sin(a)), (-math.sin(a), math.cos(a))):
            aa = [x * nx + y * ny for x, y in pa]
            bb = [x * nx + y * ny for x, y in pb]
            lower, upper = min(bb) - max(aa), max(bb) - min(aa)
            if abs(nx) < 1e-10:
                if lower >= -EPS or upper <= EPS:
                    return None
            else:
                u, v = sorted((lower / nx, upper / nx))
                lo, hi = max(lo, u), min(hi, v)
                if lo >= hi - EPS:
                    return None
    return lo, hi


def merge_intervals(intervals):
    merged = []
    for lo, hi in sorted(intervals):
        if merged and lo < merged[-1][1] - EPS:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    return merged


def solve_rows(xs, forbidden, separations, step=.001, max_shift=MAX_SHIFT):
    """Global minimum weighted displacement, preserving ordered row separation.

    A one-dimensional dynamic program uses prefix minima for O(rows*candidates)
    transitions. The only approximation is the explicitly reported 1mm grid.
    """
    bound = int(round(max_shift / step))
    shifts = [round(i * step, 9) for i in range(-bound, bound + 1)]
    previous, paths = None, []
    for i, x in enumerate(xs):
        current, trace = [math.inf] * len(shifts), [-1] * len(shifts)
        if i:
            best_cost, best_index, cursor = math.inf, -1, 0
        for k, shift in enumerate(shifts):
            if i:
                limit = x + shift - xs[i - 1] - separations[i - 1]
                while cursor < len(shifts) and shifts[cursor] <= limit + EPS:
                    if previous[cursor] < best_cost:
                        best_cost, best_index = previous[cursor], cursor
                    cursor += 1
            if any(lo + EPS < shift < hi - EPS for lo, hi in forbidden[i]):
                continue
            cost = abs(shift) + .05 * shift * shift
            if not i:
                current[k] = cost
            elif best_index >= 0:
                current[k], trace[k] = best_cost + cost, best_index
        previous = current
        paths.append(trace)
    k = min(range(len(shifts)), key=lambda n: previous[n])
    if not math.isfinite(previous[k]):
        raise RuntimeError('No arrangement satisfies the sub-1m displacement and aisle constraints')
    result = []
    for i in reversed(range(len(xs))):
        result.append(shifts[k])
        k = paths[i][k]
    return result[::-1]


def footprint(row, padded=0):
    return dict(id=row['instance_id'], position_m=row['position_m'][:2],
                size_m=[max(row['physical_depth_m'], PALLET_DEPTH) + padded * 2,
                        row['physical_span_m'] + padded * 2],
                rotation_deg=row['rotation_deg'])


def minimum_ground_block_aisle(ground):
    grouped=collections.defaultdict(list)
    for e in ground:
        grouped[e['presentation_block_id']].extend(corners(e))
    bounds=[[[min(p[k] for p in points),max(p[k] for p in points)] for k in range(2)]
            for points in grouped.values()]
    gaps=[]
    for i,a in enumerate(bounds):
        for b in bounds[i+1:]:
            for axis in (0,1):
                other=1-axis
                if min(a[other][1],b[other][1])-max(a[other][0],b[other][0])>EPS:
                    gap=max(a[axis][0]-b[axis][1],b[axis][0]-a[axis][1])
                    if gap>EPS:gaps.append(gap)
    return min(gaps)


def load_restored(mapping):
    physical = read(SOURCE / 'physical_bounds_proposed.json')
    trim_shared_end_frames({'racks': physical['racks']})
    originals = {r['id']: r for r in physical['racks']}
    by_parent = collections.defaultdict(list)
    for row in mapping['assignments'] + mapping['additional_pass_racks']:
        by_parent[row['parent_cad_id']].append(row)
    result = []
    for parent, previous in by_parent.items():
        row = copy.deepcopy(previous[0])
        split = any('_ClearanceSeg_' in r['instance_id'] for r in previous)
        if split:
            original = originals[parent]
            row.update(instance_id=parent, position_m=original['position_m'],
                       physical_span_m=original['size_m'][1],
                       physical_depth_m=original['size_m'][0])
        row['id'] = row['instance_id']
        row['parent_ids'] = [parent]
        row['replaces_instance_ids'] = [r['instance_id'] for r in previous]
        row['restored_column_split'] = split
        row['pre_v2_position_m'] = list(row['position_m'])
        row['source_center_m'] = list(row.get('source_physical_center_m', row['physical_center_m']))
        row['mapping_key'] = '%s:%d:%.4f' % (row['spec_type'], row['pass_variant'], row['physical_span_m'])
        result.append(row)
    return result


def propose_ground(layout, racks, registry):
    """Restore full loads by redistributing each original block's X clearances.

    Every block retains its original outer rectangle and every pallet its Y.
    Therefore none of the main aisles between blocks can be narrowed or crossed.
    """
    columns = []
    for col in layout['columns']:
        e = copy.deepcopy(col)
        e['size_m'] = [n + .3 + 2 * NUMERIC_MARGIN for n in e['size_m']]
        columns.append(e)
    existing = {r['id']: r for r in layout['storage']}
    blocked_ids = {r['id'] for r in layout['blocked_storage']}
    blocks, by_id = [], {}
    for block in registry['presentation']['cargo_blocks']:
        members = [copy.deepcopy(existing[id]) for id in block['slot_ids']]
        points = [p for e in members for p in corners(e)]
        bounds = [[min(p[k] for p in points),max(p[k] for p in points)] for k in range(2)]
        b = dict(block, members=members, original_bounds_m=bounds)
        blocks.append(b)
        by_id[block['id']] = b
    for old in layout['blocked_storage']:
        x,y = old['position_m']
        matches = [b for b in blocks if b['original_bounds_m'][0][0]-EPS<x<b['original_bounds_m'][0][1]+EPS
                   and b['original_bounds_m'][1][0]-EPS<y<b['original_bounds_m'][1][1]+EPS]
        assert len(matches)==1,(old['id'],'ambiguous original block',len(matches))
        matches[0]['members'].append(copy.deepcopy(old))
    output, changes = [], []
    static = columns + layout['equipment'] + [footprint(r) for r in racks]
    for block in blocks:
        members = block['members']
        assert len(members)==block['all_cad_slot_count'],block['id']
        assert all(abs(e['rotation_deg'])<EPS for e in members)
        lo,hi = block['original_bounds_m'][0]
        groups = collections.defaultdict(list)
        for e in members:
            groups[round(e['position_m'][0],3)].append(e)
        ordered = sorted(groups)
        xs = [sum(e['position_m'][0] for e in groups[x])/len(groups[x]) for x in ordered]
        forbidden=[]
        for key in ordered:
            intervals=[]
            for e in groups[key]:
                x,y=e['position_m'];half=e['size_m'][0]/2
                intervals.extend([(-math.inf,lo+half-x),(hi-half-x,math.inf)])
                for obstacle in static:
                    if abs(obstacle['position_m'][0]-x)>5 or abs(obstacle['position_m'][1]-y)>5:
                        continue
                    interval=forbidden_x_shift(e,obstacle)
                    if interval and interval[0]<MAX_SHIFT and interval[1]>-MAX_SHIFT:
                        intervals.append(interval)
            forbidden.append(merge_intervals(intervals))
        # Preserve a visible 20mm side gap, taking the needed width solely from
        # the original 330.2mm spaces between neighboring pallet columns.
        separations=[1.036 for _ in range(len(xs)-1)]
        try:
            moves=solve_rows(xs,forbidden,separations)
        except RuntimeError as error:
            raise RuntimeError('Ground block '+block['id']+' cannot restore all slots inside its original footprint with sub-1m X movement') from error
        for i,key in enumerate(ordered):
            for e in groups[key]:
                original=list(e['position_m'])
                e['position_m'][0]+=moves[i]
                e.update(original_position_m=original,displacement_m=[moves[i],0.],
                         displacement_distance_m=abs(moves[i]),was_blocked=e['id'] in blocked_ids,
                         presentation_block_id=block['id'],presentation_variant=block['variant'],
                         policy='Full CAD-size load; block-internal X column spacing; original block boundary and all Y anchors retained')
                assert all(block['original_bounds_m'][k][0]-EPS<=p[k]<=block['original_bounds_m'][k][1]+EPS
                           for p in corners(e) for k in range(2)),(block['id'],e['id'])
                output.append(e)
        if any(abs(v)>EPS for v in moves):
            changes.append(dict(block_id=block['id'],original_bounds_m=block['original_bounds_m'],
                                slot_count=len(members),restored_count=sum(e['id'] in blocked_ids for e in members),
                                column_original_x_m=xs,column_dx_m=moves,
                                minimum_internal_side_gap_m=min(xs[i+1]+moves[i+1]-xs[i]-moves[i]-1.016 for i in range(len(xs)-1))))
    assert len(output)==7530 and len({e['id'] for e in output})==7530
    proposed=[e for e in output if e['was_blocked'] or e['displacement_distance_m']>EPS]
    return output,proposed,[],changes


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    mapping = read(SOURCE / 'RackSpecs/cad_plan_mapping.json')
    layout = read(SOURCE / 'clearance_layout.json')
    registry = read(SOURCE / 'ue_scene_registry.json')
    racks = load_restored(mapping)
    rows = collections.defaultdict(list)
    for row in racks:
        if abs(row['rotation_deg']) < .001 and row['position_m'][0] < 0:
            rows[round(row['position_m'][0], 3)].append(row)
    ordered = sorted(rows)
    xs = [sum(r['position_m'][0] for r in rows[key])/len(rows[key]) for key in ordered]
    row_ids = {r['instance_id'] for key in ordered for r in rows[key]}
    fixed_racks = [footprint(r, NUMERIC_MARGIN) for r in racks if r['instance_id'] not in row_ids]
    columns = []
    for group in registry['groups']:
        if group['actor'] != 'GHS_ColumnBases':
            continue
        for r in group['instances']:
            columns.append(dict(id=r['id'],position_m=r['position_m'][:2],rotation_deg=r['rotation_deg'],
                                size_m=[v+2*(COLUMN_BASE_CLEARANCE+NUMERIC_MARGIN) for v in r['scale'][:2]]))
    assert len(columns) == 170
    # Only obstacles within the bounded horizontal motion can forbid a candidate.
    obstacles = columns + layout['storage'] + layout['equipment'] + fixed_racks
    intervals = []
    for key in ordered:
        forbidden = []
        for row in rows[key]:
            moving = footprint(row)
            for obstacle in obstacles:
                if abs(obstacle['position_m'][0]-moving['position_m'][0]) > 8:
                    continue
                blocked = forbidden_x_shift(moving, obstacle)
                if blocked and blocked[0] < MAX_SHIFT and blocked[1] > -MAX_SHIFT:
                    forbidden.append(blocked)
        intervals.append(merge_intervals(forbidden))
    old_gaps = [xs[i+1]-xs[i]-PALLET_DEPTH for i in range(len(xs)-1)]
    required_gaps = [gap if gap < 1 else min(gap,2.0) for gap in old_gaps]
    separations = [PALLET_DEPTH+gap for gap in required_gaps]
    shifts = solve_rows(xs, intervals, separations)
    changes = []
    for i,key in enumerate(ordered):
        for row in rows[key]:
            row['position_m'][0] += shifts[i]
        changes.append(dict(row_index=i,row_codes=sorted({r.get('row_code','') for r in rows[key]}),
                            original_x_m=xs[i],new_x_m=xs[i]+shifts[i],dx_m=shifts[i],
                            bay_count=len(rows[key]),restored_bay_count=sum(r['restored_column_split'] for r in rows[key]),
                            forbidden_dx_intervals_m=intervals[i]))
    for row in racks:
        row['physical_center_m'] = list(row['position_m'])
        row['displacement_from_cad_center_m'] = [row['position_m'][i]-row['source_center_m'][i] for i in range(2)]
        row['spacing_displacement_m'] = [row['position_m'][i]-row['pre_v2_position_m'][i] for i in range(2)]
        row['clearance_adjustment'] = 'V2: complete original bay; constrained row X spacing with full-size loads and fixed CAD columns'
        row['geometry_policy'] = row['clearance_adjustment']
        row['physical_envelope_depth_m'] = max(row['physical_depth_m'],PALLET_DEPTH)
    gaps = [dict(left_row=i,right_row=i+1,classification='back_to_back_gap' if old_gaps[i]<1 else 'longitudinal_aisle',
                 original_width_m=old_gaps[i],new_width_m=xs[i+1]+shifts[i+1]-xs[i]-shifts[i]-PALLET_DEPTH,
                 minimum_required_m=required_gaps[i]) for i in range(len(xs)-1)]
    # Full loaded footprints are stricter than solid-only checks. They include
    # pass empty space too, so no volume is excused in this final validation.
    collisions = collision_pairs({'rack_loaded_envelope':[footprint(r) for r in racks],
                                  'columns_with_100mm_base_clearance':columns,
                                  'ground_storage':layout['storage'],'loading_doors':layout['equipment']})
    rack_collisions = [p for p in collisions if 'rack_loaded_envelope' in (p['a_category'],p['b_category'])]
    ground, proposed_ground, unresolved_ground, ground_changes = propose_ground(layout,racks,registry)
    all_ground_checks = collision_pairs({'ground_storage_v2':ground,
                                         'columns_with_100mm_base_clearance':columns,
                                         'rack_loaded_envelope':[footprint(r) for r in racks],
                                         'loading_doors':layout['equipment']})
    ground_collisions = [p for p in all_ground_checks if 'ground_storage_v2' in (p['a_category'],p['b_category'])]
    source_files = ['RackSpecs/cad_plan_mapping.json','clearance_layout.json','physical_bounds_proposed.json','ue_scene_registry.json']
    result = dict(schema_version=2,coordinate_contract=mapping['coordinate_contract'],
                  status='geometry_verified' if not rack_collisions and not ground_collisions else 'blocked_by_collision',
                  source_sha256={p:hashlib.sha256((SOURCE/p).read_bytes()).hexdigest() for p in source_files},
                  policy=dict(max_row_displacement_m=MAX_SHIFT,solver_grid_m=.001,
                              column_base_clearance_m=COLUMN_BASE_CLEARANCE,numeric_margin_m=NUMERIC_MARGIN,
                              full_size_pallet_depth_m=PALLET_DEPTH,min_longitudinal_aisle_m=2.0,
                              preserve_all_rack_y=True,preserve_cad_columns=True,preserve_ground_block_boundaries=True,
                              shared_frame_trim_is_not_cargo_scaling=True),
                  summary=dict(previous_rack_instances=1639,new_rack_instances=len(racks),
                               restored_original_bays=sum(r['restored_column_split'] for r in racks),
                               retired_split_instances=sum(len(r['replaces_instance_ids']) for r in racks if r['restored_column_split']),
                               translated_rows=sum(abs(v)>EPS for v in shifts),translated_rack_instances=sum(abs(r['spacing_displacement_m'][0])>EPS for r in racks),
                               maximum_row_displacement_m=max(map(abs,shifts)),
                               narrowest_longitudinal_aisle_m=min(g['new_width_m'] for g in gaps if g['classification']=='longitudinal_aisle'),
                               narrowest_back_to_back_gap_m=min(g['new_width_m'] for g in gaps if g['classification']=='back_to_back_gap'),
                               rack_envelope_collision_count=len(rack_collisions),
                               blocked_ground_slots=len(layout['blocked_storage']),restored_ground_slots=sum(e['was_blocked'] for e in ground),
                               unresolved_ground_slots=len(unresolved_ground),restored_ground_collision_count=len(ground_collisions),
                               moved_existing_ground_slots=sum(not e['was_blocked'] and e['displacement_distance_m']>EPS for e in ground),
                               ground_total_count=len(ground),changed_ground_blocks=len(ground_changes),
                               maximum_ground_displacement_m=max(e['displacement_distance_m'] for e in ground),
                               narrowest_ground_interblock_aisle_m=minimum_ground_block_aisle(ground),
                               minimum_ground_internal_side_gap_m=min(b['minimum_internal_side_gap_m'] for b in ground_changes),
                               type_counts=dict(collections.Counter(r['spec_type']+('_PASS' if r['pass_variant'] else '') for r in racks))),
                  racks=racks,row_changes=changes,transverse_gaps=gaps,
                  mapping_key_counts=dict(collections.Counter(r['mapping_key'] for r in racks)),
                  rack_collisions=rack_collisions,groundcargo=ground,proposed_groundcargo=proposed_ground,
                  ground_block_changes=ground_changes,
                  unresolved_groundcargo=unresolved_ground,restored_ground_collisions=ground_collisions,
                  limitations=['This validates complete loaded XY envelopes against fixed geometry; imported UE bounds must be checked after integration.',
                               'Ground row Y and each original block outer rectangle are retained exactly, protecting all inter-block aisles.',
                               'Longitudinal aisle widths measure free space between full cargo envelopes; pass bridge clear spans retain their mapped widths.'])
    (OUT/'rack_spacing.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result['summary'],indent=2))
    if rack_collisions or ground_collisions:
        print(json.dumps(dict(rack_collisions=rack_collisions[:12],ground_collisions=ground_collisions[:12]),indent=2))
        raise RuntimeError('V2 candidate has collisions; report preserved for inspection, not ready for integration')
    assert len(racks)==1629 and sum(r['pass_variant'] for r in racks)==58
    assert all(abs(r['spacing_displacement_m'][1])<EPS for r in racks)
    assert all(g['new_width_m']+EPS>=g['minimum_required_m'] for g in gaps)
    return result


if __name__ == '__main__':
    run()
