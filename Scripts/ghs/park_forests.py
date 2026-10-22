"""Reference-style rounded woodland islands with full canopy clearance checks."""
import math
import random
from shapely.geometry import Point,Polygon,LineString
from shapely.geometry.polygon import orient
from shapely.ops import unary_union
from shapely.affinity import scale as scale_shape
from park_surfaces import emit_surface
from park_vegetation import build_tree,build_shrub

FOREST_AREAS = (
    ('West woodland',[(-175,-155),(-85,-155),(-70,-60),(-65,40),
                      (-65,170),(-95,272),(-175,300)],60),
    ('Northeast woodland',[(340,-195),(710,-195),(710,-65),
                           (615,-45),(550,-55),(510,-100),(410,-120)],60),
)

# User's five red boxes, registered from the 1994x1219 editor screenshot
# codex-clipboard-dcb24e90-c035-4373-ad8e-f527d963bd42.png using four ground
# landmarks. These are screen-selected context regions, not surveyed woods;
# estimated boundary accuracy is +/-10 m. Keep their oblique UV quadrilaterals
# instead of replacing them with axis-aligned bounding boxes.
FOREST_FILL_AREAS = (
    ('West outer woodland', [(-303.486,30.045),(-211.008,22.010),
                             (-165.955,145.302),(-251.122,152.710)], 30),
    ('Northwest outer woodland', [(-298.436,-254.247),(-227.010,-260.439),
                                  (-188.940,-140.759),(-255.726,-134.963)], 20),
    ('Gray Pine west woodland', [(-170.741,-316.104),(17.614,-332.429),
                                 (35.187,-233.911),(-143.473,-218.415)], 40),
    ('Gray Pine middle woodland', [(171.704,-304.043),(305.933,-315.680),
                                   (310.033,-169.445),(186.147,-158.693)], 40),
    ('Northeast outer woodland', [(645.319,-310.580),(775.093,-321.834),
                                  (755.602,-232.607),(631.908,-221.873)], 30),
)


def _parts(shape,kind):
    if shape.is_empty:return []
    if shape.geom_type==kind:return [shape]
    return [p for g in getattr(shape,'geoms',[]) for p in _parts(g,kind)]


def _finite_distance(shape,point):
    return shape.distance(point) if not shape.is_empty else None


def _island(center,radius,phase):
    points=[]
    for i in range(48):
        angle=i*math.tau/48
        r=radius*(1+.10*math.sin(angle*3+phase)+.05*math.sin(angle*5-phase))
        points.append((center.x+math.cos(angle)*r*1.15,center.y+math.sin(angle)*r*.88))
    return Polygon(points).buffer(1.2,quad_segs=8).buffer(-1.2,quad_segs=8)


def _emit_island(api,shape):
    emit_surface(api,shape,'Landscape',.08)
    vertices=[];faces=[]
    for polygon in _parts(shape,'Polygon'):
        polygon=orient(polygon,sign=1.)
        for ring in [polygon.exterior,*polygon.interiors]:
            for a,b in zip(ring.coords,list(ring.coords)[1:]):
                i=len(vertices)
                vertices.extend([(a[0],a[1],-.16),(b[0],b[1],-.16),(b[0],b[1],.08),(a[0],a[1],.08)])
                faces.append((i,i+1,i+2,i+3))
        if 'preview' in api:api['preview'].append(('Landscape',list(polygon.exterior.coords)))
    if faces:api['mesh']('Landscape',vertices,faces)


