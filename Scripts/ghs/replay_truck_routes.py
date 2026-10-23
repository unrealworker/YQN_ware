"""Read-only geometric audit and rear-origin paths for the three replay trucks.

Uses the same CAD curves/surface union as park_site, never edits a map or asset.
Run with a Python containing Shapely, or Blender's bundled Python. All planning
is in site UV metres, all emitted points are Unreal world metres/degrees.
"""
from pathlib import Path
import hashlib
import json
import math
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'Saved/ParkRefinement/python_deps'))
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union, substring
from shapely.prepared import prep
from park_curves import rounded_path
from park_surfaces import road_union

ORIGIN = (239.33385, 60.24019)
XMIN, XMAX, HALF_WIDTH = -.1975, 14.706, 1.5
CENTER_OFFSET = (XMIN + XMAX) / 2
HALF_LENGTH = (XMAX - XMIN) / 2
STEP = .25
OUT = ROOT / 'Saved/OrderReplay/truck_routes.json'


def load(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def parts(g):
    if g.geom_type == 'LineString':
        return [g]
    return [p for child in getattr(g, 'geoms', []) for p in parts(child)]


def geometry():
    cad = load('SourceAssets/GHS/Park/cad_layout.json')
    site = load('SourceAssets/GHS/Park/site_geometry_report.json')
    manifest = load('SourceAssets/GHS/Park/park_manifest.json')
    traffic = load('SourceAssets/GHS/Traffic/routes.json')
    scope = box(-175, -195, 725, 570).buffer(22, quad_segs=16)
    campus_ids = {'154b', '1bba', '1d99', '1d9e', '2115', '211a', '2056', '205d', '2068'}
    glen_ids = {'13a3', '1460', '1633', '149c', '1673', '17c8', '1f42', '20d4'}
    sycamore_ids = {'15ee', '140d', '16e0', '1f7f', '17a8', '13d0', '166f'}
    specs, controls = [], {}
    for row in cad['roads']:
        raw = LineString(row['points_uv_m'])
        if raw.length < .2 or row['layer'] == 'highways':
            continue
        points = list(raw.simplify(.18, preserve_topology=True).coords)
        controls[row['handle']] = points
        closed = bool(row['closed']) or math.dist(points[0], points[-1]) < .05
        width = 19. if row['handle'] in glen_ids else 7.4
        if row['handle'] in sycamore_ids:
            width = 6.6
        if row['handle'] in campus_ids:
            width = 7.6 if row['handle'] in {'2068', '154b', '1bba'} else 5.2
        curve = rounded_path(points, 4.5 if closed else 22 if row['layer'] == 'major_roads' else 12,
                             closed, max_step=1.)
        for i, line in enumerate(parts(LineString(curve).intersection(scope))):
            if line.length > 2:
                specs.append(dict(id=row['id'] + '_' + str(i), cad_id=row['id'], layer=row['layer'],
                                  path=list(line.coords), width=width, context=row['handle'] not in campus_ids))
    for name, path, width in [
        ('court_connector', [(140, 188), (140, 146), (147.05, 146.1)], 7.6),
        ('west_fire_access', [(-4, 187), (-4, 140), (-5, -5), (486, -5), (506, 0)], 5.)
    ]:
        specs.append(dict(id=name, layer='campus_service', context=False, width=width,
                          path=rounded_path(path, 10, max_step=.8)))
    roads = road_union(specs, 3.8)
    corner = box(473, -3, 501, 7.5)
    roads = roads.difference(corner).union(road_union(specs, 2.8).intersection(corner))
    # Only actual ground-level continuations, never the grade-separated I-15.
    extensions = [LineString(r['extended_path_uv_m']).buffer(r['width_m'] / 2, cap_style=2)
                  for r in traffic['roads'] if r['corridor'] == 'GlenHelen']
    roads = unary_union([roads] + extensions)
    campus = Polygon(site['campus_boundary_uv_m'])
    warehouse = Polygon(manifest['existing_warehouse_uv_m'])
    gates = []
    for name, handle, margin in [('SW Main gate', '1bba', 1.), ('NE Service gate', '2068', 1.4)]:
        road = next(s for s in specs if s.get('cad_id') == 'CAD_' + handle)
        mask = LineString(road['path']).buffer(road['width'] / 2 + margin)
        if handle == '2068':
            mask = mask.intersection(box(490, -45, 528, 12))
        gates.append(mask)
    fence = LineString(campus.buffer(-.85, join_style=1).exterior.coords).difference(unary_union(gates))
    obstacles = [warehouse, fence.buffer(.1), box(34.2, 177.6, 41.8, 182.4), box(502.6, 6.2, 507.4, 13.8)]
    obstacles += [Polygon(p) for p in site['parking']['islands_uv_m']]
    obstacles += [Point(x, y).buffer(.12) for x, y in [(42, 176), (65, 192), (130, 184), (228, 179), (315, 151), (408, 145), (536, 94), (541, 39)]]
    # Use the recorded complete crown as a conservative obstacle, even where
    # its lower branches are higher than the truck.
    obstacles += [Point(*t['center_uv_m']).buffer(t['crown_radius_m']) for t in manifest['street_tree_placement_checks']]
    obstacles += [Point(*c).buffer(.4) for gate in site['fence']['portals'] for c in gate['column_centers']]
    return dict(controls=controls, roads=roads, campus=campus, warehouse=warehouse,
                paved=roads.union(campus), obstacles=unary_union(obstacles), fence=fence,
                traffic=traffic, site=site, specs=specs)


def footprint(p, yaw):
    c, s = math.cos(yaw), math.sin(yaw)
    return Polygon([(p[0] + x*c - y*s, p[1] + x*s + y*c)
                    for x, y in [(-HALF_LENGTH, -HALF_WIDTH), (HALF_LENGTH, -HALF_WIDTH),
                                 (HALF_LENGTH, HALF_WIDTH), (-HALF_LENGTH, HALF_WIDTH)]])


def poses(points):
    line = LineString(points)
    result = []
    distances = [i * STEP for i in range(math.ceil(line.length / STEP))] + [line.length]
    for d in distances:
        p = line.interpolate(d)
        a, b = line.interpolate(max(0, d-.1)), line.interpolate(min(line.length, d+.1))
        yaw = math.atan2(b.y-a.y, b.x-a.x)
        result.append((d, (p.x, p.y), yaw))
    return result


def validate(path, geo, pose_override=None):
    worst_paved = 0.
    worst_obstacle = 0.
    min_obstacle = math.inf
    bad = []
    pose_list = pose_override if pose_override is not None else poses(path)
    paved_test, obstacle_test = prep(geo['paved']), prep(geo['obstacles'])
    # Conservative sweep between adjacent 25cm samples includes 3cm padding.
    prev = None
    for d, p, yaw in pose_list:
        poly = footprint(p, yaw)
        sweep = poly if prev is None else unary_union([prev, poly]).convex_hull.buffer(.03)
        prev = poly
        outside = 0. if paved_test.covers(sweep) else sweep.difference(geo['paved']).area
        hit = sweep.intersection(geo['obstacles']).area if obstacle_test.intersects(sweep) else 0.
        min_obstacle = min(min_obstacle, sweep.distance(geo['obstacles']))
        worst_paved = max(worst_paved, outside)
        worst_obstacle = max(worst_obstacle, hit)
        if outside > .0001 or hit > .0001:
            if not bad or d-bad[-1]['distance_m'] > 5:
                bad.append(dict(distance_m=round(d, 2), uv_m=[round(x, 3) for x in p],
                                yaw_deg=round(math.degrees(yaw), 2), outside_paved_m2=round(outside, 4),
                                obstacle_overlap_m2=round(hit, 4)))
    return dict(success=not bad, max_outside_paved_m2=worst_paved,
                max_static_obstacle_overlap_m2=worst_obstacle, min_static_obstacle_clearance_m=min_obstacle,
                sweep_step_m=STEP, sweep_padding_m=.03, sampled_poses=len(pose_list), failures=bad), pose_list


def main():
    geo = geometry()
    controls = geo['controls']
    glen = next(r for r in geo['traffic']['roads'] if r['id'] == 'glen')
    glenline = LineString(glen['extended_path_uv_m'])
    # End 22m before the visible continuation endpoint: the whole truck stays
    # on the road during the final 35m fade, including its asymmetric origin.
    east = list(substring(glenline, glenline.project(Point(509.7, -27.33)), glenline.length-22).simplify(.4).coords)
    west = list(substring(glenline, 22, glenline.project(Point(-38.89, -50.1))).simplify(.4).coords)[::-1]
    probe = load('Saved/OrderReplay/scene_probe.json')
    trucks = []
    for slot, dock in [('A', 75), ('B', 51), ('C', 20)]:
        actor = next(r for r in probe['items'] if r['label'] == 'GHS_DockTruck_%03d' % dock)
        transform = actor['instances'][0]['transform']
        xyz = [v/100 for v in transform['position_cm']]
        start = (xyz[0]+ORIGIN[0], xyz[1]+ORIGIN[1]+CENTER_OFFSET)
        if slot == 'A':
            control = [start, (start[0], 188.34)] + [p for p in controls['154b'][::-1] if p[0] < start[0]-20] + controls['1bba'][::-1][1:]
            # 35cm west of the mathematical junction keeps the entire body,
            # including the conservative sweep margin, inside the actual T.
            control[-1] = (control[-1][0]-.35, control[-1][1])
            control += controls['1f7f'][1:] + controls['140d'][1:] + controls['13d0'][1:] + west[1:]
            gate, road = 'SW Main gate', 'Sycamore → Glen Helen (west)'
        else:
            campus = controls['2068']
            control = [start, (start[0], 142.5)] + [p for p in campus if p[0] > start[0]+20] + east[1:]
            gate, road = 'NE Service gate', 'Glen Helen (east)'
        # Remove repeated joins but retain true CAD road controls.
        clean = [control[0]]
        for p in control[1:]:
            if math.dist(clean[-1], p) > .01:
                clean.append(p)
        path, meta = rounded_path(clean, 12, max_step=.2, return_metadata=True)
        validation, sample = validate(path, geo)
        points = [[round(p[0]-ORIGIN[0]-CENTER_OFFSET*math.cos(yaw), 5),
                   round(p[1]-ORIGIN[1]-CENTER_OFFSET*math.sin(yaw), 5), round(xyz[2], 8),
                   round(math.degrees(yaw), 5)] for _, p, yaw in sample]
        points[0] = [*xyz, transform['rotation_deg'][1]]
        length = sample[-1][0]
        # The body is symmetric about its geometric centre. Reversing the
        # centreline and heading preserves its swept footprint; reversing a
        # rear-origin point list and simply adding 180deg would not.
        line = LineString(path)
        target = Point(60, 188.9) if slot == 'A' else Point(435, 134) if slot == 'C' else Point(start[0]+45, 144)
        cut = line.project(target)
        prefix = list(substring(line, cut, line.length).coords)[::-1]
        anchor = prefix[-1]
        if slot == 'A':
            bend = rounded_path([anchor, (start[0]-24, 188.6), (start[0]-24, 160)], 12, max_step=.2)
            circle_center = (start[0]-12, 160)
            semicircle = [(circle_center[0]+12*math.cos(math.pi+math.pi*i/190),
                           circle_center[1]+12*math.sin(math.pi+math.pi*i/190)) for i in range(191)]
            forward = prefix + bend[1:] + semicircle[1:] + [(start[0], 174)]
            stop_y = 174.
        else:
            # The eastern court narrows against the real diagonal fence.
            # C turns inside that court and stops at v149, not in the wider
            # west-yard staging space used by A/B.
            stop_y, corner_y, radius = (149., 137., 10.) if slot == 'C' else (174., 145., 12.)
            if slot == 'C':
                approach = [anchor, (413.65, 141.25)]
            else:
                tangent_length = math.dist(prefix[-2], anchor)
                tangent = ((anchor[0]-prefix[-2][0])/tangent_length, (anchor[1]-prefix[-2][1])/tangent_length)
                approach = [anchor, (anchor[0]+6*tangent[0], anchor[1]+6*tangent[1])]
            bend = rounded_path(approach + [(start[0], corner_y), (start[0], stop_y)], radius, max_step=.2)
            forward = prefix + bend[1:]
        arrival_samples = poses(forward)
        reverse_start = arrival_samples[-1][0]
        reverse = poses([(start[0], stop_y), start])
        arrival_samples += [(reverse_start+d, p, math.pi/2) for d,p,_ in reverse[1:]]
        arrival_validation, _ = validate([], geo, arrival_samples)
        arrival_points = [[round(p[0]-ORIGIN[0]-CENTER_OFFSET*math.cos(yaw), 5),
                           round(p[1]-ORIGIN[1]-CENTER_OFFSET*math.sin(yaw), 5), round(xyz[2], 8),
                           round(math.degrees(yaw), 5)] for _,p,yaw in arrival_samples]
        arrival_points[-1] = [*xyz, transform['rotation_deg'][1]]
        arrival = dict(points_m=arrival_points, distances_m=[round(s[0], 5) for s in arrival_samples],
                       centerline_length_m=arrival_samples[-1][0],
                       reverse_start_distance_m=reverse_start,
                       fade_in_end_distance_m=35., validation=arrival_validation,
                       motion='Forward along public road and yard; align yaw90; stop then reverse straight to the original rear-origin dock pose')
        trucks.append(dict(id='REPLAY-TRUCK-'+slot, dock=dock, gate=gate, points_m=points,
                           centerline_length_m=length, distances_m=[round(s[0], 5) for s in sample],
                           roadExitReason=road+'; stays on ground-level public road; never joins I-15',
                           fade_out_start_distance_m=max(0, length-35), fade_out_end_distance_m=length,
                           min_center_turn_radius_m=meta['min_radius'], validation=validation, arrival=arrival))
    result = dict(version=1, success=all(r['validation']['success'] and r['arrival']['validation']['success'] for r in trucks), trucks=trucks,
                  coordinate_contract='points_m = Unreal rear-origin [x,y,z,yawDegrees]; centerline lengths are arclength metres',
                  vehicle_bounds_local_m=dict(x=[XMIN, XMAX], y=[-HALF_WIDTH, HALF_WIDTH]),
                  verification='Static 2D whole-body swept polygon against modeled paved area, warehouse, fence, gate columns, gatehouses, parking islands, light poles and recorded tree crowns. Dynamic vehicle conflicts are validated by the replay scheduler.',
                  assumptions=['All original dock/staging/context vehicles are hidden during replay; merged parking cars use exact no-car derivatives.',
                               'Rigid visual truck model; not an articulated vehicle dynamics or steering simulation.',
                               'The separate arrival path drives forward through the gate, turns in the hardstand, then reverses straight into the dock. Scheduler must pause at its direction-change marker.'],
                  sources={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in [
                      'Saved/OrderReplay/scene_probe.json', 'SourceAssets/GHS/Park/site_geometry_report.json',
                      'SourceAssets/GHS/Park/cad_layout.json', 'SourceAssets/GHS/Traffic/routes.json']})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(dict(success=result['success'], trucks=[dict(id=r['id'], length_m=r['centerline_length_m'],
        radius_m=r['min_center_turn_radius_m'], departure=r['validation'], arrival=r['arrival']['validation']) for r in trucks]), indent=2))


if __name__ == '__main__':
    main()
