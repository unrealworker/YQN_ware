"""Build complete rack cargo with UV1 slot IDs; run in owned background Blender.

Existing source libraries, double-pallet geometry and saved UE maps are untouched.
The material importer copies current scene materials and changes only the mask.
"""
from pathlib import Path
import copy
import hashlib
import importlib.util
import json
import math
import re
import sys

import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Scripts/ghs'))
from storage_capacity_rules import MULTIPLIER, OFFSET, slot_boxes

OUT = ROOT / 'SourceAssets/GHS/StorageCapacity'
RUNTIME = ROOT / 'Content/GHSTwinUI/data/storage-capacity.json'
OWNER = 'ghs-complete-storage-capacity-v1'
LOAD = re.compile(r'^Level (\d+) load (\d+)(?:\s|$)')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_fbx(row):
    """Reimport the actual output; every cargo triangle owns exactly one slot."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=row['fbx'])
    imported = set(bpy.data.objects) - before
    seen = set()
    frame_faces = 0
    for obj in imported:
        if obj.type != 'MESH':
            continue
        assert len(obj.data.uv_layers) == 2, (row['name'], 'Missing capacity channel')
        uv = obj.data.uv_layers[1].data
        for face in obj.data.polygons:
            values = [uv[index].uv.x for index in face.loop_indices]
            assert max(values) - min(values) < 1.e-5, (row['name'], 'Partial cargo triangle')
            value = values[0]
            assert abs(value - round(value)) < 1.e-5
            if value < 0:
                frame_faces += 1
            else:
                seen.add(round(value))
    assert seen == set(range(len(row['cargo_stacks']))), (row['name'], seen)
    assert frame_faces > 0
    for obj in imported:
        bpy.data.objects.remove(obj, do_unlink=True)
    return dict(complete_uv_slot_count=len(seen), retained_frame_faces=frame_faces,
                all_faces_have_constant_integer_slot=True, reimported_fbx_verified=True)


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / 'storage_capacity.json'
    if manifest_path.exists():
        assert read(manifest_path)['owner'] == OWNER
    source = ROOT / 'SourceAssets/GHS/RefinementV2/Racks/refined_rack_cargo.json'
    bindings = ROOT / 'Content/GHSTwinUI/data/scene-bindings.json'
    builder_path = ROOT / 'Scripts/ghs/build_refined_rack_cargo.py'
    floor_source = ROOT / 'SourceAssets/GHS/DoublePallet/double_pallet_storage.json'
    source_hashes = {str(p.relative_to(ROOT)): sha(p) for p in [source, bindings, builder_path, floor_source]}
    by_name = {row['name']: row for row in read(source)['meshes']}
    full_groups = [g for g in read(bindings)['groups'] if not g['mesh'].endswith('_Occ70')]
    rack_groups = sorted([g for g in full_groups if g['mesh'].startswith('SM_GHS_V2Rack_')], key=lambda g: g['actor'])
    floor_groups = sorted([g for g in full_groups if g['mesh'].startswith('SM_GHS_Presentation_Cargo')], key=lambda g: g['actor'])
    assert len(rack_groups) == 10 and len(floor_groups) == 3
    assert len({g['actor'] for g in rack_groups + floor_groups}) == 13
    module = importlib.util.spec_from_file_location('capacity_rack_builder', builder_path)
    builder = importlib.util.module_from_spec(module)
    module.loader.exec_module(builder)
    builder.cad.OUT = OUT
    builder.cad.prepare()
    mesh_rows, runtime_meshes, runtime_groups = [], [], []
    rack_total = 0
    for group in rack_groups:
        original = by_name[group['mesh']]
        current = {k: copy.deepcopy(v) for k, v in original.items() if k not in builder.GENERATED_FIELDS}
        current['name'] = original['name'] + '_Capacity'
        collection, stacks = builder.build(current)
        slots = {(stack['level'], stack['column']): i for i, stack in enumerate(stacks)}
        for obj in collection.objects:
            assert obj.type == 'MESH'
            match = LOAD.match(obj.name)
            slot = slots[tuple(map(int, match.groups()))] if match else -1
            first = obj.data.uv_layers.new(name='UVMap')
            capacity = obj.data.uv_layers.new(name='CapacitySlot')
            for loop in capacity.data:
                loop.uv = (float(slot), 0.)
            obj.data.uv_layers.active_index = 0
        result = builder.cad.export_asset(current, collection)
        assert builder.signature(result['solid_boxes'], ['Upright', 'Beam', 'Braces']) == builder.signature(original['solid_boxes'], ['Upright', 'Beam', 'Braces'])
        assert result['triangles'] == original['triangles'], (result['name'], 'Full source geometry was changed')
        result.update(source_mesh=original['name'], cargo_stacks=stacks,
                      slots=slot_boxes(stacks, original['cargo_width_m'], original['cargo_depth_m']),
                      kind='rack', complete_source_geometry=True, steel_unchanged=True)
        result['geometry_verification'] = verify_fbx(result)
        runtime_meshes.append({k: result[k] for k in ['name', 'source_mesh', 'kind', 'cargo_width_m', 'cargo_depth_m', 'cargo_stacks', 'slots']})
        runtime_groups.append(dict(actor=group['actor'], mesh=result['name'], source_mesh=original['name'], kind='rack',
                                   count=group['count'], base_slot=rack_total, slots_per_instance=len(stacks)))
        rack_total += group['count'] * len(stacks)
        mesh_rows.append(result)
        for obj in list(collection.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(collection)
        print('CAPACITY_RACK_EXPORTED', result['name'], len(stacks), result['triangles'], flush=True)
    floor_by_name = {row['name']: row for row in read(floor_source)['meshes']}
    floor_total = 0
    for group in floor_groups:
        original = floor_by_name[group['mesh']]
        assert original['pallet_count'] == 2
        runtime_meshes.append(dict(name=original['name'], source_mesh=original['name'], kind='floor', slots=[],
                                   pallet_count=2, pallet_base_z_m=original['pallet_base_z_m']))
        runtime_groups.append(dict(actor=group['actor'], mesh=original['name'], source_mesh=original['name'], kind='floor',
                                   count=group['count'], base_slot=floor_total, slots_per_instance=1))
        floor_total += group['count']
    assert (rack_total, floor_total) == (25056, 7530)
    assert all(math.gcd(MULTIPLIER, n) == 1 and n * MULTIPLIER + OFFSET < 2**24 for n in [rack_total, floor_total])
    runtime = dict(owner=OWNER, rack_total_slots=rack_total, floor_total_slots=floor_total,
                   multiplier=MULTIPLIER, offset=OFFSET, groups=runtime_groups, meshes=runtime_meshes)
    RUNTIME.write_text(json.dumps(runtime, ensure_ascii=False, indent=2), encoding='utf-8')
    for path, digest in source_hashes.items():
        assert sha(ROOT / path) == digest, 'Source was modified: ' + path
    report = dict(owner=OWNER, success=True, source_hashes=source_hashes, meshes=mesh_rows,
                  runtime_metadata=str(RUNTIME), runtime_metadata_sha256=sha(RUNTIME),
                  rack_total_slots=rack_total, floor_total_groups=floor_total,
                  steel_unchanged=True, full_geometry_not_scaled_occ70=True,
                  floor_double_pallet_assets_unchanged=True)
    manifest_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('STORAGE_CAPACITY_BUILD_SUCCESS', rack_total, floor_total, flush=True)


if __name__ == '__main__':
    run()