def build_forests(api,cad,roads,occupied,scope,campus):
    """Use 7 requested regions, 24 distinct small islands and large main crowns.

    Tree numbers/positions are deliberately redesigned for the supplied render.
    CAD roads, buildings, river clearances and the public site scope stay fixed.
    """
    water_records=[]
    for row in cad.get('linework',[]):
        if row.get('layer')!='water' or len(row.get('points_uv_m',[]))<2:continue
        pts=row['points_uv_m']
        water_records.append((row['id'],Polygon(pts).buffer(0) if row.get('closed') and len(pts)>=4 else LineString(pts)))
    water=unary_union([g for _,g in water_records])
    glen_ids={'13a3','1460','1633','149c','1673','17c8','1f42','20d4'}
    all_roads=[roads]
    for row in cad.get('roads',[]):
        pts=row.get('points_uv_m',[])
        if len(pts)<2:continue
        width=14. if row['layer']=='highways' else 19. if row.get('handle') in glen_ids else 7.4
        all_roads.append(LineString(pts).buffer(width/2,cap_style=2))
    roads=unary_union(all_roads)
    all_buildings=[occupied]
    for row in cad.get('buildings',[]):
        for ring in row.get('footprints_uv_m') or [row.get('footprint_uv_m',[])]:
            pts=ring.get('exterior',[]) if isinstance(ring,dict) else ring
            holes=ring.get('holes',[]) if isinstance(ring,dict) else []
            if len(pts)>=3:all_buildings.append(Polygon(pts,holes).buffer(0))
    occupied=unary_union(all_buildings)
    excluded=unary_union([roads.buffer(8),occupied.buffer(10),campus.buffer(8),water.buffer(18)])
    regions=[Polygon(outline) for _,outline,_ in FOREST_AREAS]+[
        scale_shape(Polygon(outline),xfact=1.4,yfact=1.4,origin='centroid') for _,outline,_ in FOREST_FILL_AREAS]
    hull=unary_union([scope,*[p.buffer(15,quad_segs=12) for p in regions[2:]]]).convex_hull
    forest_scope=hull.buffer(-20,quad_segs=16).buffer(20,quad_segs=16).union(scope)
    extra_ground=forest_scope.difference(scope)
    assert extra_ground.intersection(scope).area<1e-6
    emit_surface(api,extra_ground,'Ground',-.16)
    if 'preview' in api:
        for p in _parts(extra_ground,'Polygon'):api['preview'].append(('Ground',list(p.exterior.coords)))
    base_info=[build_tree({'mesh':lambda *args:None},0,0,1,i,base_z=0) for i in range(3)]
    groups=[];selected=[];all_islands=[];triangle_total=0;shrub_count=0
    for group_index,((name,outline,target),desired) in enumerate(zip((*FOREST_AREAS,*FOREST_FILL_AREAS),regions)):
        rng=random.Random(173352600+group_index*211)
        available=desired.intersection(forest_scope.buffer(-2)).difference(excluded)
        n=(5,5,3,2,3,3,3)[group_index]
        inner=available.buffer(-23)
        if inner.is_empty:inner=available.buffer(-16)
        assert not inner.is_empty,(name,'No safe island centres')
        xmin,ymin,xmax,ymax=inner.bounds
        candidates=[]
        for _ in range(2500):
            q=Point(rng.uniform(xmin,xmax),rng.uniform(ymin,ymax))
            if inner.covers(q):candidates.append(q)
        centers=[]
        for k in range(n):
            if not candidates:break
            q=min(candidates,key=lambda p:p.distance(available.centroid)) if not centers else max(candidates,key=lambda p:min(p.distance(c) for c in centers))
            centers.append(q)
            candidates=[p for p in candidates if p.distance(q)>51]
        assert len(centers)==n,(name,'Cannot spread separate islands',len(centers),n)
        placements=[];group_islands=[];group_shrubs=[]
        for island_index,center in enumerate(centers):
            radius=rng.uniform(28,34)
            island=_island(center,radius,group_index*.7+island_index).intersection(available)
            if all_islands:island=island.difference(unary_union(all_islands).buffer(5))
            island=island.buffer(-.5,quad_segs=8).buffer(.5,quad_segs=8).intersection(island)
            assert island.is_valid and island.area>650,(name,island_index,island.area)
            all_islands.append(island);_emit_island(api,island)
            island_trees=[];island_target=target//n+(island_index<target%n)
            xmin,ymin,xmax,ymax=island.bounds
            for _ in range(island_target*500):
                if len(island_trees)>=island_target:break
                q=Point(rng.uniform(xmin,xmax),rng.uniform(ymin,ymax))
                variant=rng.randrange(3);height=rng.uniform(8.4,12.7)
                size=height/base_info[variant]['height_m']
                radius_actual=base_info[variant]['radius_m']*size
                if not 3.5<=radius_actual<=5.5:continue
                crown=q.buffer(radius_actual,quad_segs=16)
                if not island.covers(crown):continue
                if any(math.dist((q.x,q.y),p['center_uv_m'])<max(10.,radius_actual+p['crown_radius_m']+.65) for p in selected):continue
                assert roads.distance(crown)>=8-1e-6 and occupied.distance(crown)>=10-1e-6
                assert campus.distance(crown)>=8-1e-6 and (water.is_empty or water.distance(crown)>=18-1e-6)
                info=build_tree(api,q.x,q.y,size,variant,base_z=.08);triangle_total+=info['triangles']
                record=dict(center_uv_m=[q.x,q.y],height_m=info['height_m']-.08,crown_radius_m=info['radius_m'],
                    variant=variant,scale=size,base_z_m=.08,island_index=island_index,
                    road_canopy_clearance_m=roads.distance(crown),building_canopy_clearance_m=_finite_distance(occupied,crown),
                    campus_canopy_clearance_m=campus.distance(crown),water_canopy_clearance_m=_finite_distance(water,crown))
                selected.append(record);placements.append(record);island_trees.append(record)
            assert len(island_trees)>=6,(name,island_index,'Undersized tree island',len(island_trees))
            bushes=[]
            for _ in range(200):
                if len(bushes)>=3:break
                q=Point(rng.uniform(xmin,xmax),rng.uniform(ymin,ymax))
                if not island.buffer(-2.5).covers(q):continue
                if any(q.distance(Point(p['center_uv_m']))<3.0 for p in island_trees):continue
                if any(math.dist((q.x,q.y),p)<4. for p in bushes):continue
                meta=build_shrub(api,q.x,q.y,rng.uniform(.8,1.3),variant=len(bushes)+group_index,base_z=.08)
                triangle_total+=meta['triangles'];bushes.append([q.x,q.y]);shrub_count+=1
            group_shrubs.extend(bushes)
            group_islands.append(dict(index=island_index,trees=len(island_trees),shrubs=len(bushes),area_m2=island.area,
                center_uv_m=[center.x,center.y],top_z_m=.08,base_z_m=-.16,
                polygons_uv_m=[dict(exterior=list(p.exterior.coords),holes=[list(r.coords) for r in p.interiors]) for p in _parts(island,'Polygon')]))
        ground=unary_union(all_islands[-n:])
        groups.append(dict(name=name,target_trees=target,trees=len(placements),islands=group_islands,shrubs=group_shrubs,
            available_area_m2=available.area,planted_ground_area_m2=ground.area,
            canopy_road_clearance_min_m=min(p['road_canopy_clearance_m'] for p in placements),
            canopy_water_clearance_min_m=min(p['water_canopy_clearance_m'] for p in placements),
            ground_polygons_uv_m=[dict(exterior=list(p.exterior.coords),holes=[list(r.coords) for r in p.interiors]) for p in _parts(ground,'Polygon')],positions=placements))
    assert 250<=len(selected)<=300,('Forest count outside reference target',len(selected))
    if 'counts' in api:
        api['counts']['woodland_trees']+=len(selected);api['counts']['woodland_groups']+=len(groups)
        api['counts']['woodland_islands']+=len(all_islands);api['counts']['woodland_shrubs']+=shrub_count
    minimum=min(math.dist(a['center_uv_m'],b['center_uv_m']) for i,a in enumerate(selected) for b in selected[:i])
    return dict(seed=173352600,total_trees=len(selected),triangles=triangle_total,total_islands=len(all_islands),
        total_shrubs=shrub_count,reference_style='Large smooth main crowns, short trunks, separate rounded landscape islands',
        public_site_scope_changed=False,original_ground_overlap_m2=extra_ground.intersection(scope).area,
        extended_ground_area_m2=extra_ground.area,forest_scope_bounds_uv_m=list(forest_scope.bounds),
        forest_scope_polygon_uv_m=list(forest_scope.exterior.coords),minimum_tree_center_spacing_m=minimum,
        required_center_spacing_m=10.,clearance_policy_m=dict(roads=8,buildings_and_driveways=10,campus=8,water=18),
        watercourses_avoided=[name for name,_ in water_records],groups=groups,
        source='User reference render, visual landscape redesign; CAD waterways/roads/buildings preserved')
