"""Build V2 CAD racks with realistic separate cartons in background Blender.

The original frame builder is reused unchanged. All previous mapping keys and
seven material roles remain compatible, with independent V2 FBX/blend output.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import importlib.util
import json
import math
import re
import sys

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'SourceAssets/GHS/RefinementV2/Racks'
SOURCE = ROOT / 'SourceAssets/GHS/RackSpecs/Models/cad_rack_models.json'
FRAME_SOURCE = ROOT / 'Scripts/ghs/build_cad_rack_models.py'
MODULE_SPEC = importlib.util.spec_from_file_location('original_cad_rack', FRAME_SOURCE)
cad = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(cad)
cad.OUT = OUT

RULES = {
    'carton_width_m': .45,
    'carton_depth_m': .55,
    'carton_height_options_m': [.36, .38, .40, .42],
    'cartons_per_layer': 4,
    'horizontal_clear_gap_m': .020,
    'layer_shift_max_m': .012,
    'edge_radius_m': .004,
    'vertical_gap_m': 0.0,
    'stack_contact': 'Cartons rest on each other; the bevel creates a visible layer seam without floating boxes.',
    'B': 'One layer of 0.36 or 0.38 m cartons per pallet in the narrow CAD shelf interval.',
    'A_D1': 'Four 0.40 or 0.42 m carton layers, with every fourth pallet having three layers.',
    'C_D2': 'Three 0.38 or 0.40 m carton layers per pallet.',
    'top_clearance': 'Do not fill the CAD envelope. Verify every stack is below the next beam bottom (or upright top for the uppermost level).',
    'pallet_dimensions': 'Original CAD 1.016 x 1.2192 x 0.123952 m; separate runners, blocks and boards preserve fork openings.',
}
GENERATED_FIELDS = {
    'fbx', 'slots', 'slot_roles', 'origin_m', 'bounds_m', 'source_parts',
    'vertices', 'triangles', 'polygons', 'solid_boxes', 'fbx_sha256',
}


def plane(name, points, role):
    return cad.mesh(name, points, [(0, 1, 2, 3)], role)


def pallet(name, x, base, spec):
    width, depth = spec['cargo_width_m'], spec['cargo_depth_m']
    ph = spec['pallet_height_m']
    deck = spec['pallet_deck_thickness_m']
    rw = spec['pallet_runner_width_m']
    spacer = ph - 2 * deck
    for sx in [-1, 0, 1]:
        xx = x + sx * (width * .5 - rw * .5)
        cad.box(name + ' pallet runner', (xx, 0, base + deck * .5), (rw, depth, deck), 'Pallet')
        for sy in [-1, 0, 1]:
            cad.box(name + ' pallet block', (xx, sy * (depth * .5 - .08), base + deck + spacer * .5),
                    (rw, .12, spacer), 'Pallet')
    for i in range(5):
        y = -(depth - .13) * .5 + i * (depth - .13) / 4
        cad.box(name + ' pallet deck', (x, y, base + ph - deck * .5), (width, .13, deck), 'Pallet')


def carton(name, center, size):
    x, y, z = center
    w, d, h = size
    obj = cad.box(name, center, size, 'Cargo', RULES['edge_radius_m'])
    obj['carton_dimensions_m'] = list(size)
    obj['unscaled_rigid_carton'] = True
    # Flat tape and small shipping labels give scale at six triangles/box.
    # They are flush with their own box, never long strips across the stack.
    front = y - d * .5 - .0004
    tape = .024
    plane(name + ' front packing tape',
          [(x - tape / 2, front, z - h / 2 + .006), (x + tape / 2, front, z - h / 2 + .006),
           (x + tape / 2, front, z + h / 2 - .006), (x - tape / 2, front, z + h / 2 - .006)], 'CargoEdges')
    top = z + h * .5 + .0004
    plane(name + ' top packing tape',
          [(x - tape / 2, y - d / 2 + .006, top), (x + tape / 2, y - d / 2 + .006, top),
           (x + tape / 2, y + d / 2 - .006, top), (x - tape / 2, y + d / 2 - .006, top)], 'CargoEdges')
    lx, lz = x + w * .25, z + h * .15
    plane(name + ' shipping label',
          [(lx - .039, front - .0001, lz - .026), (lx + .039, front - .0001, lz - .026),
           (lx + .039, front - .0001, lz + .026), (lx - .039, front - .0001, lz + .026)], 'Detail')


def layer_rule(spec, level, column):
    code = spec['spec_type']
    if code == 'B':
        return 1, (.36 if (level + column) % 2 == 0 else .38)
    if code in ['A', 'D1']:
        return (3 if (level * 3 + column) % 4 == 2 else 4), (.40 if (level + column) % 2 == 0 else .42)
    return 3, (.38 if (level + column) % 2 == 0 else .40)


def build(spec):
    collection = bpy.data.collections.new(spec['name'])
    bpy.context.scene.collection.children.link(collection)
    cad.COLLECTION = collection
    collection['cad_specification'] = spec['code']
    collection['cad_levels_including_floor'] = len(spec['cargo_base_z_m'])
    collection['refinement'] = 'separate fixed-size cartons; exact original CAD frame'
    cad.build_frame(spec)
    stacks = []
    for level, (base, envelope) in enumerate(zip(spec['cargo_base_z_m'], spec['cargo_envelope_heights_m'])):
        beam_bottoms = [z - h for z, h in zip(spec['beam_top_z_m'], spec['beam_heights_m']) if z - h > base + .01]
        overhead = min(beam_bottoms) if beam_bottoms else spec['upright_height_m']
        for column, x in enumerate(spec['cargo_center_x_m']):
            name = 'Level %02d load %d' % (level + 1, column + 1)
            pallet(name, x, base, spec)
            layers, h = layer_rule(spec, level, column)
            stack_top = base + spec['pallet_height_m'] + layers * h
            assert stack_top <= base + envelope - .035, (spec['name'], 'CAD envelope overfilled')
            assert overhead - stack_top >= .10, (spec['name'], 'beam clearance', overhead - stack_top)
            stack = dict(level=level + 1, column=column + 1, base_z_m=base, pallet_center_x_m=x,
                         carton_size_m=[.45, .55, h], layers=layers, cartons_per_layer=4,
                         carton_count=layers * 4, stack_top_z_m=stack_top,
                         overhead_z_m=overhead, top_clearance_m=overhead - stack_top,
                         cad_envelope_unused_height_m=base + envelope - stack_top,
                         layer_shifts_m=[])
            for layer in range(layers):
                dx = .012 if layer % 2 else -.012
                dy = .008 if (layer + column) % 2 else -.008
                stack['layer_shifts_m'].append([dx, dy])
                for ix in [-1, 1]:
                    for iy in [-1, 1]:
                        xx = x + ix * (.45 + .020) * .5 + dx
                        yy = iy * (.55 + .020) * .5 + dy
                        zz = base + spec['pallet_height_m'] + (layer + .5) * h
                        assert abs(xx - x) + .225 <= spec['cargo_width_m'] * .5
                        assert abs(yy) + .275 <= spec['cargo_depth_m'] * .5
                        carton(name + ' carton L%d X%d Y%d' % (layer + 1, ix, iy), (xx, yy, zz), (.45, .55, h))
            stacks.append(stack)
    return collection, stacks


def signature(parts, roles):
    values = []
    for part in parts:
        if part['role'] in roles:
            values.append((re.sub(r'\.\d+$', '', part['name']), part['role'],
                           tuple(round(x, 5) for x in part['center_m']),
                           tuple(round(x, 5) for x in part['size_m'])))
    return sorted(values)


def verify_export(result, source, stacks):
    assert result['slot_roles'] == ['Upright', 'Beam', 'Braces', 'Pallet', 'Cargo', 'CargoEdges', 'Detail']
    assert result['mapping_key'] == source['mapping_key']
    # Compare the complete physical frame and pallet geometry to the old library.
    frame_same = signature(result['solid_boxes'], ['Upright', 'Beam', 'Braces']) == signature(source['solid_boxes'], ['Upright', 'Beam', 'Braces'])
    pallets_same = signature(result['solid_boxes'], ['Pallet']) == signature(source['solid_boxes'], ['Pallet'])
    assert frame_same, (result['name'], 'CAD frame changed')
    assert pallets_same, (result['name'], 'pallet geometry changed')
    cartons = [p for p in result['solid_boxes'] if p['role'] == 'Cargo']
    assert len(cartons) == sum(s['carton_count'] for s in stacks)
    ratios = [max(p['size_m']) / min(p['size_m']) for p in cartons]
    assert max(ratios, default=0) < 1.529
    result.update(cargo_stacks=stacks, carton_count=len(cartons),
                  cargo_layers_rule=RULES[result['spec_type'] if result['spec_type'] == 'B' else ('A_D1' if result['spec_type'] in ['A', 'D1'] else 'C_D2')],
                  maximum_carton_aspect_ratio=max(ratios, default=0),
                  minimum_stack_top_clearance_m=min((s['top_clearance_m'] for s in stacks), default=None),
                  verified_frame_matches_source=frame_same, verified_pallets_match_source=pallets_same,
                  preserved_frame_dimensions_m=[result['frame_width_m'], result['frame_depth_m'], result['upright_height_m']],
                  library_only_narrow_empty_variant=not bool(result['cargo_center_x_m']),
                  sha=result['fbx_sha256'], bounds=result['bounds_m'])


def position_collection(collection, offset):
    old = Vector(collection.get('library_board_offset_m', [0, 0, 0]))
    delta = Vector(offset) - old
    for obj in collection.objects:
        obj.location += delta
    collection['library_board_offset_m'] = list(offset)


def setup_scene(collections):
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 20
    scene.cycles.use_denoising = True
    scene.render.resolution_percentage = 100
    scene.world.color = (.12, .12, .12)
    scene.view_settings.view_transform = 'AgX'
    bpy.ops.mesh.primitive_plane_add(size=160, location=(0, 0, -.025))
    floor = bpy.context.object
    floor.name = 'Preview floor - not exported'
    material = bpy.data.materials.new('Preview matte floor')
    material.diffuse_color = (.18, .20, .24, 1)
    floor.data.materials.append(material)
    for loc, power, size in [((1, -9, 12), 5500, 10), ((-8, 0, 9), 4000, 8), ((8, 5, 11), 5500, 8)]:
        bpy.ops.object.light_add(type='AREA', location=loc)
        light = bpy.context.object
        light.name = 'Preview light - not exported'
        light.data.energy = power
        light.data.shape = 'DISK'
        light.data.size = size
        light.rotation_euler = (Vector((0, 0, 3)) - light.location).to_track_quat('-Z', 'Y').to_euler()
    bpy.ops.object.camera_add(location=(6, -10, 5))
    camera = bpy.context.object
    camera.name = 'Preview camera - not exported'
    camera.data.type = 'ORTHO'
    scene.camera = camera
    scene.render.image_settings.file_format = 'PNG'
    return camera


def render_view(camera, path, position, target, ortho, resolution):
    camera.location = position
    camera.rotation_euler = (Vector(target) - camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera.data.ortho_scale = ortho
    bpy.context.scene.render.resolution_x, bpy.context.scene.render.resolution_y = resolution
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def previews(collections, specs, camera):
    paths = []
    for code, center, scale in [('A', 2.05, 5.1), ('B', 1.9, 4.8)]:
        for collection, spec in zip(collections, specs):
            show = spec['spec_type'] == code and spec['canonical'] and not spec['pass_variant']
            collection.hide_render = not show
            if show:
                position_collection(collection, (0, 0, 0))
        path = OUT / ('v2_rack_%s_carton_closeup.png' % code)
        render_view(camera, path, (5.0, -9, center + 2.7), (0, 0, center), scale, (1600, 1500))
        paths.append(str(path))
    canonical = [(c, s) for c, s in zip(collections, specs) if s['canonical'] and not s['pass_variant']]
    for collection in collections:
        collection.hide_render = True
    for i, (collection, spec) in enumerate(canonical):
        collection.hide_render = False
        position_collection(collection, ((i - 2) * 4.8, 0, 0))
    path = OUT / 'v2_rack_library_preview.png'
    render_view(camera, path, (12, -43, 20), (0, 0, 4.25), 27, (2400, 1400))
    paths.append(str(path))
    return paths


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--preview', action='store_true')
    parser.add_argument('--extra-specs', help='Optional JSON {models: [...]} containing additional old-compatible source mesh specifications')
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    args = parser.parse_args(argv)
    source = json.loads(SOURCE.read_text(encoding='utf-8'))
    original_meshes = list(source['meshes'])
    if args.extra_specs:
        original_meshes.extend(json.loads(Path(args.extra_specs).read_text(encoding='utf-8'))['models'])
    specs = []
    for old in original_meshes:
        spec = {k: copy.deepcopy(v) for k, v in old.items() if k not in GENERATED_FIELDS}
        spec['replaces_mesh'] = old['name']
        spec['name'] = old['name'].replace('SM_GHS_CADRack_', 'SM_GHS_V2Rack_')
        specs.append(spec)
    cad.prepare()
    collections, exports = [], []
    for spec, old in zip(specs, original_meshes):
        collection, stacks = build(spec)
        result = cad.export_asset(spec, collection)
        verify_export(result, old, stacks)
        collections.append(collection)
        exports.append(result)
        print('V2_RACK_EXPORTED', result['name'], result['triangles'], result['carton_count'], flush=True)
    for index, collection in enumerate(collections):
        position_collection(collection, ((index % 8 - 3.5) * 4.8, (index // 8) * 4, 0))
    camera = setup_scene(collections)
    preview_paths = previews(collections, specs, camera) if args.preview else []
    # Return all editable models to an evenly spaced board, preserving preview
    # camera and recorded PNGs as independent render artifacts.
    for index, collection in enumerate(collections):
        collection.hide_render = False
        position_collection(collection, ((index % 8 - 3.5) * 4.8, (index // 8) * 4, 0))
    camera.location = (16, -38, 23)
    camera.rotation_euler = (Vector((0, 7, 4)) - camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera.data.ortho_scale = 45
    blend = OUT / 'refined_rack_cargo.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    summary = dict(source_manifest=str(SOURCE), source_manifest_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                   original_frame_builder=str(FRAME_SOURCE), original_frame_builder_sha256=hashlib.sha256(FRAME_SOURCE.read_bytes()).hexdigest(),
                   units='metres', axis='Z up; X across rack; Y rack depth; FBX -Y forward',
                   mesh_origin='centred at floor', blend=str(blend), previews=preview_paths,
                   cargo_modeling_rules=RULES, meshes=exports,
                   verification=dict(mesh_count=len(exports), mapping_key_count=len(set(e['mapping_key'] for e in exports)),
                       all_original_mapping_keys_preserved={e['mapping_key'] for e in source['meshes']}.issubset({e['mapping_key'] for e in exports}),
                       all_frames_unchanged=all(e['verified_frame_matches_source'] for e in exports),
                       all_pallets_unchanged=all(e['verified_pallets_match_source'] for e in exports),
                       maximum_carton_aspect_ratio=max(e['maximum_carton_aspect_ratio'] for e in exports),
                       maximum_mesh_triangles=max(e['triangles'] for e in exports),
                       minimum_stack_top_clearance_m=min(e['minimum_stack_top_clearance_m'] for e in exports if e['minimum_stack_top_clearance_m'] is not None)))
    manifest = OUT / 'refined_rack_cargo.json'
    manifest.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')
    print('V2_RACK_COMPLETE', json.dumps(summary['verification']), flush=True)


if __name__ == '__main__':
    main()
