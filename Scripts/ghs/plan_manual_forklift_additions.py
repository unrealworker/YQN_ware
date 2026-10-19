"""Plan four additions against the current, possibly unsaved, warehouse.

Offline only.  Does not import Unreal, modify existing actors, or resurrect
deleted vehicles.  Run with Python -B to avoid writing helper bytecode.
"""
import collections
import hashlib
import itertools
import json
import math
from pathlib import Path

from plan_normal_stackers import SpatialGrid, intersects, xy_gap, z_overlap
from plan_manned_forklift_fleet import excluded, finite_box, footprint_samples, transformed_box

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / 'Saved/GHS_ManualFollowupProbe.json'
MODEL = ROOT / 'SourceAssets/GHS_Normal/MannedForklift/manned_forklift_50k_import_manifest.json'
OUTPUT = ROOT / 'Saved/GHS_ManualForkliftAdditionsPlan.json'
MAP = '/Game/Maps/GHS_CAD_NormalWarehouse'
CARGO_LABELS = {'GHS_CAD_PalletCargo', 'GHS_CAD_PalletCargoLow', 'GHS_CAD_PalletCargoHigh'}
MIN_SOLID_GAP = 50.0
MIN_OLD_VEHICLE_GAP = 600.0
MIN_NEW_VEHICLE_GAP = 2000.0


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contains_xy(point, triangle):
    a, b, c = triangle
    x, y = point
    den = (b[1]-c[1])*(a[0]-c[0]) + (c[0]-b[0])*(a[1]-c[1])
    if abs(den) < 1e-8:
        return False
    u = ((b[1]-c[1])*(x-c[0]) + (c[0]-b[0])*(y-c[1])) / den
    v = ((c[1]-a[1])*(x-c[0]) + (a[0]-c[0])*(y-c[1])) / den
    return min(u, v, 1-u-v) >= -1e-8


def floor_check(bounds, triangles):
    samples = footprint_samples(bounds)
    covered = [any(contains_xy(p, t) for t in triangles) for p in samples]
    return dict(passed=all(covered), sample_count=9, samples_xy_cm=samples,
                covered=covered, source='current floor top triangles')


def vehicle_kind(item):
    label, mesh, tags = item['label'], item.get('mesh', ''), item.get('tags', [])
    if 'NormalWarehouseMannedForklift' in tags or 'MannedForklift' in mesh:
        return 'manual_forklift'
    if 'NormalWarehouseFloorStacker' in tags or 'SM_VR_BlueStacker' in mesh:
        return 'stacker'
    if 'IndependentDockTruck' in tags or label.startswith('GHS_DockTruck_'):
        return 'dock_truck'
    if label.startswith('GHS_AGV_') or 'SM_GHS_KUKA' in mesh:
        return 'agv'
    return None


def nearest(bounds, records):
    records = [r for r in records if z_overlap(bounds, r['bounds_cm'])]
    if not records:
        return None
    record = min(records, key=lambda r: xy_gap(bounds, r['bounds_cm']))
    return dict(record, clearance_cm=xy_gap(bounds, record['bounds_cm']))


def candidate(target, side, yaw, local, grid, wall_grid, vehicles, floor):
    """Park adjacent to an exposed live pallet face, never at fixed coordinates."""
    b = target['bounds_cm']
    rot = transformed_box(local, [0., 0., 0.], yaw)
    parallel = yaw in (0., 180.)
    x = (b[0]+b[3]-rot[0]-rot[3])/2
    y = b[1]-MIN_SOLID_GAP-rot[4] if side == 'south' else b[4]+MIN_SOLID_GAP-rot[1]
    position = [x, y, .5-local[2]]
    bounds = transformed_box(local, position, yaw)
    nearby = grid.query(bounds, MIN_SOLID_GAP)
    if any(z_overlap(bounds, o['bounds_cm']) and xy_gap(bounds, o['bounds_cm']) < MIN_SOLID_GAP-1e-4 for o in nearby):
        return None
    if any(xy_gap(bounds, o['bounds_cm']) < MIN_OLD_VEHICLE_GAP for o in vehicles):
        return None
    if any(z_overlap(bounds, o['bounds_cm']) and xy_gap(bounds, o['bounds_cm']) < MIN_SOLID_GAP-1e-4
           for o in wall_grid.query(bounds, MIN_SOLID_GAP)):
        return None
    if not floor_check(bounds, floor)['passed']:
        return None
    # Keep an uninterrupted walking/driving strip on the free aisle side.
    # Parallel vehicles in cross aisles retain 2.5 m; head-on work retains 2 m.
    width = 250. if parallel else 200.
    passage = bounds[:]
    passage[0] -= 100.
    passage[3] += 100.
    if side == 'south':
        passage[1], passage[4] = bounds[1]-width, bounds[1]-.01
    else:
        passage[1], passage[4] = bounds[4]+.01, bounds[4]+width
    if any(intersects(passage, o['bounds_cm']) for o in grid.query(passage)):
        return None
    if any(intersects(passage, o['bounds_cm']) for o in wall_grid.query(passage)):
        return None
    if not floor_check(passage, floor)['passed']:
        return None
    return dict(position_cm=position, yaw_deg=yaw, scale=[1., 1., 1.], bounds_cm=bounds,
                target=target, target_clearance_cm=xy_gap(bounds, b),
                target_face=side, mode='parallel_aisle' if parallel else 'forks_toward_pallet',
                clear_passage=dict(bounds_cm=passage, minimum_depth_cm=width,
                                   checked_length_cm=passage[3]-passage[0], empty=True,
                                   purpose='continuous_cross_aisle' if parallel else 'rear_work_aisle'))


