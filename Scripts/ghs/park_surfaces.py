"""Polygon road unions and mesh emission, without Blender imports.

Requires Shapely >= 2.1 with GEOS >= 3.10 for constrained triangulation.
The park builder supplies api['mesh'](role, vertices, faces); an object with a
mesh method is also accepted. Coordinates remain in u/v space and horizontal
faces point upward. The caller handles its own world-space transformation.
"""
import math

import shapely
from shapely.geometry import LineString, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

_EPS = 1e-9


def _positive(value, name, allow_zero=False):
    value = float(value)
    if not math.isfinite(value) or value < 0 or (value == 0 and not allow_zero):
        raise ValueError('%s must be finite and %s' %
                         (name, 'nonnegative' if allow_zero else 'positive'))
    return value


def _polygons(geometry):
    if geometry.is_empty:
        return []
    if geometry.geom_type == 'Polygon':
        return [geometry]
    if hasattr(geometry, 'geoms'):
        return [p for part in geometry.geoms for p in _polygons(part)]
    return []


def _polygonal(geometry):
    if geometry is None or geometry.is_empty:
        return Polygon()
    if not geometry.is_valid:
        geometry = shapely.make_valid(geometry)
    polygons = _polygons(geometry)
    return unary_union(polygons) if polygons else Polygon()


def _mesh(api):
    emit = api.get('mesh') if isinstance(api, dict) else getattr(api, 'mesh', None)
    if not callable(emit):
        raise TypeError('api must supply a callable mesh(role, vertices, faces)')
    return emit


def _path(points):
    result = []
    for point in points:
        p = (float(point[0]), float(point[1]))
        if not all(math.isfinite(v) for v in p):
            raise ValueError('road coordinates must be finite')
        if not result or math.dist(result[-1], p) > _EPS:
            result.append(p)
    if len(result) < 2:
        raise ValueError('each road needs at least two distinct path points')
    return result


def _direction(a, b):
    length = math.dist(a, b)
    return (b[0] - a[0]) / length, (b[1] - a[1]) / length


def road_union(specs, junction_radius=4, return_metadata=False):
    """Union buffered road centrelines and round concave junction corners.

    Each spec contains path and width. Paths use flat caps and round joins.
    Optional extend_start / extend_end distances extend the end tangent;
    endpoint_extension sets both defaults, which are otherwise zero. Closed
    paths are inferred from their repeated endpoint or set with closed=True.

    Positive then negative buffering fills concave junction corners. Closing
    is performed per connected component so independent nearby roads do not
    acquire unwanted bridges. The original union is retained, including its
    exact end caps. This is a local operation, never a global convex hull.

    With return_metadata=True, return (geometry, metadata). Pass the metadata
    openings to emit_curb to suppress transverse curbs at exposed flat ends.
    Openings are Shapely LineStrings; opening_segments is their JSON-friendly
    coordinate equivalent. Closed loops have no openings.
    """
    junction_radius = _positive(junction_radius, 'junction_radius', True)
    road_polygons, possible_openings = [], []
    for index, spec in enumerate(specs):
        points = _path(spec['path'])
        width = _positive(spec['width'], 'road width')
        closed = bool(spec.get('closed', math.dist(points[0], points[-1]) <= _EPS))
        if closed:
            if math.dist(points[0], points[-1]) > _EPS:
                points.append(points[0])
        else:
            common = _positive(spec.get('endpoint_extension', 0), 'endpoint_extension', True)
            extension_start = _positive(spec.get('extend_start', common), 'extend_start', True)
            extension_end = _positive(spec.get('extend_end', common), 'extend_end', True)
            first_direction, last_direction = _direction(points[0], points[1]), _direction(points[-2], points[-1])
            points[0] = (points[0][0] - first_direction[0] * extension_start,
                         points[0][1] - first_direction[1] * extension_start)
            points[-1] = (points[-1][0] + last_direction[0] * extension_end,
                          points[-1][1] + last_direction[1] * extension_end)
            for point, direction in ((points[0], first_direction), (points[-1], last_direction)):
                normal = -direction[1], direction[0]
                half_width = width * .5
                cap = LineString([(point[0] - normal[0] * half_width,
                                   point[1] - normal[1] * half_width),
                                  (point[0] + normal[0] * half_width,
                                   point[1] + normal[1] * half_width)])
                possible_openings.append((cap, width))
        road_polygons.append(LineString(points).buffer(width * .5, cap_style='flat',
                                                       join_style='round', quad_segs=12))
    raw = _polygonal(unary_union(road_polygons))
    geometry = raw
    if junction_radius > _EPS and not raw.is_empty:
        rounded = [p.buffer(junction_radius, quad_segs=12, join_style='round')
                   .buffer(-junction_radius, quad_segs=12, join_style='round')
                   for p in _polygons(raw)]
        geometry = _polygonal(unary_union([raw] + rounded))
    openings = []
    for cap, width in possible_openings:
        # Boundary overlap excludes ends already joined inside another road.
        # A thin tolerance strip tolerates floating-point skewed end caps.
        overlap = geometry.boundary.intersection(cap.buffer(1e-7, cap_style='flat')).length
        if overlap > width * .25:
            openings.append(cap)
    metadata = dict(road_count=len(road_polygons), raw_area=raw.area, area=geometry.area,
                    junction_radius=junction_radius, openings=openings,
                    opening_segments=[list(line.coords) for line in openings],
                    components=len(_polygons(geometry)))
    return (geometry, metadata) if return_metadata else geometry


