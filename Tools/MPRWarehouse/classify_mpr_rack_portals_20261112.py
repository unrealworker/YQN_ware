"""Join rack ACI evidence and infer passage families from both adjacent bays.

Only same-axis, physically adjoining bays are evidence. Conflicting neighbours
stay unresolved; this module never moves, edits or imports a UE object.
"""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT/'Saved/MPR/interior_cad_20261112'
MAPPING = BASE/'rack_mapping/instance_mapping.json'
INSERTS = BASE/'rack_truth/modelspace_inserts.json'
OUT = BASE/'rack_mapping'
PLACEMENT = ROOT/'SourceAssets/MPR/interior_cad_20261112/racks/placement_manifest.json'
FAMILIES = {3: '16', 4: '20', 6: '17+1', 2: '9', 90: '5', 40: '7'}
FAMILY_CODES = {'16': 'F16', '20': 'F20', '17+1': 'F17P1', '9': 'F9', '5': 'F5', '7': 'F7'}


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def run():
    mapping_document = read(MAPPING)
    mapped = mapping_document['instances']
    inserts = {r['handle']: r for r in read(INSERTS)}
    by_handle = {r['source_handle']: r for r in mapped}
    assert len(mapped) == len(by_handle) == 2867
    colors = {h: inserts[h]['color'] for h in by_handle}
    assert all(c in FAMILIES or c == 5 for c in colors.values())
    results = []
    for row in mapped:
        handle = row['source_handle']
        source = inserts[handle]
        assert source['block'] == row['source_block'] and source['layer'] == 'W_RACK'
        color = colors[handle]
        record = dict(source_handle=handle, source_block=row['source_block'], aci=color,
                      source_position_m=row['source_position_m'],
                      family=FAMILIES.get(color), passage_variant=color == 5,
                      evidence='Direct INSERT ACI joined to rack elevation family legend', neighbours=[])
        if color == 3:
            record['evidence'] = 'ACI 3 family association inferred from remaining 16-level family and plan zone; needs plan-label corroboration'
        if color == 5:
            angle = math.radians(row['source_rotation_deg']+90)
            axis, normal = (math.cos(angle), math.sin(angle)), (-math.sin(angle), math.cos(angle))
            candidates = []
            for other in mapped:
                h = other['source_handle']
                if colors[h] == 5:
                    continue
                diff = [other['source_position_m'][i]-row['source_position_m'][i] for i in (0, 1)]
                along = sum(diff[i]*axis[i] for i in (0, 1))
                cross = sum(diff[i]*normal[i] for i in (0, 1))
                rotation_error = abs(math.sin(math.radians(other['source_rotation_deg']-row['source_rotation_deg'])))
                if abs(cross) < .002 and rotation_error < 1e-7:
                    candidates.append(dict(source_handle=h, aci=colors[h], family=FAMILIES[colors[h]],
                                           along_m=along, cross_m=cross,
                                           frame_edge_gap_m=abs(along)-(row['source_size_m'][1]+other['source_size_m'][1])/2))
            negative = sorted((n for n in candidates if n['along_m'] < 0), key=lambda n: -n['along_m'])
            positive = sorted((n for n in candidates if n['along_m'] > 0), key=lambda n: n['along_m'])
            assert negative and positive, ('Passage lacks two collinear neighbours', handle)
            neighbours = [negative[0], positive[0]]
            # Adjacent bays share a three-inch upright; tolerate CAD draft noise.
            assert all(abs(n['frame_edge_gap_m']+.0762) < .02 for n in neighbours), (handle, neighbours)
            record['neighbours'] = neighbours
            families = set(n['family'] for n in neighbours)
            if len(families) == 1:
                record.update(family=next(iter(families)), evidence='Both directly adjoining collinear bays have the same ACI/family')
            else:
                record.update(family=None, evidence='Conflicting families on equally adjoining bays; assignment intentionally unresolved')
        results.append(record)
    portals = [r for r in results if r['passage_variant']]
    conflicts = [r for r in portals if r['family'] is None]
    assert len(portals) == 141
    assert {r['source_handle'] for r in conflicts} == {'2CFE06', '2CFECC'}
    report = dict(schema_version=1, success=True, instance_count=len(results),
                  family_color_legend={str(k): v for k, v in FAMILIES.items()},
                  color_counts=dict(Counter(str(r['aci']) for r in results)),
                  passage_count=len(portals), unambiguous_passage_count=len(portals)-len(conflicts),
                  passage_family_counts=dict(Counter(str(r['family']) for r in portals)),
                  conflict_handles=[r['source_handle'] for r in conflicts],
                  maximum_neighbour_distance_m=max(abs(n['along_m']) for r in portals for n in r['neighbours']),
                  maximum_neighbour_cross_axis_error_m=max(abs(n['cross_m']) for r in portals for n in r['neighbours']),
                  inputs_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in (MAPPING, INSERTS)},
                  scope='Offline CAD/scene mapping only; no runtime/editor writes',
                  limitation='ACI 3 to 16-level association remains a semantic inference; two ACI 5 transition passages need source confirmation')
    OUT.mkdir(parents=True, exist_ok=True)
    for name, value in [('portal_classification.json', dict(report=report, passages=portals, conflicts=conflicts)),
                        ('rack_family_candidates.json', dict(report=report, instances=results))]:
        (OUT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    placement_rows = []
    for row in results:
        source = by_handle[row['source_handle']]
        family = row['family'] or 'Unresolved'
        family_code = FAMILY_CODES.get(row['family'], 'FUnresolved')
        unresolved = row['family'] is None
        inferred_portal = row['passage_variant'] and row['family'] == '16'
        width = 192 if source['source_block'] == 'RACK_42D_192B' else 144
        variant = 'Passage' if row['passage_variant'] else 'Standard'
        placement_rows.append(dict(source_handle=row['source_handle'], family=family,
                                   family_code=family_code,
                                   passage_variant=row['passage_variant'], width_inches=width,
                                   resolved=not unresolved, requires_source_confirmation=unresolved or inferred_portal,
                                   status='unresolved_common_frame' if unresolved else 'inferred_passage_clearance' if inferred_portal else 'inferred_color_family' if row['family'] == '16' else 'mapped',
                                   mesh_name=f'SM_MPR_CADRack_{family_code}_W{width}_{variant}',
                                   actor_guid=source['actor_guid'], actor_label=source['actor_label'],
                                   component_name=source['component_name'], instance_index=source['instance_index'],
                                   original_transform=source['original_transform'], existing_mesh=source['existing_mesh'],
                                   basis=dict(aci=row['aci'], method='mixed_neighbour_families' if unresolved else 'two_adjoining_bays' if row['passage_variant'] else 'insert_aci',
                                              neighbours=row['neighbours'] if row['passage_variant'] else [],
                                              color_family_is_inferred=row['family'] == '16',
                                              candidate_families=sorted({n['family'] for n in row['neighbours']}) if unresolved else [family],
                                              geometry_assumption='16-family passage front elevation is not explicit; retain only upper four levels on the standard 20-inch pitch, with provisional first beam bottom at 6.7854 m.' if inferred_portal else None,
                                              recommendation='Use common upright frame only: no beam elevations coincide between families 20 and 9. Frame W3.81/D1.0668/H9.154 m; greater passage clearance 5.210463 m. Do not choose family 20/9 automatically.' if unresolved else None)))
    for row in placement_rows:
        row['basis'] = {key: value for key, value in row['basis'].items() if value is not None and value != []}
    placement_report = mapping_document['report']
    source_hashes = {k: v for k, v in placement_report['inputs_sha256'].items() if k.lower().endswith('.dxf')}
    assert len(source_hashes) == 1
    source_file, source_sha = next(iter(source_hashes.items()))
    manifest = dict(schema_version=1, map=placement_report['map'], map_sha256=placement_report['map_sha256'],
                    source_file=source_file, source_sha256=source_sha,
                    source_layout='SourceAssets/MPR/mpr_cad_layout.json',
                    source_layout_sha256=placement_report['inputs_sha256'][str((ROOT/'SourceAssets/MPR/mpr_cad_layout.json').relative_to(ROOT))],
                    snapshot_sha256=placement_report['inputs_sha256'][str((BASE/'preservation/baseline.json.gz').relative_to(ROOT))],
                    instance_count=len(placement_rows), unresolved_count=len(conflicts),
                    unresolved_handles=report['conflict_handles'],
                    inferred_passage_count=sum(r['status'] == 'inferred_passage_clearance' for r in placement_rows),
                    source_confirmation_passage_count=sum(r['requires_source_confirmation'] for r in placement_rows),
                    color_family_inference_count=sum(r['basis']['color_family_is_inferred'] for r in placement_rows),
                    basis_methods=dict(insert_aci='Direct INSERT ACI joined to CAD elevation family legend; ACI 3 to family 16 is inference by remaining family and plan region.',
                                       two_adjoining_bays='Both collinear, physically adjoining ordinary bays carry the same family color.',
                                       mixed_neighbour_families='Both bays physically adjoin but their families differ. Use documented common-frame geometry only.'),
                    constraints=['Keep every original instance transform', 'Preserve existing map and unrelated actors',
                                 'Create MPR-private meshes; do not overwrite shared GHS meshes or materials',
                                 'Unresolved family entries use explicitly labelled common-frame geometry, never an assumed F20/F9 family'],
                    existing_groups=mapping_document['groups'], instances=placement_rows)
    PLACEMENT.parent.mkdir(parents=True, exist_ok=True)
    # One compact row per instance remains readable in diffs without repeating
    # the full common evidence narrative nearly three thousand times.
    rows = manifest.pop('instances')
    header = json.dumps(manifest, ensure_ascii=False, indent=2).rstrip()[:-1]
    text = header+',\n  "instances": [\n'+',\n'.join('    '+json.dumps(r, ensure_ascii=False, separators=(',', ':')) for r in rows)+'\n  ]\n}\n'
    PLACEMENT.write_text(text, encoding='utf8')
    assert len(read(PLACEMENT)['instances']) == 2867
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == '__main__':
    run()
