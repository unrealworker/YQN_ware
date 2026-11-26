"""Join a CAD 2.4 rack's authored position, beam schedule and WMS snapshot."""
from collections import Counter, defaultdict
import csv
import math
import re

from openpyxl import load_workbook

from build_bindings import canonical_scene_groups, dxf_insert_attributes, index_locations, read_json, sha, transform_contract


AREAS = {'R': '450', 'SR': '454', 'T': '481', 'WALL': '519'}


def read_workbook(path):
    book = load_workbook(path, read_only=True, data_only=True)
    result = defaultdict(dict)
    floor = {}
    try:
        rows = book['rack_beams'].values
        header = next(rows)
        for cells in rows:
            beam = dict(zip(header, cells))
            key = beam['rack_code'], beam['序号']
            level = beam['层']
            if (beam['warehouse'] != 'GHS' or level in result[key]
                    or beam['beam_code'] != f'{key[0]}_{key[1]}_{level}'):
                raise ValueError(f'Conflicting workbook beam {key} L{level}')
            result[key][level] = beam
        values = book['floor_pallets'].values
        header = next(values)
        for cells in values:
            pallet = dict(zip(header, cells))
            key = pallet['pallet_code'], pallet['序号']
            if key in floor or pallet['warehouse'] != 'GHS':
                raise ValueError(f'Conflicting workbook floor pallet {key}')
            floor[key] = pallet
    finally:
        book.close()
    return result, floor


def cad_levels(attributes):
    levels = {}
    for name in ('BEAM_CODE_01', 'BEAM_CODE_02', 'BEAM_CODE_03', 'BEAM_CODE_04'):
        value = attributes.get(name, '').strip()
        if not value:
            continue
        match = re.fullmatch(r'L(\d+)(?:~L(\d+))?:(\w+)', value)
        if not match:
            raise ValueError(f'Unrecognised CAD beam expression {value!r}')
        first, last = int(match[1]), int(match[2] or match[1])
        if first < 1 or last < first or any(n in levels for n in range(first, last + 1)):
            raise ValueError(f'Conflicting CAD beam range {value!r}')
        levels.update(dict.fromkeys(range(first, last + 1), match[3]))
    return levels


def verify_schedule(racks, source, beams):
    """Enforce a bijection at the bay level before proposing any slot joins."""
    by_row = defaultdict(dict)
    for rack in racks.values():
        cid = rack['id']
        insert = source[cid.removeprefix('CAD_24_')]
        attrs = insert['attributes']
        if not attrs.get('BLOCK_CODE'):
            continue
        key = attrs['BLOCK_CODE'], int(attrs['SEQ'])
        if key != (rack['row_code'], int(rack['bay_sequence'])) or key[1] in by_row[key[0]]:
            raise ValueError(f'Non-unique or conflicting CAD bay {cid} {key}')
        schedule = beams[key]
        levels = cad_levels(attrs)
        if levels != {n: beam['beam_key_code'] for n, beam in schedule.items()}:
            raise ValueError(f'CAD and workbook level schedules differ at {key}')
        for level, beam in schedule.items():
            if (math.dist(insert['position'][:2], (beam['cd_x'], beam['cd_y'])) > .001
                    or beam['库位数量'] != (0 if levels[level] == 'underpass' else 3)):
                raise ValueError(f'CAD and workbook position or slot count differs at {key} L{level}')
        by_row[key[0]][key[1]] = rack
    if set(beams) != {(row, bay) for row, entries in by_row.items() for bay in entries}:
        raise ValueError('Workbook and CAD bay sets differ')
    return by_row


def column_directions(by_row):
    """Orient local mesh columns using actual centres of consecutively numbered bays."""
    directions = {}
    for row, entries in by_row.items():
        racks = [entries[n] for n in sorted(entries)]
        first, last = racks[0]['position_m'], racks[-1]['position_m']
        dx, dy = last[0] - first[0], last[1] - first[1]
        distance = math.hypot(dx, dy)
        if distance < 1:
            raise ValueError(f'Cannot establish column direction for {row}')
        dx, dy = dx / distance, dy / distance
        previous = -math.inf
        for rack in racks:
            x, y = rack['position_m'][:2]
            projected = dx * x + dy * y
            angle = math.radians(rack['rotation_deg'])
            cosine = dx * math.cos(angle) + dy * math.sin(angle)
            if abs(cosine) < .99 or projected <= previous:
                raise ValueError(f'Conflicting orientation or bay order at {rack["id"]} in {row}')
            directions[rack['id']] = 1 if cosine > 0 else -1
            previous = projected
    return directions


def location_lookup(rows):
    by_code = index_locations(rows)
    result = defaultdict(list)
    for code, records in by_code.items():
        match = re.fullmatch(r'GHS-(R\d{2}|SR-\d{2}|T\d{2}|WALL\d{2})-(\d+)-(\d+)', code)
        if match:
            result[match[1].replace('-', ''), int(match[2]), int(match[3])].extend(records)
    return result, by_code


