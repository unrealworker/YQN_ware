"""Extract installed GHS bays, floor footprints and dimensioned elevations from the October plan."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Scripts/_vendor/cad'))
import ezdxf
from ezdxf.math import Matrix44

INCH = 0.0254
TARGETS = {'RACK_42D_144B', 'RACK_60D_144B', 'FL_PALLET_48W_40D_STD'}
DEFAULT_SOURCE = Path('D:/EdgeDownload/平面布局图_GHS_2.4_20261010_整仓规划图.dxf')
DEFAULT_OUTPUT = ROOT / 'SourceAssets/GHS/CAD24/racks.json'

# Dimension endpoints supply the floor datum and upright height. The long
# horizontal edges on each cited beam INSERT supply its actual supporting face.
# The pass-through section has its own beam layout and leaves the floor clear.
DETAILS = {
    'A': ('3F121A', '3F1218', True, '3F11EA 3F167F 3F169C'),
    'A_PASS': ('3F121A', '3F1219', False, '3F16DB 3F16D9'),
    'A1': ('3F0218', '3F0272', True, '3F0267 3F02CC 3F02E9'),
    'B': ('3F12A0', '3F12DF', True, '3F13DD 3F13F9 3F1415 3F1431 3F144D 3F1469 3F1485 3F14A1 3F14BD 3F14D9 3F14F5'),
    'B_PASS': ('3F12A0', '3F12DF', False, '3F152F 3F154B 3F1567 3F1583 3F159F 3F15BB'),
    'C': ('3F122D', '3F1282', True, '3F1281 3F15E3 3F1604 3F1620'),
    'C_PASS': ('3F122D', '3F1283', False, '3F1642 3F165E'),
    'D1': ('3F1345', '3F186C', False, '3F18A6 3F18A5'),
}


def metres(inches):
    return round(inches * INCH, 6)


def elevation_catalog(doc):
    catalog = {}
    for variant, (label_id, dimension_id, floor_storage, beam_ids) in DETAILS.items():
        dimension = doc.entitydb[dimension_id]
        floor = min(dimension.dxf.defpoint2.y, dimension.dxf.defpoint3.y)
        supports = [0] if floor_storage else []
        for handle in beam_ids.split():
            edges = [
                line.dxf.start.y for line in doc.entitydb[handle].virtual_entities()
                if line.dxftype() == 'LINE'
                and 135 < abs(line.dxf.start.x - line.dxf.end.x) < 145
                and abs(line.dxf.start.y - line.dxf.end.y) < 1e-4
            ]
            if len(edges) < 2:
                raise ValueError(f'Missing beam faces in {handle}')
            supports.append(metres(max(edges) - floor))
        if supports != sorted(set(supports)):
            raise ValueError(f'Invalid beam order in elevation {variant}')
        catalog[variant] = {
            'post_height_m': metres(dimension.get_measurement()), 'support_z_m': supports,
            'beam_height_m': metres(3 if variant.startswith('B') else 6),
            'elevation_label': doc.entitydb[label_id].plain_text(),
            'source_handles': [label_id, dimension_id, *beam_ids.split()]
        }
    return catalog


def placed_blocks(doc, layout, parent, path=()):
    for insert in layout.query('INSERT'):
        instances = insert.multi_insert() if insert.mcount > 1 else [insert]
        for index, item in enumerate(instances):
            transform = Matrix44.chain(item.matrix44(), parent)
            handle = insert.dxf.handle
            chain = (*path, f'{handle}-{index}' if insert.mcount > 1 else handle)
            if item.dxf.name in TARGETS:
                yield item, transform, chain
            else:
                yield from placed_blocks(doc, doc.blocks[item.dxf.name], transform, chain)


def cad_registration(doc):
    previous = json.loads((ROOT / 'SourceAssets/GHS/cad_layout.json').read_text(encoding='utf8'))
    # The R02-15 west bay has the same origin in both floor plans. Independently
    # verify this registration against every physical 10" x 10" pillar center.
    old = json.loads((ROOT / 'SourceAssets/GHS/RackSpecs/cad_plan_mapping.json').read_text(encoding='utf8'))
    anchor = next(r for r in old['source_rack_inserts'] if r['row_code'] == 'R02' and int(r['bay_sequence']) == 15)
    current = doc.entitydb['3F34CB']
    if (current.get_attrib_text('BLOCK_CODE'), current.get_attrib_text('SEQ')) != ('R02', '15'):
        raise ValueError('Expected matching R02-15 registration reference')
    shift = [anchor['physical_origin_dxf_xy'][i] - current.dxf.insert[i] for i in (0, 1)]
    origin = [n - delta for n, delta in zip(previous['origin_dxf_xy'], shift)]
    columns = [row['position_m'] for row in previous['columns']]
    residuals = []
    for pillar in doc.modelspace().query('INSERT[name=="PILLAR"]'):
        center = pillar.matrix44().transform((5, 5, 0))
        plan = [metres(center[i] - origin[i]) for i in (0, 1)]
        residuals.append(min(math.dist(plan, col) for col in columns))
    if not residuals or max(residuals) > .001:
        raise ValueError(f'Building column registration failed: {residuals}')
    return origin, {'origin_dxf_inches': origin, 'translation_to_old_dxf_inches': shift,
                    'matched_pillars': len(residuals), 'max_pillar_error_m': round(max(residuals), 7)}


def variant_for(entity, attrs):
    codes = ' '.join(attrs[f'BEAM_CODE_0{n}'] for n in range(1, 5))
    color = entity.dxf.color
    if color == 4 and not codes.strip():
        return 'D1'
    if color == 3 and 'p85b' in codes:
        return 'A1'  # green -24" cut-off, four-position A1 detail
    if 'underpass' in codes:
        if entity.dxf.name == 'RACK_60D_144B':
            return 'C_PASS'
        return 'B_PASS' if 'p27b' in codes else 'A_PASS'
    return {32: 'A', 190: 'B', 6: 'C'}[color]


def generate(source):
    doc = ezdxf.readfile(source)
    if doc.units != 1:
        raise ValueError('Expected inch DXF model space')
    origin, registration = cad_registration(doc)
    catalog = elevation_catalog(doc)
    racks, ground, duplicates = [], [], []
    locations = {}
    for entity, matrix, chain in placed_blocks(doc, doc.modelspace(), Matrix44()):
        name = entity.dxf.name
        attrs = {a.dxf.tag: a.dxf.text.strip() for a in entity.attribs}
        is_rack = name.startswith('RACK_')
        depth = 60 if '60D' in name else (42 if is_rack else 40)
        span = 150 if is_rack else 48
        center = matrix.transform((depth / 2, span / 2, 0))
        offset = matrix.transform((0, 0, 0))
        axis = matrix.transform_direction((0, 1, 0) if is_rack else (1, 0, 0))
        row = {
            'id': 'CAD_24_' + '_'.join(chain), 'block': name, 'source_layer': entity.dxf.layer,
            'source_xy': [round(offset[i], 6) for i in (0, 1)],
            'position_m': [metres(center[i] - origin[i]) for i in (0, 1)],
            'rotation_deg': round(math.degrees(math.atan2(axis.y, axis.x)), 6) % 360,
            'physical_depth_m': metres(depth), 'physical_span_m': metres(span),
            'attrs': attrs
        }
        if is_rack:
            variant = variant_for(entity, attrs)
            row.update(row_code=attrs['BLOCK_CODE'], bay_sequence=attrs['SEQ'],
                       spec_type='D1' if variant == 'D1' else variant[0], pass_variant=variant.endswith('_PASS'),
                       effective_aci=doc.layers.get(entity.dxf.layer).dxf.color if entity.dxf.color == 256 else entity.dxf.color,
                       variant=variant)
        key = (name, *row['position_m'], row['rotation_deg'])
        if key in locations:
            prior = locations[key]
            if attrs != prior['attrs'] or row.get('variant') != prior.get('variant'):
                raise ValueError(f'Conflicting coincident blocks {row["id"]} and {prior["id"]}')
            duplicates.append({'id': row['id'], 'same_as': prior['id']})
            continue
        locations[key] = row
        (racks if is_rack else ground).append(row)
    return {
        'schema_version': 1, 'source': source.name, 'sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'coordinate_contract': 'CAD XY metres. Rack rotation is local +Y (span) CCW from world +X; floor rotation is local +X (depth). UE reflects Y.',
        'registration': registration, 'catalog': catalog,
        'summary': {'racks': len(racks), 'ground': len(ground), 'variants': dict(Counter(r['variant'] for r in racks)),
                    'empty_row_or_bay': sum(not (r['row_code'] and r['bay_sequence']) for r in racks)},
        'coincident_duplicates': duplicates, 'racks': racks, 'ground': ground
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dxf', nargs='?', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = generate(args.dxf)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')), encoding='utf8')
    print(json.dumps(result['summary'], indent=2))
