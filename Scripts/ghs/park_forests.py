"""Deterministic, collision-checked woodland framing for the GHS campus.

These are visual-context forests in previously empty presentation areas, not
claims about surveyed trees. CAD watercourses remain clear and every canopy
is tested against roads, buildings/driveways, the campus, and the model edge.
"""
import math
import random

from shapely.geometry import Point,Polygon,LineString
from shapely.ops import unary_union

from park_surfaces import emit_surface
from park_vegetation import build_tree


FOREST_AREAS = (
    ('West woodland',[(-175,-155),(-85,-155),(-70,-60),(-65,40),
                      (-65,170),(-95,272),(-175,300)],240),
    ('Northeast woodland',[(340,-195),(710,-195),(710,-65),
                           (615,-45),(550,-55),(510,-100),(410,-120)],270),
)


def _parts(shape,kind):
    if shape.is_empty:
        return []
    if shape.geom_type==kind:
        return [shape]
    return [p for g in getattr(shape,'geoms',[]) for p in _parts(g,kind)]


def _finite_distance(shape,point):
    return shape.distance(point) if not shape.is_empty else None


def _grove_polygon(center,radius,phase):
    # Broad irregular lobes avoid the repeated circular soil discs that make
    # procedural woodland look like isolated landscaped roundabouts.
    points=[]
    for i in range(36):
        angle=i*math.tau/36
        r=radius*(.94+.115*math.sin(angle*3+phase)+.055*math.sin(angle*5-phase))
        points.append((center.x+math.cos(angle)*r,center.y+math.sin(angle)*r))
    return Polygon(points).buffer(2,quad_segs=8).buffer(-2,quad_segs=8)


