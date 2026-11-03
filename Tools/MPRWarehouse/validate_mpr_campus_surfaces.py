"""CPU-only checks of actual builder surface functions; no Blender/UE launch."""
from pathlib import Path
import ast,hashlib,json,math,sys
from collections import Counter
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'Tools/MPRWarehouse'),str(ROOT/'Scripts/ghs'),str(ROOT/'Saved/ParkRefinement/python_deps')]
import numpy as np
import shapely
from shapely.geometry import Polygon,LineString,Point,box,mapping
from shapely.ops import unary_union
from shapely.affinity import rotate,translate
import mpr_plan_site as plan
from mpr_plan_layout import plan_to_world
from park_curves import rounded_path,dash_segments

def run():
 source=ROOT/'Tools/MPRWarehouse/build_mpr_reference_v4_site.py'
 data=source.read_bytes();tree=ast.parse(data.decode('utf8'))
 names={'footprint','build_roads','build_water','terminal_surfaces','terminal_fade_at'}
 functions=[n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name in names]
 assert {n.name for n in functions}==names
 cad=json.loads((ROOT/'SourceAssets/MPR/mpr_cad_layout.json').read_text(encoding='utf8'))
 emitted={};vehicles=[];terminal_parts=[]
 def shape(name,role,geometry,z):
  emitted[name]=dict(role=role,geometry=geometry,z=z)
  if name.startswith('RoadTerminal')and not geometry.is_empty:terminal_parts.append(dict(name=name,role=role,geometry=geometry,z=z))
 ns=dict(ROOT=ROOT,json=json,np=np,math=math,shapely=shapely,plan=plan,Polygon=Polygon,LineString=LineString,Point=Point,box=box,
         unary_union=unary_union,rotate=rotate,translate=translate,plan_to_world=plan_to_world,
         rounded_path=rounded_path,dash_segments=dash_segments,MAIN=Polygon(cad['footprint_outline_m']),G=-1.2,
         COUNTS=Counter(),ROAD_DATA=[],VEHICLE_SHAPES=[],shape=shape,line=lambda *a:None,
         core=SimpleNamespace(raised_edge=lambda name,g,z,h:shape(name,'MPR3_Curb',g,z+h)),
         instance=lambda name,p,yaw,**meta:vehicles.append(dict(name=name,p=p,yaw=yaw)),
         TERMINAL_ROWS=[],TERMINAL_SUPPORT=[])
 exec(compile(ast.Module(body=functions,type_ignores=[]),str(source),'exec'),ns)
 site=ns['build_roads']();ns['build_water'](site)
 terminal_ranges={}
 for role in {part['role']for part in terminal_parts}:
  values=[ns['terminal_fade_at'](part['name'],point)for part in terminal_parts if part['role']==role for point in shapely.get_coordinates(part['geometry'])]
  terminal_ranges[role]=[min(values),max(values)]
  assert min(values)<1e-8 and max(values)>1-1e-8,(role,'Fade does not span ground transition')
 drawing=plan.pixel_box(*plan.read('outside_road_connections_v5.json')['canvas_px'])
 emitted_roads=unary_union([part['geometry']for part in terminal_parts if part['name']=='RoadTerminalRoads'])
 coverage_error=emitted_roads.symmetric_difference(site['asphalt'].difference(drawing.union(plan.road_geometry()))).area
 assert coverage_error<1e-7,('Terminal mesh source coverage error',coverage_error)
 green=site['campus_planting'];portals=plan.portal_clearance();water=site['pond'];walk=site['pond_walk']
 manifest=json.loads((ROOT/'SourceAssets/MPR/reference_v4/site/manifest.json').read_text(encoding='utf8'))
 roots=[Point(t['position_m'][:2]).buffer(.8,quad_segs=16)for t in manifest['planting']['tree_positions']]
 checks=dict(road_overlap_m2=green.intersection(site['roads']).area,portal_overlap_m2=green.intersection(portals).area,
             building_overlap_m2=green.intersection(site['buildings']).area,planting_paved_overlap_m2=green.intersection(site['paved']).area,
             pond_water_changed_m2=water.symmetric_difference(plan.named_region('SouthWestPond',False)).area,
             pond_walk_road_overlap_m2=walk.intersection(site['roads']).area,pond_walk_water_overlap_m2=walk.intersection(water).area,
             parked_car_planting_overlap_m2=sum(f.intersection(green).area for f in ns['VEHICLE_SHAPES']),
             pond_walk_preserved_tree_root_overlap_m2=sum(walk.intersection(root).area for root in roots),
             north_dock_apron_planting_overlap_m2=green.intersection(site['north_dock_apron']).area,
             north_dock_apron_unpaved_m2=site['north_dock_apron'].difference(site['paved']).area)
 assert all(abs(v)<1e-7 for v in checks.values()),checks
 # Reject an indiscriminate all-yard green fill, with a deliberately broad
 # upper bound so this check documents perimeter semantics, not exact pixels.
 fraction=green.intersection(site['main_parcel']).area/site['main_parcel'].area
 assert 0<fraction<.15,(fraction,'Green must remain a perimeter strip')
 assert walk.is_valid and green.is_valid and walk.area>0
 inputs=[source,ROOT/'Tools/MPRWarehouse/mpr_plan_site.py',ROOT/'SourceAssets/MPR/reference_v4/site/manifest.json',ROOT/'SourceAssets/MPR/reference_v4/context/manifest.json',ROOT/'SourceAssets/MPR/mpr_cad_layout.json']
 inputs.extend(plan.SITE/name for name in ['road_outline_v5.json','plan_landscape_islands_v5.json','plan_site_details_v5.json','outside_road_connections_v5.json','plan_registration_v5.json'])
 result=dict(success=True,scope='CPU AST execution of the actual road/water builder functions; not Blender or UE visual acceptance.',
             source_sha256={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in inputs},checks=checks,
             terminal_emitted_road_coverage_error_m2=coverage_error,terminal_surface_pieces=len(terminal_parts),terminal_color_ranges=terminal_ranges,
             campus_planting_area_m2=green.area,main_parcel_green_fraction=fraction,parking_cars=len(vehicles),
             pond_walk_repair=site['pond_walk_repair'],open_access_portals=len(plan.read('road_outline_v5.json')['portals_px']))
 out=ROOT/'Saved/MPR/road_v5';out.mkdir(parents=True,exist_ok=True)
 (out/'campus_surface_review.json').write_text(json.dumps(result,indent=2),encoding='utf8')
 (out/'campus_surface_geometry.json').write_text(json.dumps({k:mapping(site[k])for k in ['roads','paved','campus_planting','pond','pond_walk','main_parcel']}),encoding='utf8')
 print(json.dumps(result,indent=2));return result

if __name__=='__main__':run()