def floor_bindings(layout, source, workbook, groups, wms):
    instances = {i['id']: (i, g['mesh']) for g in groups
                 if g['mesh'].startswith('SM_GHS_Presentation_Cargo') for i in g['instances']}
    if set(instances) != {f['id'] for f in layout}:
        raise ValueError('CAD and scene floor pallet sets differ')
    zones = Counter(p['attrs']['ZONE_CODE'] for p in layout)
    found, counts, bindings = set(), Counter(), []
    for p in layout:
        cid = p['id']
        insert = source[cid.removeprefix('CAD_24_')]
        attrs = insert['attributes']
        zone = attrs['ZONE_CODE']
        key = zone, int(attrs['SEQ'])
        ref = workbook[key]
        if (key in found or zone != p['attrs']['ZONE_CODE'] or key[1] != int(p['attrs']['SEQ'])
                or math.dist(insert['position'][:2], (ref['cd_x'], ref['cd_y'])) > .001):
            raise ValueError(f'Conflicting floor pallet {key}')
        found.add(key)
        instance, mesh = instances[cid]
        # Floor meshes span their width along +X; CAD floor symbol +X is depth.
        if (math.dist(instance['position_m'][:2], p['position_m'][:2]) > .001
                or abs(math.remainder(instance['rotation_deg'] - p['rotation_deg'] - 90, 360)) > .001):
            raise ValueError(f'Floor transform differs from CAD for {cid}')
        candidates = wms.get(f'{zone}-{attrs["SEQ"]}', [])
        if not candidates:
            candidates = wms.get(zone, [])
            if candidates and zones[zone] > 1:
                counts['floor_zone_shared_by_pallets'] += 1
                continue
        if len(candidates) != 1:
            counts['floor_code_missing_or_ambiguous'] += 1
            continue
        loc = candidates[0]
        if (loc['warehouse_id'], loc['warehouse_code'], loc['warehouse_area_id']) != ('108', 'GHS_CA_US', '513'):
            counts['floor_wms_metadata_conflict'] += 1
            continue
        bindings.append(dict(cadId=cid, level=0, column=0, locationCode=loc['location_code'],
                             locationId=loc['location_id'], evidence=f'{zone}/{attrs["SEQ"]}',
                             confidence='rule_inferred', expectedPositionM=instance['position_m'],
                             expectedWorldRotationDeg=[0,-instance['rotation_deg'],0],
                             expectedWorldScale=instance['scale'], expectedMesh=mesh))
    if found != set(workbook):
        raise ValueError('Workbook and CAD floor pallets differ')
    return bindings, counts


def metadata_matches(loc, row, family, bay, position, level):
    if (loc['warehouse_id'] != '108' or loc['warehouse_code'] != 'GHS_CA_US'
            or loc['warehouse_area_id'] != AREAS[family] or loc['location_layer'] != str(level)):
        return False
    if loc['horizontal_num']:
        return loc['horizontal_num'] == str(bay)
    # WALL archive: horizontal_num absent, location_row stores the running
    # pallet number and location_col the numeric part of the named wall rack.
    return family == 'WALL' and loc['location_row'] == str(position) and loc['location_col'] == str(int(row[4:]))