def emit_surface(api, geometry, role, z):
    """Emit nonoverlapping CCW triangles constrained to polygon boundaries.

    All polygon components and interior holes are honoured. Area is checked
    before emitting; a triangulator omission raises instead of silently
    producing an incomplete surface. Return triangle/vertex/area statistics.
    """
    emit = _mesh(api)
    z = float(z)
    if not math.isfinite(z):
        raise ValueError('surface elevation must be finite')
    geometry = _polygonal(geometry)
    vertices, faces, vertex_indices = [], [], {}
    area = 0.0
    for polygon in _polygons(geometry):
        triangles = shapely.constrained_delaunay_triangles(polygon)
        for triangle in _polygons(triangles):
            if triangle.area <= _EPS:
                continue
            if not polygon.covers(triangle):
                raise ValueError('constrained triangle escaped its source polygon')
            coordinates = list(triangle.exterior.coords)[:-1]
            if len(coordinates) != 3:
                raise ValueError('constrained triangulator produced a nontriangle')
            a, b, c = coordinates
            if (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) < 0:
                coordinates.reverse()
            face = []
            for x, y in coordinates:
                vertex = (x, y, z)
                if vertex not in vertex_indices:
                    vertex_indices[vertex] = len(vertices)
                    vertices.append(vertex)
                face.append(vertex_indices[vertex])
            faces.append(tuple(face))
            area += triangle.area
    tolerance = max(1e-7, geometry.area * 1e-9)
    if abs(area - geometry.area) > tolerance:
        raise ValueError('triangulated area mismatch: %.12g versus %.12g' % (area, geometry.area))
    if faces:
        emit(role, vertices, faces)
    return dict(triangles=len(faces), vertices=len(vertices), area=area,
                geometry_area=geometry.area, components=len(_polygons(geometry)))


def emit_curb(api, geometry, role='Curbs', width=.35, z=.12, openings=None, base_z=0):
    """Emit an exterior curb band with its top and vertical side faces.

    The band is outside the asphalt polygon, including courtyard/hole edges.
    Pass road_union metadata openings (LineStrings or endpoint pairs) to cut
    away end caps; curb walls then end beside the opening instead of crossing
    its carriageway. Side winding is outward for both outer and hole rings.
    ``base_z`` is the curb bottom, and ``z`` is its top elevation.
    """
    emit = _mesh(api)
    width = _positive(width, 'curb width')
    z, base_z = float(z), float(base_z)
    if not math.isfinite(z) or not math.isfinite(base_z) or z < base_z:
        raise ValueError('curb elevations must be finite with top >= bottom')
    geometry = _polygonal(geometry)
    band = geometry.buffer(width, quad_segs=8, join_style='round').difference(geometry)
    masks = []
    for opening in openings or []:
        line = opening if hasattr(opening, 'buffer') else LineString(opening)
        masks.append(line.buffer(width * 1.1 + 1e-6, cap_style='square', join_style='mitre'))
    if masks:
        band = band.difference(unary_union(masks))
    band = _polygonal(band)
    stats = emit_surface(api, band, role, z)
    vertices, faces = [], []
    if z > base_z:
        for polygon in _polygons(band):
            polygon = orient(polygon, sign=1.0)
            for ring in [polygon.exterior] + list(polygon.interiors):
                coordinates = list(ring.coords)
                for a, b in zip(coordinates, coordinates[1:]):
                    if math.dist(a, b) <= _EPS:
                        continue
                    first = len(vertices)
                    vertices.extend([(a[0], a[1], base_z), (b[0], b[1], base_z),
                                     (b[0], b[1], z), (a[0], a[1], z)])
                    faces.append((first, first + 1, first + 2, first + 3))
    if faces:
        emit(role, vertices, faces)
    stats.update(side_faces=len(faces), side_vertices=len(vertices), width=width,
                 base_z=base_z, top_z=z, openings=len(masks))
    return stats
