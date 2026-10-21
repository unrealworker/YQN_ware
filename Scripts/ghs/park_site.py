"""CAD-aligned site, continuous roads and fenced campus for the GHS scene."""
from pathlib import Path
import json
import math

from shapely.geometry import Polygon, LineString, Point, box as rect
from shapely.ops import unary_union, linemerge, nearest_points
from park_curves import rounded_path, offset_path, sample_along, dash_segments
from park_surfaces import road_union, emit_surface, emit_curb
from park_fence import build_fence

ROOT=Path(__file__).resolve().parents[2]
PARK=ROOT/'SourceAssets/GHS/Park'


def parts(geometry,kind):
    if geometry.is_empty:return []
    if geometry.geom_type==kind:return [geometry]
    return [p for g in getattr(geometry,'geoms',[]) for p in parts(g,kind)]


def build_site(api):
    cad=json.loads((PARK/'cad_layout.json').read_text(encoding='utf-8'))
    satellite=json.loads((PARK/'satellite_trace.json').read_text(encoding='utf-8'))
    traces={r['id']:r for r in satellite['traces']}
    counts=api['counts'];preview=api['preview']
    box,poly,ribbon=api['box'],api['poly'],api['ribbon']
    warehouse=Polygon(api['warehouse'])
    scope=rect(-175,-195,725,570).buffer(22,quad_segs=16)
    # One neutral landscape field replaces scattered rectangles and exposed
    # grid gaps. Its model edge sits outside the principal campus view.
    emit_surface(api,scope,'Ground',-.16)
    preview.append(('Ground',list(scope.exterior.coords)))

    raw=traces['campus_boundary']['uv_m']
    boundary=rounded_path(raw,9,closed=True,max_step=.85)
    campus=Polygon(boundary)
    assert campus.is_valid and campus.contains(warehouse)

    campus_ids={'154b','1bba','1d99','1d9e','2115','211a','2056','205d','2068'}
    glen_ids={'13a3','1460','1633','149c','1673','17c8','1f42','20d4'}
    sycamore_ids={'15ee','140d','16e0','1f7f','17a8','13d0','166f'}
    specs=[];highways=[];curve_report=[]
    for r in cad['roads']:
        raw_line=LineString(r['points_uv_m'])
        if raw_line.length<.2:continue
        # Collapse millimetric redundant source vertices before filleting.
        controls=list(raw_line.simplify(.18,preserve_topology=True).coords)
        closed=bool(r['closed']) or math.dist(controls[0],controls[-1])<.05
        width=14. if r['layer']=='highways' else (19. if r['handle'] in glen_ids else 7.4)
        if r['handle'] in sycamore_ids:width=6.6
        if r['handle'] in campus_ids:width=7.6 if r['handle'] in {'2068','154b','1bba'} else 5.2
        radius=55 if r['layer']=='highways' else (22 if r['layer']=='major_roads' else 12)
        if closed:radius=4.5
        curve,meta=rounded_path(controls,radius,closed,max_step=1.,return_metadata=True)
        # Reject unrealistic width only on a hard U-turn; mild source bends
        # may legitimately have clamped radii without inverting an edge.
        curve_report.append(dict(id=r['id'],min_radius=meta['min_radius'],samples=len(curve),closed=closed))
        for n,line in enumerate(parts(LineString(curve).intersection(scope),'LineString')):
            if line.length<2:continue
            spec=dict(id=r['id']+'_'+str(n),cad_id=r['id'],layer=r['layer'],path=list(line.coords),
                      width=width,context=r['handle'] not in campus_ids)
            (highways if r['layer']=='highways' else specs).append(spec)

    # CAD records separate routes across the open concrete truck court. Join
    # their ends through that court; rear fire access remains continuous.
    for name,path,width in [
        ('court_connector',[(140,188),(140,146),(147.05,146.1)],7.6),
        ('west_fire_access',[(-4,187),(-4,140),(-5,-5),(486,-5),(506,0)],5.0),
    ]:
        specs.append(dict(id=name,layer='campus_service',context=False,width=width,
                          path=rounded_path(path,10,max_step=.8)))

    # Satellite parcel strokes are approximate. Respect the CAD turning road
    # and fire lane with a continuous 3.5m shoulder instead of letting the
    # fence cut across them. Gate approach portions remain outside the site.
    circulation_envelope=unary_union([
        LineString(s['path']).buffer(s['width']/2+3.5,cap_style=2)
        for s in specs if not s['context']]).intersection(rect(-15,-6,600,300))
    campus=unary_union([campus,circulation_envelope]).buffer(3.5,quad_segs=12).buffer(-3.5,quad_segs=12)
    assert campus.geom_type=='Polygon' and campus.is_valid
    boundary=list(campus.exterior.coords)
    emit_surface(api,campus,'Hardstand',-.04)
    preview.append(('Hardstand',boundary))

    # Keep the 7.7m open strip between the SW parking loop and fire access.
    # A 4m closing radius falsely joined those parallel lanes at mid-block.
    all_ground,union_meta=road_union(specs,3.8,True)
    # The NE parking loop is only ~6m from the back fire lane. Global 3.8m
    # closing filled the intervening parking strip, despite the CAD routes
    # remaining separate. Use the smaller concave fillet only in this pocket.
    # Include the complete northeast bend: its closing-radius difference
    # reaches v=6.965. Cutting at v=5.5 leaves a transverse step in the road
    # edge; v=7.5 puts the mask wholly beyond that difference, with a margin.
    ne_corner=rect(473,-3,501,7.5)
    ne_ground=road_union(specs,2.8)
    seam=all_ground.symmetric_difference(ne_ground).intersection(ne_corner.boundary)
    assert seam.length<.001, ('NE local road correction has an open seam',seam.length)
    all_ground=all_ground.difference(ne_corner).union(ne_ground.intersection(ne_corner))
    assert all_ground.is_valid
    public=all_ground.difference(campus)
    private=all_ground.intersection(campus)
    emit_surface(api,public,'ContextRoads',.015)
    emit_surface(api,private,'CampusRoads',.018)
    for role,geometry in [('ContextRoads',public),('CampusRoads',private)]:
        for p in parts(geometry,'Polygon'):preview.append((role,list(p.exterior.coords)))
    # Public sidewalks are computed from the merged surface. No independent
    # road strip border can cross a junction or the two campus entrances.
    sidewalks=all_ground.buffer(1.75,quad_segs=12).difference(all_ground).difference(campus)
    emit_surface(api,sidewalks,'Curbs',.10)
    curb_band=all_ground.buffer(.27,quad_segs=8).difference(all_ground).difference(campus)
    emit_surface(api,curb_band,'Curbs',.19)
    for s in specs:
        api['context_roads'].append((s['path'],s['width']))
        if s['layer']=='major_roads' and s['context']:
            for dash in dash_segments(s['path'],3.8,6.5,phase=1):ribbon('Markings',dash,.12,.036)
            if s['width']>15:
                for offset in (-4.6,4.6):
                    for dash in dash_segments(offset_path(s['path'],offset),3.8,6.5,phase=1):
                        ribbon('Markings',dash,.10,.037)

    # I-15 is a grade-separated pair of carriageways. Recombine source pieces
    # before drawing, so bridge gradients and lane dashes stay continuous.
    freeway_lines=linemerge(unary_union([LineString(s['path']) for s in highways]))
    freeway_polys=[]
    crossings=[]
    sycamore=unary_union([LineString(s['path']) for s in specs if s.get('cad_id','')[4:] in sycamore_ids])
    for line in parts(freeway_lines,'LineString'):
        crossing=line.intersection(sycamore)
        points=parts(crossing,'Point')
        if points:
            c=unary_union(points).centroid
            crossing_s=line.project(c)
            crossings.append([c.x,c.y])
        else:crossing_s=None
        path=list(line.coords);distance=0.;heights=[]
        for i,p in enumerate(path):
            if i:distance+=math.dist(path[i-1],p)
            delta=abs(distance-crossing_s) if crossing_s is not None else 1000
            ramp=max(0.,min(1.,(100.-delta)/64.))
            ramp=ramp*ramp*(3-2*ramp)
            heights.append(.03+6.1*ramp)
        ribbon('ContextRoads',path,14.,heights,True)
        api['context_roads'].append((path,14.))
        pavement=line.buffer(7.,cap_style=2)
        freeway_polys.append(pavement)
        # Project dash elevation onto the same continuous arclength profile.
        for offset in (-2.3,2.3):
            lane=offset_path(path,offset)
            for dash in dash_segments(lane,5.5,8.):
                zz=[]
                for p in dash:
                    d=line.project(Point(p));k=abs(d-crossing_s) if crossing_s is not None else 1000
                    q=max(0,min(1,(100-k)/64));zz.append(.055+6.1*q*q*(3-2*q))
                ribbon('Markings',dash,.13,zz)
        for offset in (-6.75,6.75):
            ribbon('Markings',offset_path(path,offset),.13,[z+.025 for z in heights])
            ribbon('Curbs',offset_path(path,offset),.23,[z+.26 for z in heights])
        # Thin side/deck shells give the flyover a real underside; grounded
        # approaches stay shallow and supports remain outside Sycamore lanes.
        for i,(a,b) in enumerate(zip(path,path[1:])):
            if min(heights[i],heights[i+1])<5.9:continue
            aa,bb=offset_path([a,b],7.),offset_path([a,b],-7.)
            verts=[(*aa[0],heights[i]-.4),(*bb[0],heights[i]-.4),
                   (*bb[1],heights[i+1]-.4),(*aa[1],heights[i+1]-.4)]
            api['mesh']('Curbs',verts,[(3,2,1,0)])
        if crossing_s is not None:
            from park_curves import point_at_distance
            for ds in (-23,23):
                p,t=point_at_distance(path,crossing_s+ds)
                for off in (-5.6,5.6):
                    q=(p[0]-t[1]*off,p[1]+t[0]*off)
                    if all_ground.distance(Point(q))>1.3:
                        box('Curbs',(q[0],q[1],2.8),(1.25,1.25,5.6))
    freeway=unary_union(freeway_polys)
    highway_verge=freeway.buffer(5).difference(freeway).difference(all_ground).difference(campus)
    emit_surface(api,highway_verge,'Landscape',-.055)

    # Thin, slightly raised perimeter planting strip and the security fence
    # share one boundary; only entrance road masks interrupt it.
    sw=[s for s in specs if s.get('cad_id')=='CAD_1bba'][0]
    ne=[s for s in specs if s.get('cad_id')=='CAD_2068'][0]
    gate_corridors=[dict(name='SW Main gate',geometry=LineString(sw['path']).buffer(sw['width']/2+1.0)),
                    dict(name='NE Service gate',geometry=LineString(ne['path'][-18:]).buffer(ne['width']/2+1.0))]
    # Limit the NE opening to the public-road connection, not its long turn.
    gate_corridors[1]['geometry']=LineString(ne['path']).buffer(ne['width']/2+1.4).intersection(rect(490,-45,528,12))
    fence_line=LineString(campus.buffer(-.85,join_style=1).exterior.coords)
    fence_result=build_fence(api,list(fence_line.coords),gate_corridors,height=2.3)
    planting=campus.difference(campus.buffer(-3.2)).difference(all_ground.buffer(1.))
    emit_surface(api,planting,'Landscape',-.005)
    for p in parts(planting,'Polygon'):preview.append(('Landscape',list(p.exterior.coords)))

    from park_parking import build_parking
    parking=build_parking(api,campus,all_ground,warehouse)
    # Rear trailer rows stay clear of the CAD circulation and existing trucks.
    bay_checks=[]
    for u,v,num,angle in [(68,213,17,-.245),(148,164,20,-.0121),(245,167,15,-.245)]:
        points=[api['rotate_point'](x,y,(u,v),angle) for x,y in [(0,0),(num*4,0),(num*4,16),(0,16)]]
        footprint=Polygon(points)
        assert all_ground.distance(footprint)>.5,('Trailer bays cross circulation',u,v)
        assert campus.contains(footprint),('Trailer bays outside fence',u,v)
        bay_checks.append(dict(origin=[u,v],count=num,road_clearance_m=all_ground.distance(footprint)))
        api['staging'](u,v,num,angle,.34)

    # Compact gatehouses are on islands beside the entrance, not in the lane.
    booths=[]
    for u,v,angle in [(38,180,0),(505,10,math.pi/2)]:
        footprint=rect(u-3.8,v-2.4,u+3.8,v+2.4)
        if angle:footprint=rect(u-2.4,v-3.8,u+2.4,v+3.8)
        assert all_ground.distance(footprint)>.25,('gatehouse on road',u,v)
        api['gatehouse'](u,v,angle)
        booths.append(dict(center=[u,v],clearance_m=all_ground.distance(footprint)))

    # Build housing at actual CAD footprints and supplement only the missing
    # Gray Pine homes visible in the current satellite reference.
    from park_residential import build_residential
    residential=build_residential(api,cad,specs+highways,all_ground.union(freeway),scope,campus)
    occupied=unary_union([Polygon(h['footprint_uv_m']) for h in residential['houses']])
    driveway_mask=unary_union([Polygon(h['driveway_polygon_uv_m'])
                             for h in residential['houses'] if h['driveway_polygon_uv_m']])
    from park_forests import build_forests
    forests=build_forests(api,cad,all_ground.union(freeway),occupied.union(driveway_mask),scope,campus)
    vehicle_clearances=[]
    for vehicle in api['parked_vehicles']:
        w,d=vehicle['size'];angle=vehicle['angle'];center=vehicle['center']
        footprint=Polygon([api['rotate_point'](x,y,center,angle) for x,y in [(-w/2,-d/2),(w/2,-d/2),(w/2,d/2),(-w/2,d/2)]])
        assert all_ground.intersection(footprint).area<.001,('Parked vehicle on road',vehicle)
        vehicle_clearances.append(all_ground.distance(footprint))
    remaining_fence=fence_line.difference(unary_union([g['geometry'] for g in gate_corridors]))
    assert remaining_fence.intersection(all_ground).length<.01,'Fence crosses road outside named gates'
    # Street trees remain individually spaced; forests occupy only the two
    # user-requested outer areas with their own road/water/building masks.
    tree_points=[]
    for p,t,d in sample_along(boundary,15.,closed=True):
        q=Point(p)
        inner=nearest_points(q,campus.buffer(-4.5).boundary)[1]
        if all_ground.distance(inner)>2.8 and warehouse.distance(inner)>3.0:
            api['tree'](inner.x,inner.y,4.6);tree_points.append([inner.x,inner.y])
    for s in specs:
        if not s['context'] or s['layer']!='major_roads':continue
        for side in (-1,1):
            edge=offset_path(s['path'],side*(s['width']/2+4.6))
            for p,t,d in sample_along(edge,24.,start=9):
                q=Point(p)
                if scope.contains(q) and campus.distance(q)>3 and occupied.distance(q)>3 and all_ground.distance(q)>3 and freeway.distance(q)>3:
                    api['tree'](*p,4.3);tree_points.append(p)
    for u,v in [(42,176),(65,192),(130,184),(228,179),(315,151),(408,145),(536,94),(541,39)]:
        if all_ground.distance(Point(u,v))>.4:
            api['cylinder']('Detail',u,v,0,.09,8,8)
            box('Curbs',(u,v,8.03),(1.25,.42,.14));counts['light_poles']+=1

    # Every retained original dock truck must remain inside the fenced site.
    before=ROOT/'Saved/ParkRefinement/Before/scene_inspection.json'
    truck_checks=[]
    if before.exists():
        for a in json.loads(before.read_text(encoding='utf-8'))['actors']:
            if not a['label'].startswith('GHS_DockTruck'):continue
            o=a['bounds']['origin'];e=a['bounds']['extent']
            footprint=rect((o[0]-e[0])/100+239.33385,(o[1]-e[1])/100+60.24019,
                           (o[0]+e[0])/100+239.33385,(o[1]+e[1])/100+60.24019)
            assert campus.contains(footprint),a['label']
            # Public context must never be painted through original equipment.
            assert public.intersection(footprint).area<.001,a['label']
            truck_checks.append(a['label'])
    counts.update(cad_road_segments=len(cad['roads']),context_road_segments=len(specs)+len(highways),
                  detailed_context_houses=len(residential['houses']))
    result=dict(version=2,campus_boundary_uv_m=boundary,source_dxf=cad['source'],
                original_dock_trucks_contained=len(truck_checks),roads=curve_report,
                fence=fence_result,gatehouses=booths,residential=residential,
                parking=parking,forests=forests,
                trailer_bay_checks=bay_checks,parked_vehicles_checked=len(vehicle_clearances),
                parked_vehicle_min_road_clearance_m=min(vehicle_clearances),fence_road_overlap_m=remaining_fence.intersection(all_ground).length,
                bridge_crossings=crossings,scope_bounds=list(scope.bounds),
                road_surface_valid=all_ground.is_valid,road_area_m2=all_ground.area,
                reference='CAD road and building XY; satellite parcel, landscape and architectural details',
                height_policy='Flat presentation ground; 6.1m highway crossing; residential source default3m replaced by image-referenced two-storey forms')
    (PARK/'site_geometry_report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result
