"""Independent Topoexport street/rail layout. CAD metres, never UE-flipped.

No previous exterior, terminal, or stitching geometry is consulted.  Source
axes determine topology; only junction-safe corner rounding and carriageway
widths are changed.  Native z is retained as evidence, not used to invent bridges.
"""
import json
import math
from pathlib import Path

import numpy as np
from shapely.geometry import GeometryCollection, LineString, Point, Polygon, mapping
from shapely.ops import unary_union, substring

SOURCE_SHA256 = '9caf3439299f1b4f38d8ee88b6a5877e9a92c213ae926c99b40c5302583718d1'


def _union(values):
    return unary_union(values) if values else GeometryCollection()


def _parts(geometry):
    return list(geometry.geoms) if hasattr(geometry, 'geoms') else [geometry]


def _transform(points, transform):
    points = np.asarray(points, dtype=float)
    xy = points[:, :2]*transform['scale'] @ np.asarray(transform['rotation_row_matrix'])
    xy += np.asarray(transform['offset_xy_m'])
    return np.column_stack([xy, points[:, 2]*transform['scale']])


def _clean(points):
    result = []
    for p in points:
        if not result or np.linalg.norm(np.asarray(p[:2])-np.asarray(result[-1][:2])) > .00001:
            result.append(list(map(float, p)))
    return result


def _mesh_polygon(obj, transform):
    vertices = _transform(obj['vertices'], transform)
    faces = []
    for face in obj['faces']:
        if len(face) < 3:
            continue
        p = Polygon(vertices[face, :2])
        if p.area > 1e-7:
            faces.append(p if p.is_valid else p.buffer(0))
    return _union(faces)


def _height(line, points, point):
    p = np.asarray(points)
    stations = np.r_[0., np.cumsum(np.linalg.norm(np.diff(p[:, :2], axis=0), axis=1))]
    return float(np.interp(line.project(point), stations, p[:, 2]))


def _smooth(points, locks, radius):
    """Round only small corners, preserve source endpoints and graph junctions.

    Quadratic segments remain in the convex hull of the original corner and
    deviate less than 0.36m for roads / 0.18m for rails.  Endpoints are exact.
    """
    if len(points) < 3:
        return points
    out = [points[0]]
    for a, b, c in zip(points, points[1:], points[2:]):
        a, b, c = map(np.asarray, (a, b, c))
        before, after = np.linalg.norm(b[:2]-a[:2]), np.linalg.norm(c[:2]-b[:2])
        if before < .02 or after < .02 or locks.distance(Point(b[:2])) < .3:
            out.append(b.tolist())
            continue
        va, vc = (a[:2]-b[:2])/before, (c[:2]-b[:2])/after
        angle = math.acos(float(np.clip(np.dot(va, vc), -1., 1.)))
        if angle < math.radians(55) or angle > math.radians(178):
            out.append(b.tolist())
            continue
        distance = min(radius, before*.2, after*.2)
        start = b+(a-b)*(distance/before)
        finish = b+(c-b)*(distance/after)
        out.extend([((1-t)**2*start+2*t*(1-t)*b+t*t*finish).tolist()
                    for t in np.linspace(0., 1., 7)])
    out.append(points[-1])
    return _clean(out)


def _source_axes(source, transform, layer):
    rows = []
    for obj in source['objects']:
        if obj.get('layer') != layer:
            continue
        for i, spline in enumerate(obj.get('splines', [])):
            points = _clean(_transform(spline['points'], transform))
            if len(points) < 2:
                continue
            rows.append(dict(id=obj['name']+(f'_{i}' if i else ''),
                             source_points_m=points,
                             geometry=LineString(np.asarray(points)[:, :2]),
                             closed=bool(spline.get('closed'))))
    return rows


def _locks(rows):
    # Every endpoint and intersection is fixed. No nearest-point reconnects.
    points = [Point(p) for r in rows for p in (r['source_points_m'][0][:2], r['source_points_m'][-1][:2])]
    for i, a in enumerate(rows):
        for b in rows[i+1:]:
            if not a['geometry'].intersects(b['geometry']):
                continue
            for p in _parts(a['geometry'].intersection(b['geometry'])):
                if p.geom_type == 'Point':
                    points.append(p)
    return _union(points)


