"""Read-only plan/context road audit; no Blender, Unreal or asset writes.

Road ends follow source tangents and dissolve into ground. This audit rejects
invented loops, junctions or connections and checks source-plan invariance.
Diagnostic JSON/SVG files are written under Saved/MPR/road_v5 only.
"""
from pathlib import Path
import hashlib,json,math,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'Tools/MPRWarehouse'),str(ROOT/'Saved/ParkRefinement/python_deps')]
import numpy as np
from shapely.geometry import Polygon,Point,LineString,box,mapping
from shapely.ops import unary_union
from shapely.affinity import rotate,translate
import mpr_plan_site as plan
from mpr_plan_layout import world_to_plan

OUT=ROOT/'Saved/MPR/road_v5'
FILES=['Tools/MPRWarehouse/mpr_plan_site.py','Tools/MPRWarehouse/validate_mpr_outside_roads.py',
 'SourceAssets/MPR/reference_v4/site/outside_road_connections_v5.json',
 'SourceAssets/MPR/reference_v4/site/road_outline_v5.json',
 'SourceAssets/MPR/reference_v4/site/plan_registration_v5.json',
 'SourceAssets/MPR/reference_v4/site/plan_landscape_islands_v5.json',
 'SourceAssets/MPR/reference_v4/site/plan_railway_v5.json',
 'SourceAssets/MPR/reference_v4/site/manifest.json',
 'SourceAssets/MPR/reference_v4/context/manifest.json',
 'SourceAssets/MPR/reference_v4/props/manifest.json','SourceAssets/MPR/mpr_cad_layout.json','Tools/MPRWarehouse/build_mpr_reference_v4_site.py','Tools/MPRWarehouse/build_mpr_reference_site.py','Scripts/ghs/build_context_transition.py','Scripts/ghs/apply_context_transition.py']

def hashes():return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()for p in FILES}
def polygons(g):return [g]if g.geom_type=='Polygon'else list(g.geoms)

def extended_rails():
    """Match the existing site builder's 160m railroad tangent completion."""
    result=[]
    for row in plan.read('plan_railway_v5.json')['tracks']:
        pts=plan.xy(row['path_px'])
        for index,neighbor,insert in [(0,1,0),(-1,-2,None)]:
            p,q=pts[index],pts[neighbor];pixel=world_to_plan(p)
            if not(pixel[1]<1 or pixel[1]>908):continue
            v=(np.asarray(p)-q)/math.dist(p,q);end=(np.asarray(p)+v*160).tolist()
            if insert==0:pts.insert(0,end)
            else:pts.append(end)
        result.append(LineString(pts))
    return result

def render_svg(path,raw,roads,buildings,railways,rows,bounds):
    xmin,ymin,xmax,ymax=roads.bounds;margin=36
    xmin-=margin;ymin-=margin;xmax+=margin;ymax+=margin
    width=xmax-xmin;height=ymax-ymin
    def point(p):return f'{p[0]-xmin:.3f},{ymax-p[1]:.3f}'
    def polygon_path(poly):
        return ' '.join('M '+' L '.join(point(p)for p in ring.coords)+' Z'for ring in [poly.exterior,*poly.interiors])
    text=[f'<svg xmlns="http://www.w3.org/2000/svg" width="1800" height="{1800*height/width:.0f}" viewBox="0 0 {width} {height}">',
          '<rect width="100%" height="100%" fill="#dbe5ce"/>']
    for p in polygons(roads):text.append(f'<path d="{polygon_path(p)}" fill="#89959c" fill-rule="evenodd" stroke="#edf0ed" stroke-width=".6"/>')
    for p in polygons(buildings):text.append(f'<path d="{polygon_path(p)}" fill="#c7cdd0" stroke="#71808a" stroke-width=".6"/>')
    for line in railways:text.append(f'<polyline points="{" ".join(point(q)for q in line.coords)}" fill="none" stroke="#6b6256" stroke-width="1.1"/>')
    text.append(f'<path d="{polygon_path(bounds)}" fill="none" stroke="#537383" stroke-width=".6" stroke-dasharray="6 5"/>')
    for row in rows:
        start=Point(row['origin_m']);end=Point(row['end_m'])
        a=point(start.coords[0]);b=point(end.coords[0]);identity=row['id']
        text.append(f'<linearGradient id="{identity}" gradientUnits="userSpaceOnUse" x1="{a.split(",")[0]}" y1="{a.split(",")[1]}" x2="{b.split(",")[0]}" y2="{b.split(",")[1]}"><stop offset="0%" stop-color="#596f7b"/><stop offset="100%" stop-color="#dbe5ce"/></linearGradient>')
        text.append(f'<polyline points="{a} {b}" fill="none" stroke="url(#{identity})" stroke-width="{row["width_m"]}"/>')
    text.append('<text x="12" y="21" font-family="Arial" font-size="13" fill="#233b48">MPR source-directed road ends / opaque ground fade / no invented connections</text>')
    text.append('</svg>');path.write_text('\n'.join(text),encoding='utf8')

