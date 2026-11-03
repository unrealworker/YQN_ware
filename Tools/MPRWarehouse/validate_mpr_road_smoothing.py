"""Read-only source geometry audit for the shared road smoothing step.

Uses isolated Python/GEOS, never Blender or Unreal. Reports old-manifest tree
contacts separately: the site builder must rerun its deterministic tree fit
after source geometry changes. --require-current-placements makes these fatal.
Only the report under Saved is written; source inputs are hash-checked.
"""
from pathlib import Path
import argparse,hashlib,json,math,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'Tools/MPRWarehouse'),str(ROOT/'Saved/ParkRefinement/python_deps')]
import numpy as np
from shapely.geometry import Polygon,Point,LineString,box
from shapely.ops import unary_union
from shapely.affinity import rotate,translate
import mpr_plan_site as plan
from mpr_plan_layout import plan_to_world

FILES=[ROOT/p for p in ['Tools/MPRWarehouse/mpr_plan_site.py','SourceAssets/MPR/reference_v4/site/road_outline_v5.json',
 'SourceAssets/MPR/reference_v4/site/plan_landscape_islands_v5.json','SourceAssets/MPR/reference_v4/site/plan_registration_v5.json',
 'SourceAssets/MPR/reference_v4/site/manifest.json','SourceAssets/MPR/reference_v4/context/manifest.json',
 'SourceAssets/MPR/reference_v4/props/manifest.json','SourceAssets/MPR/mpr_cad_layout.json']]
def hash_inputs():return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in FILES}
def polygons(shape):return [shape]if shape.geom_type=='Polygon'else list(shape.geoms)
def topology(shape):return dict(components=len(polygons(shape)),holes=sum(len(p.interiors)for p in polygons(shape)))
def turns(shape,protected):
    angles=[]
    for p in polygons(shape):
        for ring in [p.exterior,*p.interiors]:
            points=np.asarray(ring.coords)[:-1]
            for i,q in enumerate(points):
                if protected.covers(Point(q)):continue
                a=q-points[i-1];b=points[(i+1)%len(points)]-q;la=np.linalg.norm(a);lb=np.linalg.norm(b)
                if min(la,lb)<1e-8:continue
                angles.append(math.degrees(math.acos(float(np.clip(a@b/la/lb,-1,1)))))
    return dict(count=len(angles),turn_p95_deg=float(np.percentile(angles,95)),corners_over_30deg=sum(v>30 for v in angles),max_turn_deg=max(angles))

