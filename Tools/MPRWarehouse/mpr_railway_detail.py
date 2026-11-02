"""Reference-led MPR railway geometry in CAD-local metres, without Blender state.

``build_railways({'mesh': mesh, 'zone': zone, 'footprint': FOOTPRINT}, lines, G)``
emits region-batched meshes and returns a Shapely vegetation-exclusion geometry,
JSON-safe corridor polygons, smoothed centre lines, and measured geometry counts.
The callbacks match build_mpr_environment.py.  No files or UE objects are touched.
Optional ``include_freight=True`` adds three short, source-aligned tank-car consists.

CADMapper supplies track positions, not surveyed rail sections or a train roster.
Rail sections, sleeper spacing and the optional rolling stock are visual estimates
from Snipaste_2026-10-30_16-13-26 / 16-03-26 / 16-03-46, not railway engineering data.
"""
from collections import defaultdict
import math

import shapely
from shapely.geometry import LineString, Point, Polygon, box as polygon_box
from shapely.ops import unary_union


PALETTE = {
    'Ballast': [.25, .235, .215],
    'Sleepers': [.095, .085, .070],
    'RailSteel': [.27, .285, .29],
    'FreightBody': [.065, .080, .090],
    'FreightDetail': [.12, .125, .12],
}
MATERIAL_PROPERTIES = {
    'Ballast': {'roughness': .95, 'metallic': 0},
    'Sleepers': {'roughness': .9, 'metallic': 0},
    'RailSteel': {'roughness': .55, 'metallic': .65},
    'FreightBody': {'roughness': .72, 'metallic': .35},
    'FreightDetail': {'roughness': .8, 'metallic': .35},
}
GAUGE_M = 1.435  # Between inner rail-head faces, not rail centre lines.
HEAD_WIDTH_M = .07
RAIL_OFFSET_M = (GAUGE_M + HEAD_WIDTH_M) / 2
TOP_HALF_WIDTH_M = 1.85
TOE_HALF_WIDTH_M = 2.25
TREE_CLEARANCE_M = 5.5
NEAR_DISTANCE_M = 300.
NEAR_SLEEPER_SPACING_M = .75
FAR_SLEEPER_SPACING_M = 2.25  # Explicit distant visual decimation, not real spacing.
MAX_SMOOTH_DEVIATION_M = .35


def _polygons(geometry):
    if geometry.is_empty:
        return []
    if geometry.geom_type == 'Polygon':
        return [geometry]
    return [p for g in geometry.geoms for p in _polygons(g)] if hasattr(geometry, 'geoms') else []


def _clean(vertices):
    points = []
    for v in vertices:
        p = (float(v[0]), float(v[1]))
        if not all(math.isfinite(x) for x in p):
            raise ValueError('Non-finite source railway coordinate')
        if not points or math.dist(p, points[-1]) > .001:
            points.append(p)
    return points


def _key(point):
    return tuple(round(v, 4) for v in point[:2])


def _smooth(points, protected):
    """Round corners with local quadratic arcs; keep shared source nodes exact."""
    out = [points[0]]
    for a, b, c in zip(points, points[1:], points[2:]):
        la, lc = math.dist(a, b), math.dist(b, c)
        va = ((b[0]-a[0])/la, (b[1]-a[1])/la)
        vc = ((c[0]-b[0])/lc, (c[1]-b[1])/lc)
        angle = math.acos(max(-1., min(1., va[0]*vc[0] + va[1]*vc[1])))
        if _key(b) in protected or angle < .002 or angle > math.radians(100):
            out.append(b)
            continue
        # Quadratic midpoint shift is trim*sin(turn/2)/2.  This bound avoids
        # Catmull-Rom overshoot and keeps neighbouring yard tracks separate.
        trim = min(8., .35*la, .35*lc,
                   2*MAX_SMOOTH_DEVIATION_M/max(math.sin(angle/2), 1e-6))
        p = (b[0]-va[0]*trim, b[1]-va[1]*trim)
        q = (b[0]+vc[0]*trim, b[1]+vc[1]*trim)
        out.append(p)
        count = max(3, int(math.ceil(2*trim/1.5)))
        for i in range(1, count+1):
            t = i/count
            out.append(((1-t)**2*p[0]+2*(1-t)*t*b[0]+t*t*q[0],
                        (1-t)**2*p[1]+2*(1-t)*t*b[1]+t*t*q[1]))
    out.append(points[-1])
    return _clean(out)


def _normal(points, i):
    a, b = points[max(i-1, 0)], points[min(i+1, len(points)-1)]
    length = math.dist(a, b)
    return (-(b[1]-a[1])/length, (b[0]-a[0])/length)


