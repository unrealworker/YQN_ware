"""CAD-aligned houses, restrained yards and collision-checked driveways.

This module has no Blender dependency. The supplied api uses the park
generator's unreflected u/v coordinates. CAD houses retain their source
centres and rectangular axes. Satellite infill is explicitly tagged and is
limited to the existing Gray Pine minor-road network north of the warehouse.
"""
from collections import Counter
import math

import shapely
from shapely.geometry import LineString, MultiPoint, Point, Polygon
from shapely.ops import nearest_points, unary_union

from park_housing import build_house
from park_surfaces import emit_surface


def _world(center, angle, x, y):
    c, s = math.cos(angle), math.sin(angle)
    return center[0] + x * c - y * s, center[1] + x * s + y * c


def _rectangle(center, angle, xmin, ymin, xmax, ymax):
    return Polygon([_world(center, angle, x, y) for x, y in
                    ((xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax))])


def _parts(geometry, kind):
    if geometry.is_empty:
        return []
    if geometry.geom_type == kind:
        return [geometry]
    return [p for g in getattr(geometry, 'geoms', []) for p in _parts(g, kind)]


def _road_candidates(center, roads):
    point = Point(center)
    return sorted(roads, key=lambda r: r['line'].distance(point))


def _pose(footprint, center, road):
    rectangle = footprint.minimum_rotated_rectangle
    points = list(rectangle.exterior.coords)[:-1]
    target = road['line'].interpolate(road['line'].project(Point(center)))
    direction = target.x - center[0], target.y - center[1]
    angles = [math.atan2(b[1] - a[1], b[0] - a[0])
              for a, b in zip(points, points[1:] + points[:1])]
    angle = max(angles, key=lambda a: math.sin(a) * direction[0] - math.cos(a) * direction[1])
    c, s = math.cos(angle), math.sin(angle)
    local = [((p[0]-center[0])*c+(p[1]-center[1])*s,
              -(p[0]-center[0])*s+(p[1]-center[1])*c) for p in points]
    half_w = min(max(p[0] for p in local), -min(p[0] for p in local))
    half_d = min(max(p[1] for p in local), -min(p[1] for p in local))
    return angle, 1.94 * half_w, 1.94 * half_d, rectangle


def _safe_shape(center, angle, w, d, road_mask, scope, campus, occupied):
    for scale in (1, .96, .92, .88, .84):
        width, depth = w * scale, d * scale
        if width < 4 or depth < 5:
            continue
        shape = _rectangle(center, angle, -width/2, -depth/2, width/2, depth/2)
        if not scope.covers(shape) or shape.intersects(campus) or shape.intersects(road_mask):
            continue
        if any(shape.intersects(other.buffer(.35)) for other in occupied):
            continue
        return width, depth, shape
    return None


def _driveway(plan, plans, all_source_shapes, roads, road_surface, scope, campus):
    start = Point(plan['house']['garage_front_world'])
    angle, center = plan['angle'], plan['center']
    forward = math.sin(angle), -math.cos(angle)
    own_id = plan['cad_id']
    obstacles = [p['shape'].buffer(.32) for p in plans if p is not plan and p['shape'].distance(start) < 50]
    obstacles.extend(shape.buffer(.20) for cad_id, shape in all_source_shapes
                     if cad_id != own_id and shape.distance(start) < 50)
    obstacle = unary_union(obstacles + [campus.buffer(.25)])
    width = min(4.6, max(2.6, plan['house']['garage_width']))
    for road in _road_candidates((start.x, start.y), roads)[:6]:
        edge = nearest_points(start, road['surface'])[1]
        dx, dy = edge.x - start.x, edge.y - start.y
        length = math.hypot(dx, dy)
        if not .8 < length < 34 or (dx * forward[0] + dy * forward[1]) / length < .52:
            continue
        end = edge.x + dx / length * .18, edge.y + dy / length * .18
        line = LineString([(start.x, start.y), end])
        strip = line.buffer(width/2, cap_style='flat')
        other_road_area = strip.intersection(road_surface).difference(road['surface'].buffer(.55)).area
        if (scope.covers(strip) and not strip.intersects(obstacle)
                and other_road_area < .15):
            return line, strip, 'connected', road['id']
    # A blocked or misaligned garage retains a short apron rather than a
    # driveway cutting through a neighbour. Trim from the garage outward.
    for length in (5.0, 3.5, 2.0, 1.0):
        end = start.x + forward[0]*length, start.y + forward[1]*length
        line = LineString([(start.x, start.y), end])
        strip = line.buffer(width/2, cap_style='flat')
        if scope.covers(strip) and not strip.intersects(obstacle) and not strip.intersects(road_surface):
            return line, strip, 'short_apron', None
    return None, Polygon(), 'omitted_no_clearance', None


