"""Plan geometry shared by the Blender site builder and geometric validation.

Raster boundaries define the road surface. Centerlines below only place paint;
they never invent street widths or replace the approved parcel boundaries.
"""
import json,math
from pathlib import Path
import numpy as np
from shapely.geometry import Polygon, LineString, Point, box
from shapely.ops import unary_union
from mpr_plan_layout import plan_to_world, load_registration

ROOT=Path(__file__).resolve().parents[2]
SITE=ROOT/'SourceAssets/MPR/reference_v4/site'

def read(name):return json.loads((SITE/name).read_text(encoding='utf8'))

def xy(points):return [p[:2] for p in plan_to_world(points)]

def polygon(row,holes=True):
    p=Polygon(xy(row['exterior']),[xy(r) for r in row.get('holes',[])] if holes else [])
    assert p.is_valid and not p.is_empty, row.get('name',row.get('id'))
    return p

def named_region(name,holes=True):
    row=next(r for r in read('road_outline_v5.json')['parcels_px'] if r['name']==name)
    return polygon(row,holes)

def road_geometry():
    # Smooth once in the source's pixel frame so asphalt, kerbs and road paint
    # all share one boundary. Raw traced JSON remains the reproducible evidence.
    roads=unary_union([polygon(smooth_road_polygon_px(r)) for r in read('road_outline_v5.json')['polygons_px']])
    return roads.difference(landscape_islands())


ROAD_SMOOTH_TOLERANCE_PX=.6

def road_smoothing_protected_px():
    """Keep image exits and explicitly annotated entrance gates stationary."""
    portals=[LineString(r['ends_px']).buffer(3.,cap_style=2)
             for r in read('road_outline_v5.json')['portals_px']]
    # The continuation direction samples 5m inside the image: 12 pixels cover
    # both station cross sections at the smaller registered metres/pixel axis.
    return unary_union(portals+[box(-12,-12,1740,12),box(-12,898,1740,922),
                               box(-12,0,12,910),box(1716,0,1740,910)])


def _smooth_road_ring_px(ring,tolerance,protected):
    """C1 quadratic corner fillets, bounded against the existing traced line.

    A trimmed corner (A, P, B) follows quadratic Bezier A/P/B. The midpoint
    distance from P is trim*sin(turn/2)/2, so bounding trim bounds the corner
    displacement. The polygon-level Hausdorff check below verifies both sides.
    Neighbor trims use at most 45% of a segment each, leaving a straight join.
    """
    points=np.asarray(ring,dtype=float)
    if np.linalg.norm(points[0]-points[-1])<1e-9:points=points[:-1]
    result=[]
    for i,p in enumerate(points):
        incoming=p-points[i-1];outgoing=points[(i+1)%len(points)]-p
        before=float(np.linalg.norm(incoming));after=float(np.linalg.norm(outgoing))
        if min(before,after)<1e-8:
            result.append(p.tolist());continue
        u=incoming/before;v=outgoing/after
        turn=math.acos(float(np.clip(u@v,-1.,1.)))
        if turn<math.radians(.5):
            result.append(p.tolist());continue
        trim=min(.45*before,.45*after,2*tolerance/max(math.sin(turn*.5),1e-6))
        a=p-u*trim;b=p+v*trim
        if LineString([a,p,b]).intersects(protected):
            result.append(p.tolist());continue
        for t in np.linspace(0.,1.,9):
            q=(1-t)**2*a+2*(1-t)*t*p+t*t*b
            if not result or math.dist(result[-1],q)>1e-9:result.append(q.tolist())
    return result


def smooth_road_polygon_px(row):
    """Smooth a traced region without losing holes, portals or connectivity."""
    source=Polygon(row['exterior'],row.get('holes',[]))
    protected=road_smoothing_protected_px();tolerance=ROAD_SMOOTH_TOLERANCE_PX
    for _ in range(5):
        exterior=_smooth_road_ring_px(row['exterior'],tolerance,protected)
        holes=[_smooth_road_ring_px(r,tolerance,protected)for r in row.get('holes',[])]
        candidate=Polygon(exterior,holes)
        if (candidate.is_valid and len(candidate.interiors)==len(source.interiors)
                and candidate.boundary.hausdorff_distance(source.boundary)<=ROAD_SMOOTH_TOLERANCE_PX+1e-7
                and candidate.symmetric_difference(source).intersection(protected).area<1e-7):
            return dict(row,exterior=exterior,holes=holes)
        tolerance*=.5
    # A failed constrained fillet is an input/algorithm issue, never a reason to
    # silently repair topology with buffer(0), drop an island or close a gate.
    raise ValueError('Cannot smooth road region without changing protected topology: '+row.get('name',row.get('id','unknown')))

def landscape_islands():
    return unary_union([polygon(r) for r in read('plan_landscape_islands_v5.json')['polygons_px']])

