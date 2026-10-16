"""Resolve rack types from CAD colours, attributes and pass-through layers.

Only writes SourceAssets/GHS/RackSpecs/cad_plan_mapping.json and diagnostics.
Physical bounds exclude ATTRIB text extents.  W_DOCK is loading doors, not racks.
"""
from pathlib import Path
import collections
import json
import math
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Scripts/_vendor/cad'))
import ezdxf
from ezdxf.math import Matrix44
from PIL import Image, ImageDraw, ImageFont

SOURCE = Path('D:/EdgeDownload/平面布局图_GHS_0.23_20260710现状.dxf')
OUT = ROOT / 'SourceAssets/GHS/RackSpecs'
ORIGIN = (6917380., 1902500.)
UNIT = .0254


def xy(p):
    return [round((p[i] - ORIGIN[i]) * UNIT, 6) for i in range(2)]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    doc = ezdxf.readfile(SOURCE)
    layout = json.loads((ROOT / 'SourceAssets/GHS/clearance_layout.json').read_text(encoding='utf8'))
    source_racks = []
    all_racks = []

    def walk(entities, mat, chain, parent_layer='0', parent_color=7):
        for e in entities:
            if e.dxftype() != 'INSERT':
                continue
            layer = parent_layer if e.dxf.layer == '0' else e.dxf.layer
            color = e.dxf.color
            if color == 256:
                color = doc.layers.get(layer).dxf.color
            if color == 0:
                color = parent_color
            transform = Matrix44.chain(e.matrix44(), mat)
            handles = chain + [e.dxf.handle]
            name = e.dxf.name
            if name in ('RACK_42D_144B', 'RACK_60D_144B'):
                depth_in = 60 if '60D' in name else 42
                center = transform.transform((depth_in / 2, 75, 0))
                physical_origin = transform.transform((0, 0, 0))
                direction = transform.transform_direction((1, 0, 0))
                attrs = {a.dxf.tag: a.dxf.text for a in e.attribs}
                record = {
                    'source_id': 'CAD_' + '_'.join(handles),
                    'source_handles': handles, 'block': name,
                    'source_layer': layer, 'effective_aci': color,
                    'attributes': attrs,
                    'physical_origin_dxf_xy': [physical_origin.x, physical_origin.y],
                    'physical_origin_m': xy(physical_origin),
                    'physical_center_m': xy(center),
                    'rotation_deg': round(math.degrees(math.atan2(direction.y, direction.x)), 6),
                    'nominal_depth_m': depth_in * UNIT,
                    'nominal_span_m': 150 * UNIT,
                    'clear_beam_span_m': 144 * UNIT,
                    'row_code': attrs.get('BLOCK_CODE'),
                    'bay_sequence': attrs.get('SEQ'),
                    'parent_block': doc.entitydb[handles[0]].dxf.name,
                }
                all_racks.append(record)
                if 6907000 <= center.x <= 6927800 and 1898500 <= center.y <= 1905800:
                    source_racks.append(record)
            if len(chain) < 8:
                walk(doc.blocks.get(name), transform, handles, layer, color)

    walk(doc.modelspace(), Matrix44(), [])
    # These legend colours are present in the actual MTEXT runs: A=30, B=191,
    # C=6, D1=4, D2=5.  By-layer rack colour 32 and purple 190 are same families.
    # Blue at mid-row is explicitly a pass-through marker, not Dock D2.
    for rec in source_racks:
        is_pass = rec['source_layer'] == 'W_RACK_PASS' or rec['parent_block'] == 'LOCK2'
        color = rec['effective_aci']
        rec['pass_variant'] = is_pass
        rec['spec_type'] = None if is_pass else {30: 'A', 32: 'A', 190: 'B', 191: 'B', 6: 'C', 4: 'D1'}.get(color)
        rec['mapping_confidence'] = .98 if rec['spec_type'] else None
        rec['mapping_evidence'] = ['CAD INSERT effective ACI matches type legend family; entity dimensions and attributes retained'] if rec['spec_type'] else []
    regular = [r for r in source_racks if r['spec_type']]
    for rec in source_racks:
        if not rec['pass_variant']:
            assert rec['spec_type'], rec
            continue
        # A cross aisle intersects the same rack row at bay 13.  Use adjacent
        # collinear bays, not the blue marker colour, to identify its rack family.
        x, y = rec['physical_center_m']
        candidates = [r for r in regular if abs(r['physical_center_m'][0] - x) < .03
                      and abs(math.sin(math.radians(r['rotation_deg'] - rec['rotation_deg']))) < .01]
        candidates.sort(key=lambda r: abs(r['physical_center_m'][1] - y))
        assert candidates, rec
        neighbors = candidates[:2]
        assert len({n['spec_type'] for n in neighbors}) == 1, rec
        rec['spec_type'] = neighbors[0]['spec_type']
        rec['mapping_confidence'] = .96
        rec['mapping_evidence'] = ['Explicit W_RACK_PASS layer or LOCK2 cross-aisle block',
                                   'Base type inherited from two neighboring collinear CAD bays']
        rec['neighbor_source_ids'] = [n['source_id'] for n in neighbors]
    by_id = {r['source_id']: r for r in source_racks}
    assignments = []
    for current in layout['racks']:
        parent = current.get('parent_cad_id', current['id'])
        source = by_id[parent]
        rec = dict(source)
        rec.update({'instance_id': current['id'], 'parent_cad_id': parent,
                    'position_m': current['position_m'], 'rotation_deg': current['rotation_deg'],
                    'physical_depth_m': current['size_m'][0], 'physical_span_m': current['size_m'][1],
                    'clearance_adjustment': current.get('design_adjustment'),
                    'source_physical_center_m': source['physical_center_m'],
                    'physical_center_m': current['position_m'],
                    'geometry_policy': 'Preserve previously validated column/adjacent-bay clearance trim and split'})
        assignments.append(rec)
    # Pass layer was omitted by the original extraction.  Keep each physical bay
    # once even where CAD contains coincident duplicated INSERTs.
    occupied = {}
    for r in source_racks:
        if r['source_id'] in {a['parent_cad_id'] for a in assignments}:
            occupied[(round(r['physical_center_m'][0], 3), round(r['physical_center_m'][1], 3))] = r['source_id']
    additional = []
    duplicate_pass = []
    for r in source_racks:
        if not r['pass_variant'] or r['source_id'] in {a['parent_cad_id'] for a in assignments}:
            continue
        key = tuple(round(v, 3) for v in r['physical_center_m'])
        if key in occupied:
            duplicate_pass.append({'source_id': r['source_id'], 'same_physical_bay_as': occupied[key]})
            continue
        occupied[key] = r['source_id']
        rec = dict(r)
        rec.update({'instance_id': r['source_id'], 'parent_cad_id': r['source_id'],
                    'position_m': r['physical_center_m'], 'physical_depth_m': r['nominal_depth_m'],
                    'physical_span_m': 3.7138,
                    'geometry_policy': 'Previously omitted W_RACK_PASS; shared-end frame trim matches neighboring 147-inch pitch'})
        additional.append(rec)
    # Existing end bays were trimmed only on their occupied neighbor side.  A
    # newly restored pass bay must fit the *remaining* gap, not reuse the common
    # 3.7138m size and collide with the untrimmed ends.  Keep its CAD center and
    # shorten its two ends to retain a measured 20mm seam on both sides.
    sys.path.insert(0, str(ROOT / 'Scripts/ghs'))
    from plan_clearance_fix import overlap, corners
    for rec in additional:
        a = math.radians(rec['rotation_deg'])
        along = (-math.sin(a), math.cos(a)); across = (math.cos(a), math.sin(a))
        radius = rec['physical_span_m'] / 2
        neighbors = []
        for existing in layout['racks']:
            delta = [existing['position_m'][i] - rec['position_m'][i] for i in range(2)]
            if abs(sum(delta[i] * across[i] for i in range(2))) > .03:
                continue
            if abs(math.sin(math.radians(existing['rotation_deg'] - rec['rotation_deg']))) > .01:
                continue
            projected = [sum((p[i] - rec['position_m'][i]) * along[i] for i in range(2)) for p in corners(existing)]
            edge_distance = min(abs(v) for v in projected)
            if edge_distance < radius + .02:
                radius = min(radius, edge_distance - .02001)
                neighbors.append(existing['id'])
        assert radius > 1.7, rec
        rec['physical_span_m'] = round(2 * radius, 6)
        rec['geometry_policy'] = 'Keep CAD center; shorten pass-bay ends to fit existing neighboring geometry with >=20mm seam'
        rec['adjacent_clearance_instance_ids'] = neighbors
    expanded_columns = []
    for column in layout['columns']:
        expanded = dict(column)
        expanded['size_m'] = [v + .30 for v in column['size_m']]
        expanded_columns.append(expanded)
    clearance_hits = []
    for rec in additional:
        footprint = {'position_m': rec['position_m'], 'size_m': [rec['physical_depth_m'], rec['physical_span_m']], 'rotation_deg': rec['rotation_deg']}
        for category, entries in [('column_with_base_and_100mm_clearance', expanded_columns), ('rack', layout['racks']), ('storage', layout['storage']), ('loading_door', layout['equipment'])]:
            for existing in entries:
                if overlap(footprint, existing):
                    clearance_hits.append({'new_pass_id': rec['instance_id'], 'category': category, 'existing_id': existing['id']})
    for index, rec in enumerate(additional):
        footprint = {'position_m': rec['position_m'], 'size_m': [rec['physical_depth_m'], rec['physical_span_m']], 'rotation_deg': rec['rotation_deg']}
        for other in additional[index + 1:]:
            other_footprint = {'position_m': other['position_m'], 'size_m': [other['physical_depth_m'], other['physical_span_m']], 'rotation_deg': other['rotation_deg']}
            if overlap(footprint, other_footprint):
                clearance_hits.append({'new_pass_id': rec['instance_id'], 'category': 'added_pass_rack', 'existing_id': other['instance_id']})
    assert not clearance_hits, clearance_hits
    doors = []
    for e in layout['equipment']:
        source = doc.entitydb[e['source_handles'][-1]]
        at = {a.dxf.tag: a.dxf.text for a in source.attribs}
        line_points = [point for child in doc.blocks.get(source.dxf.name) if child.dxftype() == 'LINE'
                       for point in (child.dxf.start, child.dxf.end)]
        bounds = [[min(p[i] for p in line_points), max(p[i] for p in line_points)] for i in range(2)]
        physical_center = source.matrix44().transform(tuple((v[0]+v[1])/2 for v in bounds) + (0,))
        doors.append({'instance_id': e['id'], 'block': e['block'], 'position_m': e['position_m'],
                      'rotation_deg': e['rotation_deg'], 'imported_bbox_size_m': e['size_m'],
                      'physical_local_bounds_inches': bounds,
                      'physical_center_m': xy(physical_center),
                      'physical_size_m': [(v[1]-v[0])*UNIT for v in bounds],
                      'classification': 'loading_dock_door', 'is_rack': False,
                      'attributes': at,
                      'evidence': 'DOCK_NO. attribute; door leaf line between +/-55 inches and narrow +/-57-inch guide rails; no 42D/60D x144B rack geometry'})
    counts = lambda rows: dict(collections.Counter(r['spec_type'] + ('_PASS' if r['pass_variant'] else '') for r in rows))
    result = {
        'schema_version': 1, 'cad_file': str(SOURCE), 'units_to_m': UNIT, 'origin_dxf_xy': ORIGIN,
        'coordinate_contract': 'CAD right-handed XY, meters; local X is rack depth, local Y is bay span; UE uses reflected Y',
        'legend_evidence': {'A': {'mtext_handle': '1F868B', 'aci': 30, 'levels': 4},
                            'B': {'mtext_handle': '1F8711', 'aci': 191, 'levels': 12},
                            'C': {'mtext_handle': '1F869E', 'aci': 6, 'levels': 5, 'depth_inches': 60},
                            'D1': {'mtext_handle': '1F87B7', 'aci': 4, 'levels': 2},
                            'D2': {'mtext_handle': '1F87D7', 'aci': 5, 'levels': 5}},
        'unused_specs': {'C': 'Only found in detail legend south of the main building, including RACK_60D_144B at approx (-180,-162)m; no current-plan position.',
                         'D2': 'No unambiguous current-plan Dock D2 insert. Blue mid-row racks belong to explicit pass-through/cross-aisle groups, not dock storage.'},
        'summary': {'existing_clearance_instances': len(assignments), 'existing_counts': counts(assignments),
                    'additional_pass_instances': len(additional), 'additional_counts': counts(additional),
                    'coincident_pass_duplicates_skipped': len(duplicate_pass), 'loading_doors_not_racks': len(doors)},
        'assignments': assignments, 'additional_pass_racks': additional,
        'duplicate_pass_inserts': duplicate_pass, 'loading_doors': doors,
        'added_pass_clearance_audit': {'checked_instances': len(additional), 'collision_count': len(clearance_hits),
                                      'column_base_extra_total_m': .10, 'column_clearance_each_side_m': .10,
                                      'minimum_neighbor_seam_m': .02,
                                      'checked_categories': ['columns', 'existing_racks', 'ground_storage', 'loading_doors', 'added_pass_mutual']},
        'source_rack_inserts': source_racks,
        'uncertainties': ['Current-plan beam codes describe L1~L2 despite the type legend specifying 4/12 beam levels; user explicitly requested following type legend, so beam counts use that legend.',
                          'No C/D2 bay locations are invented. Those assets may be built as unused validated catalogue types.',
                          'Added pass bays passed conservative planar clearance checks; generated meshes must remain inside their registered footprint.'],
    }
    (OUT / 'cad_plan_mapping.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    render(result, layout)
    print(json.dumps(result['summary'], indent=2))


def render(result, layout):
    w, h = 2400, 880
    im = Image.new('RGB', (w, h), (14, 20, 29)); dr = ImageDraw.Draw(im)
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 24)
    scale = 4.75
    def p(xy): return (55 + (xy[0] + 240) * scale, 110 + (61 - xy[1]) * scale)
    dr.line([p(v) for v in layout['footprint_outline_m']] + [p(layout['footprint_outline_m'][0])], fill=(190,200,210), width=2)
    colors = {'A': (230, 155, 38), 'B': (170, 110, 238), 'C': (255, 30, 255), 'D1': (30, 220, 225), 'D2': (60, 100, 255)}
    for r in result['assignments'] + result['additional_pass_racks']:
        x, y = r['position_m']; a = math.radians(r['rotation_deg']); co, si = math.cos(a), math.sin(a)
        dx, dy = r['physical_depth_m']/2, r['physical_span_m']/2
        corners = [p((x + u*co-v*si, y+u*si+v*co)) for u,v in [(-dx,-dy),(dx,-dy),(dx,dy),(-dx,dy)]]
        color = (245,245,245) if r['pass_variant'] else colors[r['spec_type']]
        dr.polygon(corners, fill=color)
    for e in result['loading_doors']:
        q = p(e['position_m']); dr.ellipse((q[0]-2,q[1]-2,q[0]+2,q[1]+2), fill=(90,120,145))
    dr.text((55,25), 'CAD rack mapping: A orange / B purple / D1 cyan / pass-through white / loading doors slate', font=font, fill='white')
    dr.text((55,65), 'C and D2 have legend details, but no confirmed main-plan locations. No invented placement.', font=font, fill=(190,200,210))
    dr.text((55,795), 'Positions and clearances follow CAD meters; bay types follow legend colours, attributes, and explicit cross-aisle groups.', font=font, fill=(190,200,210))
    im.save(OUT / 'cad_plan_mapping.png')


if __name__ == '__main__':
    main()
