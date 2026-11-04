"""Full-source context for the independent MPR rebuild.

No previous completed-frame crop is used. Only the caller's main-warehouse
protection geometry is immutable. Positions come from Topoexport; elevations
can be supplied by the rebuilt terrain, keeping each building a rigid volume.
The function emits geometry and instance data without saving Blender/UE files.
"""
import math
import hashlib
from collections import Counter, defaultdict
from shapely.geometry import GeometryCollection, Point, Polygon, LineString, MultiPoint
from shapely.ops import unary_union, triangulate
from shapely.geometry.polygon import orient

TREE_NAME = "SM_MPR4_Tree_Oak"
TREE_PATH = "/Game/MPRWarehouse/ReferenceV4/Props/Meshes/" + TREE_NAME
TREE_RADIAL_EXTENT_M = 6.418041146908877
ROLES = dict(wall="MPR4_ContextWall", roof="MPR4_ContextRoof",
             trim="MPR4_ContextTrim", glass="MPR4_ContextGlass",
             paving="MPR4_ContextPaving")

def _polygons(geometry):
    if geometry.is_empty:
        return []
    if geometry.geom_type == "Polygon":
        return [geometry]
    if hasattr(geometry, "geoms"):
        return [p for child in geometry.geoms for p in _polygons(child)]
    return []

def source_footprint(row, transform_xy):
    """Union projected source triangles, retaining concavities and courtyards.

    Roof/base triangulation supplies the horizontal coverage. Vertical faces
    collapse to lines and are discarded, never replaced with a convex hull.
    """
    points = [tuple(map(float, transform_xy(v[:2]))) for v in row["vertices"]]
    pieces = []
    for face in row["faces"]:
        if len(face) < 3:
            continue
        polygon = Polygon([points[i] for i in face])
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        if polygon.area > 1e-7:
            pieces.extend(_polygons(polygon))
    if not pieces:
        return GeometryCollection()
    # Only sub-millimetre coordinate noise may be removed, never shape detail.
    return unary_union(pieces).buffer(0).simplify(.0002, preserve_topology=True)

def _stable_unit(name, salt=""):
    return int.from_bytes(hashlib.sha256((name + salt).encode()).digest()[:4],
                          "little") / 4294967295.0

def _merge(target, model, name, origin=(0, 0, 0), yaw=0):
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    ox, oy, oz = origin
    for roles in model.data.values():
        for role, (vertices, faces) in roles.items():
            target.mesh(name, role, [(ox + c*x - s*y, oy + s*x + c*y, oz+z)
                                     for x, y, z in vertices], faces)

def _envelope(model, origin=(0, 0, 0), yaw=0):
    """Conservative occupancy of ALL roof, porch, door and trim geometry."""
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    x, y, _ = origin
    return MultiPoint([(x+c*vx-s*vy, y+s*vx+c*vy)
                       for roles in model.data.values()
                       for vertices, _ in roles.values()
                       for vx, vy, _ in vertices]).convex_hull

def _rectangle(polygon):
    points = list(polygon.minimum_rotated_rectangle.exterior.coords)[:-1]
    a, b, d = points[0], points[1], points[3]
    w, depth = math.dist(a, b), math.dist(a, d)
    yaw = math.degrees(math.atan2(b[1]-a[1], b[0]-a[0]))
    if depth > w:
        w, depth = depth, w
        yaw += 90
    center = list(polygon.minimum_rotated_rectangle.centroid.coords)[0]
    return center, w, depth, yaw

