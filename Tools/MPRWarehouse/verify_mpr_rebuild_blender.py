"""Read-only native Blender/FBX validation for the independent B50B57 rebuild.

Use run_mpr_rebuild_blender_validation.py for isolated batches. Individual
Blender calls may pass -- --start N --stop N --report PATH after this script.
This script never saves a blend or a UE asset.
"""
import argparse
import hashlib
import json
import math
import sys
import traceback
from collections import defaultdict
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Saved/ParkRefinement/python_deps'))
import bpy
import numpy as np
import shapely
from shapely.geometry import Point, Polygon, shape
from shapely.ops import unary_union

OUT = ROOT / 'SourceAssets/MPR/rebuild_b50b57'
REPORT = ROOT / 'Saved/MPR/rebuild_20261104/blender_validation.json'
POSITION_TOLERANCE_M = .002
COLOR_TOLERANCE = .00002
report = dict(success=False, meshes=[], scope='Saved Blender, all FBX roundtrips, main-shell exclusion, context clearances, immutable source hashes')


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=int, default=0)
    parser.add_argument('--stop', type=int)
    parser.add_argument('--report', type=Path, default=REPORT)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    args.report = args.report.resolve()
    assert args.report.is_relative_to((ROOT / 'Saved/MPR/rebuild_20261104').resolve()), 'Report must stay in validation output'
    return args


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def contained_path(relative, root=OUT):
    path = (ROOT / relative).resolve()
    assert path.is_relative_to(root.resolve()), ('Artifact outside rebuild source', path)
    assert path.is_file(), ('Missing artifact', path)
    return path


def check_input_hashes(manifest, audit):
    assert manifest['input_hashes'] == audit['source_hashes']
    records = {}
    for name, expected in manifest['input_hashes'].items():
        path = (OUT / 'inputs' / name).resolve()
        assert path.is_relative_to((OUT / 'inputs').resolve())
        assert sha(path) == expected, ('Archived source changed', name)
        records[name] = expected
    original = Path('D:/CodexTemp/2026-11-04/topoexport-B50B57/topoexport-B50B57.blend')
    original_checked = original.is_file()
    if original_checked:
        assert sha(original) == records['topoexport-B50B57.blend'], 'User Blender input changed'
    assert manifest['source_sha256'] == records['topoexport-B50B57.blend']
    # Verify the read-only V4 mesh source bytes against their authored manifests.
    # UE package hashes and retained actors are checked separately by the native
    # new-map preservation validator, rather than inferred from this test.
    checked = {}
    for path in sorted((ROOT / 'SourceAssets/MPR/reference_v4').rglob('manifest.json')):
        for row in read(path).get('meshes', []):
            if row.get('fbx') and row.get('sha256'):
                fbx = ROOT / row['fbx']
                assert sha(fbx) == row['sha256'], ('Original V4 source mesh changed', row['fbx'])
                checked[row['fbx']] = row['sha256']
    assert checked, 'No immutable V4 source mesh evidence'
    return dict(archived_inputs=records, original_blend_checked=original_checked,
                original_blend_unchanged=True if original_checked else None,
                original_blend_path=str(original),
                original_blend_status='hash_verified' if original_checked else 'external_file_missing_archive_hash_verified',
                original_v4_fbx_count=len(checked), original_v4_fbx_hashes=checked,
                ue_package_preservation='Validated separately by validate_mpr_rebuild.py')


def mesh_arrays(obj):
    mesh = obj.data
    mesh.calc_loop_triangles()
    vertices = np.asarray([tuple(obj.matrix_world @ v.co) for v in mesh.vertices], dtype=np.float64)
    triangles = np.asarray([tuple(t.vertices) for t in mesh.loop_triangles], dtype=np.int64)
    assert vertices.size and triangles.size and np.isfinite(vertices).all(), obj.name
    assert triangles.min() >= 0 and triangles.max() < len(vertices), obj.name
    return vertices, triangles


def validate_mesh(obj, row, *, roundtrip=False):
    mesh = obj.data
    vertices, triangles = mesh_arrays(obj)
    assert len(triangles) == row['triangles'], (row['name'], 'Triangle count changed', len(triangles), row['triangles'])
    bounds = np.stack((vertices.min(axis=0), vertices.max(axis=0)), axis=1)
    error = float(np.abs(bounds - np.asarray(row['bounds_m'])).max())
    assert error < .02, (row['name'], 'Metres/axis bounds mismatch', error)
    materials = [slot.material.name if slot.material else None for slot in obj.material_slots]
    # Blender may append numeric suffixes when the previous FBX material remains.
    normalized = [name.rsplit('.', 1)[0] if name and name.rsplit('.', 1)[-1].isdigit() else name for name in materials]
    assert normalized == row['material_roles'], (row['name'], 'Material slot order', materials, row['material_roles'])
    assert len(mesh.uv_layers), (row['name'], 'No UV layer')
    for layer in mesh.uv_layers:
        uv = np.asarray([tuple(v.uv) for v in layer.data])
        assert len(uv) == len(mesh.loops) and np.isfinite(uv).all(), (row['name'], 'Incomplete/nonfinite UV')
    assert all(0 <= f.material_index < len(materials) for f in mesh.polygons)
    return dict(triangles=len(triangles), bounds_error_m=error, uv_layers=len(mesh.uv_layers),
                material_roles=normalized, imported=roundtrip), vertices, triangles


