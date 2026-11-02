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
    layout = json.loads((folder / 'reference_context_layout.json').read_text(encoding='utf-8'))
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    cal = load_calibration()
    records = {row['id']: row for row in manifest['context_buildings']}
    errors, tank_results = [], []
    for row in layout['tanks']:
        world = records[row['id']]
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
        for dependency in row.get('lod_files', []):
            if not (ROOT / dependency).is_file():
                errors.append('Missing LOD: ' + dependency)
        if not set(row['material_roles']).issubset(manifest['materials']):
            errors.append('Unresolved material: ' + row['name'])
    report = dict(
        source_manifest_sha256=hashlib.sha256((folder / 'manifest.json').read_bytes()).hexdigest(),
        calibrated_source_sha256=layout['source_sha256'],
        building_counts=dict(collections.Counter(row['type'] for row in records.values())),
        mesh_rows=len(manifest['meshes']),
        lod0_meshes=sum(row['lod'] == 0 for row in manifest['meshes']),
        lod0_triangles=sum(row['triangles'] for row in manifest['meshes'] if row['lod'] == 0),
        all_lods_triangles=sum(row['triangles'] for row in manifest['meshes']),
        tank_projection=tank_results, errors=errors,
        limits='Geometric projection verification and context-only Blender render; not final UE visual acceptance. Heights and unseen details remain visual estimates.')
    (folder / 'validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
