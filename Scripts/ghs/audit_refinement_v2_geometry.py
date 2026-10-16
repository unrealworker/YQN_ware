"""Read-only, repeatable CAD-frame audit of V2 envelope, loads and dock trucks.

This deliberately audits the two wall solid layers, not their boundary lines:
0..4.2m preserves the 87 openings; 4.2..9.6m contains the continuous lintels.
No scene or source asset is changed. The JSON report records exact source hashes.
"""
import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Scripts/_vendor/cad'))
from shapely.geometry import Polygon, box, shape
from shapely.affinity import rotate, translate
from shapely.prepared import prep

OUT=ROOT/'SourceAssets/GHS/RefinementV2/Envelope/scene_geometry_audit.json'
AREA_EPS=1e-8
VOLUME_EPS=1e-8


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def obb(bounds, xy, angle):
    local=box(bounds[0][0],bounds[1][0],bounds[0][1],bounds[1][1])
    return translate(rotate(local,angle,origin=(0,0)),xy[0],xy[1])


def centred_bounds(center,size):
    return [[center[k]-size[k]/2,center[k]+size[k]/2] for k in range(len(size))]


def overlap_height(a,b):
    return max(0,min(a[1],b[1])-max(a[0],b[0]))


def audit(layout_path,output):
    v2_rack_manifest=ROOT/'SourceAssets/GHS/RefinementV2/Racks/refined_rack_cargo.json'
    rack_fallback_used=not v2_rack_manifest.is_file()
    rack_manifest=(ROOT/'SourceAssets/GHS/RackSpecs/Models/cad_rack_models.json'
                   if rack_fallback_used else v2_rack_manifest)
    paths={
        'envelope_geometry':ROOT/'SourceAssets/GHS/RefinementV2/Envelope/envelope_geometry.json',
        'envelope_manifest':ROOT/'SourceAssets/GHS/RefinementV2/Envelope/envelope_v2.json',
        'docking_targets':ROOT/'SourceAssets/GHS/RefinementV2/Envelope/door_docking_targets.json',
        'truck_mesh':ROOT/'SourceAssets/GHS/RefinementV2/Trucks/dock_truck_v2.json',
        'rack_layout':layout_path,
        'rack_meshes':rack_manifest,
        'ground_meshes':ROOT/'SourceAssets/GHS/Presentation/presentation_storage.json',
    }
    data={key:read(path) for key,path in paths.items()}
    envelope=data['envelope_geometry']
    footprint=Polygon(envelope['main_building_polygon_cad_m'])
    lower=shape(envelope['lower_walls_geojson'])
    upper=shape(envelope['upper_walls_geojson'])
    walls=[('below_lintel',lower,(0,4.2),prep(lower)),('lintel_and_upper',upper,(4.2,9.6),prep(upper))]

    def wall_intersections(poly,zrange):
        records=[]
        for name,geom,z,prepared in walls:
            height=overlap_height(zrange,z)
            if height<=1e-9 or not prepared.intersects(poly):continue
            area=poly.intersection(geom).area
            volume=area*height
            if area>AREA_EPS and volume>VOLUME_EPS:
                records.append({'wall_layer':name,'xy_intersection_area_m2':area,
                                'overlap_height_m':height,'envelope_intersection_volume_m3':volume})
        return records

    truck_mesh=data['truck_mesh']['meshes'][0]
    bounds=truck_mesh['bounds_m']
    truck_ground_offset=-bounds[2][0]
    trucks=[]
    for door in data['docking_targets']['doors']:
        xy=list(door['truck_rear_dock_target_cad_m'])
        xy[2]+=truck_ground_offset
        yaw=door['truck_forward_cad_yaw_deg']
        poly=obb(bounds,xy,yaw)
        z=[bounds[2][0]+xy[2],bounds[2][1]+xy[2]]
        trucks.append({'id':'DockTruck_'+door['dock_number'].zfill(2),'dock_number':door['dock_number'],
                       'door_instance_id':door['instance_id'],'rear_origin_cad_m':xy,
                       'source_docking_target_cad_m':door['truck_rear_dock_target_cad_m'],
                       'ground_offset_m':truck_ground_offset,
                       'yaw_cad_deg':yaw,'z_bounds_m':z,'polygon':poly,
                       'obb_corners_cad_m':list(poly.exterior.coords),
                       'building_overlap_area_m2':poly.intersection(footprint).area,
                       'building_clearance_m':poly.distance(footprint),
                       'wall_intersections':wall_intersections(poly,z)})
    truck_pairs=[]
    minimum_truck_gap=None
    nearest_truck_pair=None
    for i,a in enumerate(trucks):
        for b in trucks[i+1:]:
            gap=a['polygon'].distance(b['polygon'])
            if minimum_truck_gap is None or gap<minimum_truck_gap:
                minimum_truck_gap=gap;nearest_truck_pair=[a['id'],b['id']]
            if not a['polygon'].intersects(b['polygon']):continue
            area=a['polygon'].intersection(b['polygon']).area
            height=overlap_height(a['z_bounds_m'],b['z_bounds_m'])
            if area>AREA_EPS and height>1e-8:
                truck_pairs.append({'truck_a':a['id'],'truck_b':b['id'],
                                    'xy_intersection_area_m2':area,'obb_overlap_volume_m3':area*height})

    rack_models={m['mapping_key']:m for m in data['rack_meshes']['meshes']}
    rack_rows=data['rack_layout']['racks']
    model_fbx_checks=[];model_fbx_issues=[]
    for key in sorted({row['mapping_key'] for row in rack_rows}):
        model=rack_models.get(key)
        if model is None:continue
        fbx=Path(model['fbx'])
        expected=model.get('fbx_sha256',model.get('sha256'))
        actual=hashlib.sha256(fbx.read_bytes()).hexdigest() if fbx.is_file() else None
        check={'mapping_key':key,'name':model['name'],'fbx':str(fbx),
               'expected_sha256':expected,'actual_sha256':actual,
               'sha256_matches':actual is not None and expected is not None and actual==expected}
        model_fbx_checks.append(check)
        if not check['sha256_matches']:model_fbx_issues.append(check)
    rack_hits=[];rack_candidates=[];rack_outside=[];missing_models=[]
    minimum_rack_wall_gap=None
    nearest_rack_wall=None
    for row in rack_rows:
        rid=row.get('instance_id',row.get('id',row.get('source_id')))
        model=rack_models.get(row['mapping_key'])
        if model is None:
            missing_models.append({'id':rid,'mapping_key':row['mapping_key']});continue
        xy=row['position_m']
        zbase=xy[2] if len(xy)>2 else 0
        yaw=row['rotation_deg']+90
        poly=obb(model['bounds_m'],xy,yaw)
        z=[v+zbase for v in model['bounds_m'][2]]
        gap=poly.distance(upper)
        if minimum_rack_wall_gap is None or gap<minimum_rack_wall_gap:
            minimum_rack_wall_gap=gap;nearest_rack_wall=rid
        outside_area=poly.difference(footprint).area
        if outside_area>AREA_EPS:rack_outside.append({'id':rid,'outside_building_area_m2':outside_area})
        broad_hits=wall_intersections(poly,z)
        if not broad_hits:continue
        summary={'id':rid,'spec_type':row['spec_type'],'mapping_key':row['mapping_key'],
                 'position_m':xy,'model_yaw_cad_deg':yaw,'wall_intersections':broad_hits}
        rack_candidates.append(summary)
        components=[]
        for solid in model.get('solid_boxes',[]):
            local=centred_bounds(solid['center_m'],solid['size_m'])
            solid_poly=obb(local,xy,yaw)
            solid_z=[v+zbase for v in local[2]]
            hits=wall_intersections(solid_poly,solid_z)
            if hits:
                components.append({'part':solid['name'],'role':solid['role'],
                                   'local_center_m':solid['center_m'],'local_size_m':solid['size_m'],
                                   'wall_intersections':hits})
        if components or not model.get('solid_boxes'):
            rack_hits.append(dict(summary,component_count=len(components),components=components,
                                  verification_basis='Per-part exported solid-box bounds' if components else 'Full model bounds; component data absent'))

    # groundcargo is authoritative. proposed_groundcargo may contain only changed
    # rows or additions in a later solver version, so merge updates by stable ID.
    ground_by_id={row['id']:dict(row) for row in data['rack_layout'].get('groundcargo',[])}
    for row in data['rack_layout'].get('proposed_groundcargo',[]):ground_by_id[row['id']]=dict(row)
    heights={m['name'].replace('SM_GHS_Presentation_Cargo',''):m['bounds_m'][2]
             for m in data['ground_meshes']['meshes'] if '_Cargo' in m['name']}
    ground_hits=[];ground_outside=[];unknown_variants=[]
    minimum_ground_wall_gap=None;nearest_ground_wall=None
    for row in ground_by_id.values():
        bounds=centred_bounds([0,0],row['size_m'][:2])
        poly=obb(bounds,row['position_m'],row.get('rotation_deg',0))
        variant=row.get('presentation_variant','High')
        z=heights.get(variant)
        if z is None:
            unknown_variants.append({'id':row['id'],'variant':variant});z=[0,4.2]
        zbase=row['position_m'][2] if len(row['position_m'])>2 else 0
        z=[v+zbase for v in z]
        gap=poly.distance(lower)
        if minimum_ground_wall_gap is None or gap<minimum_ground_wall_gap:
            minimum_ground_wall_gap=gap;nearest_ground_wall=row['id']
        outside_area=poly.difference(footprint).area
        if outside_area>AREA_EPS:ground_outside.append({'id':row['id'],'outside_building_area_m2':outside_area})
        hits=wall_intersections(poly,z)
        if hits:ground_hits.append({'id':row['id'],'position_m':row['position_m'],'size_m':row['size_m'],
                                    'variant':variant,'wall_intersections':hits})

    truck_building_hits=[{k:v for k,v in t.items() if k!='polygon'} for t in trucks if t['building_overlap_area_m2']>AREA_EPS]
    truck_wall_hits=[{k:v for k,v in t.items() if k!='polygon'} for t in trucks if t['wall_intersections']]
    closure=envelope['verification']
    closure_pass=bool(closure['main_building_outline_closed'] and closure['top_perimeter_ring_continuous']
                      and closure['top_perimeter_uncovered_area_m2']<AREA_EPS
                      and closure['all_87_door_openings_clear'] and closure['all_87_door_lintels_present'])
    summary={
        'truck_count':len(trucks),'truck_pair_count_checked':len(trucks)*(len(trucks)-1)//2,
        'truck_obb_collision_count':len(truck_pairs),'trucks_inside_building_count':len(truck_building_hits),
        'truck_wall_collision_count':len(truck_wall_hits),
        'truck_ground_offset_m':truck_ground_offset,
        'truck_lowest_world_z_m':min(t['z_bounds_m'][0] for t in trucks),
        'minimum_truck_to_truck_gap_m':minimum_truck_gap,'nearest_truck_pair':nearest_truck_pair,
        'minimum_truck_to_building_gap_m':min(t['building_clearance_m'] for t in trucks),
        'rack_count':len(rack_rows),'rack_wall_broadphase_candidates':len(rack_candidates),
        'rack_wall_component_collision_count':len(rack_hits),'rack_outside_building_count':len(rack_outside),
        'rack_missing_model_count':len(missing_models),
        'rack_mesh_manifest_fallback_used':rack_fallback_used,
        'rack_model_fbx_hash_issue_count':len(model_fbx_issues),
        'final_v2_rack_asset_binding_verified':not rack_fallback_used and not model_fbx_issues and not missing_models,
        'minimum_rack_envelope_to_wall_gap_m':minimum_rack_wall_gap,'nearest_rack_to_wall':nearest_rack_wall,
        'groundcargo_count':len(ground_by_id),'groundcargo_wall_collision_count':len(ground_hits),
        'groundcargo_outside_building_count':len(ground_outside),'groundcargo_unknown_variant_count':len(unknown_variants),
        'minimum_groundcargo_envelope_to_wall_gap_m':minimum_ground_wall_gap,'nearest_groundcargo_to_wall':nearest_ground_wall,
        'closed_top_perimeter_with_intentional_door_openings':closure_pass,
    }
    errors=[truck_pairs,truck_building_hits,truck_wall_hits,rack_hits,rack_outside,missing_models,model_fbx_issues,ground_hits,ground_outside,unknown_variants]
    passed=not any(errors) and closure_pass and len(trucks)==87
    report={
        'schema_version':1,'status':'passed' if passed else 'requires_resolution',
        'generated_at_utc':datetime.now(timezone.utc).isoformat(),
        'coordinate_contract':'CAD XY metres. Truck origin is rear, local +X points outside. Rack model local +X is span, hence CAD layout rotation +90 degrees.',
        'source_files':{key:{'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()} for key,path in paths.items()},
        'rack_asset_binding':{'requested_manifest':str(v2_rack_manifest),'used_manifest':str(rack_manifest),
                              'baseline_fallback_used':rack_fallback_used,
                              'status':'baseline_fallback_provisional' if rack_fallback_used else 'v2_current_fbx',
                              'fbx_checks':model_fbx_checks,'fbx_issues':model_fbx_issues},
        'tolerances':{'area_m2':AREA_EPS,'volume_m3':VOLUME_EPS},
        'summary':summary,'trucks':[{k:v for k,v in t.items() if k!='polygon'} for t in trucks],
        'truck_collisions':truck_pairs,'truck_building_intrusions':truck_building_hits,
        'truck_wall_collisions':truck_wall_hits,'rack_wall_candidates':rack_candidates,
        'rack_wall_collisions':rack_hits,'racks_outside_building':rack_outside,
        'missing_rack_models':missing_models,'groundcargo_wall_collisions':ground_hits,
        'groundcargo_outside_building':ground_outside,'unknown_ground_variants':unknown_variants,
        'closure_verification':closure,
        'method_limits':[
            'Truck OBBs include the full exported mirror width and all open rear-door geometry. Disjoint OBBs prove disjoint meshes.',
            'Rack broad-phase uses actual mapped mesh bounds. A hit is resolved against exported component bounds and wall solids at the overlapping elevations. Angled-part bounds are conservative.',
            'Groundcargo uses full CAD pallet XY bounds with actual presentation variant height; bounds are conservative for individual cartons.',
            'No rack-wall exemption exists for D1 or door bays. Geometry intersecting the 4.2m lintel is reported.',
            '87 intentional door apertures do not invalidate the closed top perimeter. No roof is assumed.',
            'This verifies the proposed source transforms; after UE integration, compare imported mesh bounds and applied transforms with these values.',
        ]}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf8')
    print(json.dumps({'status':report['status'],**summary},indent=2))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--layout',type=Path,default=ROOT/'SourceAssets/GHS/RefinementV2/Layout/rack_spacing.json')
    parser.add_argument('--output',type=Path,default=OUT)
    args=parser.parse_args()
    result=audit(args.layout,args.output)
    raise SystemExit(0 if result['status']=='passed' else 2)
