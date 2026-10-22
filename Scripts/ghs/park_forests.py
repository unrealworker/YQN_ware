"""Deterministic, collision-checked woodland framing for the GHS campus.

These are visual-context forests in previously empty presentation areas, not
claims about surveyed trees. CAD watercourses remain clear and every canopy
is tested against roads, buildings/driveways, the campus, and the model edge.
"""
import math
import random

from shapely.geometry import Point,Polygon,LineString
from shapely.ops import unary_union
from shapely.affinity import scale as scale_shape

from park_surfaces import emit_surface
from park_vegetation import build_tree


FOREST_AREAS = (
    ('West woodland',[(-175,-155),(-85,-155),(-70,-60),(-65,40),
                      (-65,170),(-95,272),(-175,300)],240),
    ('Northeast woodland',[(340,-195),(710,-195),(710,-65),
                           (615,-45),(550,-55),(510,-100),(410,-120)],270),
)

# User's five red boxes, registered from the 1994x1219 editor screenshot
# codex-clipboard-dcb24e90-c035-4373-ad8e-f527d963bd42.png using four ground
# landmarks. These are screen-selected context regions, not surveyed woods;
# estimated boundary accuracy is +/-10 m. Keep their oblique UV quadrilaterals
# instead of replacing them with axis-aligned bounding boxes.
FOREST_FILL_AREAS = (
    ('West outer woodland', [(-303.486,30.045),(-211.008,22.010),
                             (-165.955,145.302),(-251.122,152.710)], 100),
    ('Northwest outer woodland', [(-298.436,-254.247),(-227.010,-260.439),
                                  (-188.940,-140.759),(-255.726,-134.963)], 70),
    ('Gray Pine west woodland', [(-170.741,-316.104),(17.614,-332.429),
                                 (35.187,-233.911),(-143.473,-218.415)], 150),
    ('Gray Pine middle woodland', [(171.704,-304.043),(305.933,-315.680),
                                   (310.033,-169.445),(186.147,-158.693)], 150),
    ('Northeast outer woodland', [(645.319,-310.580),(775.093,-321.834),
                                  (755.602,-232.607),(631.908,-221.873)], 120),
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


def _fill_grove_lobes(outline,index):
    """Broad uneven woodland edge, without three repeated circular clumps."""
    def local(s,t):
        weights=((1-s)*(1-t),s*(1-t),s*t,(1-s)*t)
        return Point(*(sum(p[axis]*w for p,w in zip(outline,weights)) for axis in (0,1)))

    points=[]
    for i in range(64):
        angle=i*math.tau/64
        radius=.65*(1+.12*math.sin(angle*2+index*.79)+.07*math.sin(angle*5-index))
        p=local(.5+math.cos(angle)*radius,.5+math.sin(angle)*radius)
        points.append((p.x,p.y))
    grove=Polygon(points).buffer(3,quad_segs=8).buffer(-3,quad_segs=8)
    return grove,[]


def build_forests(api,cad,roads,occupied,scope,campus):
    """Preserve the two original woods and append five requested forest groups.

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

    def is_spaced(point,minimum=global_spacing):
        key=(math.floor(point.x/global_spacing),math.floor(point.y/global_spacing))
        reach=math.ceil(minimum/global_spacing)
        for dx in range(-reach,reach+1):
            for dy in range(-reach,reach+1):
                for other in bins.get((key[0]+dx,key[1]+dy),[]):
                    if math.dist((point.x,point.y),other)<minimum:
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

    # Everything above retains the original two groups, random call sequence,
    # crown records and ground output. Expanded masks and independent seeds
    # apply only to the five new user-selected groups below.
    original_tree_count=len(selected)
    full_roads=[]
    glen_ids={'13a3','1460','1633','149c','1673','17c8','1f42','20d4'}
    for row in cad.get('roads',[]):
        points=row.get('points_uv_m',[])
        if len(points)<2:continue
        width=14. if row['layer']=='highways' else (19. if row.get('handle') in glen_ids else 7.4)
        full_roads.append(LineString(points).buffer(width/2,cap_style=2))
    expanded_roads=unary_union([roads,*full_roads])
    full_buildings=[]
    for row in cad.get('buildings',[]):
        rings=row.get('footprints_uv_m') or [row.get('footprint_uv_m',[])]
        for ring in rings:
            points=ring.get('exterior',[]) if isinstance(ring,dict) else ring
            holes=ring.get('holes',[]) if isinstance(ring,dict) else []
            if len(points)>=3:
                full_buildings.append(Polygon(points,holes).buffer(0))
    expanded_occupied=unary_union([occupied,*full_buildings])
    expanded_excluded=unary_union([expanded_roads.buffer(8),expanded_occupied.buffer(10),
                                   campus.buffer(8),water.buffer(18)])
    requested=[scale_shape(Polygon(outline),xfact=1.4,yfact=1.4,origin='centroid')
               for _,outline,_ in FOREST_FILL_AREAS]
    # Extend a single coherent rounded ground envelope, never the public site
    # scope used to filter roads and housing. Only emit the new exterior band:
    # the old ground stays byte-for-byte identical and has no overlaid face.
    hull=unary_union([scope,*[p.buffer(15,quad_segs=12) for p in requested]]).convex_hull
    forest_scope=hull.buffer(-20,quad_segs=16).buffer(20,quad_segs=16).union(scope)
    assert forest_scope.geom_type=='Polygon' and forest_scope.is_valid
    assert scope.difference(forest_scope).area<1e-6
    extra_ground=forest_scope.difference(scope)
    assert extra_ground.intersection(scope).area<1e-6
    emit_surface(api,extra_ground,'Ground',-.16)
    if 'preview' in api:
        for p in _parts(extra_ground,'Polygon'):
            api['preview'].append(('Ground',list(p.exterior.coords)))

    for fill_index,((name,outline,target),desired) in enumerate(zip(FOREST_FILL_AREAS,requested)):
        seed=173352210+fill_index*101
        fill_rng=random.Random(seed)
        # A broader irregular envelope keeps the reference centre but gives
        # the trees open transitions and scattered margins, not tight clumps.
        grove,centers=_fill_grove_lobes(outline,fill_index)
        grove=grove.intersection(desired).intersection(forest_scope.buffer(-1)).difference(expanded_excluded)
        grove=grove.buffer(-.5,quad_segs=8).buffer(.5,quad_segs=8).intersection(grove)
        # New soil is clipped against prior soil to avoid coplanar overlaps;
        # all original grove faces and previous tree positions remain intact.
        prior_ground=unary_union([Polygon(p['exterior'],p['holes'])
                                 for g in groups for p in g['ground_polygons_uv_m']])
        added_grove=grove.difference(prior_ground)
        assert added_grove.is_valid and added_grove.intersection(expanded_excluded).area<1e-6
        emit_surface(api,added_grove,'Landscape',-.12)
        if 'preview' in api:
            for p in _parts(added_grove,'Polygon'):
                api['preview'].append(('Landscape',list(p.exterior.coords)))
        xmin,ymin,xmax,ymax=grove.bounds
        placements=[]
        for attempt in range(target*250):
            if len(placements)>=target:break
            q=Point(fill_rng.uniform(xmin,xmax),fill_rng.uniform(ymin,ymax))
            if not grove.contains(q) or not is_spaced(q,10.):continue
            # Sparse edges and broad variable-density transitions prevent a
            # uniformly filled perimeter even with deterministic spacing.
            edge_distance=q.distance(grove.boundary)
            density=.57+.18*math.sin(q.x*.038+fill_index)*math.cos(q.y*.045)
            if edge_distance<12:density*=.55
            if fill_rng.random()>density:continue
            # Larger mature crowns fill the distant red-box areas, with a
            # smaller fringe. A very light density variation avoids rows.
            if (math.sin(q.x*.083+fill_index)*math.cos(q.y*.077)>.72 and attempt%3):continue
            variant=fill_rng.randrange(3)
            edge_distance=q.distance(grove.boundary)
            target_height=fill_rng.uniform(5.5,7.4) if edge_distance<9 else fill_rng.uniform(6.8,9.4)
            size=target_height/(5.74,6.75,5.40)[variant]
            shape_info=build_tree({'mesh':lambda *args:None},q.x,q.y,size,variant)
            crown=q.buffer(shape_info['radius_m'],quad_segs=12)
            if not grove.covers(crown):continue
            assert expanded_roads.distance(crown)>=8-1e-6
            assert expanded_occupied.is_empty or expanded_occupied.distance(crown)>=10-1e-6
            assert campus.distance(crown)>=8-1e-6
            assert water.is_empty or water.distance(crown)>=18-1e-6
            assert forest_scope.covers(crown)
            meta=build_tree(api,q.x,q.y,size,variant)
            record=dict(center_uv_m=[q.x,q.y],height_m=meta['height_m'],
                        crown_radius_m=meta['radius_m'],variant=variant,scale=size,
                        road_canopy_clearance_m=expanded_roads.distance(crown),
                        building_canopy_clearance_m=_finite_distance(expanded_occupied,crown),
                        campus_canopy_clearance_m=campus.distance(crown),
                        water_canopy_clearance_m=_finite_distance(water,crown))
            placements.append(record);selected.append(record)
            key=(math.floor(q.x/global_spacing),math.floor(q.y/global_spacing))
            bins.setdefault(key,[]).append((q.x,q.y))
        # Respect the 10 m spacing when river exclusion limits an outer site;
        # the target is a cap rather than a reason to pack the grove tightly.
        assert len(placements)>=target*.65,('Requested woodland under-filled',name,len(placements),target)
        groups.append(dict(name=name,target_trees=target,trees=len(placements),seed=seed,
                           reference='User red-box screenshot, 2026-10-22; +/-10m registration estimate',
                           requested_polygon_uv_m=outline,expanded_polygon_uv_m=list(desired.exterior.coords),
                           new_tree_minimum_spacing_m=10.,available_area_m2=grove.area,
                           grove_centers_uv_m=[dict(center_uv_m=[p.x,p.y],radius_m=r) for p,r in centers],
                           planted_ground_area_m2=added_grove.area,
                           canopy_road_clearance_min_m=min(p['road_canopy_clearance_m'] for p in placements),
                           canopy_water_clearance_min_m=min(p['water_canopy_clearance_m'] for p in placements),
                           ground_polygons_uv_m=[dict(exterior=list(p.exterior.coords),
                                                       holes=[list(r.coords) for r in p.interiors]) for p in _parts(added_grove,'Polygon')],
                           positions=placements))
    if 'counts' in api:
        api['counts']['woodland_trees']+=len(selected)
        api['counts']['woodland_groups']+=sum(g['trees']>0 for g in groups)
    distances=[math.dist(a['center_uv_m'],b['center_uv_m'])
               for i,a in enumerate(selected) for b in selected[:i]]
    minimum=min(distances,default=None)
    assert minimum is None or minimum>=global_spacing-1e-6
    return dict(seed=173350210,total_trees=len(selected),triangles=len(selected)*320,
                original_tree_count=original_tree_count,additional_tree_count=len(selected)-original_tree_count,
                additional_group_count=len(FOREST_FILL_AREAS),public_site_scope_changed=False,
                additional_tree_required_spacing_m=10.,
                original_ground_overlap_m2=extra_ground.intersection(scope).area,
                extended_ground_area_m2=extra_ground.area,
                forest_scope_bounds_uv_m=list(forest_scope.bounds),
                forest_scope_polygon_uv_m=list(forest_scope.exterior.coords),
                minimum_tree_center_spacing_m=minimum,required_center_spacing_m=global_spacing,
                clearance_policy_m=dict(roads=8,buildings_and_driveways=10,campus=8,water=18),
                watercourses_avoided=[name for name,s in water_records],groups=groups,
                source='Illustrative woodland in user-requested empty context areas; CAD waterways, roads and buildings are preserved')
