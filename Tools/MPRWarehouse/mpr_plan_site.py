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

def extend_road_tails(roads,distance=160.,blockers=None):
    """Continue cropped outlets beyond the drawing, without changing its interior.

    The continuation is stylistic context, explicitly not measured road data.
    Two inward cross sections estimate outlet direction. Individual lanes are
    never inferred from black line thickness or merged through a land parcel.
    """
    bounds=pixel_box(-.5,-.5,1727.5,909.5);xmin,ymin,xmax,ymax=bounds.bounds
    rows=[];parts=[]
    for axis,edge,sign in [(0,xmin,-1),(0,xmax,1),(1,ymin,-1),(1,ymax,1)]:
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
            a,b=list(segment.coords)[0],list(segment.coords)[-1]
            quad=Polygon([a,b,(b[0]+direction[0]*distance,b[1]+direction[1]*distance),(a[0]+direction[0]*distance,a[1]+direction[1]*distance)])
            extension=quad.difference(bounds)
            if blockers is not None and extension.buffer(1.).intersects(blockers):continue
            parts.append(extension)
            rows.append(dict(origin_m=[outer.x,outer.y],direction=list(direction),length_m=distance))
    return unary_union([roads,*parts]),rows

def portal_clearance():
    return unary_union([LineString(xy(r['ends_px'])).buffer(2.2,cap_style=2)
                        for r in read('road_outline_v5.json')['portals_px']
                        if r['do_not_close_in_runtime']])

def pixel_polygon(points):return Polygon(xy(points))

def pixel_box(x1,y1,x2,y2):return pixel_polygon([(x1,y1),(x2,y1),(x2,y2),(x1,y2)])

def plan_details():
    return read('plan_site_details_v5.json')