def audit():
    before=hashes();raw=plan.road_geometry();config=plan.read('outside_road_connections_v5.json');bounds=plan.pixel_box(*config['canvas_px'])
    context=json.loads((ROOT/'SourceAssets/MPR/reference_v4/context/manifest.json').read_text(encoding='utf8'))
    cad=json.loads((ROOT/'SourceAssets/MPR/mpr_cad_layout.json').read_text(encoding='utf8'))
    buildings=unary_union([Polygon(cad['footprint_outline_m']),*[Polygon(p)for p in context['footprints_m']]])
    roads,rows=plan.extend_road_tails(raw,blockers=buildings);addition=roads.difference(raw)
    source_change=roads.symmetric_difference(raw).intersection(bounds).area
    assert source_change<1e-7 and roads.is_valid and len(polygons(roads))==len(polygons(raw))==2
    assert len(rows)==len(plan._road_outlets(raw))==29
    assert 'groups' not in config and 'branches' not in config and 'collectors' not in config
    assert config['status']=='source_tangent_terminal_fade_no_authored_connections'
    paths=[(r,LineString(r['path_m']))for r in rows]
    crossings=[];uncovered=[];fades=[];direction_errors=[]
    for i,(row,line)in enumerate(paths):
        assert row['kind']=='source_tangent_fade' and len(row['path_m'])==2
        assert raw.covers(Point(row['origin_m'])) and not bounds.covers(Point(row['end_m']))
        expected=np.asarray(row['origin_m'])+np.asarray(row['direction'])*row['length_m']
        direction_error=float(np.linalg.norm(expected-row['end_m']));direction_errors.append(direction_error)
        assert direction_error<1e-8 and 0<row['length_m']<=config['extension_m']
        uncovered_length=line.difference(roads).length
        if uncovered_length>1e-6:uncovered.append(dict(id=row['id'],length_m=uncovered_length))
        values=[plan.terminal_fade(row,np.asarray(row['origin_m'])+np.asarray(row['direction'])*d)for d in np.linspace(0,row['length_m'],129)]
        assert values[0]<1e-10 and values[-1]>1.-1e-10 and all(a<=b+1e-12 for a,b in zip(values,values[1:]))
        fades.append(dict(id=row['id'],length_m=row['length_m'],fade_start_m=row['fade_start_m'],range=[values[0],values[-1]],shortened_for=row['shortened_for']))
        for other,otherline in paths[i+1:]:
            hit=line.intersection(otherline).difference(bounds)
            overlap=plan.terminal_shape(row).intersection(plan.terminal_shape(other)).difference(bounds).area
            if not hit.is_empty or overlap>1e-7:crossings.append(dict(ids=[row['id'],other['id']],overlap_m2=overlap))
    assert not crossings and not uncovered
    railways=extended_rails();rail=unary_union(railways);rail_overlap=addition.intersection(rail.buffer(2,quad_segs=24)).area
    building_overlap=addition.intersection(buildings).area
    assert building_overlap<1e-7 and rail_overlap<1e-7
    # No original tree or vehicle may be moved to make authored context fit.
    manifest=plan.read('manifest.json');tree_hits=[]
    for t in manifest['planting']['tree_positions']:
        crown=Point(t['position_m'][:2]).buffer(max(.8,t['crown_radius_m']*.4),quad_segs=24)
        area=crown.intersection(addition).area
        if area>1e-6:tree_hits.append(dict(source_id=t['source_id'],overlap_m2=area))
    props=json.loads((ROOT/'SourceAssets/MPR/reference_v4/props/manifest.json').read_text(encoding='utf8'));prop_bounds={r['name']:r['bounds_m']for r in props['meshes']};vehicle_hits=[]
    for name,items in manifest['instances'].items():
        if not any(k in name for k in ['Trailer','_Car_','FreightBoxcar']):continue
        for i,t in enumerate(items):
            b=prop_bounds[name];s=t.get('scale',[1,1,1]);f=box(b[0][0]*s[0],b[1][0]*s[1],b[0][1]*s[0],b[1][1]*s[1]);f=translate(rotate(f,t.get('rotation_deg',0),origin=(0,0)),*t['position_m'][:2]);area=f.intersection(addition).area
            if area>1e-6:vehicle_hits.append(dict(mesh=name,index=i,overlap_m2=area))
    assert not tree_hits and not vehicle_hits
    paint=roads.buffer(-.55,quad_segs=16).boundary.difference(plan.portal_clearance().buffer(1)).buffer(.075,quad_segs=16)
    paint_outside=paint.difference(roads).area;assert paint_outside<1e-6
    tiny_islands=[Polygon(ring).area for poly in polygons(roads)for ring in poly.interiors if Polygon(ring).area<100 and not bounds.covers(Polygon(ring))]
    assert not tiny_islands,'Straight independent terminal stubs must not create outside enclosed islands'
    assert bounds.buffer(125).covers(roads),'Keep inferred context within a restrained band'
    assert before==hashes(),'Inputs changed during source audit'
    result=dict(status='passed_source_geometry',input_sha256=before,scope='Source geometry audit only; no Blender/UE temporal or visual acceptance. Outside segments use measured source tangents and widths, with open fading ends, not surveyed extension topology.',
        policy='source_tangent_terminal_fade_no_authored_connections',no_authored_connections=True,source_exit_count=len(rows),terminal_count=len(rows),authored_junction_count=0,authored_closed_connection_count=0,
        source_image_area_change_m2=source_change,road_components_before=len(polygons(raw)),road_components_after=len(polygons(roads)),
        outside_added_area_m2=addition.area,roads_bounds_m=list(roads.bounds),recommended_ground_padding_from_image_m=80,
        unplanned_centerline_crossings=crossings,intentionally_open_faded_endpoints=len(rows),uncovered_path_segments=uncovered,
        maximum_tangent_endpoint_error_m=max(direction_errors),terminal_fade=fades,fade_monotonic=True,
        building_overlap_m2=building_overlap,rail_4m_bed_overlap_m2=rail_overlap,
        closest_road_to_rail_center_m=roads.distance(rail),tree_contacts=tree_hits,vehicle_contacts=vehicle_hits,
        road_edge_paint_outside_m2=paint_outside,tiny_outside_islands_m2=tiny_islands,
        notes=['The previous seven closed collectors and fifteen branches are absent; no existing exits are joined to each other.',
               'Each measured mouth retains its original tangent and width. Stubs are shortened before collisions and fade sooner.',
               'Open ends are intentional. Vertex colors and opaque grass blending require subsequent Blender/FBX and UE verification.',
               'GHS reference source hashes are recorded; GHS assets are not modified.'])
    OUT.mkdir(parents=True,exist_ok=True);(OUT/'outside_road_review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    render_svg(OUT/'outside_road_review.svg',raw,roads,buildings,railways,rows,bounds)
    (OUT/'outside_road_review_geometry.json').write_text(json.dumps(dict(roads=mapping(roads),raw=mapping(raw),buildings=mapping(buildings),rails=[list(l.coords)for l in railways],rows=rows)),encoding='utf8')
    print(json.dumps({k:v for k,v in result.items()if k not in ['input_sha256','terminal_fade']},ensure_ascii=False,indent=2))
    return result

if __name__=='__main__':audit()
