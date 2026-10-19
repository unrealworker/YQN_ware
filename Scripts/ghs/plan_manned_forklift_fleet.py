"""Plan eight independent staffed forklifts from a fresh live warehouse probe.

Pure offline Python: never imports Unreal/Blender and never changes source data.
Coordinates are UE centimetres; the FBX model points along local +X.  The
result is a placement proposal, not proof of live wall/floor triangle clearance.
Run with Python 3.11+; -B avoids writing optional imported-module bytecode.
"""
import hashlib
import itertools
import json
import math
from pathlib import Path

from plan_normal_stackers import boundary_clearance, in_polygon, intersects, xy_gap, z_overlap


ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / 'Saved/GHS_MannedForkliftLiveProbe.json'
MODEL = ROOT / 'SourceAssets/GHS_Normal/MannedForklift/manned_forklift_50k_validation.json'
ROUNDTRIP = ROOT / 'SourceAssets/GHS_Normal/MannedForklift/manned_forklift_50k_roundtrip.json'
LAYOUT = ROOT / 'SourceAssets/GHS/clearance_layout.json'
REPORT = ROOT / 'Saved/GHS_MannedForkliftFleetPlan.json'
MAP = '/Game/Maps/GHS_CAD_NormalWarehouse'
GAP = 50.0
GROUND_GAP = 0.5
MIN_STACKER_GAP = 500.0
MIN_VEHICLE_PAIR_GAP = 2500.0
WALLS = {'GHS_CAD_WallFaces', 'GHS_CAD_WallSections', 'GHS_CAD_WallEdges'}

# These are CAD/live-instance identities, not baked world-space coordinates.
# The narrow central cross aisle receives longitudinal vehicles.  Parking a
# 3.45 m vehicle across it would leave only about 1.1 m behind the counterweight.
CONFIG = [
    dict(number=1, zone='south_ground_edge', target_actor='GHS_CAD_PalletCargoHigh', target_instance=127, yaw_deg=90., mode='forks_to_south_face'),
    dict(number=2, zone='south_ground_edge', target_actor='GHS_CAD_PalletCargoHigh', target_instance=668, yaw_deg=90., mode='forks_to_south_face'),
    dict(number=3, zone='south_ground_edge', target_actor='GHS_CAD_PalletCargoHigh', target_instance=1208, yaw_deg=90., mode='forks_to_south_face'),
    dict(number=4, zone='central_cross_aisle', target_actor='GHS_CAD_PalletCargo', target_instance=544, yaw_deg=0., mode='parallel_cross_aisle'),
    dict(number=5, zone='central_cross_aisle', target_actor='GHS_CAD_PalletCargo', target_instance=1444, yaw_deg=180., mode='parallel_cross_aisle'),
    dict(number=6, zone='north_ground_edge', target_actor='GHS_CAD_PalletCargoLow', target_instance=1259, yaw_deg=-90., mode='forks_to_north_face'),
    dict(number=7, zone='north_ground_edge', target_actor='GHS_CAD_PalletCargoLow', target_instance=1455, yaw_deg=-90., mode='forks_to_north_face'),
    dict(number=8, zone='north_ground_edge', target_actor='GHS_CAD_PalletCargoLow', target_instance=1675, yaw_deg=-90., mode='forks_to_north_face'),
]


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finite_box(bounds):
    return len(bounds) == 6 and all(math.isfinite(v) for v in bounds) and all(bounds[i] <= bounds[i+3] for i in range(3))


def excluded(item):
    name = item['label']
    if item['hidden'] or not item['visible'] or item.get('hidden_in_game', False):
        return 'currently_hidden_or_invisible'
    if name in WALLS:
        return 'merged_wall_bounds_require_live_triangle_check'
    if name in {'GHS_CAD_ExactFootprint', 'GHS_DarkSurround', 'GHN_StudioGround', 'GHN_StudioSky'}:
        return 'ground_or_sky_not_a_solid_obstacle'
    if name.startswith('CAM_'):
        return 'camera_visualization'
    if any(word in name for word in ('ContextGrid', 'Outlines', 'Clearances')):
        return 'decorative_markings'
    return None


def footprint_samples(bounds):
    return [(x, y) for x in (bounds[0], (bounds[0]+bounds[3])/2, bounds[3])
            for y in (bounds[1], (bounds[1]+bounds[4])/2, bounds[4])]


def strictly_cross(a, b, c, d):
    def side(p, q, r):
        return (q[0]-p[0])*(r[1]-p[1]) - (q[1]-p[1])*(r[0]-p[0])
    return side(a, b, c)*side(a, b, d) < -1e-8 and side(c, d, a)*side(c, d, b) < -1e-8