def _road_outlets(roads):
    """Measure the unchanged plan exits, including cropped narrow side streets."""
    bounds=pixel_box(-.5,-.5,1727.5,909.5);xmin,ymin,xmax,ymax=bounds.bounds
    rows=[]
    for edge_name,axis,edge,sign in [('left',0,xmin,-1),('right',0,xmax,1),('bottom',1,ymin,-1),('top',1,ymax,1)]:
        def section(inset):
            a=edge-sign*inset
            line=LineString([(a,ymin-1),(a,ymax+1)]) if axis==0 else LineString([(xmin-1,a),(xmax+1,a)])
            cut=roads.intersection(line)
            return [cut] if cut.geom_type=='LineString' else [g for g in getattr(cut,'geoms',[]) if g.geom_type=='LineString']
        back=section(5.)
        for segment in section(.75):
            if segment.length<2.5 or segment.length>40 or not back:continue
            inner=min(back,key=lambda s:s.centroid.distance(segment.centroid))
            outer=segment.centroid;dx=outer.x-inner.centroid.x;dy=outer.y-inner.centroid.y
            length=(dx*dx+dy*dy)**.5
            if length<1e-5:continue
            direction=(dx/length,dy/length)
            if direction[axis]*sign<.25:continue
            rows.append(dict(origin_m=[outer.x,outer.y],direction=list(direction),edge=edge_name,
                             section_m=[list(p) for p in segment.coords],width_m=segment.length*abs(direction[axis])))
    return rows


def terminal_shape(row):
    """Constant source-width ribbon with an exact oblique source mouth."""
    origin=np.asarray(row['origin_m']);direction=np.asarray(row['direction']);normal=np.array([-direction[1],direction[0]])
    length=row['length_m'];width=row['width_m'];end=origin+direction*length
    a=origin+direction*min(4.,length)
    ribbon=Polygon([origin-normal*width*.5,end-normal*width*.5,end+normal*width*.5,origin+normal*width*.5])
    mouth=Polygon([*row['section_m'],a-normal*width*.5,a+normal*width*.5]).convex_hull
    return unary_union([ribbon,mouth])


def terminal_fade(row,point):
    distance=float(np.dot(np.asarray(point[:2])-row['origin_m'],row['direction']))
    start=row['fade_start_m'];length=row['length_m']
    t=max(0.,min(1.,(distance-start)/max(length-start,1e-9)))
    return t*t*(3.-2.*t)


def extend_road_tails(roads,distance=None,blockers=None):
    """Preserve source tangents; open ends fade, never close to another street."""
    import shapely
    config=read('outside_road_connections_v5.json');bounds=pixel_box(*config['canvas_px'])
    assert config['status']=='source_tangent_terminal_fade_no_authored_connections'
    assert 'groups' not in config and 'collectors' not in config and 'branches' not in config
    length=float(config['extension_m'] if distance is None else distance)
    assert 0<length<=config['extension_m']
    rows=[]
    for i,outlet in enumerate(_road_outlets(roads)):
        rows.append(dict(outlet,id='SourceTerminal_%02d'%i,kind='source_tangent_fade',length_m=length,shortened_for=[]))
    tracks=[]
    for track in read('plan_railway_v5.json')['tracks']:
        points=xy(track['path_px']);a=np.asarray(points[0]);b=np.asarray(points[-1])
        da=(a-points[1]);da/=np.linalg.norm(da);db=(b-points[-2]);db/=np.linalg.norm(db)
        tracks.append(LineString([a+da*160.,*points,b+db*160.]).buffer(2.,quad_segs=8))
    hard=unary_union([*tracks,*([] if blockers is None else [blockers.buffer(.35)])])
    def first_station(row,geometry):
        coords=shapely.get_coordinates(geometry)
        return min((float(np.dot(p-row['origin_m'],row['direction'])) for p in coords),default=length)
    clearance=float(config['terminal_clearance_m'])
    for row in rows:
        hit=terminal_shape(row).difference(bounds).intersection(hard)
        if hit.area>1e-8:
            row['length_m']=max(1.5,first_station(row,hit)-clearance)
            row['shortened_for'].append('preserved_building_or_rail')
    # Clip before mutual contact; never bend an inferred road into a junction.
    for _ in range(4):
        changed=False
        for i,row in enumerate(rows):
            for other in rows[i+1:]:
                hit=terminal_shape(row).intersection(terminal_shape(other)).difference(bounds.buffer(.01))
                if hit.area<=1e-8:continue
                for item in (row,other):
                    station=first_station(item,hit)-clearance
                    assert station>1.,('Source road mouths overlap beyond plan',row['id'],other['id'])
                    if station<item['length_m']:
                        item['length_m']=station;item['shortened_for'].append('other_source_terminal');changed=True
        if not changed:break
    parts=[]
    for row in rows:
        row['end_m']=(np.asarray(row['origin_m'])+np.asarray(row['direction'])*row['length_m']).tolist()
        row['path_m']=[row['origin_m'],row['end_m']]
        row['fade_start_m']=max(0.,row['length_m']-config['fade_length_m'])
        row['fade_end_m']=row['length_m'];row['fade_rgb_endpoints']=[0.,1.]
        row['shortened_for']=sorted(set(row['shortened_for']))
        part=terminal_shape(row).difference(bounds)
        assert part.intersection(hard).area<1e-7,('Terminal clearance failed',row['id'])
        parts.append(part)
    addition=unary_union(parts);result=unary_union([roads,addition])
    assert result.is_valid and result.symmetric_difference(roads).intersection(bounds).area<1e-7
    return result,rows


def portal_clearance():
    return unary_union([LineString(xy(r['ends_px'])).buffer(2.2,cap_style=2)
                        for r in read('road_outline_v5.json')['portals_px']
                        if r['do_not_close_in_runtime']])

def pixel_polygon(points):return Polygon(xy(points))

def pixel_box(x1,y1,x2,y2):return pixel_polygon([(x1,y1),(x2,y1),(x2,y2),(x1,y2)])

def plan_details():
    return read('plan_site_details_v5.json')
