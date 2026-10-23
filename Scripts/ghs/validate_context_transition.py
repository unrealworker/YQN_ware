"""Source-level geometry and preservation checks for the context extension.

Runs without Blender or Unreal. Verifies shared route joins, spatial material
mask exclusion, original features' clearance and exported asset receipts.
"""
from pathlib import Path
import hashlib
import json
import math
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'Saved/ParkRefinement/python_deps'))
from shapely.geometry import Polygon,LineString,Point
from shapely.ops import unary_union
from context_road_ends import classify_context_road_ends
from validate_road_terminal_junction_fix import validate_scoped_repair


def read(path):return json.loads(path.read_text(encoding='utf-8'))


def main():
    source=ROOT/'SourceAssets/GHS/ContextTransition'
    manifest=read(source/'context_transition.json')
    routes=read(ROOT/'SourceAssets/GHS/Traffic/routes.json')
    site=read(ROOT/'SourceAssets/GHS/Park/site_geometry_report.json')
    cad=read(ROOT/'SourceAssets/GHS/Park/cad_layout.json')
    by={r['id']:r for r in routes['roads']}
    joins=[]
    for end in manifest['roads']:
        road=by[end['road_id']];side=end['side'];index=0 if side=='start' else -1
        assert road['extend_'+side]
        assert math.dist(end['old_end_uv_m'],road['path_uv_m'][index])<1e-7
        assert math.dist(end['new_end_uv_m'],road['extended_path_uv_m'][index])<1e-6
        assert abs(end['width_m']-road['width_m'])<1e-6
        assert abs(end['height_m']-road['heights_m'][index]-.003)<1e-7
        assert abs(math.dist(end['new_end_uv_m'],end['old_end_uv_m'])-65)<1e-6
        joins.append(end['road_id']+':'+side)
    classified=classify_context_road_ends(routes['roads'],cad['roads'])
    expected={r['road_id']+':'+r['side'] for r in classified['external']}
    assert len(expected)==6
    scoped=None
    # The original version 1 blend/manifest remains immutable. Its eight
    # source tails are not the active geometry once the scoped repair exists.
    if manifest.get('version',1)>=2:
        assert set(joins)==expected
    else:
        scoped=validate_scoped_repair(ROOT)
        legacy=expected|{r['road_id']+':'+r['side'] for r in classified['internal']}
        assert set(joins)==legacy
    hull=manifest['protected_campus_hull_uv_m']
    def outside(p):
        return max(((b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0]))/math.dist(a,b)
                   for a,b in zip(hull,hull[1:]))
    maximum_campus=max(outside(p) for p in site['campus_boundary_uv_m'])
    minimum_house=min(outside(p) for h in site['residential']['houses'] for p in h['footprint_uv_m'])
    assert maximum_campus<5,'A campus surface would be de-emphasized'
    assert minimum_house>9,'An exterior house would escape the contrast mask'
    roads=unary_union([LineString(r['points_uv_m']).buffer(12) for r in cad['roads'] if len(r['points_uv_m'])>1]+[
        LineString(e['path_uv_m']).buffer(e['width_m']/2+9) for e in manifest['roads']])
    buildings=unary_union([Polygon(h['footprint_uv_m']).buffer(10) for h in site['residential']['houses']])
    old_islands=unary_union([Polygon(p['exterior'],p.get('holes',[]))
        for g in site['forests']['groups'] for p in g['ground_polygons_uv_m']])
    previous=Polygon()
    centers=[]
    for island in manifest['islands']:
        polygon=Polygon(island['polygon_uv_m'])
        assert polygon.is_valid and polygon.area>500
        assert polygon.intersection(roads).area<.001
        assert polygon.intersection(buildings).area<.001
        assert polygon.intersection(old_islands.buffer(14.99)).area<.001
        assert polygon.intersection(previous).area<.001
        previous=previous.union(polygon)
        for tree in island['trees']:
            point=Point(tree['position_uv_m'])
            assert polygon.covers(point.buffer(tree['radius_m'])),'Tree canopy outside its island'
            centers.append(tree['position_uv_m'])
    spacing=min(math.dist(a,b) for i,a in enumerate(centers) for b in centers[:i])
    assert spacing>=9.5
    for row in manifest['meshes']:
        path=ROOT/row['fbx']
        assert path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256']
    assert manifest['triangles']==sum(r['triangles'] for r in manifest['meshes'])<110000
    assert manifest['trees']==len(centers)<=54
    report=dict(success=True,road_end_joins=sorted(expected),
        context_geometry_source='scoped repaired meshes' if scoped else 'version 2 context meshes',
        legacy_source_not_active=bool(scoped),scoped_repair=scoped,
        islands=len(manifest['islands']),trees=len(centers),
        triangles=manifest['triangles'],minimum_tree_spacing_m=spacing,
        maximum_protected_campus_distance_m=maximum_campus,minimum_house_distance_m=minimum_house,
        all_source_assets_hash_verified=True)
    (ROOT/'Saved/RoofTraffic').mkdir(parents=True,exist_ok=True)
    (ROOT/'Saved/RoofTraffic/context-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