def check_footprint(bounds, polygon, minimum):
    assert all(in_polygon(p, polygon) for p in footprint_samples(bounds)), ('Outside CAD footprint', bounds)
    corners = [(bounds[0], bounds[1]), (bounds[3], bounds[1]),
               (bounds[3], bounds[4]), (bounds[0], bounds[4])]
    for a, b in zip(corners, corners[1:]+corners[:1]):
        for c, d in zip(polygon, polygon[1:]+polygon[:1]):
            assert not strictly_cross(a, b, c, d), ('Vehicle/passage crosses CAD boundary', bounds)
    clearance = boundary_clearance(bounds, polygon)
    assert clearance >= minimum, ('Insufficient CAD boundary clearance', clearance, minimum)
    return clearance


def transformed_box(local, position, yaw):
    angle = math.radians(yaw)
    co, si = math.cos(angle), math.sin(angle)
    points = [(position[0]+co*x-si*y, position[1]+si*x+co*y, position[2]+z)
              for x, y, z in itertools.product((local[0], local[3]), (local[1], local[4]), (local[2], local[5]))]
    return [min(p[i] for p in points) for i in range(3)] + [max(p[i] for p in points) for i in range(3)]


def nearest_record(bounds, obstacles):
    candidates = [dict(ob, clearance_cm=xy_gap(bounds, ob['bounds_cm']))
                  for ob in obstacles if z_overlap(bounds, ob['bounds_cm'])]
    assert candidates
    return min(candidates, key=lambda ob: ob['clearance_cm'])


def make_placement(config, local, obstacles, stackers, polygon):
    matches = [ob for ob in obstacles if ob['label'] == config['target_actor'] and ob['index'] == config['target_instance']]
    assert len(matches) == 1, ('Configured live target missing or ambiguous', config)
    target = matches[0]
    target_box = target['bounds_cm']
    rotated = transformed_box(local, [0., 0., 0.], config['yaw_deg'])
    x = (target_box[0]+target_box[3]-rotated[0]-rotated[3])/2
    if config['mode'] == 'forks_to_north_face':
        y = target_box[4]+GAP-rotated[1]
    else:
        y = target_box[1]-GAP-rotated[4]
    position = [x, y, GROUND_GAP-local[2]]
    bounds = transformed_box(local, position, config['yaw_deg'])
    assert finite_box(bounds) and abs(bounds[2]-GROUND_GAP) < 1e-6
    target_gap = xy_gap(bounds, target_box)
    assert abs(target_gap-GAP) < 1e-6
    nearest = nearest_record(bounds, obstacles)
    assert nearest['clearance_cm'] >= GAP-1e-4, ('Live scene blocks configured placement', config, nearest)
    old_stacker = nearest_record(bounds, stackers)
    assert old_stacker['clearance_cm'] >= MIN_STACKER_GAP, ('Too close to an existing stacker', config, old_stacker)
    boundary = check_footprint(bounds, polygon, 300.)
    passage = list(bounds)
    passage[0] -= 100.
    passage[3] += 100.
    width = 250. if config['mode'] == 'parallel_cross_aisle' else 200.
    if config['mode'] == 'forks_to_north_face':
        passage[1], passage[4] = bounds[4]+.01, bounds[4]+width
    else:
        passage[1], passage[4] = bounds[1]-width, bounds[1]-.01
    assert not any(intersects(passage, ob['bounds_cm']) for ob in obstacles), ('Passage blocked', config)
    passage_boundary = check_footprint(passage, polygon, 30.)
    return dict(config, label='GHN_MannedForklift_%02d' % config['number'],
                twin_id='GHN_MannedForklift_%02d' % config['number'],
                position_cm=position, scale=[1., 1., 1.], bounds_cm=bounds,
                target=target, target_clearance_cm=target_gap,
                clearance_relation='side_to_pallet' if config['mode'] == 'parallel_cross_aisle' else 'fork_tip_to_pallet',
                nearest_obstacle=nearest, nearest_existing_stacker=old_stacker,
                cad_boundary_clearance_cm=boundary,
                clear_passage=dict(bounds_cm=passage, minimum_depth_cm=width, empty=True,
                                   cad_boundary_clearance_cm=passage_boundary,
                                   purpose='continuous_cross_aisle' if config['mode'] == 'parallel_cross_aisle' else 'rear_vehicle_clearance'))


