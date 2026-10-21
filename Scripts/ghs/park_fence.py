"""Continuous perimeter fence with explicit, road-aligned gate openings."""
import math

from shapely.geometry import LineString, Polygon
from shapely.ops import linemerge, unary_union

from park_curves import point_at_distance, sample_along


def _line_parts(geometry):
    """Join contiguous cuts, including a gate crossing the closed-line seam."""
    def collect(item):
        if item.geom_type == 'LineString':
            return [item] if item.length > 1e-8 else []
        return [line for child in getattr(item,'geoms',[]) for line in collect(child)]
    parts = collect(geometry)
    if len(parts) < 2:
        return parts
    return collect(linemerge(parts))


def _post_cap(point, tangent):
    x,y = point
    tx,ty = tangent
    return Polygon([(x+dx*tx-dy*ty,y+dx*ty+dy*tx) for dx,dy in
                    ((-.31,-.31),(.31,-.31),(.31,.31),(-.31,.31))])


def build_fence(api, boundary, gate_corridors, height=2.3, spacing=2.5):
    """Emit the exact sampled perimeter minus named entrance corridors.

    ``boundary`` is a closed sampled u/v polyline. Each gate has ``name`` and
    a valid Polygon ``geometry`` covering its entrance road. Gate columns are
    set back along the remaining boundary so their .62 m caps do not reduce
    the opening. ``width_m`` remains boundary gap length; ``clear_width_m``
    measures the actual shortest distance between the two cap footprints.
    All input/gate checks complete before geometry emission.
    """
    if not math.isfinite(height) or height <= .64:
        raise ValueError('Fence height must be finite and greater than .64 m')
    if not math.isfinite(spacing) or spacing <= 0:
        raise ValueError('Fence post spacing must be finite and positive')
    points=[]
    for point in boundary:
        p=(float(point[0]),float(point[1]))
        if not all(math.isfinite(value) for value in p):
            raise ValueError('Fence boundary coordinates must be finite')
        if not points or math.dist(points[-1],p)>1e-8:
            points.append(p)
    if len(points)<4 or points[0]!=points[-1]:
        raise ValueError('Fence boundary must be explicitly closed')
    line=LineString(points)
    if not line.is_ring or not line.is_simple:
        raise ValueError('Fence boundary must be a simple closed ring')

    portals=[]
    cuts=[]
    names=set()
    for gate in gate_corridors:
        name,geometry=gate['name'],gate['geometry']
        if name in names:
            raise ValueError('Fence gate names must be unique: '+str(name))
        names.add(name)
        if geometry.geom_type!='Polygon' or not geometry.is_valid or geometry.is_empty:
            raise ValueError(str(name)+': Gate corridor must be a valid Polygon')
        parts=_line_parts(line.intersection(geometry))
        if len(parts)!=1 or parts[0].length<=.05:
            raise ValueError(str(name)+': Gate must meet perimeter in one contiguous opening')
        cut=parts[0]
        coords=list(cut.coords)
        portals.append(dict(name=name,endpoints=[coords[0],coords[-1]],width_m=cut.length))
        cuts.append(cut)
    gap_length=sum(part.length for part in cuts)
    if cuts and abs(unary_union(cuts).length-gap_length)>1e-7:
        raise ValueError('Gate openings must not overlap along the fence')
    corridors=unary_union([gate['geometry'] for gate in gate_corridors])
    remaining=line.difference(corridors)
    parts=_line_parts(remaining)
    if not parts or abs(line.length-remaining.length-gap_length)>1e-7:
        raise ValueError('Fence perimeter cannot be accounted for by the named gates')

    # Prepare gate columns before emitting anything. Finding their points on
    # real remaining paths works on straight spans and on rounded corners.
    gate_posts=[]
    for portal in portals:
        caps=[]
        anchors=[]
        for endpoint in portal['endpoints']:
            away=None
            for part in parts:
                path=list(part.coords)
                if math.dist(endpoint,path[0])<1e-7:
                    away=path
                    break
                if math.dist(endpoint,path[-1])<1e-7:
                    away=list(reversed(path))
                    break
            if away is None:
                raise ValueError(portal['name']+': Gate endpoint has no adjacent fence')
            distance=.32
            limit=LineString(away).length*.49
            while distance<limit:
                p,t=point_at_distance(away,distance)
                cap=_post_cap(p,t)
                if cap.intersection(corridors).area<1e-10:
                    break
                distance*=1.25
            else:
                raise ValueError(portal['name']+': Insufficient fence space for gate columns')
            gate_posts.append((p,t))
            caps.append(cap)
            anchors.append(p)
        portal['column_centers']=anchors
        portal['opening_chord_m']=math.dist(*portal['endpoints'])
        portal['clear_width_m']=caps[0].distance(caps[1])

    mesh,box=api['mesh'],api['box']
    posts=rails=bars=0
    for part in parts:
        path=list(part.coords)
        closed=part.is_ring
        if closed:
            # Put the ribbon seam inside a straight sampled segment. Its two
            # end tangents then agree, even with an open-only ribbon callback.
            a,b=path[:2]
            seam=((a[0]+b[0])/2,(a[1]+b[1])/2)
            path=[seam]+path[1:]+[seam]
        api['ribbon']('Curbs',path,.30,.16)
        for a,b in zip(path,path[1:]):
            length=math.dist(a,b)
            angle=math.atan2(b[1]-a[1],b[0]-a[0])
            for h in (.48,height-.16):
                # Exact end-to-end lengths; no extension into a named gate.
                box('Fence',((a[0]+b[0])/2,(a[1]+b[1])/2,h),(length,.06,.065),angle)
                rails+=1
        samples=sample_along(path,spacing,closed=closed)
        for p,t,s in samples:
            if any(math.dist(p,anchor)<.55 for anchor,_ in gate_posts):
                continue
            box('Fence',(p[0],p[1],height/2),(.12,.12,height),math.atan2(t[1],t[0]))
            box('Curbs',(p[0],p[1],.10),(.28,.28,.20),math.atan2(t[1],t[0]))
            posts+=1
        # Crossed single-face strips use the Fence material's two-sided render
        # flag; reversed duplicate polygons fail Blender mesh validation.
        for p,t,s in sample_along(path,.24,start=.12,closed=closed):
            if not closed and s>part.length-.026:
                continue
            n=(-t[1],t[0]);w=.025
            for direction in (t,n):
                a=(p[0]-direction[0]*w,p[1]-direction[1]*w)
                b=(p[0]+direction[0]*w,p[1]+direction[1]*w)
                mesh('Fence',[(a[0],a[1],.23),(b[0],b[1],.23),
                              (b[0],b[1],height-.05),(a[0],a[1],height-.05)],
                     [(0,1,2,3)])
            bars+=1
    for p,t in gate_posts:
        angle=math.atan2(t[1],t[0])
        box('Buildings',(p[0],p[1],1.42),(.60,.60,2.84),angle)
        box('Blue',(p[0],p[1],2.28),(.62,.62,.23),angle)
    api['counts'].update(fence_posts=posts,fence_bars=bars,fence_rails=rails,
                         gate_columns=len(gate_posts),perimeter_gates=len(portals))
    return dict(perimeter_m=line.length,fence_m=remaining.length,
                gap_total_m=gap_length,continuous_except_named_gates=True,
                portals=portals,post_count=posts,bar_count=bars,rail_count=rails,
                gate_column_count=len(gate_posts))
