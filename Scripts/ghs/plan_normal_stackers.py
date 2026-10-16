"""Plan 12 independent, full-scale BlueStackers from the current live probe.

Offline only: writes a plan and a 2D preview, never loads Unreal or changes assets.
All geometry is in Unreal world centimetres.  The conservative AABB check uses
the complete fork-inclusive model and visible scene instance envelopes.
"""
import collections
import hashlib
import itertools
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SAVED = ROOT / 'Saved'
PROBE = SAVED / 'GHS_NormalStackerProbe.json'
PLAN = SAVED / 'GHS_NormalStackerPlan.json'
LOCAL = [-36.00001, -131.00001, 0., 36.00001, 53.50001, 180.70001]
TIP_GAP = 30.
OBSTACLE_GAP = 20.
BACK_PASSAGE = 200.
PAIR_DISTANCE = 1000.
CELL = 400.


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def excluded(item):
    label = item['label']
    if item['hidden'] or not item['visible']:
        return 'hidden_or_invisible'
    if label in ('GHS_CAD_ExactFootprint', 'GHS_DarkSurround', 'GHN_StudioGround'):
        return 'floor_or_surround'
    if label == 'GHN_StudioSky':
        return 'sky'
    if label.startswith('CAM_'):
        return 'camera_visualization'
    if label in ('GHS_CAD_DoorClearances', 'GHS_CAD_ChargingBayOutlines', 'GHS_ColumnEdgeOutlines'):
        return 'decorative_ground_or_column_markings'
    if label.startswith('GHS_CAD_Wall'):
        return 'merged_wall_AABB_not_a_solid_obstacle_requires_triangle_validation'
    return None


def xy_gap(a, b):
    dx = max(a[0] - b[3], b[0] - a[3], 0.)
    dy = max(a[1] - b[4], b[1] - a[4], 0.)
    return math.hypot(dx, dy)


def z_overlap(a, b):
    return min(a[5], b[5]) > max(a[2], b[2]) + 1e-5


def intersects(a, b):
    return all(min(a[k + 3], b[k + 3]) > max(a[k], b[k]) + 1e-6 for k in range(3))


def in_polygon(point, polygon):
    x, y = point
    inside = False
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        if (a[1] > y) != (b[1] > y):
            if x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]:
                inside = not inside
    return inside