def _default_zones():
    return {'Near': polygon_box(-250, -170, 250, 240),
            'Far_E': polygon_box(250, -2000, 2000, 2000),
            'Far_W': polygon_box(-2000, -2000, -250, 2000),
            'Far_N': polygon_box(-250, 240, 250, 2000),
            'Far_S': polygon_box(-250, -2000, 250, -170)}


def build_railways(api, lines, ground_z=-1.2):
    """Build rail geometry; ``mesh`` and ``zone`` callbacks are required.

    Optional api keys: footprint (exact main CAD XY polygon), regions (matching
    zone-name -> Shapely clip polygon), include_freight (False by default).
    Return ``exclusion`` for trees and ``corridor_polygons`` for serialization.
    ``stats`` is JSON-safe and reports only geometry emitted by this invocation.
    """
    sink, zone = api['mesh'], api['zone']
    footprint = Polygon(api['footprint']) if api.get('footprint') else polygon_box(-182, -94, 183, 84)
    stats = {'source_lines': 0, 'source_length_m': 0., 'smoothed_length_m': 0.,
             'max_centerline_deviation_m': 0., 'sleepers_near': 0, 'sleepers_far': 0,
             'sleepers_omitted_at_junctions': 0, 'freight_cars': 0,
             'rail_gauge_m': GAUGE_M, 'rail_head_center_spacing_m': 2*RAIL_OFFSET_M,
             'near_sleeper_spacing_m': NEAR_SLEEPER_SPACING_M,
             'far_visual_sleeper_spacing_m': FAR_SLEEPER_SPACING_M,
             'near_distance_to_main_footprint_m': NEAR_DISTANCE_M,
             'tree_exclusion_half_width_m': TREE_CLEARANCE_M,
             'material_roles': [], 'triangles': 0, 'batches': {},
             'source_policy': 'CADMapper paths retained; endpoints/junction nodes exact; bounded local curve rounding.',
             'estimated_geometry': ['rail sections', 'ballast depth', 'sleeper dimensions and spacing', 'freight cars if enabled'],
             'references': ['Snipaste_2026-10-30_16-13-26.png', 'Snipaste_2026-10-30_16-03-26.png', 'Snipaste_2026-10-30_16-03-46.png']}
    batches = defaultdict(lambda: {'triangles': 0, 'vertices': 0, 'material_roles': set()})

    def emit(name, role, vertices, faces):
        if not faces:
            return
        sink(name, role, vertices, faces)
        tris = sum(len(f)-2 for f in faces)
        stats['triangles'] += tris
        batches[name]['triangles'] += tris
        batches[name]['vertices'] += len(vertices)
        batches[name]['material_roles'].add(role)

    def block(name, role, center, size, yaw=0., sleeper=False):
        x, y, z = center
        a, b, h = [s*.5 for s in size]
        c, s = math.cos(yaw), math.sin(yaw)
        xy = [(x+u*c-v*s, y+u*s+v*c) for u, v in [(-a,-b),(a,-b),(a,b),(-a,b)]]
        vv = [(u,v,z-h) for u,v in xy] + [(u,v,z+h) for u,v in xy]
        # No invisible underside; static non-collision context.
        faces = [(4,5,6,7),(1,2,6,5),(3,0,4,7)] if sleeper else [(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
        emit(name, role, vv, faces)

    source = []
    for item in lines:
        if isinstance(item, dict):
            if item.get('layer', 'railways') != 'railways':
                continue
            points, identity = _clean(item['vertices']), item.get('id', str(len(source)))
        else:
            points, identity = _clean(item), str(len(source))
        if len(points) >= 2:
            source.append((identity, points))
    if not source:
        return {'exclusion': Polygon(), 'corridor_polygons': [], 'centerlines': [], 'stats': stats}
    protected = {_key(p) for _, pts in source for p in (pts[0], pts[-1])}
    tracks = []
    for identity, pts in source:
        raw = LineString(pts)
        smooth = _smooth(pts, protected)
        line = LineString(smooth)
        deviation = raw.hausdorff_distance(line)
        assert deviation <= MAX_SMOOTH_DEVIATION_M+.002, (identity, deviation)
        stats['source_length_m'] += raw.length
        stats['smoothed_length_m'] += line.length
        stats['max_centerline_deviation_m'] = max(stats['max_centerline_deviation_m'], deviation)
        tracks.append({'id': identity, 'points': smooth, 'line': line})
    stats['source_lines'] = len(tracks)
    top = unary_union([t['line'].buffer(TOP_HALF_WIDTH_M, cap_style=2, quad_segs=3) for t in tracks])
    toe = unary_union([t['line'].buffer(TOE_HALF_WIDTH_M, cap_style=2, quad_segs=3) for t in tracks])
    # The aerial reference shows contiguous gravel in the tightly spaced yard,
    # not narrow grass stripes between every siding.  Close only <=2.2m gaps;
    # preserve larger real separations and the existing source track geometry.
    yard_floor = toe.buffer(1.1, quad_segs=3).buffer(-1.1, quad_segs=3).difference(toe)
    exclusion = unary_union([t['line'].buffer(TREE_CLEARANCE_M, quad_segs=3) for t in tracks])
    # A unioned ballast top and sloped shoulder has no coplanar overlaps at
    # crossovers.  Sparse vertical detail reads as a railway instead of paint.
    regions = api.get('regions', _default_zones())
    for region, clip in regions.items():
        for shape, shoulder in ((top.intersection(clip), False), (toe.difference(top).intersection(clip), True), (yard_floor.intersection(clip), None)):
            for p in _polygons(shapely.make_valid(shape)):
                for tri in shapely.constrained_delaunay_triangles(p).geoms:
                    pts = list(tri.exterior.coords)[:3]
                    vv = [(x, y, ground_z + (.04 if shoulder is None else .18-min(.14, Point(x,y).distance(top)*.35) if shoulder else .18)) for x,y in pts]
                    cross = (vv[1][0]-vv[0][0])*(vv[2][1]-vv[0][1])-(vv[1][1]-vv[0][1])*(vv[2][0]-vv[0][0])
                    emit('SM_MPR_Env_'+region+'_RailBed', 'Ballast', vv, [(0,1,2) if cross>0 else (0,2,1)])

    sleeper_positions = defaultdict(list)
    # Segments use interpolated normals from the same joined centre line so
    # both rail ribbons meet exactly; no independent white segment strips.
    for track in tracks:
        pts, line = track['points'], track['line']
        normals = [_normal(pts, i) for i in range(len(pts))]
        for i, (a,b) in enumerate(zip(pts, pts[1:])):
            region = zone((a[0]+b[0])/2, (a[1]+b[1])/2)
            near = footprint.distance(Point((a[0]+b[0])/2, (a[1]+b[1])/2)) <= NEAR_DISTANCE_M
            na, nb = normals[i], normals[i+1]
            for side in (-1, 1):
                center_a = (a[0]+na[0]*RAIL_OFFSET_M*side, a[1]+na[1]*RAIL_OFFSET_M*side)
                center_b = (b[0]+nb[0]*RAIL_OFFSET_M*side, b[1]+nb[1]*RAIL_OFFSET_M*side)
                # Extruded rail head and dark web: visible raised profile,
                # reduced to head top only outside the near detail zone.
                for width, bottom, height, role in ((HEAD_WIDTH_M,.39,.055,'RailSteel'),(.035,.315,.075,'Sleepers')):
                    if not near and role == 'Sleepers':
                        continue
                    xy=[(center_a[0]-na[0]*width/2,center_a[1]-na[1]*width/2),
                        (center_b[0]-nb[0]*width/2,center_b[1]-nb[1]*width/2),
                        (center_b[0]+nb[0]*width/2,center_b[1]+nb[1]*width/2),
                        (center_a[0]+na[0]*width/2,center_a[1]+na[1]*width/2)]
                    vv=[(x,y,ground_z+bottom) for x,y in xy]+[(x,y,ground_z+bottom+height) for x,y in xy]
                    ff=[(4,5,6,7),(0,1,5,4),(3,7,6,2)] if near else [(4,5,6,7)]
                    emit('SM_MPR_Env_'+region+'_Rails',role,vv,ff)
        distance = .375
        while distance < line.length-.375:
            p=line.interpolate(distance)
            near=footprint.distance(p)<=NEAR_DISTANCE_M
            spacing=NEAR_SLEEPER_SPACING_M if near else FAR_SLEEPER_SPACING_M
            a,b=line.interpolate(max(0,distance-.2)),line.interpolate(min(line.length,distance+.2))
            yaw=math.atan2(b.y-a.y,b.x-a.x)
            cell=(int(math.floor(p.x/.45)),int(math.floor(p.y/.45)))
            neighbours=[q for dx in (-1,0,1) for dy in (-1,0,1) for q in sleeper_positions[(cell[0]+dx,cell[1]+dy)]]
            if any(math.hypot(p.x-q[0],p.y-q[1])<.42 for q in neighbours):
                stats['sleepers_omitted_at_junctions']+=1
            else:
                region=zone(p.x,p.y)
                if near:
                    block('SM_MPR_Env_'+region+'_Sleepers','Sleepers',(p.x,p.y,ground_z+.245),(.23,2.6,.13),yaw,sleeper=True)
                    stats['sleepers_near']+=1
                else:
                    c,s=math.cos(yaw),math.sin(yaw)
                    vv=[(p.x+u*c-v*s,p.y+u*s+v*c,ground_z+.31) for u,v in [(-.115,-1.3),(.115,-1.3),(.115,1.3),(-.115,1.3)]]
                    emit('SM_MPR_Env_'+region+'_Sleepers','Sleepers',vv,[(0,1,2,3)])
                    stats['sleepers_far']+=1
                sleeper_positions[cell].append((p.x,p.y))
            distance += spacing

    if api.get('include_freight', False):
        _freight(tracks, emit, block, zone, ground_z, stats)
    stats['ballast_area_m2']=top.area
    stats['yard_gap_gravel_area_m2']=yard_floor.area
    stats['tree_exclusion_area_m2']=exclusion.area
    stats['material_roles']=sorted({r for batch in batches.values() for r in batch['material_roles']})
    stats['batches']={name:{**batch,'material_roles':sorted(batch['material_roles'])} for name,batch in sorted(batches.items())}
    assert stats['triangles'] < 220000, ('Railway geometry budget exceeded',stats['triangles'])
    return {'exclusion': exclusion,
            'corridor_polygons': [{'exterior':list(p.exterior.coords),'holes':[list(r.coords) for r in p.interiors]} for p in _polygons(exclusion)],
            'centerlines':[{'id':t['id'],'vertices':t['points']} for t in tracks], 'stats':stats}


def _freight(tracks, emit, block, zone, ground_z, stats):
    """Sparse tank cars on three actual yard paths; all occupancy is estimated."""
    # These are existing parallel source tracks visible outside Prologis Way.
    # Avoid turnouts and source endpoints; never add invented track geometry.
    selected={'1429':(20.,12),'14e3':(45.,12),'13e3':(20.,12)}
    placements=[]
    for track in tracks:
        if track['id'] not in selected:
            continue
        line=track['line']
        minimum_start,count=selected[track['id']]
        start=max(minimum_start,line.project(Point(220.,-50.))-115.)
        for j in range(count):
            distance=start+j*18.7
            if distance+9 > line.length-20:
                break
            a,b=line.interpolate(distance-7),line.interpolate(distance+7)
            p=line.interpolate(distance)
            yaw=math.atan2(b.y-a.y,b.x-a.x)
            c,s=math.cos(yaw),math.sin(yaw)
            name='SM_MPR_Env_'+zone(p.x,p.y)+'_Freight'
            def tx(x,y,z):
                return (p.x+x*c-y*s,p.y+x*s+y*c,ground_z+z)
            # 12-sided tank with tapered ends; saddle supports, bogies and a
            # hatch read at the overview distance without per-car actors.
            profile=[(-8.25,.3),(-7.8,1.05),(-7.0,1.34),(7.0,1.34),(7.8,1.05),(8.25,.3)]
            vv=[tx(x,math.cos(k*math.tau/12)*r,2.7+math.sin(k*math.tau/12)*r) for x,r in profile for k in range(12)]
            ff=[tuple(reversed(range(12))),tuple(range(60,72))]
            for row in range(len(profile)-1):
                for k in range(12):
                    nk=(k+1)%12
                    ff.append((row*12+k,row*12+nk,(row+1)*12+nk,(row+1)*12+k))
            emit(name,'FreightBody',vv,ff)
            for x in (-5.8,5.8):
                block(name,'FreightDetail',tx(x,0,.87),(2.5,2.1,.85),yaw)
                block(name,'FreightBody',tx(x,0,1.52),(.8,1.4,.8),yaw)
            block(name,'FreightDetail',tx(0,0,1.35),(17.,.36,.24),yaw)
            block(name,'FreightDetail',tx(0,0,4.1),(.9,.9,.22),yaw)
            for x in (-8.6,8.6):
                block(name,'FreightDetail',tx(x,0,1.08),(.7,.28,.2),yaw)
            placements.append({'source_track_id':track['id'],'distance_along_m':distance,
                               'position_m':[p.x,p.y,ground_z],'yaw_deg':math.degrees(yaw)})
    stats['freight_cars']=len(placements)
    stats['freight_placements_estimated']=placements
    stats['freight_policy']=str(len(placements))+' estimated dark tank cars in three source-aligned consists nearest Prologis Way; visual reference reconstruction, not surveyed occupancy.'
