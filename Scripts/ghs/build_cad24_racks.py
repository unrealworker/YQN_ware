"""Build CAD 2.4 rack geometry and slot metadata using the original GHS steel and carton profiles."""
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Scripts/ghs'))
import build_refined_rack_cargo as style
from build_storage_capacity import LOAD, verify_fbx
from storage_capacity_rules import slot_boxes

DATA = ROOT / 'SourceAssets/GHS/CAD24'
OUT = ROOT / 'Saved/GHS_CAD24/Models'


def build_mesh(variant, layout, rack):
    heights = layout['support_z_m']
    first_level = {'A_PASS':3, 'B_PASS':7, 'C_PASS':4}.get(variant, 1)
    physical_levels = list(range(first_level, first_level + len(heights)))
    assert len(physical_levels) == len(heights) and heights == sorted(set(heights))
    width = rack['physical_span_m']
    depth = rack['physical_depth_m']
    post = layout.get('post_width_m', .0762)
    clear = width - 2 * post
    count = layout.get('columns', 3)
    centers = [(i - (count - 1) / 2) * clear / count for i in range(count)]
    height = layout['post_height_m']
    beams = [z for z in heights if z > .001]
    thickness = layout.get('beam_height_m', .1524 if rack['spec_type'] != 'B' else .0762)
    mesh = 'SM_GHS_V2Rack_CAD24_' + variant
    spec = dict(name=mesh + '_Capacity', code=variant, clear_width_m=clear, frame_width_m=width,
                frame_depth_m=depth, upright_height_m=height, cargo_width_m=1.016, cargo_depth_m=1.2192,
                pallet_height_m=.123952, pallet_deck_thickness_m=.0254, pallet_runner_width_m=.1016,
                beam_top_z_m=beams, beam_heights_m=[thickness] * len(beams), cargo_center_x_m=centers)
    group = bpy.data.collections.new(mesh)
    bpy.context.scene.collection.children.link(group)
    style.cad.COLLECTION = group
    style.cad.build_frame(spec)
    stacks = []
    # The B elevation shows a top rail at L12. The bay schedule assigns pallet storage through L11.
    occupied_levels = heights[:-1] if variant in ('B', 'B_PASS') else heights
    for level, base in enumerate(occupied_levels):
        clearance = heights[level + 1] - thickness - base if level + 1 < len(heights) else height - base
        for col, x in enumerate(centers):
            name = 'Level %02d load %d' % (level + 1, col + 1)
            style.pallet(name, x, base, spec)
            layers, box_h = style.layer_rule({'spec_type':rack['spec_type']}, level, col)
            layers = min(layers, math.floor((clearance - spec['pallet_height_m'] - .04) / box_h))
            assert layers >= 1, (variant, clearance, box_h)
            for layer in range(layers):
                dx = .012 if layer % 2 else -.012
                dy = .008 if (layer + col) % 2 else -.008
                for sx in [-1, 1]:
                    for sy in [-1, 1]:
                        style.carton(name + ' carton', (x + sx * .235 + dx, sy * .285 + dy,
                            base + spec['pallet_height_m'] + (layer + .5) * box_h), (.45, .55, box_h))
            stacks.append(dict(level=level+1, column=col+1, physical_level=physical_levels[level], base_z_m=base,
                pallet_center_x_m=x, stack_top_z_m=base + spec['pallet_height_m'] + layers * box_h))
    slot_by_lc = {(s['level'], s['column']): i for i,s in enumerate(stacks)}
    for obj in group.objects:
        match = LOAD.match(obj.name)
        index = slot_by_lc[tuple(map(int, match.groups()))] if match else -1
        obj.data.uv_layers.new(name='UVMap')
        layer = obj.data.uv_layers.new(name='CapacitySlot')
        for uv in layer.data:
            uv.uv = (index, 0.)
        obj.data.uv_layers.active_index = 0
    spec['cargo_base_z_m'] = [s['base_z_m'] for s in stacks]
    spec['cargo_envelope_heights_m'] = [s['stack_top_z_m'] - s['base_z_m'] for s in stacks]
    full = style.cad.export_asset(spec, group)
    keep = ('name','fbx','fbx_sha256','triangles','bounds_m','slot_roles','cargo_width_m','cargo_depth_m')
    row = {k:full[k] for k in keep}
    row.update(kind='rack', source_mesh=mesh, variant=variant, cargo_stacks=stacks,
               slots=slot_boxes(stacks, spec['cargo_width_m'], spec['cargo_depth_m']))
    for slot, stack in zip(row['slots'], stacks):
        slot['physical_level'] = stack['physical_level']
    verify_fbx(row)
    for obj in list(group.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.collections.remove(group)
    return row


def main():
    source = DATA / 'racks.json'
    cad = json.loads(source.read_text(encoding='utf8'))
    OUT.mkdir(parents=True, exist_ok=True)
    style.cad.OUT = OUT
    style.cad.prepare()
    rows = []
    for variant in sorted({r['variant'] for r in cad['racks']}):
        subset = [r for r in cad['racks'] if r['variant'] == variant]
        dimensions = {(round(r['physical_span_m'],4), round(r['physical_depth_m'],4)) for r in subset}
        assert len(dimensions) == 1, (variant, dimensions)
        rows.append(build_mesh(variant, cad['catalog'][variant], subset[0]))
        print('CAD24 mesh', variant, len(rows[-1]['slots']), flush=True)
    (OUT / 'meshes.json').write_text(json.dumps(dict(cad_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        meshes=rows), ensure_ascii=False), encoding='utf8')


if __name__ == '__main__':
    main()
