"""Read-only MPR exterior road/tree review; writes only Saved/MPR/ExteriorV2.

Run with isolated Blender --background --factory-startup --python <this file>.
Existing generated blend/FBX files and UE packages are never modified.
"""
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT/'Saved/ParkRefinement/python_deps'))
sys.path.insert(0, str(ROOT/'Scripts/ghs'))
sys.path.insert(0, str(ROOT/'Tools/MPRWarehouse'))
import shapely
from shapely.geometry import Polygon, Point, LineString, MultiPoint, box
from shapely.ops import unary_union
from shapely.affinity import rotate, scale, translate
from mpr_site_roads import build_site_roads, REPLACED_ROADS
from mpr_railway_detail import build_railways
from park_vegetation import build_tree

OUT = ROOT/'Saved/MPR/ExteriorV2'
SRC = ROOT/'SourceAssets/MPR/environment'


def parts(g):
    if g.is_empty:
        return []
    if g.geom_type == 'Polygon':
        return [g]
    return [p for child in getattr(g, 'geoms', []) for p in parts(child)]


def brief(g):
    return {'area_m2':g.area, 'bounds_m':list(g.bounds),
            'centroid_m':list(g.centroid.coords)[0] if not g.is_empty else None}


def source_road(m):
    vv=m['vertices']
    return unary_union([Polygon([vv[i][:2] for i in f]) for f in m['faces']
                        if Polygon([vv[i][:2] for i in f]).area>1e-7])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    tracked=[ROOT/'Tools/MPRWarehouse/mpr_site_roads.py',ROOT/'Tools/MPRWarehouse/build_mpr_environment.py',
             SRC/'environment_local.json',SRC/'environment_manifest.json',SRC/'MPR_Environment.blend']
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    before={p.relative_to(ROOT).as_posix():digest(p) for p in tracked}
    source=json.loads((SRC/'environment_local.json').read_text())
    manifest=json.loads((SRC/'environment_manifest.json').read_text())
    noop=lambda *args,**kwargs:None
    marking_shapes=[]
    def strip(name,role,a,b,width,z):
        if role in ('LaneWhite','LaneYellow'):
            marking_shapes.append(LineString([a[:2],b[:2]]).buffer(width/2,cap_style=2))
    def zone(x,y):
        if abs(x)<250 and -170<y<240:return 'Near'
        return 'Far_'+('E' if x>250 else 'W' if x<-250 else 'N' if y>240 else 'S')
    api=dict(mesh=noop,poly=noop,box=noop,strip=strip,zone=zone,
             footprint=source['alignment']['targetFootprint_m'],include_freight=False)
    site=build_site_roads(api,source,manifest['ground_z_m'])
    rail=build_railways(api,source['polylines'],manifest['ground_z_m'])
    buildings=[]
    for m in source['meshes']:
        if m['layer']=='buildings' and m['id']!='1583' and m.get('footprintLoops'):
            buildings.append((m['id'],Polygon([m['vertices'][i][:2] for i in m['footprintLoops'][0]])))
    buildings.append(('main',site['main']))
    building_union=unary_union([p for _,p in buildings])
    parking=unary_union([box(-211,-93,-182.2,83),box(183.3,-17,211,83)]).difference(site['islands'])
    islands_road_area=site['islands'].intersection(site['roads']).area
    islands_outside_parking=site['islands'].difference(unary_union([box(-211,-93,-182.2,83),box(183.3,-17,211,83)])).area
    marking_outside=unary_union(marking_shapes).difference(site['paved'].buffer(.025))
    targets={'road':site['roads'],'all_paved':site['paved'],'parking':parking,
             'rail_corridor':rail['exclusion'],'buildings':building_union,'pond':site['pond']}
    crowns={}
    radii={}
    for variant in range(3):
        vv=[]
        build_tree({'mesh':lambda role,vertices,faces:vv.extend(vertices) if role.startswith('Trees') else None},0,0,variant=variant,base_z=0)
        crowns[variant]=MultiPoint([(p[0],p[1]) for p in vv]).convex_hull
        radii[variant]=max(math.hypot(p[0],p[1]) for p in vv)
    intersections=[]
    trees=[]
    clearances=defaultdict(list)
    for name, rows in manifest['instances'].items():
        if '_Tree_' not in name:continue
        variant=int(name.rsplit('_',1)[-1])
        for index,row in enumerate(rows):
            x,y,_=row['position_m']
            crown=translate(rotate(scale(crowns[variant],xfact=row['scale'][0],yfact=row['scale'][1],origin=(0,0)),row['rotation_deg'],origin=(0,0)),xoff=x,yoff=y)
            identity=name+'#'+str(index)
            trees.append((identity,crown,row))
            for kind,target in targets.items():
                area=crown.intersection(target).area
                clearances[kind].append(crown.distance(target))
                if area>1e-5:
                    intersections.append({'instance':identity,'target':kind,'overlap_m2':area,'position_m':row['position_m'],
                                          'scale':row['scale'][0],'variant':variant})
    tree_pair=[]
    for i,(name,crown,row) in enumerate(trees):
        for other,shape,_ in trees[:i]:
            overlap=crown.intersection(shape).area
            if overlap>.01:tree_pair.append({'a':name,'b':other,'overlap_m2':overlap})

    roads={m['id']:source_road(m) for m in source['meshes'] if m['layer'] in ('major_roads','minor_roads','paths')}
    retained=unary_union([p for identity,p in roads.items() if identity not in REPLACED_ROADS])
    original_roads=unary_union(list(roads.values()))
    retained_missing=retained.difference(site['roads'].buffer(.002))
    connections=[]
    for identity in sorted(REPLACED_ROADS):
        if identity not in roads:continue
        # Original adjacency is recovered independently from the source CAD
        # union, not from the replacement control points or cached audit.
        contact=roads[identity].intersection(retained.buffer(.3))
        clusters=parts(contact.buffer(.6).buffer(-.6))
        for n,patch in enumerate(clusters):
            if patch.area<.1:continue
            point=patch.representative_point()
            gap=patch.distance(site['roads'])
            coverage=patch.intersection(site['roads']).area/patch.area
            connections.append({'source_replaced_id':identity,'interface':n,'position_m':list(point.coords)[0],
                                'gap_m':gap,'coverage_fraction':coverage,'source_contact_area_m2':patch.area})
    path_review=[]
    for name,pts in site['paths'].items():
        line=LineString(pts)
        outside=line.difference(site['paved'].buffer(.01)).length
        max_step=max(math.dist(a,b) for a,b in zip(pts,pts[1:]))
        turns=[]
        for a,b,c in zip(pts,pts[1:],pts[2:]):
            ab=(b[0]-a[0],b[1]-a[1]);bc=(c[0]-b[0],c[1]-b[1]);den=math.hypot(*ab)*math.hypot(*bc)
            if den>1e-12:turns.append(math.degrees(math.acos(max(-1,min(1,(ab[0]*bc[0]+ab[1]*bc[1])/den)))))
        path_review.append({'name':name,'length_m':line.length,'max_sample_step_m':max_step,
                            'max_sample_turn_deg':max(turns,default=0),'length_outside_paving_m':outside,'simple':line.is_simple})
    # Opening removes thin ribbons/tips.  Report only substantial candidates,
    # not the tiny scallops inherent in round polygon buffers.
    near_window=box(-300,-240,300,360)
    near_road=site['roads'].intersection(near_window)
    removed=near_road.difference(near_road.buffer(-.8,quad_segs=8).buffer(.8,quad_segs=8))
    spike_candidates=[]
    for p in parts(removed):
        if p.area<.5:continue
        coords=list(p.minimum_rotated_rectangle.exterior.coords)
        edges=[math.dist(a,b) for a,b in zip(coords,coords[1:])]
        width,length=min(edges),max(edges)
        if length>3 and width<1.6 and length/max(width,1e-6)>3:
            spike_candidates.append({**brief(p),'length_m':length,'width_m':width})
    building_road=[]
    for identity,p in buildings:
        overlap=p.intersection(site['paved'])
        if overlap.area>.05:building_road.append({'building_id':identity,**brief(overlap),
            'original_source_road_overlap_m2':p.intersection(original_roads).area,
            'new_paving_overlap_m2':overlap.difference(original_roads).area})
    components=sorted(parts(site['roads']),key=lambda p:p.area,reverse=True)
    main_component=next((p for p in components if p.intersects(LineString(site['paths']['Prologis']))),None)
    for connection in connections:
        point=Point(connection['position_m'])
        connection['connected_to_main_network']=bool(main_component and main_component.buffer(.01).covers(point))
    path_connectivity=[]
    for name,pts in site['paths'].items():
        path_connectivity.append({'name':name,'connected_to_prologis':bool(main_component and main_component.buffer(.01).covers(LineString(pts)))})
    warnings=[]
    if any(r['gap_m']>.5 for r in connections):warnings.append('Source-to-replacement road interfaces have gaps >0.5m')
    if spike_candidates:warnings.append('Thin pavement protrusions need visual review; not all candidates are defects')
    if building_road:warnings.append('Paving overlaps building footprints; source and newly introduced areas recorded separately')
    if tree_pair:warnings.append('Actual tree crown projections overlap each other')
    if islands_road_area>.001 or islands_outside_parking>.001:warnings.append('Parking planting islands overlap roads or escape parking parcels')
    if marking_outside.area>.5:warnings.append('Some painted line geometry lies outside pavement')
    success=not intersections and retained_missing.area<.1 and not any(r['gap_m']>.5 or not r['connected_to_main_network'] for r in connections) and all(p['connected_to_prologis'] for p in path_connectivity) and not any(b['new_paving_overlap_m2']>2 for b in building_road) and islands_road_area<.001 and islands_outside_parking<.001
    report={'success':success,'time_utc':datetime.now(timezone.utc).isoformat(),'read_only':True,
      'scope':'Actual manifest placements against true source-tree crown vertex convex hulls; CAD interfaces and regenerated pure road/rail polygons. No asset writes or UE execution.',
      'input_sha256':before,'tree_count':len(trees),'actual_base_tree_radii_m':radii,
      'tree_intersections':intersections,'tree_pair_intersections':tree_pair,
      'minimum_crown_clearance_m':{k:min(v) for k,v in clearances.items()},
      'retained_source_road_missing_m2':retained_missing.area,'source_road_interfaces':connections,
      'parking_island_road_overlap_m2':islands_road_area,'parking_island_outside_parcel_m2':islands_outside_parking,
      'marking_outside_pavement_m2':marking_outside.area,
      'marking_outside_pavement_regions':[brief(p) for p in parts(marking_outside) if p.area>.02],
      'generated_manifest_matches_current_road_audit':manifest.get('road_audit')==site['audit'],
      'road_paths':path_review,'path_connectivity':path_connectivity,
      'road_connected_components':len(components),'near_pavement_spike_candidates':spike_candidates,
      'paving_building_intersections':building_road,'warnings':warnings,
      'geometry_limits':'Tree convex hull is conservative over leaf clusters. Narrow tips are heuristic candidates; road survey accuracy and render quality require separate visual review.'}
    report['inputs_unchanged']=all(digest(ROOT/p)==sha for p,sha in before.items())
    if not report['inputs_unchanged']:report['success']=False;warnings.append('Input changed concurrently; rerun required')
    (OUT/'site_geometry_review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('MPR_SITE_REVIEW '+json.dumps({k:v for k,v in report.items() if k not in ('source_road_interfaces','input_sha256','road_paths','path_connectivity','near_pavement_spike_candidates','paving_building_intersections','tree_pair_intersections')},ensure_ascii=False))
    print('INTERFACES '+json.dumps([r for r in connections if r['gap_m']>.5],ensure_ascii=False))
    print('SPIKES '+json.dumps(spike_candidates,ensure_ascii=False))
    print('PAVING_BUILDINGS '+json.dumps(building_road,ensure_ascii=False))


if __name__=='__main__':main()