def build_forests(api,cad,roads,occupied,scope,campus):
    """Append two green woodland groups and return fully auditable placement.

    api requires mesh and may provide counts/preview; no api['tree'] is needed.
    roads is the union of pavement (including the freeway), occupied should
    include house roofs and driveways. All inputs use unreflected u/v metres.
    CAD water line/polygon geometries receive an 18 m no-canopy buffer.
    """
    water_records=[]
    for row in cad.get('linework',[]):
        if row.get('layer')!='water' or len(row.get('points_uv_m',[]))<2:
            continue
        points=row['points_uv_m']
        if row.get('closed') and len(points)>=4:
            water=Polygon(points).buffer(0)
        else:
            water=LineString(points)
        water_records.append((row['id'],water))
    water=unary_union([s for _,s in water_records])
    excluded=unary_union([roads.buffer(8),occupied.buffer(10),campus.buffer(8),water.buffer(18)])
    outer_safe=scope.buffer(-1)
    rng=random.Random(173350210)
    selected=[]
    groups=[]
    global_spacing=5.7
    bins={}

    def is_spaced(point):
        key=(math.floor(point.x/global_spacing),math.floor(point.y/global_spacing))
        for dx in (-1,0,1):
            for dy in (-1,0,1):
                for other in bins.get((key[0]+dx,key[1]+dy),[]):
                    if math.dist((point.x,point.y),other)<global_spacing:
                        return False
        return True

    for group_index,(name,outline,target) in enumerate(FOREST_AREAS):
        desired=Polygon(outline)
        available=desired.intersection(outer_safe).difference(excluded)
        available=available.buffer(-2,quad_segs=8).buffer(2,quad_segs=8).intersection(available)
        if available.is_empty:
            groups.append(dict(name=name,trees=0,available_area_m2=0,reason='No safe woodland area'))
            continue
        xmin,ymin,xmax,ymax=available.bounds
        centers=[]
        for _ in range(1200):
            q=Point(rng.uniform(xmin,xmax),rng.uniform(ymin,ymax))
            if available.contains(q) and all(q.distance(c[0])>24 for c in centers):
                centers.append((q,rng.uniform(25,36)))
                if len(centers)>=9:
                    break
        # Overlapping irregular groves leave several clearings and a varied
        # edge. A mild closing pass removes tiny notches without filling the
        # road, residential or watercourse buffers.
        grove=unary_union([_grove_polygon(point,radius,index*1.357+group_index)
                           for index,(point,radius) in enumerate(centers)])
        grove=grove.intersection(available).buffer(2,quad_segs=8).buffer(-2,quad_segs=8).intersection(available)
        assert grove.is_valid and outer_safe.covers(grove)
        assert grove.intersection(excluded).area<1e-6
        emit_surface(api,grove,'Landscape',-.12)
        if 'preview' in api:
            for polygon in _parts(grove,'Polygon'):
                api['preview'].append(('Landscape',list(polygon.exterior.coords)))
        placements=[]
        for attempt in range(target*180):
            if len(placements)>=target:
                break
            if attempt%5:
                center,radius=centers[rng.randrange(len(centers))]
                q=Point(rng.gauss(center.x,radius*.48),rng.gauss(center.y,radius*.48))
            else:
                q=Point(rng.uniform(xmin,xmax),rng.uniform(ymin,ymax))
            if not grove.contains(q) or not is_spaced(q):
                continue
            variant=rng.randrange(3)
            # Crown height blends down at grove margins. Keep varied sizes
            # rather than uniformly scaled ranks of identical trees.
            edge_distance=q.distance(grove.boundary)
            target_height=rng.uniform(5.1,6.6) if edge_distance<8 else rng.uniform(5.4,8.0)
            base_heights=(5.74,6.75,5.40)
            size=target_height/base_heights[variant]
            shape_info=build_tree({'mesh':lambda *args:None},q.x,q.y,size,variant)
            crown=q.buffer(shape_info['radius_m'],quad_segs=12)
            if not grove.covers(crown):
                continue
            # Recheck actual model bounds (not nominal height-based radii).
            assert roads.distance(crown)>=8-1e-6
            assert occupied.is_empty or occupied.distance(crown)>=10-1e-6
            assert campus.distance(crown)>=8-1e-6
            assert water.is_empty or water.distance(crown)>=18-1e-6
            assert scope.covers(crown)
            meta=build_tree(api,q.x,q.y,size,variant)
            record=dict(center_uv_m=[q.x,q.y],height_m=meta['height_m'],
                        crown_radius_m=meta['radius_m'],variant=variant,scale=size,
                        road_canopy_clearance_m=roads.distance(crown),
                        building_canopy_clearance_m=_finite_distance(occupied,crown),
                        campus_canopy_clearance_m=campus.distance(crown),
                        water_canopy_clearance_m=_finite_distance(water,crown))
            placements.append(record)
            selected.append(record)
            key=(math.floor(q.x/global_spacing),math.floor(q.y/global_spacing))
            bins.setdefault(key,[]).append((q.x,q.y))
        groups.append(dict(name=name,target_trees=target,trees=len(placements),
                           available_area_m2=available.area,planted_ground_area_m2=grove.area,
                           canopy_road_clearance_min_m=min((p['road_canopy_clearance_m'] for p in placements),default=None),
                           canopy_water_clearance_min_m=min((p['water_canopy_clearance_m'] for p in placements if p['water_canopy_clearance_m'] is not None),default=None),
                           ground_polygons_uv_m=[dict(exterior=list(p.exterior.coords),
                                                       holes=[list(r.coords) for r in p.interiors]) for p in _parts(grove,'Polygon')],
                           positions=placements))
    if 'counts' in api:
        api['counts']['woodland_trees']+=len(selected)
        api['counts']['woodland_groups']+=sum(g['trees']>0 for g in groups)
    distances=[math.dist(a['center_uv_m'],b['center_uv_m'])
               for i,a in enumerate(selected) for b in selected[:i]]
    minimum=min(distances,default=None)
    assert minimum is None or minimum>=global_spacing-1e-6
    return dict(seed=173350210,total_trees=len(selected),triangles=len(selected)*320,
                minimum_tree_center_spacing_m=minimum,required_center_spacing_m=global_spacing,
                clearance_policy_m=dict(roads=8,buildings_and_driveways=10,campus=8,water=18),
                watercourses_avoided=[name for name,s in water_records],groups=groups,
                source='Illustrative woodland in user-requested empty context areas; CAD waterways, roads and buildings are preserved')
