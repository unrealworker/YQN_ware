"""Reproducible, CPU-only site completion for the existing B50B57 level.

Only --output is written.  Existing scene sources, packages and instances are
never edited. Coordinates remain CAD metres (+Y); Unreal reflects Y once.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Saved/ParkRefinement/python_deps'))
import shapely
from shapely.affinity import rotate, translate
from shapely.geometry import Polygon, LineString, Point, box, shape
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

GROUND = -1.2
ROAD_CLEARANCE = .35
TREE_MARGIN = .25
SOURCE = 'SourceAssets/MPR/rebuild_b50b57'
OUTPUT = 'SourceAssets/MPR/site_completion_20261105/site_plan.json'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parts(geometry, kind):
    if geometry.is_empty:
        return []
    if geometry.geom_type == kind:
        return [geometry]
    return [p for child in getattr(geometry, 'geoms', ()) for p in parts(child, kind)]


def polygons(geometry):
    result = []
    for p in sorted(parts(shapely.make_valid(geometry), 'Polygon'), key=lambda p: (*p.bounds, p.area)):
        if p.area < .0001:
            continue
        p = orient(p, sign=1)
        result.append(dict(outer=[[round(x, 6), round(y, 6)] for x, y in p.exterior.coords],
                           holes=[[[round(x, 6), round(y, 6)] for x, y in h.coords] for h in p.interiors]))
    return result


def from_polygons(rows):
    return unary_union([Polygon(p['outer'], p['holes']) for p in rows])


def footprint(row, length, width):
    return translate(rotate(box(-length/2, -width/2, length/2, width/2),
                            row['rotation_deg'], origin=(0, 0)), *row['position_m'][:2])


class Ground:
    """Read the committed terrain triangles, including the sloped yard fringe."""
    def __init__(self, root, manifest, area, source_hashes):
        # The FBX decoder is read-only and imports neither Blender nor Unreal.
        from validate_mpr_rebuild_surface_clearance import fbx_nodes
        self.triangles = []
        for row in manifest['meshes']:
            if not row['name'].startswith('SM_MPRR_Terrain_'):
                continue
            b = row['bounds_m']
            if not area.intersects(box(b[0][0], b[1][0], b[0][1], b[1][1])):
                continue
            path = root / row['fbx']
            actual = digest(path)
            if actual != row['sha256']:
                raise ValueError('Terrain FBX differs from source manifest: ' + row['fbx'])
            source_hashes[row['fbx']] = actual
            objects = next(n for n in fbx_nodes(path) if n[0] == b'Objects')
            meshes = [n for n in objects[2] if n[0] == b'Geometry']
            if len(meshes) != 1:
                raise ValueError('Expected one terrain mesh')
            fields = {n[0]: n for n in meshes[0][2]}
            raw = list(fields[b'Vertices'][1][0])
            vertices = [raw[i:i+3] for i in range(0, len(raw), 3)]
            face = []
            for index in fields[b'PolygonVertexIndex'][1][0]:
                face.append(index if index >= 0 else -index-1)
                if index < 0:
                    for j in range(1, len(face)-1):
                        tri = [vertices[k] for k in (face[0], face[j], face[j+1])]
                        p = Polygon([v[:2] for v in tri])
                        if p.area > 1e-10 and p.intersects(area):
                            self.triangles.append(tri)
                    face = []
        self.shapes = [Polygon([v[:2] for v in t]) for t in self.triangles]
        self.index = shapely.STRtree(self.shapes)
        if not self.triangles:
            raise ValueError('No terrain support found')

    def at(self, x, y):
        point = Point(x, y)
        ids = self.index.query(point, predicate='intersects')
        if not len(ids):
            ids = self.index.query(point.buffer(.00001), predicate='intersects')
        if not len(ids):
            raise ValueError('No existing terrain under coordinate: ' + str((x, y)))
        heights = []
        for i in ids:
            a, b, c = self.triangles[int(i)]
            dx, dy = x-a[0], y-a[1]
            ux, uy, vx, vy = b[0]-a[0], b[1]-a[1], c[0]-a[0], c[1]-a[1]
            determinant = ux*vy-uy*vx
            s, t = (dx*vy-dy*vx)/determinant, (ux*dy-uy*dx)/determinant
            heights.append(a[2]+s*(b[2]-a[2])+t*(c[2]-a[2]))
        return max(heights)

    def triangles_for(self, geometry, offset):
        """Split on existing terrain edges before triangulation; no native APIs."""
        result = []
        for index in sorted(self.index.query(geometry, predicate='intersects')):
            triangle = self.triangles[int(index)]
            clipped = geometry.intersection(self.shapes[int(index)])
            a, b, c = triangle
            ux, uy, vx, vy = b[0]-a[0], b[1]-a[1], c[0]-a[0], c[1]-a[1]
            determinant = ux*vy-uy*vx
            for polygon in parts(shapely.make_valid(clipped), 'Polygon'):
                if polygon.area < 1e-10:
                    continue
                for tri in shapely.constrained_delaunay_triangles(polygon).geoms:
                    vertices = []
                    for x, y in orient(tri, sign=1).exterior.coords[:-1]:
                        dx, dy = x-a[0], y-a[1]
                        s, t = (dx*vy-dy*vx)/determinant, (ux*dy-uy*dx)/determinant
                        z = a[2]+s*(b[2]-a[2])+t*(c[2]-a[2])+offset
                        vertices.append([round(x, 6), round(y, 6), round(z, 6)])
                    result.append(vertices)
        return result


def build_plan(root=ROOT):
    root = Path(root).resolve()
    paths = dict(cad='SourceAssets/MPR/mpr_cad_layout.json',
                 layout=SOURCE+'/transport_revision_20261105/layout.json',
                 audit=SOURCE+'/geometry_audit.json', manifest=SOURCE+'/manifest.json')
    source_hashes = {p: digest(root/p) for p in paths.values()}
    data = {k: json.loads((root/p).read_text(encoding='utf-8')) for k, p in paths.items()}
    cad, layout, audit, manifest = (data[k] for k in ('cad', 'layout', 'audit', 'manifest'))
    main = Polygon(cad['footprint_outline_m'])
    roads, rail, water = (shape(layout[k]) for k in ('roads', 'rail_corridor', 'water'))
    buildings = shape(layout['building_protection']).union(main.buffer(.10))
    old_yard, old_green = (shape(audit[k]) for k in ('main_apron', 'campus_green'))
    instances = manifest['instances']
    trees = instances['SM_MPR4_Tree_Oak']
    source_trees = [(i, row) for i, row in enumerate(trees) if row.get('provenance') != 'campus_green_row']
    crown = lambda row: Point(row['position_m'][:2]).buffer(row['crown_radius_m']+TREE_MARGIN, quad_segs=12)
    source_tree_mask = unary_union([crown(row) for _, row in source_trees])
    # Polygonal round joins lie slightly inside the analytic circular buffer.
    # Keep an explicit 2 mm construction allowance instead of relaxing clearance.
    forbidden = unary_union([roads.buffer(ROAD_CLEARANCE+.002,quad_segs=32), rail.buffer(.352,quad_segs=32), water.buffer(.35), buildings])
    minx, miny, maxx, maxy = main.bounds
    south_y = min(d['position_m'][1] for d in cad['dock_doors'])
    north_y = max(d['position_m'][1] for d in cad['dock_doors'])
    # The perimeter road and measured warehouse stay fixed. A rear green strip
    # remains between the northern work apron and the road at Y ~= 105.92.
    north_end = 96.5
    north_work = box(minx-11, north_y-.2, maxx+9, north_end)
    south_work = box(minx-11, south_y-24, maxx+9, south_y+.2)
    operations = unary_union([north_work.intersection(box(-166.08,north_y-.2,166.79,north_end)),
                              south_work.intersection(box(-166.08,south_y-24,135.37,south_y+.2))]).difference(main)

    assemblies = defaultdict(list)
    vehicle_rows, vehicle_shapes, cars = [], [], []
    for name, rows in instances.items():
        if not any(token in name for token in ('Trailer', 'Tractor', '_Car_')):
            continue
        length, width = (16.4, 2.68) if 'Trailer' in name else (6.71, 3.) if 'Tractor' in name else (4.52, 1.90)
        for i, row in enumerate(rows):
            f = footprint(row, length, width)
            vehicle_shapes.append(f)
            vehicle_rows.append(dict(mesh=name, instance_index=i, position_m=row['position_m'], rotation_deg=row['rotation_deg']))
            if row.get('assembly_id'):
                assemblies[row['assembly_id']].append((name, row, f))
            if '_Car_' in name:
                cars.append((name, i, row, f))
    occupied = unary_union(vehicle_shapes)
    stands = []
    bay_candidates = []
    approaches = []
    for identity, rows in sorted(assemblies.items()):
        if identity.startswith('Dock'):
            continue
        unit = unary_union([v[2] for v in rows]).convex_hull
        stand = unit.buffer(.65, join_style=2)
        stands.append(stand)
        tractor = next((v[1] for v in rows if 'Tractor' in v[0]), None)
        if tractor is None:
            raise ValueError('Uncoupled parked assembly: '+identity)
        yaw = math.radians(tractor['rotation_deg']);ux, uy = math.cos(yaw), math.sin(yaw)
        cx, cy = tractor['position_m'][:2]
        front = (cx+ux*3.7, cy+uy*3.7)
        end = (front[0]+ux*12, front[1]+uy*12)
        approach = LineString([front, end]).buffer(2.1, cap_style=2)
        approaches.append(approach)
        bay_candidates.append((identity, unit, tractor, front, end))
    # Closing the narrow gaps between existing pads makes a continuous surface;
    # protected source trees and all transport corridors remain hard exclusions.
    parking = unary_union(stands).buffer(3, join_style=2).buffer(-3, join_style=2)
    approach_mask = unary_union(approaches)
    paving = unary_union([old_yard, north_work, south_work, parking, approach_mask]).difference(forbidden).difference(source_tree_mask)
    paving = shapely.make_valid(paving)
    north_green = box(minx-15, north_end+.30, maxx+15, 102.12)
    green = unary_union([old_green, north_green]).difference(paving.buffer(.12)).difference(forbidden)
    green = green.difference(approach_mask.buffer(.5)).difference(occupied.buffer(.5))

    # Only supplemental campus trees may move. Existing Topoexport trees retain
    # their full crown exclusion; no instance is silently discarded.
    displaced = [(i, row) for i, row in enumerate(trees)
                 if row.get('provenance') == 'campus_green_row' and crown(row).intersects(paving)]
    moving_ids = {i for i, _ in displaced}
    fixed_crowns = [crown(row) for i, row in enumerate(trees) if i not in moving_ids]
    fixed_index = shapely.STRtree(fixed_crowns)
    relocation_blockers = unary_union([forbidden, paving.buffer(.20), operations, approach_mask.buffer(.5)])
    candidates = [(row['position_m'][0], 99.30) for _, row in displaced]
    for x in range(math.ceil(green.bounds[0]/2.5), math.floor(green.bounds[2]/2.5)+1):
        for y in range(math.ceil(green.bounds[1]/2.5), math.floor(green.bounds[3]/2.5)+1):
            p = Point(x*2.5, y*2.5)
            if green.covers(p):
                candidates.append((p.x, p.y))
    candidates = sorted(set(candidates))
    moves, unplaced, relocated_crowns = [], [], []
    for index, row in displaced:
        old = row['position_m']
        for x, y in sorted(candidates, key=lambda p: ((p[0]-old[0])**2+(p[1]-old[1])**2, p)):
            c = Point(x, y).buffer(row['crown_radius_m']+TREE_MARGIN, quad_segs=12)
            if not green.covers(c) or c.intersects(relocation_blockers):
                continue
            if len(fixed_index.query(c, predicate='intersects')) or any(c.intersects(other) for other in relocated_crowns):
                continue
            moves.append(dict(source_id=row.get('source_id'), original_instance_index=index,
                              from_position_m=old, to_position_m=[x, y, 0], scale=row['scale'],
                              rotation_deg=row['rotation_deg'], crown_radius_m=row['crown_radius_m'],
                              match_position_tolerance_m=.05))
            relocated_crowns.append(c)
            break
        else:
            unplaced.append(dict(source_id=row.get('source_id'), original_instance_index=index,
                                 from_position_m=old, match_position_tolerance_m=.05,
                                 reason='No safe existing site green position; remove only this supplemental campus tree'))

    ground = Ground(root, manifest, paving.union(green).buffer(3), source_hashes)
    for move in moves:
        x, y = move['to_position_m'][:2]
        move['to_position_m'][2] = round(ground.at(x, y)+.01, 6)
    surfaces, lines = [], []
    def surface(identity, role, geometry, offset):
        if not geometry.is_empty:
            surfaces.append(dict(id=identity, role=role, polygons=polygons(geometry),
                                 z_m=GROUND+offset, elevation_mode='existing_terrain', offset_m=offset,
                                 triangles_m=ground.triangles_for(geometry,offset)))
    def line(identity, role, geometry, width, height, offset, clip):
        geometry = geometry.intersection(clip.buffer(-width/2-.002))
        for n, segment in enumerate(parts(geometry, 'LineString')):
            if segment.length < .08:
                continue
            dense = shapely.segmentize(segment, .75)
            points = [[round(x, 6), round(y, 6), round(ground.at(x, y)+offset, 6)] for x, y in dense.coords]
            lines.append(dict(id=identity+'_'+str(n), role=role, points_m=points,
                              width_m=width, height_m=height, z_m=GROUND+offset,
                              elevation_mode='existing_terrain', offset_m=offset, cap='flat'))
    walkway = box(minx-2.80, miny+4, minx-.45, maxy-4).intersection(paving)
    # Separate the existing car-bay strips by material, at the same elevation.
    # Their width follows the existing 5.4 m U-shaped bay lines plus 20 cm each
    # side; each side's occupied rows form one continuous strip. Clip to the
    # already validated paving so neither the apron perimeter nor green changes.
    car_rows = defaultdict(list)
    for _, _, row, _ in cars:
        car_rows['west' if row['position_m'][0] < 0 else 'east'].append(row['position_m'])
    parking_envelopes = [box(min(p[0] for p in points)-2.90, min(p[1] for p in points)-1.55,
                            max(p[0] for p in points)+2.90, max(p[1] for p in points)+1.55)
                         for points in car_rows.values()]
    car_parking = unary_union(parking_envelopes).intersection(paving).difference(walkway)
    concrete = paving.difference(walkway).difference(car_parking)
    surface('MainConcrete', 'MPR3_Concrete', concrete, .075)
    surface('WestWalkway', 'MPRSC_Walkway', walkway, .075)
    surface('CampusGreen', 'MPRR_CampusGreen', green, .045)
    surface('CarParkingAsphalt', 'MPRSC_ParkingAsphalt', car_parking, .075)

    # Existing dock positions determine markings, not an invented repeated grid.
    for door in cad['dock_doors']:
        x, y = door['position_m'];nx, ny = door['outward_normal_xy'];tx, ty = -ny, nx
        for sign in (-1, 1):
            l = LineString([(x+tx*sign*1.65+nx, y+ty*sign*1.65+ny),
                            (x+tx*sign*1.65+nx*23, y+ty*sign*1.65+ny*23)])
            line('Dock_'+door['id']+'_'+str(sign), 'MPR3_YellowLine', l, .11, 0, .097, paving)
    car_bays = []
    door_clearance = unary_union([Point(d['position_m']).buffer(2.1) for d in cad['pedestrian_doors']])
    wheelstop_safe = paving.difference(door_clearance).difference(occupied.buffer(.10))
    for name, i, row, f in cars:
        x, y = row['position_m'][:2];side = 1 if x < 0 else -1
        mouth_x, rear_x = x-side*2.7, x+side*2.7
        polyline = LineString([(mouth_x, y-1.35), (rear_x, y-1.35), (rear_x, y+1.35), (mouth_x, y+1.35)])
        identity = name+'_'+str(i)
        line('CarBay_'+identity, 'MPR3_WhiteLine', polyline, .10, 0, .097, paving.difference(occupied.buffer(.08)))
        stop_x = x+side*2.55
        line('WheelStop_'+identity, 'MPR4_TerminalCurb', LineString([(stop_x,y-.78),(stop_x,y+.78)]),
             .16, .10, .075, wheelstop_safe)
        mouth = LineString([(mouth_x,y),(mouth_x-side*4,y)]).buffer(1.5,cap_style=2)
        approaches.append(mouth)
        car_bays.append(dict(id=identity, centre_m=[x,y], mouth_direction_xy=[-side,0],
                             mouth_clearance=polygons(mouth), footprint=polygons(f)))
    approach_mask = unary_union(approaches)
    for identity, unit, tractor, front, end in bay_candidates:
        # Remove the forward side of the outline: bays stay visibly open toward
        # the aisle. Painting is also clipped away from actual vehicle bodies.
        yaw=math.radians(tractor['rotation_deg']);ux,uy=math.cos(yaw),math.sin(yaw)
        boundary=unit.buffer(.50,join_style=2).boundary
        mouth=LineString([(front[0]-uy*3,front[1]+ux*3),(front[0]+uy*3,front[1]-ux*3)]).buffer(1.0,cap_style=2)
        boundary=boundary.difference(mouth)
        line('TrailerBay_'+identity,'MPR3_WhiteLine',boundary,.12,0,.097,paving.difference(occupied.buffer(.12)))

    # Raised curbs only follow landscape away from manoeuvring, access mouths,
    # buildings and trees. No obstacle spans a dock approach or parking exit.
    fixed_tree_points = [Point(t['position_m'][:2]).buffer(.65) for i,t in enumerate(trees) if i not in moving_ids]
    all_trunks = unary_union(fixed_tree_points+[Point(m['to_position_m'][:2]).buffer(.65) for m in moves])
    curb_safe = green.difference(operations.buffer(.65)).difference(approach_mask.buffer(.75))
    curb_safe = curb_safe.difference(occupied.buffer(.75)).difference(roads.buffer(.65))
    curb_safe = curb_safe.difference(main.buffer(1.5)).difference(door_clearance).difference(all_trunks)
    curb_path = green.buffer(-.18).boundary
    # Seat the solid curb 1 cm into the .045 m landscape surface. Its top is
    # 16 cm above the .075 m concrete; no thin floating strip remains.
    line('LandscapeCurb','MPR4_TerminalCurb',curb_path,.24,.20,.035,curb_safe)

    raised = unary_union([LineString(v['points_m']).buffer(v['width_m']/2,cap_style=2)
                          for v in lines if v['height_m'] > 0])
    source_tree_overlap = paving.intersection(source_tree_mask).area
    audit_result = dict(paving_area_m2=paving.area, original_paving_area_m2=old_yard.area,
                        car_parking_area_m2=car_parking.area,
                        car_parking_concrete_overlap_m2=car_parking.intersection(concrete).area,
                        car_parking_green_overlap_m2=car_parking.intersection(green).area,
                        car_parking_counts={side:len(points) for side,points in car_rows.items()},
                        green_area_m2=green.area, paving_road_overlap_m2=paving.intersection(roads).area,
                        paving_building_overlap_m2=paving.intersection(main).area,
                        paving_rail_overlap_m2=paving.intersection(rail).area,
                        source_tree_crown_overlap_m2=source_tree_overlap,
                        raised_operating_area_overlap_m2=raised.intersection(operations).area,
                        raised_parking_mouth_overlap_m2=raised.intersection(approach_mask).area,
                        tree_relocations=len(moves), supplemental_trees_to_remove=len(unplaced),
                        vehicles_repositioned=0, source_trees_repositioned=0,
                        north_work_y_m=[north_y,north_end], south_work_y_m=[south_y-24,south_y],
                        semantic_note='Geometric access preservation only; no articulated-vehicle swept-path certification.')
    violations = [k for k,v in audit_result.items() if k.endswith('_overlap_m2') and v > .0001]
    if violations:
        raise ValueError('Site plan violated protected geometry: '+str(violations))
    return dict(schema_version=1,map='/Game/Maps/MPR_CAD_Warehouse_B50B57',
                coordinate_frame='CAD_METRES_POSITIVE_Y',ue_transform=dict(location='(100*x,-100*y,100*z)',yaw='-rotation_deg'),
                ground_z_m=GROUND,source_hashes=source_hashes,
                replacement_mesh_prefixes=['SM_MPRR_MainApron_','SM_MPRR_CampusGreen_','SM_MPRR_ParkingLines_','SM_MPRR_DockLines_'],
                replacement_policy='Replace only these mesh actors in the existing B50B57 map after successful import; preserve all other actors and instance transforms except explicit tree relocation/removal records.',
                surfaces=surfaces,linear_features=lines,terrain_triangles_m=ground.triangles,
                terrain_policy='Split every emitted surface/curb/marking footprint by these existing terrain triangle planes before triangulating; add offset_m. z_m is nominal only, never a global flat elevation.',
                materials={'MPRSC_Walkway':dict(source_srgb_hex='#CAD0CD',roughness=.90,metallic=0),
                           'MPRSC_ParkingAsphalt':dict(source_role='MPR3_Asphalt',source_srgb_hex='#87909A',
                                                      roughness=.92,metallic=0)},
                tree_relocations=moves,tree_removals=unplaced,car_bays=car_bays,
                protected_geometry=dict(roads=polygons(roads),main=polygons(main),rail_corridor=polygons(rail),
                                        operating_area=polygons(operations),parking_mouths=polygons(approach_mask)),
                preserved_instance_counts={k:len(v) for k,v in instances.items()},vehicle_instances=vehicle_rows,
                audit=audit_result)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    plan=build_plan(args.root)
    output=args.output or args.root/OUTPUT
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(plan,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
    print(json.dumps(dict(output=str(output),surfaces=len(plan['surfaces']),linear_features=len(plan['linear_features']),audit=plan['audit']),ensure_ascii=False))


if __name__=='__main__':
    main()
