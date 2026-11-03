"""Independent V4 geometry audit, no Blender/UE or source writes.

Reconstructs exported road/water/rail topology with emit callbacks disabled;
checks the actual manifest vehicle/tree placements and context footprints.
"""
import ast,json,math,sys,random,hashlib,types
from pathlib import Path
from collections import defaultdict,Counter
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'Tools/MPRWarehouse'),str(ROOT/'Saved/ParkRefinement/python_deps'),str(ROOT/'Scripts/ghs')]
import numpy as np
from shapely.geometry import Polygon,Point,LineString,box
from shapely.ops import unary_union
from shapely.affinity import rotate,translate
import shapely
import mpr_plan_site as plan
from mpr_plan_layout import plan_to_world,load_registration
from calibrate_mpr_reference_camera import image_to_ground,project_world_to_image,load_calibration
from mpr_railway_detail import build_railways
import mpr_railway_detail as rail_detail
from park_curves import rounded_path,offset_path,dash_segments,sample_along

OUT=ROOT/'SourceAssets/MPR/reference_v4/site'
SOURCE=json.loads((OUT/'reference_site_pixels.json').read_text(encoding='utf-8'));CAL=load_calibration();G=-1.2
CAD=json.loads((ROOT/'SourceAssets/MPR/mpr_cad_layout.json').read_text(encoding='utf-8'));MAIN=Polygon(CAD['footprint_outline_m'])
COUNTS=Counter();INSTANCES=defaultdict(list);ROAD_DATA=[];TREE_ROWS=[];VEHICLE_SHAPES=[];RNG=random.Random(110203)
noop=lambda *a,**kw:None
API=dict(mesh=noop,poly=noop,box=noop,strip=noop,zone=lambda *p:'Near',footprint=CAD['footprint_outline_m'],include_freight=False)
core=types.SimpleNamespace(MAIN=MAIN,CAD=CAD,shape=noop,lines=noop,raised_edge=noop,build_railways=build_railways,API=API)
script=ROOT/'Tools/MPRWarehouse/build_mpr_reference_v4_site.py'
module=ast.parse(script.read_text(encoding='utf-8'))
functions=[n for n in module.body if isinstance(n,ast.FunctionDef) and n.name in
           ('world','poly_world','meters','shape','line','instance','round_polygon','footprint','build_roads','build_water','extend_track','build_rail','place_trailers')]
exec(compile(ast.Module(body=functions,type_ignores=[]),str(script),'exec'))