def point_segment_distance(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = max(0., min(1., ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def boundary_clearance(bounds, polygon):
    corners = [(x, y) for x in (bounds[0], bounds[3]) for y in (bounds[1], bounds[4])]
    if not all(in_polygon(p, polygon) for p in corners):
        return -1.
    return min(point_segment_distance(p, a, b) for p in corners for a, b in zip(polygon, polygon[1:] + polygon[:1]) if a != b)


class SpatialGrid:
    def __init__(self, obstacles):
        self.obstacles = obstacles
        self.cells = collections.defaultdict(set)
        for idx, ob in enumerate(obstacles):
            for cell in self.keys(ob['bounds_cm']):
                self.cells[cell].add(idx)

    @staticmethod
    def keys(b):
        return itertools.product(range(math.floor(b[0] / CELL), math.floor(b[3] / CELL) + 1),
                                 range(math.floor(b[1] / CELL), math.floor(b[4] / CELL) + 1))

    def query(self, b, pad=0.):
        region = [b[0] - pad, b[1] - pad, b[2], b[3] + pad, b[4] + pad, b[5]]
        ids = set()
        for cell in self.keys(region):
            ids.update(self.cells.get(cell, ()))
        return [self.obstacles[i] for i in sorted(ids)]


def make_candidate(target, side, polygon, grid):
    """Approach the exposed +/-Y pallet face; forks retain their real length."""
    b = target['bounds_cm']
    x = (b[0] + b[3]) / 2
    if side == 1:
        yaw = 0.
        y = b[4] + TIP_GAP - LOCAL[1]
    else:
        yaw = 180.
        y = b[1] - TIP_GAP + LOCAL[1]
    z = .5
    cy, sy = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    points = [(x + cy * xx - sy * yy, y + sy * xx + cy * yy)
              for xx in (LOCAL[0], LOCAL[3]) for yy in (LOCAL[1], LOCAL[4])]
    bounds = [min(p[0] for p in points), min(p[1] for p in points), z,
              max(p[0] for p in points), max(p[1] for p in points), z + LOCAL[5]]
    boundary = boundary_clearance(bounds, polygon)
    if boundary < 300.:
        return None
    nearby = [ob for ob in grid.query(bounds, 100.) if z_overlap(bounds, ob['bounds_cm'])]
    if any(xy_gap(bounds, ob['bounds_cm']) < OBSTACLE_GAP - 1e-5 for ob in nearby):
        return None
    # Require a clear 2 m strip directly behind the full-width vehicle.  Expand
    # sideways to 6 m to ensure this is an aisle segment, not a narrow dead end.
    passage = bounds[:]
    passage[0] -= 264.
    passage[3] += 264.
    if side == 1:
        passage[1], passage[4] = bounds[4] + .01, bounds[4] + BACK_PASSAGE
    else:
        passage[1], passage[4] = bounds[1] - BACK_PASSAGE, bounds[1] - .01
    if boundary_clearance(passage, polygon) < 30.:
        return None
    if any(intersects(passage, ob['bounds_cm']) for ob in grid.query(passage)):
        return None
    nearest = min(nearby, key=lambda ob: xy_gap(bounds, ob['bounds_cm']))
    other = [ob for ob in grid.query(bounds, 1000.) if z_overlap(bounds, ob['bounds_cm'])
             and (ob['label'], ob['index']) != (target['label'], target['index'])]
    other_nearest = min(other, key=lambda ob: xy_gap(bounds, ob['bounds_cm']))
    return dict(position_cm=[round(x, 6), round(y, 6), z], yaw_deg=yaw, scale=1.,
                bounds_cm=[round(v, 6) for v in bounds], target=target,
                fork_tip_gap_cm=TIP_GAP, nearest_clearance_cm=round(xy_gap(bounds, nearest['bounds_cm']), 6),
                nearest_obstacle={'label': nearest['label'], 'index': nearest['index']},
                other_obstacle_clearance_cm=round(xy_gap(bounds, other_nearest['bounds_cm']), 6),
                other_nearest_obstacle={'label': other_nearest['label'], 'index': other_nearest['index']},
                rear_aisle_clear_box_cm=[round(v, 6) for v in passage],
                rear_aisle_clear_width_cm=BACK_PASSAGE, rear_aisle_checked_length_cm=600.,
                cad_boundary_distance_cm=round(boundary, 6))


def render(plan, polygon):
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new('RGB', (2200, 1500), '#101b28')
    d = ImageDraw.Draw(image)
    title = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 31)
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 21)
    small = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 16)
    d.text((35, 23), 'Normal warehouse | 12 independent BlueStackers, scale 1:1', font=title, fill='white')
    d.text((35, 67), 'Orange = stacker    Yellow = target pallet    Cyan = 2 m clear rear passage (6 m long)', font=font, fill='#bed5e8')
    d.text((35, 99), 'Fork gap 0.30 m | Complete model 0.72 x 1.845 x 1.807 m | Conservative scene-instance AABB check', font=font, fill='#bed5e8')
    area = (35, 155, 2165, 980)
    window = (-7600., -6200., 21100., 5900.)
    def panel(rect, window, selected, labels=True):
        x0, y0, x1, y1 = rect
        minx, miny, maxx, maxy = window
        s = min((x1 - x0) / (maxx - minx), (y1 - y0) / (maxy - miny))
        ox = (x0 + x1 - (maxx - minx) * s) / 2
        oy = (y0 + y1 - (maxy - miny) * s) / 2
        def pt(x, y): return (ox + (x - minx) * s, oy + (y - miny) * s)
        def box(b, fill, outline=None, width=1):
            if b[3] < minx or b[0] > maxx or b[4] < miny or b[1] > maxy: return
            d.rectangle((*pt(max(minx, b[0]), max(miny, b[1])), *pt(min(maxx, b[3]), min(maxy, b[4]))), fill, outline, width)
        d.rectangle(rect, fill='#182735', outline='#476076')
        for ob in plan['obstacles']:
            color = '#506d78' if ob['label'].startswith('GHS_CAD_PalletCargo') else '#67727d'
            if 'Rack' in ob['label']: color = '#725c80'
            if 'AGV' in ob['label'] or 'Charging' in ob['label'] or ob['label'].startswith('GHS_CH_'): color = '#718d67'
            if ob['bounds_cm'][2] < 181.3: box(ob['bounds_cm'], color)
        for p in selected:
            box(p['rear_aisle_clear_box_cm'], None, '#43bfd9', 2)
            box(p['target']['bounds_cm'], '#ecd16a', '#fff2a7', 1)
            box(p['bounds_cm'], '#f78d39', '#ffe2be', 2)
            x, y, _ = p['position_cm']
            a = math.radians(p['yaw_deg'])
            d.line([pt(x, y), pt(x + 180 * math.sin(a), y - 180 * math.cos(a))], '#ffda76', 3)
            if labels:
                u, v = pt(x, y)
                text = p['label'][-2:]
                d.rectangle((u + 8, v - 25, u + 39, v + 1), fill='#10202d')
                d.text((u + 10, v - 25), text, font=font, fill='white')
    panel(area, window, plan['placements'])
    for k, p in enumerate((plan['placements'][0], plan['placements'][4], plan['placements'][8])):
        x, y, _ = p['position_cm']
        rect = (35 + k * 720, 1035, 720 + k * 720, 1435)
        panel(rect, (x - 650, y - 400, x + 650, y + 400), [p])
        d.text((rect[0] + 10, rect[1] + 10), p['label'] + ' | ' + p['zone'], font=font, fill='white')
    d.text((35, 1460), 'Merged walls and floor triangles require the separate UE geometry validation before scene placement.', font=small, fill='#c6d5dd')
    image.save(SAVED / 'GHS_NormalStackerPlan.png')