def build(csv_path, cad_path, workbook, root):
    data = root / 'Content/GHSTwinUI/data'
    layout_path = root / 'SourceAssets/GHS/CAD24/racks.json'
    scene_path, slots_path, capacity_path = [data / name for name in ('scene-bindings.json', 'rack-slots.json', 'storage-capacity.json')]
    layout = read_json(layout_path)
    cad_sha = sha(cad_path)
    csv_sha = sha(csv_path)
    if cad_sha != layout['sha256']:
        raise ValueError('Original DXF differs from the layout source')
    index = read_json(data/'inventory/index.json')
    if csv_sha != index['snapshotId']:
        raise ValueError('Import this WMS snapshot before building inventory bindings')
    del index
    racks = {r['id']: r for r in layout['racks']}
    beams, floor = read_workbook(workbook)
    source = dxf_insert_attributes(cad_path)
    directions = column_directions(verify_schedule(racks, source, beams))
    with csv_path.open(encoding='utf-8-sig', newline='') as stream:
        wms, by_code = location_lookup(csv.DictReader(stream))
    wms_count = sum(map(len, by_code.values()))
    groups = canonical_scene_groups(read_json(scene_path))
    capacity = read_json(capacity_path)
    definitions = {g['name']: g for g in capacity['meshes']}
    models = {g['source_mesh']: g for g in capacity['groups'] if g['kind'] == 'rack'}
    bindings, seen_racks, used_ids = [], set(), set()
    counts, families = Counter(), Counter()
    floor_count = 0
    for group in groups:
        mesh = group['mesh']
        if mesh.startswith('SM_GHS_Presentation_Cargo'):
            floor_count += len(group['instances'])
        if mesh not in models:
            continue
        model = models[mesh]
        slots = definitions[model['mesh']]['cargo_stacks']
        by_level = defaultdict(list)
        for slot in slots:
            by_level[slot['physical_level']].append(slot)
        for instance in group['instances']:
            cid = instance['id']
            rack = racks[cid]
            if cid in seen_racks:
                raise ValueError(f'Duplicate scene rack {cid}')
            seen_racks.add(cid)
            if cid not in directions:
                counts['cad_bay_without_identifier'] += len(slots)
                continue
            # The common transform checker validates scale and final capacity mesh.
            contract = transform_contract(instance, mesh, instance, model)
            if (not contract or math.dist(instance['position_m'][:2], rack['position_m'][:2]) > .001
                    or abs(math.remainder(instance['rotation_deg'] - rack['rotation_deg'], 360)) > .001):
                raise ValueError(f'Runtime transform differs from CAD for {cid}')
            row, bay = rack['row_code'], int(rack['bay_sequence'])
            family = re.sub(r'\d+$', '', row)
            schedule = beams[row, bay]
            for physical_level, beam in schedule.items():
                if beam['库位数量'] != len(by_level.get(physical_level, [])):
                    raise ValueError(f'Model slot count differs from CAD at {beam["beam_code"]}')
            for physical_level, level_slots in by_level.items():
                if physical_level not in schedule:
                    counts['no_cad_beam_at_visual_level'] += len(level_slots)
                    continue
                beam = schedule[physical_level]
                ordered = sorted(level_slots, key=lambda s: directions[cid] * s['pallet_center_x_m'])
                if len({s['pallet_center_x_m'] for s in ordered}) != len(ordered):
                    raise ValueError(f'Overlapping model columns in {cid}')
                for n, slot in enumerate(ordered, start=1):
                    position = 3 * (bay - 1) + n
                    matches = wms.get((row, position, physical_level), [])
                    if len(matches) != 1:
                        counts['wms_code_missing_or_ambiguous'] += 1
                        continue
                    loc = matches[0]
                    if not metadata_matches(loc, row, family, bay, position, physical_level):
                        counts['wms_metadata_conflict'] += 1
                        continue
                    if loc['location_id'] in used_ids:
                        raise ValueError(f'Duplicate proposed WMS assignment {loc["location_id"]}')
                    used_ids.add(loc['location_id'])
                    bindings.append(dict(cadId=cid, level=slot['level'], column=slot['column'],
                        locationCode=loc['location_code'], locationId=loc['location_id'],
                        confidence='rule_inferred', evidence=beam['beam_code'], **contract))
                    families[family] += 1
    if seen_racks != set(racks):
        raise ValueError('Scene and CAD rack sets differ')
    rack_total = sum(counts.values()) + len(bindings)
    if rack_total != capacity['rack_total_slots']:
        raise ValueError('Coverage differs from total runtime rack capacity')
    rack_matched = len(bindings)
    floor_mapped, floor_issues = floor_bindings(layout['ground'], source, floor, groups, by_code)
    bindings.extend(floor_mapped)
    counts.update(floor_issues)
    if len({b['locationId'] for b in bindings}) != len(bindings):
        raise ValueError('Conflicting WMS location assigned to several scene targets')
    return dict(schemaVersion=1, warehouseId=108, warehouseCode='GHS_CA_US',
                sourceCadSha256=cad_sha, sourceWorkbookSha256=sha(workbook), sourceInventorySha256=csv_sha,
                sourceHashes={p.relative_to(root).as_posix(): sha(p) for p in (layout_path, scene_path, slots_path, capacity_path)},
                rule=dict(id='cad24-beam-position', description='以 CAD 的 BLOCK_CODE、SEQ、BEAM_CODE 为准，核对工作表梁号、插入点、层和每层三托位。档内按排的增号方向编号，WMS 分库区和编码族复核。', physicalVerification='规则关联，档内标牌方向未经现场核验'),
                issues=dict(counts=dict(counts), mappedByFamily=dict(families), sceneRackInstances=len(racks),
                            sceneRackSlots=rack_total, sceneFloorSlots=floor_count, mappedRackSlots=rack_matched,
                            mappedFloorSlots=len(floor_mapped), unmappedSceneSlots=rack_total+floor_count-len(bindings),
                            ruleInferredBindings=len(bindings), fieldConfirmedBindings=0, wmsLocations=wms_count,
                            unmappedWmsLocations=wms_count-len(bindings)),
                bindings=sorted(bindings, key=lambda v: (v['cadId'], v['level'], v['column'])))