def _extrude(geo, name, polygon, height, *, windows=True):
    """Closed shell including inner courtyard walls; no bridged concavities."""
    polygon = orient(polygon, sign=1.0)
    for tri in triangulate(polygon):
        if not polygon.covers(tri):
            continue
        pts = list(orient(tri, sign=1.0).exterior.coords)[:-1]
        geo.mesh(name, ROLES["roof"], [(x, y, height) for x, y in pts], [(0, 1, 2)])
        geo.mesh(name, ROLES["wall"], [(x, y, 0) for x, y in pts], [(2, 1, 0)])
    for ring in [polygon.exterior, *polygon.interiors]:
        pts = list(ring.coords)
        for a, b in zip(pts, pts[1:]):
            geo.mesh(name, ROLES["wall"],
                     [(a[0], a[1], 0), (b[0], b[1], 0),
                      (b[0], b[1], height), (a[0], a[1], height)], [(0, 1, 2, 3)])
            geo.segment(name, ROLES["trim"], a, b, .13, height+.04, .13)
            length = math.dist(a, b)
            if length < 4 or not windows:
                continue
            # Quiet repeated facade recesses follow the measured facade, not
            # a global grid. No windows are generated on very short edges.
            tx, ty = (b[0]-a[0])/length, (b[1]-a[1])/length
            nx, ny = ty, -tx
            yaw = math.degrees(math.atan2(ty, tx))
            count = max(1, min(20, int(length/5)))
            for index in range(count):
                distance = length*(index+.5)/count
                x, y = a[0]+tx*distance+nx*.025, a[1]+ty*distance+ny*.025
                z = min(2.4, height*.55)
                width, high = min(1.7, length/count*.48), min(1.25, height*.3)
                geo.box(name, ROLES["trim"], (x, y, z), (width+.12, .065, high+.12), yaw)
                geo.box(name, ROLES["glass"], (x+nx*.04, y+ny*.04, z), (width, .026, high), yaw)

MATERIALS = {
    'MPRR_ContextWall': dict(base_color=[.70, .735, .72], roughness=.9),
    'MPRR_ContextRoof': dict(base_color=[.61, .65, .66], roughness=.9),
    'MPRR_ContextTrim': dict(base_color=[.56, .61, .59], roughness=.9),
    'MPRR_ContextGlass': dict(base_color=[.30, .36, .35], roughness=.60),
    'MPRR_ContextPaving': dict(base_color=[.53, .57, .54], roughness=.96),
    'MPRR_Bark': dict(base_color=[.205, .18, .135], roughness=.95),
    'MPRR_LeafMid': dict(base_color=[.29, .355, .28], roughness=.90, two_sided=True),
    'MPRR_LeafLight': dict(base_color=[.375, .425, .35], roughness=.90, two_sided=True),
    'MPRR_LeafShade': dict(base_color=[.215, .285, .215], roughness=.90, two_sided=True),
}


class _MaterialSink:
    def __init__(self, geo):
        self.geo = geo

    def mesh(self, name, role, vertices, faces):
        self.geo.mesh(name, role.replace('MPR4_Context', 'MPRR_Context'), vertices, faces)


def _doors(model, name, polygon, height, main_center):
    """Closed contextual dock doors, with real frames and a shallow canopy."""
    if polygon.area < 3000 or height < 4:
        return 0
    pts = list(polygon.exterior.coords)
    edges = [(a, b, math.dist(a, b)) for a, b in zip(pts, pts[1:])]
    longest = max(length for _, _, length in edges)
    candidates = [(a, b, length) for a, b, length in edges if length > max(55, longest*.60)]
    if not candidates:
        return 0
    a, b, length = min(candidates, key=lambda e: Point((e[0][0]+e[1][0])/2,
                                 (e[0][1]+e[1][1])/2).distance(main_center))
    tx, ty = (b[0]-a[0])/length, (b[1]-a[1])/length
    nx, ny = ty, -tx
    midpoint = ((a[0]+b[0])/2, (a[1]+b[1])/2)
    if polygon.covers(Point(midpoint[0]+nx*.05, midpoint[1]+ny*.05)):
        nx, ny = -nx, -ny
    yaw = math.degrees(math.atan2(ty, tx))
    count = min(40, max(4, int(length/8)))
    door_h = min(4.1, height*.62)
    for index in range(count):
        at = (index+.5)*length/count
        x, y = a[0]+tx*at, a[1]+ty*at
        # Flush closed doors do not require fake holes through a solid wall.
        model.box(name, 'MPR4_ContextTrim', (x+nx*.045, y+ny*.045, door_h/2+.25),
                  (3.6, .10, door_h+.25), yaw)
        model.box(name, 'MPR4_ContextGlass', (x+nx*.105, y+ny*.105, door_h/2+.25),
                  (3.15, .035, door_h), yaw)
        for offset in (-1.9, 1.9):
            model.box(name, 'MPR4_ContextWall', (x+tx*offset+nx*.18, y+ty*offset+ny*.18, (door_h+.6)/2),
                      (.32, .42, door_h+.6), yaw)
        model.box(name, 'MPR4_ContextRoof', (x+nx*.40, y+ny*.40, door_h+.65),
                  (4.35, 1.0, .18), yaw)
    return count


