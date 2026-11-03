"""Verify context references, projected tank silhouettes and delivery mesh paths.

This only reads the generated context and writes a compact verification report.
Run with Python including NumPy; no Blender or Unreal session is needed.
"""
from pathlib import Path
import collections
import hashlib
import json
import math
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Tools/MPRWarehouse'))
from calibrate_mpr_reference_camera import project_world_to_image, load_calibration


def main():
    folder = ROOT / 'SourceAssets/MPR/reference_v4/context'
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    plan_mode=manifest.get('geometry_version')==5
    layout = json.loads((folder / ('reference_context_plan_v5.json' if plan_mode else 'reference_context_layout.json')).read_text(encoding='utf-8'))
    cal = None if plan_mode else load_calibration()
    records = {row['id']: row for row in manifest['context_buildings']}
    errors, tank_results = [], []
    for row in layout['tanks']:
        world = records[row['id']]
        if plan_mode:
            from mpr_plan_layout import plan_to_world,load_registration
            expected=plan_to_world(row['pixel_center']);radius=row['pixel_radius']*math.sqrt(abs(math.prod(load_registration()['scale_m_per_px'])))
            center_error=math.dist(world['center_m'],expected);radius_error=abs(world['radius_m']-radius)
            circularity=max(abs(math.dist(p,expected[:2])-radius)for p in world['footprint_m'])
            tank_results.append(dict(id=row['id'],center_error_m=center_error,radius_error_m=radius_error,circularity_error_m=circularity))
            if max(center_error,radius_error,circularity)>1e-7:errors.append(row['id']+' differs from registered circular plan geometry')
            continue
        center = row['pixel_roof_center']
        radii = row['pixel_roof_ellipse_radius_px']
        points = world['footprint_m']
        deviations = []
        for i, point in enumerate(points):
            actual = project_world_to_image([*point, cal['ground_plane_z_m'] + world['estimated_height_m']], cal)
            expected = [center[0] + radii[0] * math.cos(i * math.tau / len(points)),
                        center[1] + radii[1] * math.sin(i * math.tau / len(points))]
            deviations.append(math.dist(actual, expected))
        maximum = max(deviations)
        tank_results.append(dict(id=row['id'],top_outline_max_error_px=maximum))
        if maximum > .01:
            errors.append(f"{row['id']} top ellipse projection differs by {maximum:.4f} px")
    for row in manifest['meshes']:
        if not (ROOT / row['fbx']).is_file():
            errors.append('Missing FBX: ' + row['fbx'])
        elif row.get('sha256') and hashlib.sha256((ROOT/row['fbx']).read_bytes()).hexdigest()!=row['sha256']:
            errors.append('FBX hash mismatch: '+row['fbx'])
        for dependency in row.get('lod_files', []):
            if not (ROOT / dependency).is_file():
                errors.append('Missing LOD: ' + dependency)
        if not set(row['material_roles']).issubset(manifest['materials']):
            errors.append('Unresolved material: ' + row['name'])
    if plan_mode:
        audit=json.loads((folder/'orthogonality_validation.json').read_text(encoding='utf8'))
        if not audit['success'] or audit['source_manifest_sha256']!=hashlib.sha256((folder/'manifest.json').read_bytes()).hexdigest():errors.append('Saved source geometry audit is stale or failed')
        source=ROOT/layout['source']
        if hashlib.sha256(source.read_bytes()).hexdigest()!=layout['source_sha256']:errors.append('Plan drawing hash mismatch')
        sys.path.insert(0,str(ROOT/'Saved/ParkRefinement/python_deps'))
        from shapely.geometry import Polygon
        from shapely.ops import unary_union
        from mpr_plan_site import road_geometry
        pads=unary_union([Polygon(p)for p in manifest['paved_footprints_m']]);roads=road_geometry();pad_rows=[]
        for row in records.values():
            if row['type']!='cylindrical_tank':continue
            footprint=Polygon(row['footprint_m']);coverage=footprint.intersection(pads).area/footprint.area
            overlap=footprint.intersection(roads).area
            pad_rows.append(dict(id=row['id'],pad_coverage=coverage,road_overlap_m2=overlap))
            if coverage<.9999 or overlap>.001:errors.append(row['id']+': incomplete foundation or road collision')
        pad_road_overlap=pads.intersection(roads).area
        if pad_road_overlap>.001:errors.append('Tank foundation intersects road')
        (folder/'tank_pad_validation.json').write_text(json.dumps(dict(success=all(r['pad_coverage']>.9999 and r['road_overlap_m2']<.001 for r in pad_rows)and pad_road_overlap<.001,
            source_manifest_sha256=hashlib.sha256((folder/'manifest.json').read_bytes()).hexdigest(),tanks=pad_rows,pad_road_overlap_m2=pad_road_overlap),indent=2)+'\n',encoding='utf8')
    report = dict(
        success=not errors,geometry_version=manifest.get('geometry_version',4),
        source_manifest_sha256=hashlib.sha256((folder / 'manifest.json').read_bytes()).hexdigest(),
        calibrated_source_sha256=layout['source_sha256'],
        building_counts=dict(collections.Counter(row['type'] for row in records.values())),
        mesh_rows=len(manifest['meshes']),
        lod0_meshes=sum(row['lod'] == 0 for row in manifest['meshes']),
        lod0_triangles=sum(row['triangles'] for row in manifest['meshes'] if row['lod'] == 0),
        all_lods_triangles=sum(row['triangles'] for row in manifest['meshes']),
        tank_geometry=tank_results, errors=errors,
        limits='Source dependency and physical geometry verification; not final UE visual acceptance. Heights and unseen facade details remain visual estimates.')
    (folder / 'validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