def main():
    probe = read(PROBE)
    assert probe['map'].split('.')[0] == '/Game/Maps/GHS_CAD_NormalWarehouse'
    expected = probe['stacker']['bounds']
    measured = [expected['origin'][k] - expected['extent'][k] for k in range(3)] + [expected['origin'][k] + expected['extent'][k] for k in range(3)]
    assert max(abs(x - y) for x, y in zip(measured, LOCAL)) < .001
    obstacles, excluded_rows = [], []
    for item in probe['items']:
        reason = excluded(item)
        if reason:
            excluded_rows.append({'label': item['label'], 'count': len(item['instances']), 'reason': reason})
        else:
            obstacles.extend({'label': item['label'], 'index': inst['index'], 'bounds_cm': inst['bounds']}
                             for inst in item['instances'])
    cargo = [ob for ob in obstacles if ob['label'].startswith('GHS_CAD_PalletCargo')]
    grid = SpatialGrid(obstacles)
    layout = read(ROOT / 'SourceAssets/GHS/clearance_layout.json')
    polygon = [[x * 100, -y * 100] for x, y in layout['footprint_outline_m']]
    candidates = []
    for target in cargo:
        for side in (-1, 1):
            candidate = make_candidate(target, side, polygon, grid)
            if candidate:
                candidates.append(candidate)
    zones = [('south_ground_edge', -5600., -5250., [-5000., 0., 6000., 12500.]),
             ('central_cross_aisle', -620., -430., [-5000., 2000., 9500., 18500.]),
             ('north_ground_edge', 4150., 4500., [-5000., 2000., 9500., 18500.])]
    placements = []
    availability = {}
    for name, lo, hi, anchor_xs in zones:
        pool = [p for p in candidates if lo <= p['position_cm'][1] <= hi]
        availability[name] = len(pool)
        for anchor_x in anchor_xs:
            eligible = [p for p in pool if all(math.dist(p['position_cm'][:2], old['position_cm'][:2]) >= PAIR_DISTANCE for old in placements)]
            assert eligible, ('No candidate for zone', name, anchor_x)
            p = dict(min(eligible, key=lambda c: abs(c['position_cm'][0] - anchor_x)))
            p.update(label=f'GHN_FloorStacker_{len(placements) + 1:02d}', zone=name)
            placements.append(p)
    # Independent brute-force validation of all 12 selections against all live
    # obstacles, without reusing the spatial-grid lookup used for planning.
    for p in placements:
        near = [ob for ob in obstacles if z_overlap(p['bounds_cm'], ob['bounds_cm'])]
        closest = min(near, key=lambda ob: xy_gap(p['bounds_cm'], ob['bounds_cm']))
        assert xy_gap(p['bounds_cm'], closest['bounds_cm']) >= OBSTACLE_GAP - 1e-5
        assert abs(xy_gap(p['bounds_cm'], p['target']['bounds_cm']) - TIP_GAP) < .001
        assert not any(intersects(p['rear_aisle_clear_box_cm'], ob['bounds_cm']) for ob in obstacles)
    pair_min = min(math.dist(a['position_cm'][:2], b['position_cm'][:2]) for a, b in itertools.combinations(placements, 2))
    assert len(placements) == 12 and pair_min >= PAIR_DISTANCE
    report = dict(schema_version=1, success=True, map=probe['map'].split('.')[0], asset=probe['stacker']['asset'],
                  source_probe_sha256=sha(PROBE), source_live_baseline_sha256=sha(SAVED / 'GHS_NormalStackerLiveBaseline.json'),
                  source_probe_actor_count=probe['actor_count'], source_probe_dirty_maps=probe['dirty_maps'],
                  unit='Unreal world centimetres', coordinate_contract='position_cm; yaw_deg about UE +Z; forks point (sin yaw, -cos yaw); uniform scale 1.0',
                  local_bounds_cm=LOCAL, placements=placements, obstacles=obstacles, excluded_categories=excluded_rows,
                  summary={'placement_count': len(placements), 'candidate_count': len(candidates), 'candidate_count_by_zone': availability,
                           'checked_obstacle_instance_count': len(obstacles), 'ground_cargo_count': len(cargo),
                           'min_pair_distance_cm': round(pair_min, 6),
                           'min_target_fork_gap_cm': TIP_GAP,
                           'min_other_obstacle_clearance_cm': min(p['other_obstacle_clearance_cm'] for p in placements),
                           'min_rear_aisle_width_cm': BACK_PASSAGE,
                           'min_CAD_boundary_distance_cm': min(p['cad_boundary_distance_cm'] for p in placements),
                           'collisions': 0, 'clearance_violations': 0},
                  policy=['12 individual placements in NormalWarehouse only; shared mesh and all existing scene objects stay unchanged.',
                          'Full fork-inclusive bounds, not a reduced chassis box; target pallets stay untouched.',
                          'Use exposed north/south pallet faces in three broad horizontal aisles; retain a checked 2 m by 6 m rear passage at every placement.',
                          'All selections have at least 3 m setback from the CAD footprint boundary; no placement in narrow 1.676 m block-to-block aisles.'],
                  limitations=['Merged wall bounds span the building and cannot be collision-tested as solid AABBs. Independent UE wall-triangle check is required before applying.',
                               'CAD polygon containment is checked; independent UE floor-triangle coverage is required before applying.',
                               'The 2 m rear-passage checks cover 6 m around each vehicle. They do not certify a new navigation network or turning manoeuvre.',
                               'Only visible static component instances in the current live probe participate. Decals, lights, text markers and non-mesh actors are not physical obstacles.'])
    PLAN.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    render(report, polygon)
    print(json.dumps(report['summary'], indent=2))
    for p in placements:
        print(p['label'], p['zone'], p['position_cm'], 'yaw', p['yaw_deg'], 'other gap', p['other_obstacle_clearance_cm'])
    print('GHS_NORMAL_STACKER_PLAN_VALIDATED')


if __name__ == '__main__':
    main()