def _roof_vents(model, name, polygon, height):
    """Sparse low-profile plant, fully inside the measured warehouse roof."""
    if polygon.area <= 3000 or height <= 4:
        return 0
    if 4*math.pi*polygon.area/polygon.length**2 > .94:
        return 0  # Cylindrical storage tanks are not warehouse buildings.
    safe = polygon.buffer(-8.)
    if safe.is_empty:
        return 0
    center, width, depth, yaw = _rectangle(polygon)
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    count = 0
    for ix in range(math.ceil(-width/80), math.floor(width/80)+1):
        for iy in range(math.ceil(-depth/80), math.floor(depth/80)+1):
            x = center[0]+c*ix*40-s*iy*40
            y = center[1]+s*ix*40+c*iy*40
            footprint = Polygon([(x+c*dx-s*dy, y+s*dx+c*dy)
                                 for dx, dy in [(-1.4, -.9), (1.4, -.9), (1.4, .9), (-1.4, .9)]])
            if not safe.covers(footprint):
                continue
            # Each unit is two closed cuboids; no thin floating decal surfaces.
            model.box(name, ROLES['trim'], (x, y, height+.06), (2.8, 1.8, .12), yaw)
            model.box(name, ROLES['wall'], (x, y, height+.31), (2.2, 1.3, .38), yaw)
            count += 1
    return count


def _nearby(accepted, x, y, radius):
    return [(px, py, pr) for px, py, pr in accepted
            if abs(px-x) <= radius and abs(py-y) <= radius
            and (px-x)**2+(py-y)**2 < radius**2]


def _terrain_support(footprint, height_at):
    """A level base over the sampled boundary; no building deformation."""
    samples = []
    for poly in _polygons(footprint):
        for ring in [poly.exterior, *poly.interiors]:
            pts = list(ring.coords)
            for a, b in zip(pts, pts[1:]):
                divisions = max(1, math.ceil(math.dist(a, b)/8.0))
                for step in range(divisions):
                    t = step/divisions
                    x, y = a[0]*(1-t)+b[0]*t, a[1]*(1-t)+b[1]*t
                    z = float(height_at(x, y))
                    assert math.isfinite(z), ('Non-finite terrain support', x, y, z)
                    samples.append(z)
    lo, hi = min(samples), max(samples)
    return dict(sample_count=len(samples), max_sample_spacing_m=8., terrain_min_z_m=lo,
                terrain_max_z_m=hi, terrain_span_m=hi-lo, base_z_m=hi+.025,
                foundation_bottom_z_m=lo-.1,
                foundation_height_m=hi-lo+.125 if hi-lo > .12 else 0.)


def _foundation(geo, name, footprint, bottom, top):
    """Closed foundation, precisely within the original building footprint."""
    for polygon in _polygons(footprint):
        polygon = orient(polygon, sign=1.0)
        for triangle in triangulate(polygon):
            if not polygon.covers(triangle):
                continue
            pts = list(orient(triangle, sign=1.0).exterior.coords)[:-1]
            geo.mesh(name, 'MPR4_ContextPaving', [(x, y, top) for x, y in pts], [(0, 1, 2)])
            geo.mesh(name, 'MPR4_ContextPaving', [(x, y, bottom) for x, y in pts], [(2, 1, 0)])
        for ring in [polygon.exterior, *polygon.interiors]:
            pts = list(ring.coords)
            for a, b in zip(pts, pts[1:]):
                geo.mesh(name, 'MPR4_ContextPaving',
                         [(a[0], a[1], bottom), (b[0], b[1], bottom),
                          (b[0], b[1], top), (a[0], a[1], top)], [(0, 1, 2, 3)])