def main():
    probe, model = read(PROBE), read(MODEL)
    source_sha = sha(PROBE)
    assert probe['map'].split('.')[0] == MAP
    assert model['triangles'] <= 50000
    bm = model['bounds_m']
    local = [bm[0][0]*100, -bm[1][1]*100, bm[2][0]*100,
             bm[0][1]*100, -bm[1][0]*100, bm[2][1]*100]
    assert finite_box(local)
    obstacles, exclusions = [], []
    for item in probe['items']:
        reason = excluded(item)
        if '/EditorMeshes/' in item.get('mesh', ''):
            reason = 'editor_visualization'
        if reason:
            exclusions.append(dict(label=item['label'], component=item.get('component'), reason=reason))
            continue
        for instance in item['instances']:
            assert finite_box(instance['bounds'])
            obstacles.append(dict(label=item['label'], path=item.get('path'),
                                  component=item.get('component'), index=instance['index'],
                                  mesh=item['mesh'], bounds_cm=instance['bounds'],
                                  vehicle_kind=vehicle_kind(item)))
    cargo = [o for o in obstacles if o['label'] in CARGO_LABELS]
    vehicles = [o for o in obstacles if o['vehicle_kind']]
    manuals = [o for o in vehicles if o['vehicle_kind'] == 'manual_forklift']
    walls = probe['walls']
    floor = probe['floor']
    assert len(manuals) == 12 and len(probe['forklifts']) == 12, 'Baseline changed; inspect before changing count'
    assert cargo and walls and floor
    for wall in walls:
        assert finite_box(wall['bounds_cm'])
    grid, wall_grid = SpatialGrid(obstacles), SpatialGrid(walls)
    candidates, seen = [], set()
    for target in cargo:
        for side, yaw in (('south', 90.), ('north', -90.), ('south', 0.), ('north', 180.)):
            c = candidate(target, side, yaw, local, grid, wall_grid, vehicles, floor)
            if c is None:
                continue
            key = tuple(round(v, 3) for v in c['bounds_cm']) + (yaw,)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(c)
    assert len(candidates) >= 4, ('Insufficient candidates', len(candidates))
    selected = []
    for number in range(13, 17):
        def compatible(c):
            return all(xy_gap(c['bounds_cm'], p['bounds_cm']) >= MIN_NEW_VEHICLE_GAP
                       and not intersects(c['clear_passage']['bounds_cm'], p['bounds_cm'])
                       and not intersects(p['clear_passage']['bounds_cm'], c['bounds_cm'])
                       for p in selected)
        eligible = [c for c in candidates if compatible(c)]
        assert eligible, 'Four well-separated additions do not fit current scene'
        # Greedy farthest-point sampling fills the least-covered ground-storage
        # areas first, taking every user copy into account by physical bounds.
        def score(c):
            others = manuals + selected
            distance = min(xy_gap(c['bounds_cm'], p['bounds_cm']) for p in others)
            return (distance, c['mode'] == 'forks_toward_pallet', -c['position_cm'][0])
        pick = max(eligible, key=score)
        pick['coverage_score_cm'] = score(pick)[0]
        pick['label'] = pick['twin_id'] = 'GHN_MannedForklift_%02d' % number
        assert not any(o['label'] == pick['label'] for o in obstacles)
        selected.append(pick)
    # Final independent all-record checks, not spatial-index-only evidence.
    for pick in selected:
        b, passage = pick['bounds_cm'], pick['clear_passage']['bounds_cm']
        pick['nearest_obstacle'] = nearest(b, obstacles)
        pick['nearest_existing_vehicle'] = nearest(b, vehicles)
        pick['nearest_existing_manual_forklift'] = nearest(b, manuals)
        pick['nearest_wall_triangle'] = nearest(b, walls)
        assert pick['nearest_obstacle']['clearance_cm'] >= MIN_SOLID_GAP-1e-4
        assert pick['nearest_existing_vehicle']['clearance_cm'] >= MIN_OLD_VEHICLE_GAP
        assert pick['nearest_wall_triangle']['clearance_cm'] >= MIN_SOLID_GAP-1e-4
        assert not any(intersects(passage, o['bounds_cm']) for o in obstacles+walls)
        pick['floor_check'] = floor_check(b, floor)
        pick['clear_passage']['floor_check'] = floor_check(passage, floor)
        assert pick['floor_check']['passed'] and pick['clear_passage']['floor_check']['passed']
        pick['wall_check'] = dict(passed=True, triangle_aabbs_checked=len(walls),
                                  minimum_clearance_cm=pick['nearest_wall_triangle']['clearance_cm'])
        pick['clear_passage']['wall_check'] = dict(passed=True, triangle_aabbs_checked=len(walls))
    pairwise = [dict(a=a['label'], b=b['label'], clearance_cm=xy_gap(a['bounds_cm'], b['bounds_cm']))
                for a, b in itertools.combinations(selected, 2)]
    assert min(p['clearance_cm'] for p in pairwise) >= MIN_NEW_VEHICLE_GAP
    assert sha(PROBE) == source_sha, 'Probe changed during planning'
    summary = dict(additional_manual_forklifts=4, current_manual_forklifts=len(manuals),
                   resulting_manual_forklifts=16, valid_candidates=len(candidates),
                   current_vehicle_counts=dict(collections.Counter(o['vehicle_kind'] for o in vehicles)),
                   obstacle_instances=len(obstacles), wall_triangle_aabbs=len(walls), floor_triangles=len(floor),
                   minimum_solid_clearance_cm=min(p['nearest_obstacle']['clearance_cm'] for p in selected),
                   minimum_existing_vehicle_clearance_cm=min(p['nearest_existing_vehicle']['clearance_cm'] for p in selected),
                   minimum_addition_pair_clearance_cm=min(p['clearance_cm'] for p in pairwise))
    report = dict(schema_version=1, success=True, offline_plan_only=True, map=MAP,
                  source_probe=str(PROBE), source_probe_sha=source_sha, source_probe_sha256=source_sha,
                  source_actor_count=probe['actor_count'], source_dirty_maps=probe['dirty_maps'],
                  source_dirty_content=probe.get('dirty_content', []), source_model_manifest=str(MODEL),
                  source_model_manifest_sha256=sha(MODEL), source_fbx=model['fbx'],
                  mesh_triangles=model['triangles'], local_bounds_cm=local,
                  unit='UE centimetres', forward_axis='+X', scale_policy='1:1, no scaling',
                  thresholds_cm=dict(solids=MIN_SOLID_GAP, existing_vehicles=MIN_OLD_VEHICLE_GAP,
                                     additional_vehicle_pairs=MIN_NEW_VEHICLE_GAP,
                                     work_aisle_depth=200., parallel_aisle_depth=250.),
                  placements=selected, pairwise_clearances=pairwise, summary=summary,
                  preserved_existing_manuals=manuals, excluded_categories=exclusions,
                  verification=dict(targets_derived_from_current_instances=True,
                                    vehicle_and_passage_floor_nine_points=True,
                                    actual_wall_triangle_bounds_checked=True,
                                    all_solids_and_vehicles_final_bruteforce_checked=True,
                                    existing_actors_moved=False, deleted_actors_recreated=False),
                  apply_notes=['Guard source probe/hash and current map before applying.',
                               'Add only the four placements; preserve all existing actors and unsaved map edits.',
                               'Existing user copies are separate physical obstacles even when their TwinId tags repeat.',
                               'Recheck imported mesh bounds and full actor/passage geometry in the live map.',
                               'All current vehicle counts are taken from this probe, not the former scene.'])
    OUTPUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(dict(report=str(OUTPUT), **summary,
                         placements=[{k:p[k] for k in ('label','position_cm','yaw_deg','coverage_score_cm')} for p in selected]), indent=2))


if __name__ == '__main__':
    main()