def color_samples(obj):
    mesh = obj.data
    attribute = mesh.color_attributes.get('EdgeFade')
    assert attribute and attribute.domain in {'POINT', 'CORNER'}, (obj.name, 'Missing EdgeFade')
    indices = np.empty(len(mesh.loops), dtype=np.int32)
    mesh.loops.foreach_get('vertex_index', indices)
    points = np.asarray([tuple(obj.matrix_world @ v.co) for v in mesh.vertices])
    rgba = np.asarray([tuple(c.color) for c in attribute.data])
    values = rgba[indices] if attribute.domain == 'POINT' else rgba
    assert len(values) == len(indices) and np.isfinite(values).all()
    assert values.min() >= -COLOR_TOLERANCE and values.max() <= 1 + COLOR_TOLERANCE
    assert np.max(np.abs(values[:, :3] - values[:, 0, None])) < COLOR_TOLERANCE
    assert np.max(np.abs(values[:, 3] - 1)) < COLOR_TOLERANCE
    return np.column_stack((points[indices], values))


def compare_color_samples(source, current, name):
    """Capacity matching avoids false failures at FBX spatial bucket boundaries."""
    assert source.shape == current.shape, (name, 'Color corner count changed')
    tolerance = np.asarray([POSITION_TOLERANCE_M] * 3 + [COLOR_TOLERANCE] * 4)
    sv, sc = np.unique(source, axis=0, return_counts=True)
    cv, cc = np.unique(current, axis=0, return_counts=True)
    buckets = defaultdict(list)
    for i, point in enumerate(sv):
        buckets[tuple(np.floor(point[:3] / POSITION_TOLERANCE_M).astype(np.int64))].append(i)
    candidates = []
    for point in cv:
        key = np.floor(point[:3] / POSITION_TOLERANCE_M).astype(np.int64)
        ids = np.asarray([i for delta in product((-1, 0, 1), repeat=3)
                          for i in buckets.get(tuple(key + delta), ())], dtype=np.int64)
        ids = ids[np.all(np.abs(sv[ids] - point) <= tolerance, axis=1)]
        distance = np.linalg.norm((sv[ids] - point) / tolerance, axis=1)
        candidates.append([int(i) for i in ids[np.argsort(distance, kind='stable')]])
    free, pending = sc.copy(), cc.copy()
    allocations, clients = [{} for _ in cv], [{} for _ in sv]

    def assign(j, i, amount):
        value = allocations[j].get(i, 0) + amount
        if value:
            allocations[j][i] = value
            clients[i][j] = value
        else:
            allocations[j].pop(i, None)
            clients[i].pop(j, None)
        free[i] -= amount
        pending[j] -= amount

    for j in sorted(range(len(cv)), key=lambda j: len(candidates[j])):
        for i in candidates[j]:
            count = min(pending[j], free[i])
            if count:
                assign(j, i, count)
            if not pending[j]:
                break
    for start in np.flatnonzero(pending):
        while pending[start]:
            parents, sources, queue, destination = {int(start): None}, {}, [int(start)], None
            for j in queue:
                for i in candidates[j]:
                    if i in sources:
                        continue
                    sources[i] = j
                    if free[i]:
                        destination = i
                        break
                    for other in clients[i]:
                        if other not in parents:
                            parents[other] = i
                            queue.append(other)
                if destination is not None:
                    break
            assert destination is not None, (name, 'FBX coordinate/color distribution changed', int(pending.sum()))
            amount, adds, removes, i = min(pending[start], free[destination]), [], [], destination
            while True:
                j = sources[i]
                adds.append((j, i))
                if j == start:
                    break
                old = parents[j]
                removes.append((j, old))
                amount = min(amount, allocations[j][old])
                i = old
            for j, i in removes:
                assign(j, i, -amount)
            for j, i in adds:
                assign(j, i, amount)
    assert not free.any() and not pending.any()
    errors = [np.abs(sv[i] - cv[j]) for j, matches in enumerate(allocations) for i in matches]
    maximum = np.max(errors, axis=0)
    return dict(corner_samples=len(source), coordinate_tolerance_m=POSITION_TOLERANCE_M,
                rgba_tolerance=COLOR_TOLERANCE, maximum_position_error_m=float(maximum[:3].max()),
                maximum_rgba_error=float(maximum[3:].max()), multiset_equal=True)