def main():
    probe, model, roundtrip, layout = map(read, (PROBE, MODEL, ROUNDTRIP, LAYOUT))
    assert probe['map'].split('.')[0] == MAP
    assert roundtrip['passed'] and model['triangles'] == roundtrip['fbx_reimported_triangles'] <= 50000
    assert max(abs(a-b) for a, b in zip(sum(model['bounds_m'], []), sum(roundtrip['bounds_m'], []))) < 1e-6
    bounds_m = model['bounds_m']
    local = [bounds_m[0][0]*100, -bounds_m[1][1]*100, bounds_m[2][0]*100,
             bounds_m[0][1]*100, -bounds_m[1][0]*100, bounds_m[2][1]*100]
    assert finite_box(local)
    polygon = [[x*100, -y*100] for x, y in layout['footprint_outline_m']]
    obstacles, exclusions = [], []
    for item in probe['items']:
        reason = excluded(item)
        if reason:
            exclusions.append(dict(label=item['label'], component=item.get('component'), reason=reason, instances=len(item['instances'])))
            continue
        for instance in item['instances']:
            assert finite_box(instance['bounds']), ('Invalid live instance bounds', item['label'], instance['index'])
            obstacles.append(dict(label=item['label'], component=item.get('component'), index=instance['index'],
                                  mesh=item['mesh'], bounds_cm=instance['bounds']))
    stackers = [ob for ob in obstacles if ob['label'].startswith('GHN_FloorStacker_')]
    assert stackers, 'Expected existing stackers in fresh live probe'
    assert not any(ob['label'].startswith('GHN_MannedForklift_') for ob in obstacles), 'Fleet already exists; review before planning another copy'
    placements = [make_placement(c, local, obstacles, stackers, polygon) for c in CONFIG]
    pairwise = []
    for a, b in itertools.combinations(placements, 2):
        gap = xy_gap(a['bounds_cm'], b['bounds_cm'])
        assert gap >= MIN_VEHICLE_PAIR_GAP, ('New vehicles not sufficiently dispersed', a['label'], b['label'], gap)
        assert not intersects(a['clear_passage']['bounds_cm'], b['bounds_cm'])
        assert not intersects(b['clear_passage']['bounds_cm'], a['bounds_cm'])
        pairwise.append(dict(a=a['label'], b=b['label'], clearance_cm=gap,
                             origin_distance_cm=math.dist(a['position_cm'][:2], b['position_cm'][:2])))
    report = dict(schema_version=1, success=True, offline_plan_only=True, map=MAP,
                  source_live_probe=str(PROBE), source_live_probe_sha256=sha(PROBE),
                  source_actor_count=probe['actor_count'], source_dirty_maps=probe['dirty_maps'],
                  source_dirty_content=probe.get('dirty_content', []),
                  source_model_validation_sha256=sha(MODEL), source_fbx_roundtrip_sha256=sha(ROUNDTRIP),
                  source_cad_footprint_sha256=sha(LAYOUT), source_fbx=model['fbx'], source_fbx_sha256=sha(Path(model['fbx'])),
                  unit='Unreal world centimetres', coordinate_contract='UE X/Y/Z; model forward +X; yaw about +Z; scale 1; wheels minimum Z=0.5 cm',
                  mesh_triangles=model['triangles'], model_dimensions_m=model['dimensions_m'], local_bounds_cm=local,
                  configuration=CONFIG, placements=placements, pairwise_clearances=pairwise,
                  summary=dict(added_vehicle_count=len(placements), live_obstacle_instances=len(obstacles),
                               current_existing_stacker_count=len({o['label'] for o in stackers}),
                               current_existing_stacker_labels=sorted({o['label'] for o in stackers}),
                               minimum_obstacle_clearance_cm=min(p['nearest_obstacle']['clearance_cm'] for p in placements),
                               minimum_existing_stacker_clearance_cm=min(p['nearest_existing_stacker']['clearance_cm'] for p in placements),
                               minimum_new_vehicle_clearance_cm=min(p['clearance_cm'] for p in pairwise),
                               minimum_cad_boundary_clearance_cm=min(p['cad_boundary_clearance_cm'] for p in placements)),
                  excluded_categories=exclusions,
                  verification=dict(all_live_obstacles_bruteforce_checked=True, fork_and_driver_included=True,
                                    target_positions_derived_from_current_live_instances=True,
                                    cad_boundary_checks='9 footprint samples, 4 rectangle edges and conservative boundary distance for each vehicle and passage',
                                    old_deleted_actors_not_reintroduced=True, wall_triangles_checked=False, floor_triangles_checked=False),
                  pending_live_checks=['Imported FBX bounds/axis/scale and LOD0 triangle count',
                                       'Fresh live probe hash matches before applying plan',
                                       'Floor triangles cover all vehicle and passage samples',
                                       'Merged wall triangles clear vehicles and passage strips',
                                       'Snapshot existing actors before change; preserve dirty live-map edits',
                                       'New MannedForklift HUD type and unique TwinId registration'])
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(dict(report=str(REPORT), **report['summary']), indent=2))


if __name__ == '__main__':
    main()