def audit():
    site=build_roads();build_water(site);build_rail(site);place_trailers(site)
    manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
    context_path=ROOT/'SourceAssets/MPR/reference_v4/context/manifest.json'
    context=json.loads(context_path.read_text(encoding='utf-8'))
    context_paved=unary_union([Polygon(p) for p in context.get('paved_footprints_m',[])])
    site['paved']=site['paved'].union(context_paved)
    buildings=[(r['id'],Polygon(r['footprint_m'])) for r in context['context_buildings']]
    road_issues=[]
    for name,building in buildings:
        if building.intersection(site['roads']).area>.5:
            roads=[dict(name=r['name'],area_m2=round(building.intersection(r['geometry']).area,2))
                   for r in ROAD_DATA if building.intersection(r['geometry']).area>.5]
            road_issues.append(dict(building=name,overlap_m2=round(building.intersection(site['roads']).area,2),roads=roads))
    pond_issues={key:round(site[key].intersection(site['paved']).area,3) for key in ('pond','pond_walk')}
    vehicle_shapes=[];vehicle_offroad=[];train_shapes=[]
    props=json.loads((ROOT/'SourceAssets/MPR/reference_v4/props/manifest.json').read_text(encoding='utf-8'))
    bounds={r['name']:r['bounds_m'] for r in props['meshes']}
    for name,rows in manifest.get('instances',{}).items():
        for index,row in enumerate(rows):
            p=row['position_m'];yaw=row.get('rotation_deg',0)
            if not any(v in name for v in ('Trailer','_Car_','FreightBoxcar')):continue
            bb=bounds[name];scale=row.get('scale',[1,1,1])
            poly=box(bb[0][0]*scale[0],bb[1][0]*scale[1],bb[0][1]*scale[0],bb[1][1]*scale[1])
            poly=translate(rotate(poly,yaw,origin=(0,0)),*p[:2])
            record=(name,index,poly)
            if 'Freight' in name:train_shapes.append(record);continue
            vehicle_shapes.append(record)
            off=poly.difference(site['paved']).area;intrusion=poly.intersection(site['roads']).area
            if off>.25 or intrusion>.5:
                vehicle_offroad.append(dict(mesh=name,index=index,position_m=p,off_paved_m2=round(off,2),road_intrusion_m2=round(intrusion,2)))
    def collisions(rows):
        result=[]
        for i,(name,index,poly) in enumerate(rows):
            for name2,index2,poly2 in rows[i+1:]:
                area=poly.intersection(poly2).area
                if area>.05:result.append(dict(a=[name,index],b=[name2,index2],overlap_m2=round(area,3)))
        return result
    building_union=unary_union([p for _,p in buildings]+[MAIN]);tree_issues=[];tree_overhang=[]
    for index,row in enumerate(manifest.get('planting',{}).get('tree_positions',[])):
        p=row['position_m'];radius=row['crown_radius_m'];disk=Point(p[:2]).buffer(radius,quad_segs=16)
        road=disk.intersection(site['roads']).area;walls=disk.intersection(building_union).area;rail=disk.intersection(site['rail']['exclusion']).area
        inner85=Point(p[:2]).buffer(radius*.85,quad_segs=24);trunk=Point(p[:2]).buffer(.8,quad_segs=24)
        violations=dict(building_core_m2=inner85.intersection(building_union).area,rail_core_m2=inner85.intersection(site['rail']['exclusion']).area,
                        trunk_road_m2=trunk.intersection(site['roads']).area)
        record=dict(index=index,reference_pixel=row['reference_pixel'],crown_radius_m=round(radius,2),road_overlap_m2=round(road,2),building_overlap_m2=round(walls,2),rail_overlap_m2=round(rail,2),
                    violations={k:round(v,3) for k,v in violations.items() if v>.05})
        if record['violations']:tree_issues.append(record)
        elif max(road,walls,rail)>.5:tree_overhang.append(record)
    tracks=[LineString(r['vertices']) for r in site['rail']['centerlines']]
    spacing=[tracks[i].distance(tracks[i+1]) for i in range(len(tracks)-1)]
    return dict(source_manifest_sha256=hashlib.sha256((OUT/'manifest.json').read_bytes()).hexdigest(),
                context_manifest_sha256=hashlib.sha256(context_path.read_bytes()).hexdigest(),
                reconstructed_source_hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in
                  (script,OUT/'plan_site_details_v5.json',OUT/'road_outline_v5.json',OUT/'plan_railway_v5.json',OUT/'plan_vegetation_v5.json',OUT/'plan_registration_v5.json',ROOT/'SourceAssets/MPR/reference_v4/context/reference_context_plan_v5.json')},
                scope='Road/water/rail geometry reconstructed from current generator inputs; vehicles and trees read from exported site manifest. Regenerate site after input changes before final acceptance.',
                buildings_on_roads=road_issues,pond_paving_overlaps_m2=pond_issues,vehicles_outside_standing_surfaces=vehicle_offroad,
                vehicle_collisions=collisions(vehicle_shapes),boxcar_collisions=collisions(train_shapes),
                tree_clearance_violations=tree_issues,allowed_crown_edge_overhang=tree_overhang,minimum_track_center_spacing_m=min(spacing),
                tree_policy='85 percent radius excludes buildings/rail; 0.8m trunk excludes roads; source-measured trees in courts receive explicit planted islands; crown-edge overhang permitted',
                counts=dict(buildings=len(buildings),road_segments=len(ROAD_DATA),parked_vehicles=len(vehicle_shapes),boxcars=len(train_shapes),
                            trees=len(manifest.get('planting',{}).get('tree_positions',[]))))


if __name__=='__main__':
    report=audit();report['success']=not any(report[k] for k in ('buildings_on_roads','vehicles_outside_standing_surfaces','vehicle_collisions','boxcar_collisions','tree_clearance_violations')) and max(report['pond_paving_overlaps_m2'].values(),default=0)<.1;path=ROOT/'SourceAssets/MPR/reference_v4/validation/spatial_audit.json';path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:(len(v) if isinstance(v,list) else v) for k,v in report.items()},ensure_ascii=False,indent=2))

    if not report['success']:raise SystemExit('Spatial validation failed; see '+str(path))