def projected_overlap(vertices, triangles, exclusion):
    xy = vertices[triangles, :2]
    a, b = xy[:, 1] - xy[:, 0], xy[:, 2] - xy[:, 0]
    area = np.abs(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]) / 2
    faces = shapely.polygons(xy[area > 1e-7])
    return float(np.sum(shapely.area(shapely.intersection(faces, exclusion))))


def check_context(manifest, audit, layout):
    main = shape(audit['main_footprint'])
    buildings = audit['context']['buildings']
    assert len({row['source_id'] for row in buildings}) == len(buildings)
    source_rows = {row['id']: shape(row['geometry']) for row in layout['source_buildings']}
    envelopes = []
    for row in buildings:
        envelope = Polygon(row['full_geometry_envelope_m'])
        assert not envelope.intersects(main.buffer(.75)), (row['source_id'], 'Main protection')
        envelopes.append(envelope)
        support = row['terrain_support']
        span = support['terrain_max_z_m'] - support['terrain_min_z_m']
        assert abs(span - row['terrain_span_m']) < 1e-8
        assert abs(row['base_z_m'] - support['terrain_max_z_m'] - .025) < 1e-8
        expected = span + .125 if span > .12 else 0
        assert abs(row['foundation_height_m'] - expected) < 1e-8
        assert support['max_sample_spacing_m'] <= 8 and support['sample_count'] >= 3
        assert row['source_id'] in source_rows
    blockers = unary_union([main.buffer(.75), shape(layout['roads']).union(shape(audit['main_apron'])).buffer(.45),
                            shape(layout['rail_corridor']).buffer(.65), shape(audit['water']).buffer(.4),
                            unary_union(list(source_rows.values()) + envelopes).buffer(.3)])
    frame = shape(layout['frame'])
    tree_rows = manifest['instances'].get('SM_MPR4_Tree_Oak', [])
    trees = audit['context']['trees']
    assert len(trees) == len(tree_rows) == audit['context']['summary']['total_trees']
    by_id = {row['source_id']: row for row in tree_rows}
    assert len(by_id) == len(trees)
    for row in trees:
        actual = by_id[row['source_id']]
        assert actual['position_m'] == row['position_m']
        crown = Point(actual['position_m'][:2]).buffer(row['crown_radius_m'] + .25, quad_segs=16)
        assert frame.covers(crown), (row['source_id'], 'Tree outside source boundary')
        assert not crown.intersects(blockers), (row['source_id'], 'Tree canopy overlaps building/transport/water')
        if row['provenance'] == 'campus_green_row':
            assert shape(audit['campus_green']).covers(crown), (row['source_id'], 'Campus crown outside planted bed')
            assert .24 <= actual['scale'][0] <= .32, (row['source_id'], 'Campus tree scale')
    campus_count = sum(row['provenance'] == 'campus_green_row' for row in trees)
    assert campus_count == audit['context']['summary'].get('campus_green_trees', 0)
    roles = manifest['instance_material_roles']['SM_MPR4_Tree_Oak']
    assert roles == ['MPRR_Bark', 'MPRR_LeafMid', 'MPRR_LeafLight', 'MPRR_LeafShade']
    assert all(role in manifest['materials'] for role in roles)
    assemblies = defaultdict(set)
    for mesh, instances in manifest['instances'].items():
        for row in instances:
            assert np.isfinite(row['position_m'] + row['scale']).all()
            assert math.isfinite(row['rotation_deg'])
            assert math.isfinite(row.get('pitch_deg', 0.))
            if row.get('assembly_id'):
                assemblies[row['assembly_id']].add('tractor' if 'Tractor' in mesh else 'trailer' if 'Trailer' in mesh else mesh)
    assert all(kinds == {'tractor', 'trailer'} for kinds in assemblies.values()), ('Orphan tractor/trailer assemblies', assemblies)
    assert audit['context']['summary']['previous_completed_frame_used'] is False
    return dict(buildings=len(buildings), trees=len(trees), full_canopy_clearance=True,
                campus_green_trees=campus_count,
                rigid_building_bases=True, foundations=sum(row['foundation_height_m'] > 0 for row in buildings),
                complete_truck_assemblies=len(assemblies), tree_material_slot_order=roles,
                previous_completed_frame_used=False)


