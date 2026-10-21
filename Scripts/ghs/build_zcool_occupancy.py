"""Export private, partly loaded rack meshes without altering source libraries.

Run in an owned background Blender process. Existing CAD rack frames and carton
geometry are rebuilt by their original builders. Only complete, selected loads
are omitted; no opaque geometry is hidden with an opacity mask.
"""
from pathlib import Path
import copy
import hashlib
import importlib.util
import json
import math
import re

import bpy


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'SourceAssets/GHS/ZcoolOccupancy'
SOURCE = ROOT / 'SourceAssets/GHS/RefinementV2/Racks/refined_rack_cargo.json'
BINDINGS = ROOT / 'Content/GHSTwinUI/data/scene-bindings.json'
BUILDER = ROOT / 'Scripts/ghs/build_refined_rack_cargo.py'
OWNER = 'ghs-zcool-occupancy-70-v1'
LOAD_NAME = re.compile(r'^Level (\d+) load (\d+)(?:\s|$)')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def allocation(groups, by_name):
    """Choose one load count per shared mesh, closest to the whole-scene target.

    The squared fractional deviation keeps individual rack specifications close
    to 70%. The first priority is the nearest representable scene-wide count.
    Small integer rounding differences are unavoidable for six-slot rack bays.
    """
    capacity = sum(g['count'] * len(by_name[g['mesh']]['cargo_stacks']) for g in groups)
    target = round(capacity * .7)
    states = {0: (0., [])}
    for group in groups:
        count = group['count']
        slots = len(by_name[group['mesh']]['cargo_stacks'])
        next_states = {}
        for previous, (cost, choices) in states.items():
            for keep in range(max(1, math.floor(.7 * slots) - 1),
                              min(slots - 1, math.ceil(.7 * slots) + 1) + 1):
                total = previous + count * keep
                next_cost = cost + count * (keep / slots - .7) ** 2
                if total not in next_states or next_cost < next_states[total][0]:
                    next_states[total] = (next_cost, choices + [keep])
        states = next_states
    occupied = min(states, key=lambda total: (abs(total - target), states[total][0]))
    assert abs(occupied / capacity - .7) <= .005, (capacity, target, occupied)
    return capacity, occupied, states[occupied][1]


def run():
    manifest_path = OUT / 'zcool_occupancy.json'
    if manifest_path.exists():
        assert read(manifest_path).get('owner') == OWNER, 'Unrelated destination exists'
    source_hashes = {str(p.relative_to(ROOT)): digest(p) for p in (SOURCE, BINDINGS, BUILDER)}
    originals = read(SOURCE)
    by_name = {m['name']: m for m in originals['meshes']}
    groups = sorted((g for g in read(BINDINGS)['groups']
                     if g['mesh'].startswith('SM_GHS_V2Rack_') and not g['mesh'].endswith('_Occ70')),
                    key=lambda g: g['actor'])
    assert groups and all(g['count'] == len(g['instances']) for g in groups)
    capacity, occupied, counts = allocation(groups, by_name)
    spec = importlib.util.spec_from_file_location('zcool_original_rack_builder', BUILDER)
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    builder.cad.OUT = OUT
    builder.cad.prepare()
    exported = []
    for group, keep_count in zip(groups, counts):
        old = by_name[group['mesh']]
        current = {key: copy.deepcopy(value) for key, value in old.items()
                   if key not in builder.GENERATED_FIELDS}
        current['name'] = old['name'] + '_Occ70'
        current['source_mesh'] = old['name']
        collection, stacks = builder.build(current)
        rank = lambda stack: hashlib.sha256(
            ('ghs-occupied-70:' + old['name'] + ':L%d:C%d' % (stack['level'], stack['column']))
            .encode('utf-8')).hexdigest()
        kept = {(s['level'], s['column']) for s in sorted(stacks, key=rank)[:keep_count]}
        before_frame = {o.name for o in collection.objects if not LOAD_NAME.match(o.name)}
        removed_parts = 0
        for obj in list(collection.objects):
            match = LOAD_NAME.match(obj.name)
            if match and tuple(map(int, match.groups())) not in kept:
                bpy.data.objects.remove(obj, do_unlink=True)
                removed_parts += 1
        after_frame = {o.name for o in collection.objects if not LOAD_NAME.match(o.name)}
        assert before_frame == after_frame and removed_parts > 0
        visible_slots = {tuple(map(int, match.groups())) for obj in collection.objects
                         if (match := LOAD_NAME.match(obj.name))}
        assert visible_slots == kept and len(kept) == keep_count
        result = builder.cad.export_asset(current, collection)
        frame_roles = ['Upright', 'Beam', 'Braces']
        assert builder.signature(result['solid_boxes'], frame_roles) == builder.signature(old['solid_boxes'], frame_roles)
        selected_stacks = [s for s in stacks if (s['level'], s['column']) in kept]
        cartons = [part for part in result['solid_boxes'] if part['role'] == 'Cargo']
        assert len(cartons) == sum(s['carton_count'] for s in selected_stacks)
        assert result['slot_roles'] == ['Upright', 'Beam', 'Braces', 'Pallet', 'Cargo', 'CargoEdges', 'Detail']
        result.update(source_mesh=old['name'], source_actor=group['actor'],
                      instance_count=group['count'], capacity_per_instance=len(stacks),
                      occupied_per_instance=keep_count, cargo_stacks=selected_stacks,
                      empty_stacks=[s for s in stacks if (s['level'], s['column']) not in kept],
                      original_cargo_stacks=stacks, carton_count=len(cartons),
                      original_triangles=old['triangles'],
                      removed_parts=removed_parts, verified_frame_unchanged=True)
        assert result['triangles'] < old['triangles']
        exported.append(result)
        print('ZCOOL_OCCUPANCY_EXPORTED', result['name'], keep_count, '/', len(stacks),
              'triangles', result['triangles'], flush=True)
        # Keep the background process bounded: these copies are already exported.
        for obj in list(collection.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(collection)
    assert sum(m['instance_count'] * m['occupied_per_instance'] for m in exported) == occupied
    assert sum(m['instance_count'] * m['capacity_per_instance'] for m in exported) == capacity
    for relative, value in source_hashes.items():
        assert digest(ROOT / relative) == value, 'Source changed: ' + relative
    report = dict(owner=OWNER, success=True, source_hashes=source_hashes,
                  target_occupancy=.7, rack_instance_count=sum(g['count'] for g in groups),
                  rack_capacity=capacity, rack_occupied=occupied, rack_empty=capacity - occupied,
                  rack_occupancy=occupied / capacity, additional_hism_groups=0,
                  all_frames_unchanged=True, source_assets_unchanged=True,
                  meshes=exported)
    manifest_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('ZCOOL_OCCUPANCY_SUCCESS', json.dumps({k: v for k, v in report.items()
                                             if k not in ('meshes', 'source_hashes')}), flush=True)


if __name__ == '__main__':
    run()
