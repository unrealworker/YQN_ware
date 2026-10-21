"""Satellite-referenced parking rows, end islands and entrance landscaping.

The DXF supplies drive aisles; stall and planting details are visual reference
geometry. All parking keeps clear of the unchanged road corridors.
"""
import math
import random

from shapely.geometry import LineString, Point, Polygon, box as rect
from shapely.ops import unary_union
from park_surfaces import emit_surface, emit_curb
from park_vegetation import build_shrub


def build_parking(api, campus, roads, warehouse):
    rng = random.Random(17335)
    rotate = api['rotate_point']
    lots = [rect(-.5,137.8,42.1,175.6).buffer(.75,quad_segs=10),
            rect(-.8,197.0,39.6,239.3).buffer(.75,quad_segs=10),
            rect(471,1,502,42).buffer(1.1,quad_segs=10)]
    lots = [p.intersection(campus).difference(warehouse.buffer(.40)) for p in lots]
    for lot in lots:
        emit_surface(api,lot,'Roads',.028)
        emit_curb(api,lot,'Curbs',.22,.18,openings=[roads.buffer(.25)],base_z=.025)
        for p in _parts(lot):api['preview'].append(('Roads',list(p.exterior.coords)))

    island_lines = [((14.3,151),(14.3,160.6)),((27.6,151),(27.6,160.6)),
                    ((14.3,209.5),(24.5,209.5)),((14.3,226),(24.5,226))]
    islands = [LineString(p).buffer(1.05,quad_segs=10) for p in island_lines]
    for island in islands:
        assert island.distance(roads)>.5, 'Planting island blocks a drive aisle'
        emit_surface(api,island,'Landscape',.13)
        emit_curb(api,island,'Curbs',.18,.24,base_z=.028)
        api['preview'].append(('Landscape',list(island.exterior.coords)))
    for a,b in island_lines:
        line=LineString((a,b))
        for i in range(int(line.length/1.7)+1):
            p=line.interpolate((i+.3)*line.length/(int(line.length/1.7)+1))
            build_shrub(api,p.x,p.y,size=.48,variant=i%3)
        for fraction in (.12,.88):
            p=line.interpolate(line.length*fraction)
            api['tree'](p.x,p.y,3.9)

    stall_shapes=[]; stall_records=[]; rejected=[]; row_records=[]
    island_mask=unary_union(islands).buffer(.20)

    def row(name,origin,count,angle=0,depth=5.15,filled=.62,flip=False):
        """Local x follows the row; local y is the stall's vehicle length."""
        accepted=0; parked=0; width=2.65
        for i in range(count):
            corners=[rotate(x,y,origin,angle) for x,y in
                     [(i*width,0),((i+1)*width,0),((i+1)*width,depth),(i*width,depth)]]
            footprint=Polygon(corners)
            reason=None
            if not unary_union(lots).buffer(.02).covers(footprint):reason='outside lot'
            elif footprint.intersection(roads).area>.005:reason='drive aisle'
            elif footprint.intersects(island_mask):reason='planting island'
            elif any(footprint.intersection(other).area>.01 for other in stall_shapes):reason='another stall'
            if reason:
                rejected.append(dict(row=name,index=i,reason=reason));continue
            stall_shapes.append(footprint);accepted+=1
            closed_end=(corners[0],corners[1]) if flip else (corners[3],corners[2])
            for a,b in ((corners[0],corners[3]),(corners[1],corners[2]),closed_end):
                api['ribbon']('Markings',[a,b],.095,.047)
            cx,cy=rotate((i+.5)*width,depth*.5,origin,angle)
            heading=angle+math.pi/2+(math.pi if flip else 0)
            occupied=rng.random()<filled
            if occupied:
                api['car'](cx,cy,heading,blue=(len(stall_records)%19==5));parked+=1
            # Discrete low wheel stop emphasises a real bay without enclosing
            # the vehicle in raised kerbs or obstructing the aisle.
            stop=rotate((i+.5)*width,.48 if flip else depth-.48,origin,angle)
            api['box']('Curbs',(*stop,.105),(1.55,.16,.14),angle)
            stall_records.append(dict(row=name,center=[cx,cy],heading=heading,occupied=occupied,
                                      footprint_uv_m=list(footprint.exterior.coords)))
        row_records.append(dict(name=name,planned=count,accepted=accepted,occupied=parked))
        api['counts']['car_spaces']+=accepted

    # Upper lot: central cars run along v, flanked by two long end islands.
    row('upper_center_north',(15.6,150.5),4,filled=.70)
    row('upper_center_south',(26.2,160.8),4,math.pi,filled=.70)
    row('upper_warehouse_edge',(11.2,138.1),8,depth=5.05,filled=.68,flip=True)
    row('upper_entrance_edge',(11.2,169.1),8,depth=5.05,filled=.52)
    row('upper_west_edge',(4.60,149.3),6,math.pi/2,depth=5.05,filled=.65)
    row('upper_east_edge',(35.95,165.2),6,-math.pi/2,depth=5.05,filled=.58)
    # Lower lot: central cars run along u, rotated 90 degrees from upper lot.
    row('lower_center_west',(19.4,211.35),5,math.pi/2,filled=.56,flip=True)
    row('lower_center_east',(19.4,224.6),5,-math.pi/2,filled=.56,flip=True)
    row('lower_entrance_edge',(11.3,197.25),7,depth=5.05,filled=.45,flip=True)
    row('lower_south_edge',(11.3,233.15),7,depth=5.05,filled=.58)
    row('lower_west_edge',(5.30,208.4),7,math.pi/2,depth=5.05,filled=.55)
    row('lower_east_edge',(33.3,227.0),7,-math.pi/2,depth=5.05,filled=.42)
    # Small NE lot retains its source circulation and rows.
    row('northeast_west',(485.5,12),5,math.pi/2,filled=.65)
    row('northeast_east',(485.9,28.8),5,-math.pi/2,filled=.55)

    # Garden pockets around the employee lots, plus the gatehouse island.
    # Cropping against true asphalt and road shapes keeps entries fully open.
    booth=rect(33.8,177.2,42.2,182.8)
    garden_candidates=[
        Polygon([(-12,138),(-.7,138),(-.7,175),(-11,180)]),
        Polygon([(-10,196),(-1,196),(-1,239),(8,244),(8,255),(-9,245)]),
        rect(1,176.8,31,182.8),rect(0,191.5,40,196),
        rect(40.8,199,46.3,238),rect(8,240.7,40,246.7),
        rect(42.9,139,46.6,175),booth.buffer(1.5),
    ]
    gardens=unary_union(garden_candidates).intersection(campus.buffer(-1.8))
    gardens=gardens.difference(roads.buffer(.55)).difference(unary_union(lots).buffer(.5))
    gardens=gardens.difference(warehouse.buffer(.6)).difference(booth.buffer(.2))
    gardens=unary_union([p for p in _parts(gardens) if p.area>2])
    emit_surface(api,gardens,'Landscape',.06)
    emit_curb(api,gardens,'Curbs',.17,.16,base_z=.025)
    for p in _parts(gardens):api['preview'].append(('Landscape',list(p.exterior.coords)))
    shrubs=[];garden_trees=[]
    for p in _parts(gardens):
        minx,miny,maxx,maxy=p.bounds
        # Multiple staggered shrubs and a few shade trees, not a regular tree
        # grid. Shrub envelopes stay inside planting soil and clear of traffic.
        for _ in range(max(10,int(p.area*1.2))):
            q=Point(rng.uniform(minx,maxx),rng.uniform(miny,maxy))
            if not p.buffer(-.65).contains(q):continue
            if any(q.distance(Point(old))<1.65 for old in shrubs):continue
            build_shrub(api,q.x,q.y,size=rng.uniform(.32,.48),variant=len(shrubs)%3)
            shrubs.append([q.x,q.y])
        for _ in range(max(5,int(p.area*.12))):
            q=Point(rng.uniform(minx,maxx),rng.uniform(miny,maxy))
            if not p.buffer(-1).contains(q) or roads.distance(q)<2.8:continue
            if unary_union(stall_shapes).distance(q)<2.5 or booth.distance(q)<2.8:continue
            if any(q.distance(Point(old))<6.4 for old in garden_trees):continue
            if api['tree'](q.x,q.y,rng.uniform(4.6,5.6)):
                garden_trees.append([q.x,q.y])

    # Circulation direction arrows are contained within the source loop aisles.
    def arrow(center,angle):
        pts=[(-.16,-1.25),(.16,-1.25),(.16,.40),(.62,.40),(0,1.35),(-.62,.40),(-.16,.40)]
        shape=[rotate(x,y,center,angle) for x,y in pts]
        if roads.covers(Polygon(shape)):api['poly']('Markings',shape,.045)
    for center,angle in [((8.8,155),0),((33.0,156),math.pi),((8.6,218),0),((30.3,217),math.pi)]:
        arrow(center,angle)
    # Accessible markings at the warehouse side use blue outline/hatching,
    # no large blue pads competing with the digital twin's selection colour.
    for x in (12.525,15.175):
        for a,b in [((x-.85,139.1),(x+.85,139.1)),((x-.85,139.1),(x-.85,142.2)),((x+.85,139.1),(x+.85,142.2))]:
            api['ribbon']('Blue',[a,b],.075,.049)

    return dict(reference='User 2026-10-21 parking satellite close-up; visual detail over unchanged CAD drive aisles',
                stall_count=len(stall_records),rows=row_records,rejected_stalls=rejected,
                stalls=stall_records,island_count=len(islands),islands_uv_m=[list(p.exterior.coords) for p in islands],
                minimum_island_road_clearance_m=min(p.distance(roads) for p in islands),
                minimum_stall_road_clearance_m=min(p.distance(roads) for p in stall_shapes),
                gardens_area_m2=gardens.area,garden_shrubs=len(shrubs),garden_tree_candidates=len(garden_trees),
                planting_road_overlap_m2=unary_union(islands+[gardens]).intersection(roads).area)


def _parts(geometry):
    if geometry.is_empty:return []
    if geometry.geom_type=='Polygon':return [geometry]
    return [p for g in getattr(geometry,'geoms',[]) for p in _parts(g)]