def build_layout(source, transform, main_footprint):
    """Return Shapely surfaces and JSON-safe source-corresponding line records.

    Args: source=archived source_geometry.json; transform=registration transform
    (or complete registration dict); main_footprint=Shapely actual main building.
    All surfaces are XY metres. points_m/source_points_m retain source XYZ in
    scaled metres. The builder must use its common terrain function for mesh z.
    """
    if source.get('sha256') != SOURCE_SHA256:
        raise ValueError('Unexpected Topoexport source; inspect new source before rebuilding')
    transform = transform.get('transform', transform)
    frames, road_hatches, waters, buildings = [], [], [], []
    building_records = []
    for obj in source['objects']:
        layer = obj.get('layer')
        if layer == 'TPX_FRAME_PROJECT':
            for spline in obj.get('splines', []):
                points = _transform(spline['points'], transform)
                frames.append(Polygon(points[:, :2]).buffer(0))
        elif layer == 'TPX_ROADS_HATCH':
            road_hatches.append(_mesh_polygon(obj, transform))
        elif layer == 'TPX_WATERWAYS_HATCH':
            waters.append(_mesh_polygon(obj, transform))
        elif layer == 'TPX_BUILDINGS':
            shape = _mesh_polygon(obj, transform)
            if not shape.is_empty:
                buildings.append(shape)
                building_records.append(dict(id=obj['name'], geometry=shape))
    frame = _union(frames)
    if frame.is_empty or main_footprint.is_empty:
        raise ValueError('Frame and real main warehouse protection are required')
    source_roads = _union(road_hatches).intersection(frame)
    building_protection = _union([*buildings, main_footprint]).buffer(.35, quad_segs=8)
    roads = _source_axes(source, transform, 'TPX_ROADS_AXES')
    rails = _source_axes(source, transform, 'TPX_RAILWAYS_AXES')
    locks = _locks([*roads, *rails])
    road_surfaces, road_records, rail_records, deviations = [], [], [], []
    for kind, rows, records in [('road', roads, road_records), ('rail', rails, rail_records)]:
        for row in rows:
            original = row['geometry']
            points = _smooth(row['source_points_m'], locks, .7 if kind == 'road' else .35)
            line = LineString(np.asarray(points)[:, :2])
            deviation = original.hausdorff_distance(line)
            if deviation > (.36 if kind == 'road' else .18):
                points = row['source_points_m']
                line = original
                deviation = 0.
            record = dict(id=row['id'], points_m=points,
                          source_points_m=row['source_points_m'], length_m=line.length,
                          source_length_m=original.length,
                          max_smoothing_deviation_m=deviation, closed=row['closed'])
            if kind == 'road':
                # The source ribbons are typically 2.98m wide; their axes and
                # junctions, rather than their cartographic width, are retained.
                width = 3.5 if original.length < 35 else (9. if original.length > 550 else 6.5)
                record['width_m'] = width
                record['road_class'] = 'access' if width == 3.5 else ('primary' if width == 9 else 'residential')
                road_surfaces.append(line.buffer(width*.5, cap_style=2, join_style=1, quad_segs=12))
            else:
                record['gauge_m'] = 1.435
                record['bed_half_width_m'] = 3.
            records.append(record)
            deviations.append(deviation)
    paved_before_protection = _union([source_roads, *road_surfaces]).intersection(frame)
    paved = paved_before_protection.difference(building_protection)
    # Outlines come from the unified road surface, hence no transverse tile or
    # street-by-street cap lines at valid road junctions.
    curbs = paved.buffer(.24, quad_segs=12).difference(paved).intersection(frame).difference(building_protection)
    white = paved.buffer(-.42, quad_segs=12).boundary.buffer(.06, quad_segs=6).intersection(paved)
    dashes = []
    for r in road_records:
        if r['width_m'] < 6.:
            continue
        line = LineString(np.asarray(r['points_m'])[:, :2])
        for start in np.arange(2., line.length, 10.):
            dashes.append(substring(line, start, min(start+3., line.length)).buffer(.065, cap_style=2))
    dash_lines = _union(dashes).intersection(paved.buffer(-1.4))
    railway_lines = [LineString(np.asarray(r['points_m'])[:, :2]) for r in rail_records]
    # Parallel tracks share a continuous ballast bed instead of isolated strips.
    corridor = _union([line.buffer(3., cap_style=2, quad_segs=12) for line in railway_lines])
    corridor = corridor.buffer(1.1, quad_segs=12).buffer(-1.1, quad_segs=12).intersection(frame).difference(main_footprint.buffer(.5))
    crossings = []
    for road in roads:
        for rail in rails:
            for point in _parts(road['geometry'].intersection(rail['geometry'])):
                if point.is_empty or point.geom_type != 'Point':
                    continue
                rz = _height(road['geometry'], road['source_points_m'], point)
                tz = _height(rail['geometry'], rail['source_points_m'], point)
                same = next((c for c in crossings if Point(c['point_m']).distance(point) < .02), None)
                if same:
                    same['rail_ids'].append(rail['id'])
                    continue
                crossings.append(dict(id=f'Crossing_{len(crossings):02d}', point_m=list(point.coords)[0],
                    road_id=road['id'], rail_ids=[rail['id']], road_source_z_m=rz, rail_source_z_m=tz,
                    source_height_difference_m=rz-tz, treatment='detailed_level_crossing',
                    evidence='Source road and rail share terrain-sampled z; no bridge layer or deck-height evidence'))
    water = _union(waters).intersection(frame).difference(main_footprint.buffer(.5))
    # Centreline connectivity remains source-derived. Deliberate source dead
    # ends are reported, never connected to nearby streets without source data.
    endpoints = []
    for row in roads:
        other = _union([r['geometry'] for r in roads if r is not row])
        for end, p in [('start', row['source_points_m'][0]), ('end', row['source_points_m'][-1])]:
            point = Point(p[:2])
            if other.distance(point) > .08:
                endpoints.append(dict(road_id=row['id'], end=end, point_m=p[:2],
                     kind='source_frame_exit' if frame.boundary.distance(point) < .2 else 'source_dead_end'))
    audit = dict(source_sha256=SOURCE_SHA256, policy='Complete independent source topology; no old exterior joins or invented closures',
        source_road_axis_count=len(roads), source_rail_axis_count=len(rails), source_building_count=len(buildings),
        source_water_count=len(waters), road_widths_m=[3.5, 6.5, 9.],
        frame_area_m2=frame.area, roads_area_m2=paved.area, rail_corridor_area_m2=corridor.area,
        building_clearance_clip_m2=paved_before_protection.intersection(building_protection).area,
        main_building_road_overlap_m2=paved.intersection(main_footprint).area,
        main_building_rail_overlap_m2=corridor.intersection(main_footprint).area,
        max_axis_smoothing_deviation_m=max(deviations, default=0.),
        unique_rail_road_crossings=len(crossings), source_endpoints=endpoints,
        water_road_overlap_m2=water.intersection(paved).area,
        surfaces_valid=all(g.is_valid for g in [frame,paved,curbs,white,dash_lines,corridor,water]),
        limitations=['Road widths are presentation widths constrained by source building footprints.',
          'Source elevations are terrain samples, not evidence of bridge deck elevations.',
          'Use one shared terrain elevation for buildings, road and rail mesh generation.'])
    assert audit['surfaces_valid'] and audit['main_building_road_overlap_m2'] < 1e-7
    return dict(frame=frame, roads=paved, curbs=curbs, white_edges=white, dash_lines=dash_lines,
        road_centerlines=road_records, rail_centerlines=rail_records, rail_corridor=corridor,
        water=water, crossings=crossings, building_protection=building_protection,
        source_buildings=building_records, source_road_hatches=source_roads, audit=audit)


def dump_layout(layout, output):
    """Optional independent pure-geometry evidence writer; no engine dependency."""
    def serialize(value):
        if hasattr(value, 'geom_type'):
            return mapping(value)
        if isinstance(value, dict):
            return {k:serialize(v) for k,v in value.items()}
        if isinstance(value, list):
            return [serialize(v) for v in value]
        return value
    Path(output).write_text(json.dumps(serialize(layout), ensure_ascii=False, indent=2), encoding='utf8')