def audit(require_current_placements=False):
    hashes=hash_inputs();raw=plan.read('road_outline_v5.json');rows=[];before_px=[];after_px=[];protected=plan.road_smoothing_protected_px()
    for row in raw['polygons_px']:
        smooth=plan.smooth_road_polygon_px(row);a=Polygon(row['exterior'],row.get('holes',[]));b=Polygon(smooth['exterior'],smooth.get('holes',[]));before_px.append(a);after_px.append(b)
        delta=a.boundary.hausdorff_distance(b.boundary);protected_delta=a.symmetric_difference(b).intersection(protected).area
        assert b.is_valid and topology(a)==topology(b) and delta<=.600001 and protected_delta<1e-7
        rows.append(dict(id=row['id'],name=row['name'],valid=True,topology_before=topology(a),topology_after=topology(b),boundary_hausdorff_px=delta,protected_area_change_px2=protected_delta,
                         before_turns=turns(a,protected),after_turns=turns(b,protected)))
    old=unary_union([plan.polygon(r)for r in raw['polygons_px']]).difference(plan.landscape_islands());new=plan.road_geometry()
    assert topology(old)==topology(new) and new.is_valid
    context=json.loads(FILES[5].read_text(encoding='utf8'));cad=json.loads(FILES[7].read_text(encoding='utf8'))
    buildings=unary_union([Polygon(cad['footprint_outline_m']),*[Polygon(p)for p in context['footprints_m']]])
    old_extended,old_tails=plan.extend_road_tails(old,blockers=buildings);new_extended,new_tails=plan.extend_road_tails(new,blockers=buildings)
    assert len(old_tails)==len(new_tails) and all(math.dist(a['origin_m'],b['origin_m'])<1e-8 and math.dist(a['direction'],b['direction'])<1e-8 for a,b in zip(old_tails,new_tails)), 'Image-edge protection must preserve road continuations'
    building_overlap=new_extended.intersection(buildings).area;island_overlap=new.intersection(plan.landscape_islands()).area
    assert building_overlap<1e-6 and island_overlap<1e-6
    oldpx=unary_union(before_px);newpx=unary_union(after_px);gates=[]
    for gate in raw['portals_px']:
        window=LineString(gate['ends_px']).buffer(2.9,cap_style=2)
        delta=oldpx.symmetric_difference(newpx).intersection(window).area
        assert delta<1e-7
        gates.append(dict(id=gate['id'],is_open_entrance=gate['do_not_close_in_runtime'],local_geometry_change_px2=delta))
    island=plan.read('plan_landscape_islands_v5.json')['polygons_px'][0];island_px=Polygon(island['exterior']);route=[]
    for y in range(385,641,3):
        edge=island_px.intersection(LineString([[0,y],[500,y]])).bounds[0];route.append(plan_to_world([edge-12,y])[:2])
    route=LineString(route);corridor_ok=new_extended.contains(route.buffer(2.5,quad_segs=24));assert corridor_ok
    manifest=plan.read('manifest.json');props=json.loads(FILES[6].read_text(encoding='utf8'));bounds={r['name']:r['bounds_m']for r in props['meshes']};vehicle_contacts=[]
    for name,items in manifest['instances'].items():
        if not any(x in name for x in ['Trailer','_Car_','FreightBoxcar']):continue
        for i,item in enumerate(items):
            b=bounds[name];s=item.get('scale',[1,1,1]);p=box(b[0][0]*s[0],b[1][0]*s[1],b[0][1]*s[0],b[1][1]*s[1]);p=translate(rotate(p,item.get('rotation_deg',0),origin=(0,0)),*item['position_m'][:2]);area=p.intersection(new_extended).area
            if area>.001:vehicle_contacts.append(dict(mesh=name,index=i,overlap_m2=area))
    assert not vehicle_contacts,'Fixed source vehicles must not intersect the smoothed roads'
    tree_contacts=[]
    for tree in manifest['planting']['tree_positions']:
        pt=Point(tree['position_m'][:2]);r=tree['crown_radius_m'];trunk=pt.buffer(.8,quad_segs=24);crown40=pt.buffer(r*.4,quad_segs=24)
        violations=dict(trunk_with_road_margin_m2=trunk.intersection(new_extended.buffer(.35)).area,crown40_with_road_m2=crown40.intersection(new_extended).area)
        if max(violations.values())>1e-6:tree_contacts.append(dict(source_id=tree['source_id'],**violations))
    # Road paint is regenerated from the same smoothed surface, with the old
    # width/inset and the same entrance masks; no independently warped paint.
    paint=new_extended.buffer(-.55,quad_segs=16).boundary.difference(plan.portal_clearance().buffer(1)).buffer(.075,quad_segs=16)
    paint_outside=paint.difference(new_extended).area;assert paint_outside<1e-6
    after_hashes=hash_inputs();assert hashes==after_hashes,'Source input changed during the read-only audit'
    result=dict(status='passed_source_geometry_requires_tree_refit' if tree_contacts else 'passed',input_sha256=hashes,
        scope='Shared mathematical road source only; no Blender/UE rebuild or render. Old exported tree placements are checked explicitly.',
        algorithm='Quadratic corner fillets, maximum bidirectional boundary distance 0.6px; protected image edges and annotated portals; landscape islands subtracted after smoothing.',
        polygons=rows,world_topology_before=topology(old),world_topology_after=topology(new),entrances=gates,unchanged_road_extension_count=len(new_tails),
        building_overlap_m2=building_overlap,island_overlap_m2=island_overlap,vehicle_road_contacts=vehicle_contacts,road_paint_outside_m2=paint_outside,
        west_island_continuous_5m_road_corridor=corridor_ok,west_corridor_min_edge_distance_m=route.distance(new_extended.boundary),
        old_manifest_tree_contacts=tree_contacts,required_next_step='Rebuild site to refit trees and regenerate asphalt/kerbs/paint together, run spatial audit and compare the same UE close view.')
    return result

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--require-current-placements',action='store_true');ap.add_argument('--out',type=Path,default=ROOT/'Saved/MPR/road_v5/road_smoothing_review.json');args=ap.parse_args()
    report=audit(args.require_current_placements);args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in report.items()if k not in ['input_sha256','polygons']},ensure_ascii=False,indent=2))
    if args.require_current_placements and report['old_manifest_tree_contacts']:raise SystemExit('Tree placements need the site builder refit; see report')
