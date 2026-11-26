"""Build conservative GHS CAD/WMS bindings without changing either source.

Existing CAD row attributes or a strictly verified visible R1 axis are matched
to fully qualified current WMS codes. Ambiguous targets remain unbound.
Run with --csv and --cad; all other inputs default to this repository.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
RULE = 'cad-row-bay-three-pallets-v4'

# Measured once from the actual source TEXT with its original Romans SHX font.
# Runtime generation verifies the text/style/transform identity, without loading
# ezdxf or requiring that workstation font to be installed on another machine.
R1_AXIS_CALIBRATION = {
    'handle': '2379D0', 'text': 'R1',
    'positionDxf': [6907983.530347786, 1900808.299315862, 0.],
    'height': 20., 'width': .8, 'textAdvanceInches': 31.238095238095237,
    'font': 'romans.shx',
    'fontSha256': '511a13122074b47de7c798a077e946abd72fd15b48944d5f259751cc5774bf60',
}


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def integer(value):
    try:
        result = int(str(value))
        return result if str(value).strip() and result > 0 else None
    except (ValueError, TypeError):
        return None


def resolve_visible_r1_axis(rack, all_racks, attrs, evidence):
    """Recover only exact same-Y bays bracketed by the R02/R03 row evidence.

    The bottom R2..R69 labels use a different physical numbering system; none
    of them are eligible here. Eight shifted R1 bays deliberately stay unknown.
    """
    failure = (None, evidence, 'cad_row_not_business_identifier')
    axis = attrs.get('2379D0', {})
    style = attrs.get('__styles__', {}).get('romans', {})
    layer = attrs.get('__layers__', {}).get('CONC', {})
    base = attrs.get('__blocks__', {}).get('LINE1', {})
    rack_base = attrs.get('__blocks__', {}).get('RACK_42D_144B', {})
    parent = attrs.get('35ED2D', {})
    def close_vector(a, b, tolerance=.001):
        return (isinstance(a, (list, tuple)) and len(a) == len(b)
                and all(isinstance(v, (int, float)) and math.isfinite(v) for v in a)
                and math.dist(a, b) <= tolerance)
    if (axis.get('entity_type') != 'TEXT' or axis.get('text') != 'R1'
            or not close_vector(axis.get('position'), R1_AXIS_CALIBRATION['positionDxf'])
            or axis.get('style') != 'romans' or axis.get('height') != 20.
            or axis.get('width') != .8 or axis.get('rotation') != 0.
            or axis.get('align_horizontal') != 0 or axis.get('align_vertical') != 0
            or axis.get('oblique') != 0. or axis.get('text_flags') != 0
            or axis.get('layer') != 'CONC' or axis.get('owner_block') is not None
            or axis.get('invisible') != 0 or axis.get('paperspace') != 0
            or not close_vector(axis.get('normal'), [0, 0, 1])
            or style.get('font') != 'romans.shx' or style.get('width') != .8
            or style.get('oblique') != 0. or style.get('flags') != 0
            or not layer or layer.get('flags', 1) & 1 or layer.get('color', -1) < 0
            or parent.get('block') != 'LINE1'
            or not close_vector(parent.get('position'), [0, 0, 0])
            or parent.get('rotation') != 0. or not close_vector(parent.get('scale'), [1, 1, 1])
            or not close_vector(parent.get('normal'), [0, 0, 1])
            or not close_vector(base.get('position'), [0, 0, 0]) or base.get('flags', 4) & 12
            or not close_vector(rack_base.get('position'), [0, 0, 0]) or rack_base.get('flags', 4) & 12):
        return failure

    def source_center(row):
        handles = row.get('source_handles', [])
        source = attrs.get(handles[-1], {}) if handles else {}
        values = source.get('attributes', {})
        if (values.get('BLOCK_CODE') != row['row_code']
                or integer(values.get('SEQ')) != integer(row['bay_sequence'])
                or source.get('block') != 'RACK_42D_144B'
                or source.get('rotation') != 0. or not close_vector(source.get('scale'), [1, 1, 1])
                or not close_vector(source.get('normal'), [0, 0, 1])
                or row.get('rotation_deg') != 0. or row.get('spec_type') != 'A'
                or row.get('pass_variant') or row.get('nominal_depth_m') != 1.0668
                or row.get('nominal_span_m') != 3.81):
            return None
        if len(handles) == 2:
            if handles[0] != '35ED2D' or source.get('owner_block') != 'LINE1':return None
        elif len(handles) != 1 or source.get('owner_block') is not None:
            return None
        p = source.get('position', [])
        if (len(p) != 3 or not close_vector(p[:2], row.get('physical_origin_dxf_xy', []))):
            return None
        calculated = [(p[0] + 21 - 6917380.) * .0254, (p[1] + 75 - 1902500.) * .0254]
        if not close_vector(row.get('source_physical_center_m'), calculated):return None
        return calculated

    target = source_center(rack)
    if (target is None or rack['row_code'] != 'A_A_000' or integer(rack['bay_sequence']) != 1
            or len(rack['source_handles']) != 2):
        return failure
    axis_x = axis['position'][0] + R1_AXIS_CALIBRATION['textAdvanceInches'] / 2
    target_x = target[0] / .0254 + 6917380.
    if abs(axis_x - target_x) >= 21:
        return failure
    columns_at_axis = {round(r['source_physical_center_m'][0], 3) for r in all_racks
                       if r.get('source_physical_center_m') and r.get('rotation_deg') == 0.
                       and abs(r['source_physical_center_m'][0] / .0254 + 6917380. - axis_x) < 21}
    if len(columns_at_axis) != 1:
        return failure
    # Reject a repeated physical cell rather than accepting the first candidate.
    overlapping = [r for r in all_racks if r.get('source_physical_center_m')
                   and close_vector(r['source_physical_center_m'], target)]
    if len(overlapping) != 1 or overlapping[0]['instance_id'] != rack['instance_id']:
        return failure
    references = []
    for row_name in ('R02', 'R03'):
        same_y = [r for r in all_racks if r['row_code'] == row_name
                  and r.get('source_physical_center_m')
                  and abs(r['source_physical_center_m'][1] - target[1]) <= .001]
        if len(same_y) != 1 or source_center(same_y[0]) is None:return failure
        references.append(same_y[0])
    first, second = references
    bay = integer(first['bay_sequence'])
    if (not bay or integer(second['bay_sequence']) != bay
            or not target[0] < first['source_physical_center_m'][0] < second['source_physical_center_m'][0]):
        return failure
    result = dict(evidence, resolvedRow='R01', resolvedBay=str(bay),
                  method='visible_r1_axis_two_row_alignment', axisText=dict(R1_AXIS_CALIBRATION),
                  sourceCenterM=target,
                  neighbors=[dict(cadId=r['instance_id'], row=r['row_code'], bay=r['bay_sequence'],
                                  centerM=r['source_physical_center_m']) for r in references])
    return dict(rack, row_code='R01', bay_sequence=str(bay)), result, ''


def resolve_rack_identity(rack, all_racks, attrs):
    """Resolve only a unique named, collinear, bilateral one-bay CAD bracket.

    Original source attributes are never overwritten. The resolved copy is a
    rule inference and its audit evidence accompanies each resulting binding.
    """
    def original_matches(row):
        handles = row.get('source_handles', [])
        original = attrs.get(handles[-1], {}).get('attributes', {}) if handles else {}
        return (original.get('BLOCK_CODE') == row['row_code']
                and integer(original.get('SEQ')) == integer(row['bay_sequence']))

    row, bay = rack['row_code'], rack['bay_sequence']
    evidence = dict(originalRow=row, originalBay=bay, resolvedRow=row,
                    resolvedBay=bay, method='direct_cad_attributes')
    if not original_matches(rack):
        return None, evidence, 'original_cad_attributes_mismatch'
    if row == 'A_A_000':
        return resolve_visible_r1_axis(rack, all_racks, attrs, evidence)
    direct = bool(re.fullmatch(r'(?:R|SR)\d{2}', row))
    special = bool(re.fullmatch(r'S\d{2}', row))
    if not direct and not (special and rack.get('pass_variant')):
        return None, evidence, 'cad_row_not_business_identifier'
    if not rack.get('pass_variant'):
        return dict(rack), evidence, ''
    # Unsupported orientations and unbracketed normal labels retain the exact
    # original identity. Sxx labels require positive bilateral evidence.
    def fallback():
        return (dict(rack), evidence, '') if direct else (None, evidence, 'special_pass_identity_unresolved')
    if abs(rack['rotation_deg']) > 0.001:
        return fallback()
    center = rack.get('physical_center_m')
    if not center or len(center) != 2:
        return fallback()
    neighbors = []
    for other in all_racks:
        if (other['instance_id'] == rack['instance_id'] or other.get('pass_variant')
                or other['spec_type'] != rack['spec_type']
                or abs(other['rotation_deg'] - rack['rotation_deg']) > 0.001
                or not re.fullmatch(r'(?:R|SR)\d{2}', other['row_code'])):
            continue
        p = other.get('physical_center_m', [])
        if len(p) != 2 or abs(p[0] - center[0]) > 0.0001:
            continue
        neighbors.append((p[1] - center[1], other))
    left = sorted((n for n in neighbors if n[0] < 0), key=lambda n: -n[0])
    right = sorted((n for n in neighbors if n[0] > 0), key=lambda n: n[0])
    if not left or not right:
        return fallback()
    if ((len(left) > 1 and abs(left[0][0] - left[1][0]) < 0.0001)
            or (len(right) > 1 and abs(right[0][0] - right[1][0]) < 0.0001)):
        return fallback()
    a, lower = left[0]; b, upper = right[0]
    lower_bay, upper_bay = integer(lower['bay_sequence']), integer(upper['bay_sequence'])
    if (not original_matches(lower) or not original_matches(upper)
            or lower['row_code'] != upper['row_code']
            or not lower_bay or not upper_bay or upper_bay - lower_bay != 2
            or abs(a + b) > 0.0001 or not (3.4 < -a < 4.2 and 3.4 < b < 4.2)):
        return fallback()
    resolved_row = lower['row_code']; resolved_bay = str(lower_bay + 1)
    if (special and (resolved_row != 'SR' + row[1:] or bay != resolved_bay)
            or direct and row != resolved_row):
        return fallback()
    if row == resolved_row and bay == resolved_bay:
        return dict(rack), evidence, ''
    evidence.update(resolvedRow=resolved_row, resolvedBay=resolved_bay,
                    method='collinear_bilateral_pass_bracket',
                    neighbors=[dict(cadId=n['instance_id'], row=n['row_code'],
                                    bay=n['bay_sequence'], centerM=n['physical_center_m'])
                               for n in (lower, upper)])
    return dict(rack, row_code=resolved_row, bay_sequence=resolved_bay), evidence, ''


def expected_code(rack, local_level, column, physical):
    """Never normalize old Rxx or GHS-SRxx aliases into active WMS names."""
    row = rack['row_code']
    if not re.fullmatch(r'(?:R|SR)\d{2}', row) or not integer(re.sub(r'\D', '', row)):
        return None
    bay = integer(rack['bay_sequence'])
    if not bay or column not in (1, 2, 3) or not integer(physical):
        return None
    prefix = 'GHS-SR-' + row[2:] if row.startswith('SR') else 'GHS-' + row
    return f'{prefix}-{3 * (bay - 1) + column:02d}-{physical:02d}'


def numeric_code_key(code):
    """Only normalize digit width inside the same exact current code family."""
    match = re.fullmatch(r'GHS-(R|SR-)(\d+)-(\d+)-(\d+)', code)
    if not match:
        return None
    return (match[1], *(int(value) for value in match.groups()[1:]))


def numeric_code_index(by_code):
    result = collections.defaultdict(list)
    for code, rows in by_code.items():
        key = numeric_code_key(code)
        if key is not None:
            result[key].extend(rows)
    return result


def physical_level(base_z, canonical_slots):
    levels = {s['level'] for s in canonical_slots if abs(float(s['base_z_m']) - base_z) < 0.001}
    return next(iter(levels)) if len(levels) == 1 else None


def crosscheck_location(location, rack, physical):
    if location.get('warehouse_id') != '108' or location.get('warehouse_code') != 'GHS_CA_US':
        return 'warehouse_mismatch'
    expected_area = '454' if rack['row_code'].startswith('SR') else '450'
    if location.get('warehouse_area_id') != expected_area:
        return 'warehouse_area_mismatch'
    if integer(location.get('horizontal_num')) != integer(rack['bay_sequence']):
        return 'wms_horizontal_number_mismatch'
    if integer(location.get('location_layer')) != physical:
        return 'wms_physical_layer_mismatch'
    return None


def increasing_sequence_rows(racks):
    """Check CAD bay progression; this does not certify WMS labels in a bay."""
    by_row = collections.defaultdict(list)
    for rack in racks:
        if re.fullmatch(r'(?:R|SR)\d{2}', rack['row_code']):
            bay = integer(rack['bay_sequence'])
            if bay:
                by_row[rack['row_code']].append((bay, rack['position_m'][1]))
    accepted = set()
    for row, values in by_row.items():
        values.sort()
        increments = [b[1] - a[1] for a, b in zip(values, values[1:]) if a[0] != b[0]]
        if increments and all(delta > 0.001 for delta in increments):
            accepted.add(row)
    return accepted


def sequence_conflicts(racks):
    """Return both endpoints of actual-centre order inversions, never swap IDs.

    INSERT origins can lie at the opposite end of a mirrored rack. Use current
    instance centres; duplicated bay numbers remain the separate identity check.
    """
    by_row = collections.defaultdict(list)
    for rack in racks:
        bay = integer(rack['bay_sequence'])
        if re.fullmatch(r'(?:R|SR)\d{2}', rack['row_code']) and bay:
            by_row[rack['row_code']].append((bay, rack['position_m'][1], rack['instance_id']))
    conflicts = set()
    for rows in by_row.values():
        rows.sort()
        for a, b in zip(rows, rows[1:]):
            if a[0] != b[0] and b[1] - a[1] <= 0.001:
                conflicts.update((a[2], b[2]))
    return conflicts


def transform_contract(instance, source_mesh, registry_row, capacity_group):
    """Use the authored placement and capacity mesh, never an observed new pose.

    apply_refinement_v2.py converts registry CAD metres to UE centimetres,
    reflects world Y, and sets UE yaw to minus registry rotation_deg.
    """
    if not registry_row or registry_row.get('id') != instance['id']:
        return None
    if math.dist(registry_row.get('position_m', []), instance['position_m']) > 0.001:
        return None
    rotation = registry_row.get('rotation_deg')
    scale = registry_row.get('scale')
    if not isinstance(rotation, (int, float)) or not math.isfinite(rotation):
        return None
    if not isinstance(scale, list) or len(scale) != 3 or not all(
            isinstance(v, (int, float)) and math.isfinite(v) and v > 0 for v in scale):
        return None
    if (not capacity_group or capacity_group.get('source_mesh') != source_mesh
            or not capacity_group.get('mesh', '').endswith('_Capacity')):
        return None
    return dict(expectedPositionM=instance['position_m'],
                expectedWorldRotationDeg=[0, -rotation, 0],
                expectedWorldScale=scale, expectedMesh=capacity_group['mesh'])


def authored_placements(groups):
    """Do not let a repeated CAD identity silently pick its last transform."""
    result = collections.defaultdict(dict)
    conflicts = set()
    for group in groups:
        mesh = group['mesh']
        for row in group['instances']:
            cid = row['id']
            previous = result[mesh].get(cid)
            if previous and any(previous.get(k) != row.get(k) for k in ('position_m', 'rotation_deg', 'scale')):
                conflicts.add((mesh, cid))
            result[mesh][cid] = row
    for mesh, cid in conflicts:
        result[mesh].pop(cid, None)
    return dict(result)


def reject_ambiguous(bindings):
    targets = collections.Counter((x['cadId'], x['level'], x['column']) for x in bindings)
    locations = collections.Counter(x['locationId'] for x in bindings)
    good, rejected = [], []
    for x in bindings:
        (good if targets[(x['cadId'], x['level'], x['column'])] == 1
         and locations[x['locationId']] == 1 else rejected).append(x)
    return good, rejected


def index_locations(rows):
    unique = {}
    # Stock rows repeat location metadata. Do not count them as duplicate slots.
    fixed = ('warehouse_id', 'warehouse_code', 'warehouse_area_id', 'location_code', 'horizontal_num', 'location_layer')
    for row in rows:
        key = (row['warehouse_id'], row['location_id'])
        if key in unique and any(unique[key].get(k) != row.get(k) for k in fixed):
            raise ValueError(f'Conflicting WMS location metadata: {key}')
        unique[key] = row
    by_code = collections.defaultdict(list)
    for row in unique.values():
        by_code[row['location_code']].append(row)
    return by_code


def canonical_scene_groups(scene):
    """Occ70 is the same physical layout with demo cargo removed, not new bins."""
    canonical = {g['mesh']: g for g in scene['groups'] if not g['mesh'].endswith('_Occ70')}
    for group in scene['groups']:
        if not group['mesh'].endswith('_Occ70'):
            continue
        base = canonical.get(group['mesh'][:-6])
        if not base:
            raise ValueError('Demo occupancy alias lacks its canonical scene group')
        originals = {x['id']: x['position_m'] for x in base['instances']}
        for item in group['instances']:
            if item['id'] not in originals or math.dist(originals[item['id']], item['position_m']) > 0.001:
                raise ValueError('Demo occupancy alias changed CAD identity/position')
    return list(canonical.values())


def dxf_insert_attributes(path):
    """Read ASCII DXF INSERT/ATTRIB evidence without any geometry conversion.

    Handles and attribute values are ASCII in this source. Retain source text;
    never repair garbled Chinese annotations into guessed business identifiers.
    """
    def entities():
        current = []
        with Path(path).open(encoding='utf-8-sig') as stream:
            while True:
                code = stream.readline()
                if not code:
                    break
                value = stream.readline()
                if not value:
                    raise ValueError('Truncated DXF pair')
                key = code.strip()
                if key == '0' and current:
                    yield current
                    current = []
                current.append((key, value.rstrip('\r\n')))
        if current:
            yield current
    result = {}
    active = None
    owner_block = None
    for pairs in entities():
        entity = dict(pairs)
        kind = entity.get('0')
        if kind == 'BLOCK':
            owner_block = entity.get('2')
            result.setdefault('__blocks__', {})[owner_block] = {
                'position': [float(entity.get(k, '0')) for k in ('10', '20', '30')],
                'flags': int(entity.get('70', '0'))}
            active = None
        elif kind == 'ENDBLK':
            owner_block = None
            active = None
        elif kind == 'STYLE':
            result.setdefault('__styles__', {})[entity.get('2')] = {
                'font': entity.get('3', ''), 'width': float(entity.get('41', '1')),
                'oblique': float(entity.get('50', '0')), 'flags': int(entity.get('70', '0'))}
            active = None
        elif kind == 'LAYER':
            result.setdefault('__layers__', {})[entity.get('2')] = {
                'flags': int(entity.get('70', '0')), 'color': int(entity.get('62', '7'))}
            active = None
        elif kind == 'TEXT' and entity.get('5') == '2379D0':
            result['2379D0'] = dict(
                entity_type='TEXT', text=entity.get('1', ''), style=entity.get('7', 'Standard'),
                position=[float(entity.get(k, '0')) for k in ('10', '20', '30')],
                normal=[float(entity.get(k, default)) for k, default in (('210', '0'), ('220', '0'), ('230', '1'))],
                height=float(entity.get('40', '0')), width=float(entity.get('41', '1')),
                rotation=float(entity.get('50', '0')), layer=entity.get('8', '0'),
                align_horizontal=int(entity.get('72', '0')), align_vertical=int(entity.get('73', '0')),
                oblique=float(entity.get('51', '0')), text_flags=int(entity.get('71', '0')),
                invisible=int(entity.get('60', '0')), paperspace=int(entity.get('67', '0')),
                owner_block=owner_block)
            active = None
        elif kind == 'INSERT':
            active = {'block': entity.get('2'), 'attributes': {},
                      'position': [float(entity.get(k, '0')) for k in ('10', '20', '30')],
                      'rotation': float(entity.get('50', '0')),
                      'scale': [float(entity.get(k, '1')) for k in ('41', '42', '43')],
                      'normal': [float(entity.get(k, default)) for k, default in (('210', '0'), ('220', '0'), ('230', '1'))],
                      'owner_block': owner_block}
            result[entity['5']] = active
        elif kind == 'ATTRIB' and active is not None:
            active['attributes'][entity.get('2')] = entity.get('1', '')
        elif kind == 'SEQEND':
            active = None
        else:
            active = None
    return result


def build(csv_path, cad_path, root=ROOT):
    scene_path = root / 'Content/GHSTwinUI/data/scene-bindings.json'
    slot_path = root / 'Content/GHSTwinUI/data/rack-slots.json'
    layout_path = root / 'SourceAssets/GHS/RefinementV2/Layout/rack_spacing.json'
    model_path = root / 'SourceAssets/GHS/RefinementV2/Racks/refined_rack_cargo.json'
    floor_path = root / 'SourceAssets/GHS/cad_layout.json'
    registry_path = root / 'SourceAssets/GHS_Normal/ue_scene_registry.json'
    capacity_path = root / 'Content/GHSTwinUI/data/storage-capacity.json'
    with Path(csv_path).open(encoding='utf-8-sig', newline='') as stream:
        wms = index_locations(csv.DictReader(stream))
    numeric_wms = numeric_code_index(wms)
    attrs = dxf_insert_attributes(cad_path)
    scene = read_json(scene_path)
    authored_groups = authored_placements(read_json(registry_path)['groups'])
    capacity_groups = {g['source_mesh']: g for g in read_json(capacity_path)['groups']}
    slots = {m['name']: m['cargo_stacks'] for m in read_json(slot_path)['meshes']}
    layouts = {r['instance_id']: r for r in read_json(layout_path)['racks']}
    resolutions = {cid: resolve_rack_identity(r, layouts.values(), attrs) for cid, r in layouts.items()}
    resolved_racks = [result[0] for result in resolutions.values() if result[0] is not None]
    conflicting_sequence = sequence_conflicts(resolved_racks)
    ordered_rows = increasing_sequence_rows(r for r in resolved_racks if r['instance_id'] not in conflicting_sequence)
    models = {m['mapping_key']: m for m in read_json(model_path)['meshes']}
    canonical = {m['spec_type']: m['cargo_stacks'] for m in models.values()
                 if m.get('canonical') and not m.get('pass_variant')}
    problems = collections.Counter()
    examples = collections.defaultdict(list)
    candidates = []
    rack_count = floor_count = total_rack_slots = 0

    def issue(reason, identity, count=1):
        problems[reason] += count
        if len(examples[reason]) < 8:
            examples[reason].append(identity)

    for group in canonical_scene_groups(scene):
        if group['mesh'].startswith('SM_GHS_Presentation_Cargo'):
            floor_count += len(group['instances'])
        if not group['mesh'].startswith('SM_GHS_V2Rack_'):
            continue
        if group['mesh'] not in slots:
            raise ValueError('Scene rack mesh has no slot metadata: ' + group['mesh'])
        current_slots = slots[group['mesh']]
        for instance in group['instances']:
            rack_count += 1
            total_rack_slots += len(current_slots)
            cid = instance['id']
            rack = layouts.get(cid)
            if not rack:
                issue('scene_cad_identity_missing', cid, len(current_slots))
                continue
            rack, resolution, resolution_error = resolutions[cid]
            if rack is None:
                issue(resolution_error, cid, len(current_slots))
                continue
            if cid in conflicting_sequence:
                issue('cad_numbering_geometry_conflict', cid, len(current_slots))
                continue
            source = attrs.get(rack['source_handles'][-1])
            if len(rack['source_handles']) == 1:
                expected = rack['physical_origin_dxf_xy']
                if math.dist(expected, source['position'][:2]) > 0.001:
                    issue('original_cad_anchor_mismatch', cid, len(current_slots))
                    continue
            expected = [*rack['position_m'], 0]
            if math.dist(expected, instance['position_m']) > 0.001:
                issue('current_scene_anchor_mismatch', cid, len(current_slots))
                continue
            model = models[rack['mapping_key']]
            if model['name'] != group['mesh']:
                issue('current_scene_mesh_mismatch', cid, len(current_slots))
                continue
            authored = authored_groups.get(group['mesh'], {}).get(cid)
            contract = transform_contract(instance, group['mesh'], authored,
                                          capacity_groups.get(group['mesh']))
            if (contract is None or abs((authored['rotation_deg'] - rack['rotation_deg'] - 90) % 360) > 0.001):
                issue('authored_transform_contract_missing', cid, len(current_slots))
                continue
            # CAD bays increase along +Y; assume the three WMS labels within a
            # bay continue that direction. This remains an inferred rule, not a
            # field-verified label association.
            if abs(rack['rotation_deg']) > 0.001 or rack['row_code'] not in ordered_rows:
                issue('unverified_sequence_orientation', cid, len(current_slots))
                continue
            x_by_col = {s['column']: s['pallet_center_x_m'] for s in current_slots}
            if set(x_by_col) != {1, 2, 3} or not x_by_col[1] < x_by_col[2] < x_by_col[3]:
                issue('unverified_pallet_column_geometry', cid, len(current_slots))
                continue
            for slot in current_slots:
                physical = physical_level(slot['base_z_m'], canonical.get(rack['spec_type'], []))
                if physical is None:
                    issue('unverified_physical_layer', f'{cid}:{slot["level"]}:{slot["column"]}')
                    continue
                code = expected_code(rack, slot['level'], slot['column'], physical)
                if code:
                    candidates.append(dict(cadId=cid, level=slot['level'], column=slot['column'],
                                           locationCode=code, rack=rack, physical=physical,
                                           cadResolution=resolution,
                                           **contract))

    # Reject all competing targets even if one would subsequently fail a WMS check.
    code_count = collections.Counter(c['locationCode'] for c in candidates)
    proposed = []
    for candidate in candidates:
        code = candidate['locationCode']
        if code_count[code] != 1:
            issue('ambiguous_cad_targets_for_code', code)
            continue
        matches = numeric_wms.get(numeric_code_key(code), [])
        if len(matches) != 1:
            issue('wms_code_missing' if not matches else 'ambiguous_wms_location_code', code)
            continue
        loc = matches[0]
        mismatch = crosscheck_location(loc, candidate['rack'], candidate['physical'])
        if mismatch:
            issue(mismatch, code)
            continue
        generated_code = code
        # Preserve the actual source code, including a three-digit pallet index.
        candidate['locationCode'] = loc['location_code']
        proposed.append({k: candidate[k] for k in ('cadId', 'level', 'column', 'locationCode', 'expectedPositionM',
                                                  'expectedWorldRotationDeg', 'expectedWorldScale', 'expectedMesh')} |
                        dict(locationId=loc['location_id'], confidence='rule_inferred',
                             evidence=RULE, cadResolution=candidate['cadResolution'],
                             codeResolution=dict(generatedCode=generated_code, sourceCode=loc['location_code'],
                                                 method='exact' if generated_code == loc['location_code'] else 'same_family_numeric_width')))
    bindings, rejected = reject_ambiguous(proposed)
    for value in rejected:
        issue('duplicate_target_or_location', value['locationCode'])
    bindings.sort(key=lambda b: (b['cadId'], b['level'], b['column']))

    # Verify ground IDs against original floor attributes. No semantic bridge is
    # present from A01..A54 / SEQ to WMS TS/TMP codes; never infer one by position.
    floor_codes = set()
    for f in read_json(floor_path)['storage']:
        source = attrs.get(f['source_handles'][-1], {})
        values = source.get('attributes', {})
        if values.get('ZONE_CODE') and values.get('SEQ'):
            floor_codes.add(values['ZONE_CODE'] + '-' + values['SEQ'])
    floor_direct_matches = sum(c in wms or ('GHS-' + c) in wms for c in floor_codes)
    issue('floor_business_code_bridge_missing', 'CAD A01..A54/SEQ vs WMS TS/TMP; no verified link', floor_count)
    return {
        'schemaVersion': 1, 'warehouseId': 108, 'warehouseCode': 'GHS_CA_US',
        'sourceCadSha256': sha(cad_path), 'sourceInventorySha256': sha(csv_path),
        'sourceHashes': {str(p.relative_to(root)).replace('\\', '/'): sha(p)
                         for p in (scene_path, slot_path, layout_path, model_path, floor_path, registry_path, capacity_path)},
        'rule': {'id': RULE,
                 'description': 'CAD BLOCK_CODE/SEQ 或经原图R1轴文字及R02/R03双排同档核对的编号 + 每跨三个托位 + 由实际高度推定物理层；核对 WMS 完整编码、库区 450/454、horizontal_num、location_layer 和当前场景身份/位置/网格。',
                 'physicalVerification': '按编码和几何规则推断，未现场核验；不是直接读取 CAD 中每个完整 WMS 库位码。',
                 'assumptions': ['档内 C1/C2/C3 沿 CAD 档号递增方向排列；现场标签方向尚未确认。',
                                 '通道上方货位沿用同规格完整货架的物理层号：A 上两层为 3/4，B 上六层为 7–12。'],
                 'unknownPolicy': '未映射不代表空位，不应用库存占用状态；保留可检索的 WMS 档案。'},
        'bindings': bindings,
        'issues': {'counts': dict(problems), 'examples': dict(examples),
                   'sceneRackInstances': rack_count, 'sceneRackSlots': total_rack_slots,
                   'sceneFloorSlots': floor_count, 'mappedRackSlots': len(bindings),
                   'mappedFloorSlots': 0, 'unmappedSceneSlots': total_rack_slots + floor_count - len(bindings),
                   'ruleInferredBindings': len(bindings), 'fieldConfirmedBindings': 0,
                   'cadIncreasingSequenceRows': len(ordered_rows),
                   'wmsLocations': sum(len(v) for v in wms.values()),
                   'unmappedWmsLocations': sum(len(v) for v in wms.values()) - len(bindings),
                   'floorDirectCodeMatches': floor_direct_matches}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv', type=Path, required=True)
    parser.add_argument('--cad', type=Path, required=True)
    parser.add_argument('--workbook', type=Path, help='CAD 2.4 库位明细（含 rack_beams 和 floor_pallets）')
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    current_groups = read_json(args.root / 'Content/GHSTwinUI/data/scene-bindings.json')['groups']
    if any(g['mesh'].startswith('SM_GHS_V2Rack_CAD24_') for g in current_groups):
        if not args.workbook:
            parser.error('当前场景使用 CAD 2.4，请通过 --workbook 指定配套库位明细')
        import bind_cad24
        result = bind_cad24.build(args.csv, args.cad, args.workbook, args.root)
    else:
        if args.workbook:
            parser.error('请先生成 CAD 2.4 的场景和托位清单')
        result = build(args.csv, args.cad, args.root)
    dest = args.output or args.root / 'Content/GHSTwinUI/data/inventory-bindings.json'
    dest.parent.mkdir(parents=True, exist_ok=True)
    from import_inventory import refresh_floor_zones, write_payload
    if result['rule']['id'] == 'cad24-beam-position' and not args.output:
        refresh_floor_zones(args.root/'Content/GHSTwinUI/data/inventory')
    write_payload(dest, result)
    print(json.dumps({'output': str(dest), **result['issues']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