def build_rebuild_context(geo, source, transform_xy, main_protected_geometry,
                          road_geometry, rail_geometry, water_geometry,
                          source_frame_geometry, *, ground_z=-1.2, tile_size=150.,
                          ground_elevation=None, supplement_limit=220,
                          campus_green=None, tree_exclusion=None):
    """Return ``instances/reused_meshes/materials/audit`` for the full source.

    ``ground_elevation(x,y)`` is optional. Corners and boundary samples at no
    more than 8m select a level base; facade and roof vertices remain rigid.
    Both supplied road and railway geometry represent their complete corridors.
    Trees are full-canopy excluded from all occupied/protected geometry.
    """
    from mpr_blender_common import Geometry
    import build_mpr_reference_context_v4 as style
    objects = source['objects'] if isinstance(source, dict) else source
    frame = source_frame_geometry
    protection = main_protected_geometry.buffer(.25)
    roads = road_geometry.buffer(.45)
    rail = rail_geometry.buffer(.65)
    water = water_geometry.buffer(.4)
    transport = unary_union([roads, rail, water])
    height_at = ground_elevation if ground_elevation else lambda x, y: ground_z
    main_center = main_protected_geometry.centroid
    output = _MaterialSink(geo)
    audit = dict(policy='Full registered Topoexport context; protect main warehouse only; no previous scene-frame crop',
                 buildings=[], trees=[], rejected_buildings=[], rejected_trees=[], source_driven=True,
                 supplement_policy='Sparse roadside and source-green-space gaps; fixed source IDs; full-canopy clearance')
    raw = [(row, source_footprint(row, transform_xy)) for row in objects if row.get('layer') == 'TPX_BUILDINGS']
    occupied = []
    for row, footprint in raw:
        identity = row['name']
        reason = None
        if footprint.is_empty or footprint.area < 3:
            reason = 'tiny_or_invalid_source'
        elif footprint.intersects(protection):
            reason = 'main_warehouse_protection'
        elif not frame.covers(footprint.buffer(.25)):
            reason = 'source_frame_boundary'
        elif footprint.intersects(transport):
            reason = 'transport_or_water_conflict'
        if reason:
            audit['rejected_buildings'].append(dict(source_id=identity, reason=reason))
            continue
        polys = _polygons(footprint)
        zs = [v[2] for v in row['vertices']]
        height = max(zs)-min(zs)
        if height < .2:
            audit['rejected_buildings'].append(dict(source_id=identity, reason='missing_source_height'))
            continue
        model = Geometry()
        cx, cy = footprint.centroid.coords[0]
        support = _terrain_support(footprint, height_at)
        base_z = support['base_z_m']
        origin, yaw, kind = (0, 0, base_z), 0., 'source_shell'
        dock_count = 0
        if len(polys) == 1 and not polys[0].interiors:
            poly = polys[0]
            center, width, depth, angle = _rectangle(poly)
            if (poly.area/poly.minimum_rotated_rectangle.area > .982
                    and 5 <= depth <= 16 and width <= 30 and poly.area < 420 and 3.5 <= height <= 13):
                # Keep roof axis/footprint, place the porch on the closer street.
                radians = math.radians(angle)
                normal = (-math.sin(radians), math.cos(radians))
                front = Point(center[0]-normal[0]*(depth/2+2), center[1]-normal[1]*(depth/2+2))
                back = Point(center[0]+normal[0]*(depth/2+2), center[1]+normal[1]*(depth/2+2))
                if back.distance(roads) < front.distance(roads):
                    angle += 180
                previous = style.G
                try:
                    style.G = model
                    style.house(identity, width, depth, max(2.65, height-min(2.3, depth*.23)), height,
                                variant=int(_stable_unit(identity)*2), compact=True)
                finally:
                    style.G = previous
                origin, yaw, kind = (center[0], center[1], base_z), angle, 'source_aligned_house'
        if not model.data:
            for poly in polys:
                circular = 4*math.pi*poly.area/poly.length**2 > .94 and poly.area > 120 and len(poly.exterior.coords) > 12
                _extrude(model, identity, poly, height, windows=not circular)
                if circular:
                    kind = 'source_tank'
                else:
                    dock_count += _doors(model, identity, poly, height, main_center)
        envelope = _envelope(model, origin, yaw)
        if envelope.intersects(protection) or envelope.intersects(transport) or not frame.covers(envelope):
            # A safe source footprint stays in place; decorative eaves and
            # canopies may be omitted rather than moving or rotating its body.
            model = Geometry()
            for poly in polys:
                _extrude(model, identity, poly, height, windows=kind != 'source_tank')
            origin, yaw, kind, dock_count = (0, 0, base_z), 0., 'exact_shell_clearance_fallback', 0
            envelope = _envelope(model, origin, yaw)
        if envelope.intersects(protection) or envelope.intersects(transport) or not frame.covers(envelope):
            audit['rejected_buildings'].append(dict(source_id=identity, reason='full_geometry_clearance'))
            continue
        # Large source shells use measured XY coordinates and a rigid base Z.
        # Equipment stays >=8m inside those roofs, so it cannot alter occupancy.
        roof_vents = sum(_roof_vents(model, identity, poly, height) for poly in polys)
        tile = (math.floor(cx/tile_size), math.floor(cy/tile_size))
        name = 'SM_MPRR_Context_%d_%d' % tile
        _merge(output, model, name, origin, yaw)
        if support['foundation_height_m'] > 0:
            _foundation(output, name, footprint, support['foundation_bottom_z_m'], base_z)
        occupied.append(envelope)
        audit['buildings'].append(dict(source_id=identity, mesh=name, kind=kind, source_height_m=height,
                    base_z_m=base_z, terrain_support=support, terrain_span_m=support['terrain_span_m'],
                    foundation_height_m=support['foundation_height_m'],
                    tile=list(tile), source_footprints_m=[list(p.exterior.coords) for p in polys],
                    full_geometry_envelope_m=list(envelope.exterior.coords), rotation_deg=yaw,
                    dock_doors=dock_count, roof_ventilation_units=roof_vents,
                    protected_clearance_m=envelope.distance(main_protected_geometry)))

    all_buildings = unary_union([fp for _, fp in raw]+occupied)
    blockers = unary_union([protection, transport, all_buildings.buffer(.3),
                           tree_exclusion if tree_exclusion is not None else GeometryCollection()])
    accepted, instances = [], []

    def place_tree(identity, xy, scale, provenance):
        x, y = map(float, xy)
        radius = TREE_RADIAL_EXTENT_M*scale
        crown = Point(x, y).buffer(radius+.25, quad_segs=16)
        reason = None
        if not frame.covers(crown):
            reason = 'source_frame_boundary'
        elif crown.intersects(protection):
            reason = 'main_warehouse_protection'
        elif crown.intersects(blockers):
            reason = 'full_canopy_clearance'
        elif any(math.hypot(x-px, y-py) < (radius+pr)*.61 for px, py, pr in _nearby(accepted, x, y, 15)):
            reason = 'crowded_canopy'
        if reason:
            if provenance == 'source':
                audit['rejected_trees'].append(dict(source_id=identity, reason=reason))
            return False
        tile = (math.floor(x/tile_size), math.floor(y/tile_size))
        item = dict(position_m=[x, y, float(height_at(x, y))+.01], rotation_deg=360*_stable_unit(identity, 'yaw'),
                    scale=[scale]*3, source_id=identity, tile=list(tile), crown_radius_m=radius, provenance=provenance)
        instances.append(item)
        accepted.append((x, y, radius))
        audit['trees'].append(dict(source_id=identity, position_m=item['position_m'], crown_radius_m=radius,
                    provenance=provenance, protected_clearance_m=crown.distance(main_protected_geometry)))
        return True

    for row in objects:
        if row.get('layer') != 'TPX_VEGETATION_TREES_INDIVIDUAL':
            continue
        identity = row['name']
        point = row.get('position', [r[3] for r in row['matrix'][:3]])
        place_tree(identity, transform_xy(point[:2]), .48+.34*_stable_unit(identity, 'scale'), 'source')
    source_accepted = len(instances)

    # Smaller, ordered campus trees fit the narrow planted strip without
    # relaxing the source-tree canopy exclusions. Stations follow the main
    # warehouse's long axis, keeping the rear row aligned across separate beds.
    campus_added = 0
    campus_positions = []
    if campus_green is not None and not campus_green.is_empty:
        min_scale = .24
        radius = TREE_RADIAL_EXTENT_M*min_scale+.25
        feasible = campus_green.buffer(-radius).difference(blockers.buffer(radius)).intersection(frame.buffer(-radius))
        rectangle = list(main_protected_geometry.minimum_rotated_rectangle.exterior.coords)
        a, b = max(zip(rectangle, rectangle[1:]), key=lambda pair: math.dist(*pair))
        length = math.dist(a, b)
        ux, uy = (b[0]-a[0])/length, (b[1]-a[1])/length
        # Make ordering independent of exterior ring winding.
        if ux < 0 or (abs(ux) < 1e-8 and uy < 0):
            ux, uy = -ux, -uy
        nx, ny = -uy, ux
        coordinates = [p for poly in _polygons(campus_green) for p in poly.exterior.coords]
        along = [x*ux+y*uy for x, y in coordinates]
        across = [x*nx+y*ny for x, y in coordinates]
        station_min, station_max = min(along), max(along)
        cross_min, cross_max = min(across)-1, max(across)+1

        def line_parts(geometry):
            if geometry.is_empty:
                return []
            if geometry.geom_type == 'LineString':
                return [geometry]
            return [line for child in getattr(geometry, 'geoms', ()) for line in line_parts(child)]

        for station in range(math.ceil(station_min/8.5), math.floor(station_max/8.5)+1):
            at = station*8.5
            cross = LineString([(at*ux+cross_min*nx, at*uy+cross_min*ny),
                                (at*ux+cross_max*nx, at*uy+cross_max*ny)])
            segments = sorted(line_parts(feasible.intersection(cross)), key=lambda line: line.centroid.x*nx+line.centroid.y*ny)
            for band, line in enumerate(segments):
                if line.length < .01:
                    continue
                point = line.interpolate(.5, normalized=True)
                identity = 'CampusRow_%d_%d' % (station, band)
                if any(math.hypot(point.x-x, point.y-y) < 8.0 for x, y in campus_positions):
                    continue
                jitter = (_stable_unit(identity, 'offset')-.5)*.4
                candidate = Point(point.x+ux*jitter, point.y+uy*jitter)
                if not feasible.covers(candidate):
                    candidate = point
                desired = .24+.08*_stable_unit(identity, 'scale')
                for scale in sorted({desired, min(.28, desired), min_scale}, reverse=True):
                    crown = candidate.buffer(TREE_RADIAL_EXTENT_M*scale+.25, quad_segs=16)
                    if not campus_green.covers(crown):
                        continue
                    if place_tree(identity, (candidate.x, candidate.y), scale, 'campus_green_row'):
                        campus_positions.append((candidate.x, candidate.y))
                        campus_added += 1
                        break

    supplements = 0
    axes = []
    for row in objects:
        if row.get('layer') == 'TPX_ROADS_AXES':
            for spline in row['splines']:
                if len(spline['points']) > 1:
                    axes.append((row['name'], LineString([transform_xy(p[:2]) for p in spline['points']])))
    # Supplement only gaps that are visibly sparse at the source road margin.
    road_limit = math.ceil(supplement_limit*.75)
    for axis_id, curve in sorted(axes):
        if supplements >= road_limit:
            break
        for station in range(12, int(curve.length)-5, 30):
            if supplements >= road_limit:
                break
            p, a, b = curve.interpolate(station), curve.interpolate(station-1), curve.interpolate(station+1)
            dx, dy = b.x-a.x, b.y-a.y
            length = math.hypot(dx, dy)
            if length < .001 or len(_nearby(accepted, p.x, p.y, 25)) >= 3:
                continue
            for side in (-1, 1):
                if supplements >= road_limit:
                    break
                identity = 'Roadside_'+axis_id+'_%d_%d' % (station, side)
                scale = .48+.14*_stable_unit(identity)
                for distance in (9, 13, 17):
                    xy = (p.x-dy/length*side*distance, p.y+dx/length*side*distance)
                    if place_tree(identity, xy, scale, 'roadside_gap_supplement'):
                        supplements += 1
                        break
    greens = unary_union([source_footprint(row, transform_xy) for row in objects
                          if row.get('layer') == 'TPX_VEGETATION_GREEN_SPACES_HATCH'])
    green_added = 0
    if not greens.is_empty:
        green_inner = greens.buffer(-5)
        x0, y0, x1, y1 = greens.bounds
        for ix in range(math.floor(x0/24), math.ceil(x1/24)):
            for iy in range(math.floor(y0/24), math.ceil(y1/24)):
                if supplements >= supplement_limit:
                    break
                identity = 'GreenSpace_%d_%d' % (ix, iy)
                x = ix*24+12+(_stable_unit(identity, 'x')-.5)*10
                y = iy*24+12+(_stable_unit(identity, 'y')-.5)*10
                if not green_inner.covers(Point(x, y)) or len(_nearby(accepted, x, y, 24)) >= 2:
                    continue
                if place_tree(identity, (x, y), .50+.17*_stable_unit(identity), 'source_green_space_gap_supplement'):
                    supplements += 1
                    green_added += 1
    triangles = sum(sum(len(f)-2 for f in faces) for name, model in geo.data.items()
                    if name.startswith('SM_MPRR_Context_') for _, faces in model.values())
    audit['summary'] = dict(source_buildings=len(raw), buildings_added=len(audit['buildings']),
            buildings_rejected=dict(Counter(r['reason'] for r in audit['rejected_buildings'])),
            source_trees=sum(row.get('layer') == 'TPX_VEGETATION_TREES_INDIVIDUAL' for row in objects),
            source_trees_added=source_accepted, source_trees_rejected=dict(Counter(r['reason'] for r in audit['rejected_trees'])),
            supplemental_trees=supplements, supplemental_green_space_trees=green_added,
            campus_green_trees=campus_added, campus_tree_station_spacing_m=8.5,
            campus_tree_scale_range=[.24, .32],
            total_trees=len(instances), tree_hism_tiles=len({tuple(r['tile']) for r in instances}),
            building_mesh_tiles=len({r['mesh'] for r in audit['buildings']}), building_triangles=triangles,
            neighboring_warehouse_dock_doors=sum(r['dock_doors'] for r in audit['buildings']),
            context_roof_ventilation_units=sum(r['roof_ventilation_units'] for r in audit['buildings']),
            foundation_count=sum(r['foundation_height_m'] > 0 for r in audit['buildings']),
            max_foundation_height_m=max((r['foundation_height_m'] for r in audit['buildings']), default=0),
            old_resources_modified=0, previous_completed_frame_used=False)
    return dict(instances={TREE_NAME: instances}, reused_meshes={TREE_NAME: TREE_PATH},
                instance_material_roles={TREE_NAME: ['MPRR_Bark', 'MPRR_LeafMid', 'MPRR_LeafLight', 'MPRR_LeafShade']},
                materials=MATERIALS, audit=audit)