def build_residential(api, cad, road_specs, road_surface, scope_polygon, campus_polygon):
    """Build CAD houses and modest satellite-confirmed Gray Pine infill.

    Required api key: mesh. Optional keys: box, tree, car, counts, preview.
    Returns a JSON-serializable manifest with houses, rejected candidates and
    statistics. footprint_uv_m is the actual model's oriented bounds, not
    the irregular source footprint; source geometry is kept separately.
    """
    roads = []
    for spec in road_specs:
        if spec.get('layer') == 'highways' or not spec.get('context', True):
            continue
        if len(spec.get('path', [])) < 2:
            continue
        line = LineString(spec['path'])
        if line.length < .1:
            continue
        roads.append(dict(id=spec.get('id', 'road'), layer=spec.get('layer', ''),
                          width=spec['width'], line=line,
                          surface=line.buffer(spec['width']/2, cap_style='flat', join_style='round')))
    if not roads:
        return dict(houses=[], rejected=[], statistics={'houses':0, 'reason':'no accessible street centrelines'})
    road_mask = road_surface.buffer(.65)
    campus = campus_polygon.buffer(.50)
    scope = scope_polygon.buffer(-.15)
    source_shapes = [(b['id'], Polygon(b['footprint_uv_m'])) for b in cad['buildings']
                     if b['handle'] != cad.get('warehouse_handle', '1eb6')]
    source_by_id = dict(source_shapes)
    plans, rejected = [], []
    for building in cad['buildings']:
        if building['handle'] == cad.get('warehouse_handle', '1eb6'):
            continue
        center = building['centroid_uv_m']
        source = source_by_id[building['id']]
        if not scope.covers(Point(center)):
            continue
        road = _road_candidates(center, roads)[0]
        angle, width, depth, source_rectangle = _pose(source, center, road)
        fit = _safe_shape(center, angle, width, depth, road_mask, scope, campus,
                          [p['shape'] for p in plans])
        if fit is None:
            rejected.append(dict(cad_id=building['id'], center_uv_m=center,
                                 reason='insufficient footprint size, boundary, or road clearance'))
            continue
        width, depth, shape = fit
        plans.append(dict(cad_id=building['id'], source_type='cad', center=list(center),
                          angle=angle, w=width, d=depth, shape=shape,
                          source_rectangle=source_rectangle,
                          source_footprint=building['footprint_uv_m'],
                          street_id=road['id'], variant=int(building['handle'],16)%4))

    # Source CAD has only four houses north of the warehouse, whereas the
    # supplied satellite view shows populated Gray Pine street branches.
    # Infill follows those actual minor-road centrelines, never invented roads.
    infill_limit = min(60, max(0, 340 - len(plans)))
    infill_count = 0
    north_roads = [r for r in roads if r['layer']=='minor_roads'
                   and -195 < r['line'].centroid.y < -48
                   and -90 < r['line'].centroid.x < 485]
    north_roads.sort(key=lambda r:(-r['line'].length, r['id']))
    source_union = unary_union([shape for _, shape in source_shapes])
    for road in north_roads:
        line = road['line']
        if line.length < 24:
            continue
        count = max(1, int((line.length-15)/24))
        for index in range(count):
            distance = min(line.length-9, 12+index*24)
            q = line.interpolate(distance)
            a, b = line.interpolate(max(0,distance-.5)), line.interpolate(min(line.length,distance+.5))
            tangent = (b.x-a.x, b.y-a.y)
            length = math.hypot(*tangent)
            if length < 1e-6:
                continue
            tx, ty = tangent[0]/length, tangent[1]/length
            for side in (-1, 1):
                if infill_count >= infill_limit:
                    break
                setback = road['width']/2 + 10.1
                center = [q.x-ty*side*setback, q.y+tx*side*setback]
                if not (-180 < center[1] < -48 and -70 < center[0] < 485):
                    continue
                angle = math.atan2(ty,tx) + (0 if side==1 else math.pi)
                width, depth = 11.4, 12.5
                candidate = _rectangle(center,angle,-width/2,-depth/2,width/2,depth/2)
                if candidate.buffer(3).intersects(source_union):
                    continue
                fit = _safe_shape(center,angle,width,depth,road_mask,scope,campus,
                                  [p['shape'].buffer(2.4) for p in plans])
                if fit is None:
                    continue
                width, depth, shape = fit
                plans.append(dict(cad_id=None, source_type='satellite_infill', center=center,
                                  angle=angle,w=width,d=depth,shape=shape,
                                  source_rectangle=shape,source_footprint=None,
                                  street_id=road['id'],variant=infill_count%4))
                infill_count += 1
    if not plans:
        return dict(houses=[],rejected=rejected,statistics={'houses':0})

    templates = [build_house({'mesh':lambda *args:None},0,0,12,13,0,variant)
                 for variant in range(4)]
    for plan in plans:
        variant, width, depth = plan['variant'], plan['w'], plan['d']
        native_scale = min(1.08,max(.86,math.sqrt(width/12*depth/13)))
        target_height = 7.45 + .12*variant
        zscale = target_height/(templates[variant]['height']*native_scale)
        roof_points = []
        def house_mesh(role, vertices, faces):
            if role in ('Roofs','Solar'):
                roof_points.extend((p[0],p[1]) for p in vertices)
            api['mesh'](role,[(x,y,z*zscale) for x,y,z in vertices],faces)
        house_api = dict(api,mesh=house_mesh)
        house = build_house(house_api,*plan['center'],width,depth,plan['angle'],variant)
        house['height'] *= zscale
        plan['house'] = house
        local = house['bounds_local']
        actual = _rectangle(plan['center'],plan['angle'],local[0][0],local[1][0],local[0][1],local[1][1])
        plan['actual_shape'] = actual
        roof = MultiPoint(roof_points).convex_hull
        plan['roof_outside'] = roof.difference(plan['source_rectangle'].buffer(1e-7)).area
        if plan['roof_outside'] > 1e-6:
            raise ValueError('house roof escaped its source rectangle')
        if 'counts' in api:
            api['counts']['context_houses'] = api['counts'].get('context_houses',0)+1
        if isinstance(api.get('preview'),list):
            api['preview'].append(('Buildings',list(actual.exterior.coords)[:-1]))

    if len(plans)>1:
        cells = list(shapely.voronoi_polygons(MultiPoint([p['center'] for p in plans]),
                     extend_to=scope.envelope,ordered=True).geoms)
    else:
        cells = [scope]
    all_shapes = unary_union([p['shape'] for p in plans])
    yard_exclusion = unary_union([all_shapes.buffer(.45),road_surface.buffer(.55),campus])
    driveways = []
    for plan in plans:
        driveway = _driveway(plan,plans,source_shapes,roads,road_surface,scope,campus)
        plan['driveway'] = driveway
        driveways.append(driveway[1])
    driveway_union = unary_union(driveways)
    # Some curved-street driveways meet at a shared mouth. Emit their union
    # once so the concrete does not contain overlapping coplanar faces.
    if not driveway_union.is_empty:
        emit_surface(api,driveway_union,'Hardstand',.035)
        if isinstance(api.get('preview'),list):
            api['preview'].extend(('Hardstand',list(p.exterior.coords)[:-1])
                                  for p in _parts(driveway_union,'Polygon'))
    fence_clear=unary_union([all_shapes.buffer(.5),road_surface.buffer(.75),driveway_union.buffer(.5),campus])
    records, lawn_polygons = [], []
    total_fences, parked_cars, trees = 0, 0, 0
    for index,(plan,cell) in enumerate(zip(plans,cells)):
        center,angle,width,depth = plan['center'],plan['angle'],plan['w'],plan['d']
        line,driveway,status,driveway_road = plan['driveway']
        lot = _rectangle(center,angle,-width/2-2.2,-depth/2-7.0,width/2+2.2,depth/2+3.6)
        lot = lot.intersection(cell.buffer(-.08)).intersection(scope).difference(campus)
        front = _rectangle(center,angle,-width/2-1.8,-depth/2-7.0,width/2+1.8,-depth/2+.5)
        lawn = front.intersection(lot).difference(yard_exclusion).difference(driveway_union.buffer(.18))
        lawn = unary_union([p for p in _parts(lawn,'Polygon') if p.area > 1.2])
        if not lawn.is_empty:
            emit_surface(api,lawn,'Landscape',.025)
            lawn_polygons.extend(_parts(lawn,'Polygon'))
            if isinstance(api.get('preview'),list):
                api['preview'].extend(('Landscape',list(p.exterior.coords)[:-1]) for p in _parts(lawn,'Polygon'))
        fence_paths=[]
        x0,x1,y0,y1=-width/2-2.0,width/2+2.0,-depth/2+1.3,depth/2+3.3
        for a,b in (((x0,y0),(x0,y1)),((x0,y1),(x1,y1)),((x1,y1),(x1,y0))):
            candidate=LineString([_world(center,angle,*a),_world(center,angle,*b)])
            safe=candidate.intersection(cell.buffer(-.14)).intersection(scope).difference(fence_clear)
            for segment in _parts(safe,'LineString'):
                points=list(segment.coords)
                for start,end in zip(points,points[1:]):
                    length=math.dist(start,end)
                    if length<.6:
                        continue
                    if callable(api.get('box')):
                        api['box']('Buildings',((start[0]+end[0])/2,(start[1]+end[1])/2,.70),
                                   (length,.16,1.4),math.atan2(end[1]-start[1],end[0]-start[0]))
                    fence_paths.append([list(start),list(end)])
                    total_fences+=1
        if line is not None and line.length>7.2 and index%3==0 and callable(api.get('car')):
            point=line.interpolate(min(3.7,line.length*.45))
            a,b=list(line.coords)[0],list(line.coords)[-1]
            car_angle=math.atan2(b[1]-a[1],b[0]-a[0])
            car_shape=_rectangle((point.x,point.y),car_angle,-2.3,-.95,2.3,.95)
            if driveway.covers(car_shape) and not car_shape.intersects(road_surface):
                api['car'](point.x,point.y,car_angle,index%9==0)
                parked_cars+=1
        if index%5==0 and lawn.area>12 and callable(api.get('tree')):
            point=lawn.representative_point()
            if point.distance(road_surface)>2 and point.distance(all_shapes)>1.5:
                api['tree'](point.x,point.y,3.5,.65)
                trees+=1
        actual=plan['actual_shape']
        clearance=actual.distance(road_surface)
        record=dict(cad_id=plan['cad_id'],source_type=plan['source_type'],
                    center=plan['center'],center_uv_m=plan['center'],angle=angle,angle_rad=angle,
                    size_m=[width,depth],height_m=plan['house']['height'],variant=plan['variant'],
                    footprint_uv_m=[list(p) for p in actual.exterior.coords],
                    footprintbounds=list(actual.bounds),
                    footprint_bounds_uv_m=[list(actual.bounds[:2]),list(actual.bounds[2:])],
                    cad_footprint_uv_m=plan['source_footprint'],
                    road_clearance_m=clearance,clearance=clearance,
                    roof_outside_cad_rectangle_area_m2=plan['roof_outside'],
                    street_id=plan['street_id'],driveway_status=status,driveway_road_id=driveway_road,
                    driveway_length_m=line.length if line is not None else 0,
                    driveway_path_uv_m=[list(p) for p in line.coords] if line is not None else [],
                    driveway_polygon_uv_m=[list(p) for p in driveway.exterior.coords] if not driveway.is_empty else [],
                    front_lawn_area_m2=lawn.area,side_rear_fence_paths_uv_m=fence_paths,
                    fence_height_m=1.4,source_height_status='CADmapper default 3m extrusion ignored; model height is visual context')
        records.append(record)
    counts=Counter(r['source_type'] for r in records)
    statuses=Counter(r['driveway_status'] for r in records)
    statistics=dict(houses=len(records),cad_houses=counts['cad'],satellite_infill=counts['satellite_infill'],
                    rejected=len(rejected),min_road_clearance_m=min(r['road_clearance_m'] for r in records),
                    driveway_status_counts=dict(statuses),side_rear_wall_segments=total_fences,
                    driveway_surface_union_area_m2=driveway_union.area,
                    shared_driveway_mouth_area_m2=max(0,sum(p.area for p in driveways)-driveway_union.area),
                    front_lawn_area_m2=sum(p.area for p in lawn_polygons),
                    front_lawn_overlap_area_m2=max(0,sum(p.area for p in lawn_polygons)-unary_union(lawn_polygons).area),
                    parked_driveway_cars=parked_cars,front_yard_tree_candidates=trees,
                    model_height_range_m=[min(r['height_m'] for r in records),max(r['height_m'] for r in records)])
    if 'counts' in api:
        api['counts']['satellite_infill_houses']=counts['satellite_infill']
        api['counts']['residential_driveways']=sum(not p.is_empty for p in driveways)
        api['counts']['residential_yard_wall_segments']=total_fences
    return dict(houses=records,rejected=rejected,statistics=statistics,
                satellite_infill=dict(basis='User-provided Gray Pine satellite close-up; existing CAD minor-road centrelines',
                                      count=counts['satellite_infill'],maximum=60,
                                      note='Infill building positions are illustrative and explicitly separate from CAD-derived positions.'))