def run(args):
    manifest, audit, layout = read(OUT / 'manifest.json'), read(OUT / 'geometry_audit.json'), read(OUT / 'layout.json')
    stop = len(manifest['meshes']) if args.stop is None else args.stop
    assert 0 <= args.start < stop <= len(manifest['meshes']), 'Invalid FBX batch range'
    selected_rows = manifest['meshes'][args.start:stop]
    report['batch'] = dict(start=args.start, stop=stop, total_meshes=len(manifest['meshes']))
    report['source_validation'] = check_input_hashes(manifest, audit)
    report['context_validation'] = check_context(manifest, audit, layout)
    assert manifest['rebuild_namespace'] == '/Game/MPRWarehouse/RebuildB50B57'
    assert len({row['name'] for row in manifest['meshes']}) == len(manifest['meshes'])
    frame = shape(layout['frame'])
    main_interior = shape(audit['main_footprint']).buffer(-.025)
    blend = contained_path(manifest['blend'])
    blend_hash, manifest_hash = sha(blend), sha(OUT / 'manifest.json')
    bpy.ops.wm.open_mainfile(filepath=str(blend), load_ui=False, use_scripts=False)
    actual_names = {obj.name for obj in bpy.context.scene.objects if obj.type == 'MESH'}
    assert actual_names == {row['name'] for row in manifest['meshes']}, 'Saved Blender object set differs from manifest'
    source_colors = {}
    for index, row in enumerate(selected_rows, start=args.start):
        report['active_check'] = dict(stage='saved_blend', index=index, mesh=row['name'])
        obj = bpy.data.objects[row['name']]
        record, vertices, triangles = validate_mesh(obj, row)
        # Ground is intentionally continuous below the retained building.
        ground = row['name'].startswith(('SM_MPRR_Terrain', 'SM_MPRR_Background', 'SM_MPRR_MainApron'))
        overlap = 0. if ground else projected_overlap(vertices, triangles, main_interior)
        assert overlap < .03, (row['name'], 'New solid geometry intrudes retained main shell', overlap)
        record.update(name=row['name'], main_footprint_overlap_m2=overlap, ground_exempt=ground)
        if row.get('vertex_color_fade'):
            samples = color_samples(obj)
            source_colors[row['name']] = samples
            distance = shapely.distance(shapely.points(samples[:, :2]), frame.boundary)
            expected = np.clip(1 - distance / 24., 0, 1)
            expected = expected * expected * (3 - 2 * expected)
            assert np.max(np.abs(expected - samples[:, 3])) < 5e-5, (row['name'], 'Fade away from outer source boundary')
            record['fade_only_at_source_perimeter'] = True
        report['meshes'].append(record)
        if index % 100 == 0:
            print('MPRR_VALIDATE_SAVED', index, len(manifest['meshes']), flush=True)
    images = []
    for image in bpy.data.images:
        if image.source == 'FILE' and image.filepath:
            assert image.filepath.startswith('//'), ('Nonrelative source texture path', image.filepath)
            path = Path(bpy.path.abspath(image.filepath))
            assert path.is_file(), ('Missing source texture', path)
            images.append(dict(path=image.filepath, sha256=sha(path)))
    report['relative_textures'] = images
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for index, (row, record) in enumerate(zip(selected_rows, report['meshes']), start=args.start):
        report['active_check'] = dict(stage='fbx_import', index=index, mesh=row['name'], fbx=row['fbx'])
        fbx = contained_path(row['fbx'])
        assert sha(fbx) == row['sha256'], (row['name'], 'Export hash changed')
        bpy.ops.import_scene.fbx(filepath=str(fbx), use_custom_normals=True, colors_type='LINEAR')
        objects = [obj for obj in bpy.context.selected_objects if obj.type == 'MESH']
        assert len(objects) == 1, (row['name'], 'FBX object count', len(objects))
        obj = objects[0]
        data, _, _ = validate_mesh(obj, row, roundtrip=True)
        record['fbx'] = data
        if row.get('vertex_color_fade'):
            record['fbx_color_roundtrip'] = compare_color_samples(source_colors.pop(row['name']), color_samples(obj), row['name'])
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        for collection in (bpy.data.meshes, bpy.data.materials, bpy.data.images):
            for block in list(collection):
                if block.users == 0:
                    collection.remove(block)
        if index % 100 == 0:
            print('MPRR_VALIDATE_FBX', index, len(manifest['meshes']), flush=True)
    assert not source_colors
    assert sha(blend) == blend_hash and sha(OUT / 'manifest.json') == manifest_hash, 'Validator modified source artifacts'
    assert check_input_hashes(manifest, audit) == report['source_validation'], 'Immutable inputs changed during validation'
    report.pop('active_check', None)
    report.update(success=True, fbx_roundtrip_meshes=len(selected_rows),
                  triangles=sum(row['triangles'] for row in selected_rows),
                  manifest_sha256=manifest_hash, blend_sha256=blend_hash)


if __name__ == '__main__':
    args = arguments()
    try:
        run(args)
    except Exception:
        report['error'] = traceback.format_exc()
        print(report['error'], flush=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('MPRR_BLENDER_VALIDATION', report['success'], flush=True)
    if not report['success']:
        raise RuntimeError(report['error'])
