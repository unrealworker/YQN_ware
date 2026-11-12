"""Audit CAD rack handles against an existing UE snapshot without editing UE.

This produces a strict bijection, not a nearest-neighbour guess. The CAD plan
contains two footprint blocks but does not identify rack elevation families;
that separate semantic assignment must be joined by source handle later.
"""
from collections import Counter, defaultdict
from copy import deepcopy
import gzip
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT/'Saved/MPR/interior_cad_20261112/preservation'
OUT = ROOT/'Saved/MPR/interior_cad_20261112/rack_mapping'
LAYOUT = ROOT/'SourceAssets/MPR/mpr_cad_layout.json'
EXTRACTED = ROOT/'SourceAssets/MPR/mpr_cad_extracted.json'
SOURCE = Path(r'D:\Data\仓库数据\MPR\平面布局图_MPR规划图V1.1_ALL-IN-ONE_0921.dxf')
MAP = '/Game/Maps/MPR_CAD_Warehouse_B50B57'
IDENTITY = dict(translation_cm=[0., 0., 0.], rotation_xyzw=[0., 0., 0., 1.], scale=[1., 1., 1.])
MESHES = {
    'RACK_42D_144B': '/Game/GHSRefinementV2/Meshes/SM_GHS_V2Rack_A.SM_GHS_V2Rack_A',
    'RACK_42D_192B': '/Game/MPRWarehouse/Storage/Meshes/SM_MPR_Rack_42D_192.SM_MPR_Rack_42D_192',
}


def read(path):
    data = path.read_bytes()
    return json.loads((gzip.decompress(data) if path.suffix == '.gz' else data).decode('utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def error(left, right):
    return max(abs(a-b) for a, b in zip(left, right))


def quaternion_error(left, right):
    return min(error(left, right), error(left, [-x for x in right]))


def expected_pose(row):
    half = math.radians(-row['mesh_long_x_yaw_deg'])/2
    return dict(translation_cm=[row['position_m'][0]*100, -row['position_m'][1]*100, 0.],
                rotation_xyzw=[0., 0., math.sin(half), math.cos(half)], scale=[1., 1., 1.])


def position_key(translation):
    return tuple(round(x, 3) for x in translation)


def frame_bounds(pose, long_m, depth_m):
    """World XY AABB of the declared frame, excluding cargo overhang."""
    q = pose['rotation_xyzw']
    angle = 2*math.atan2(q[2], q[3])
    cs, sn = math.cos(angle), math.sin(angle)
    points = []
    for x in (-long_m*50, long_m*50):
        for y in (-depth_m*50, depth_m*50):
            x1, y1 = x*pose['scale'][0], y*pose['scale'][1]
            points.append([pose['translation_cm'][0]+cs*x1-sn*y1,
                           pose['translation_cm'][1]+sn*x1+cs*y1])
    return [[min(p[i] for p in points) for i in (0, 1)],
            [max(p[i] for p in points) for i in (0, 1)]]


def run():
    baseline_path = BASE/'baseline.json.gz'
    baseline, layout, extracted = read(baseline_path), read(LAYOUT), read(EXTRACTED)
    assert baseline['map'] == MAP
    assert baseline['dirty_maps'] == baseline['dirty_content'] == []
    rack_actors = [a for a in baseline['actors'] if a['folder'] == 'MPR/Storage/Racks']
    assert {a['guid']: a for a in rack_actors} == {a['guid']: a for a in read(BASE/'racks.json')}
    assert len(rack_actors) == 27
    source_rows = {r['id']: r for r in extracted['racks'] if r['block'] in MESHES}
    assert len(source_rows) == len(layout['racks']) == 2867
    assert len({r['id'] for r in layout['racks']}) == 2867
    instances = defaultdict(list)
    groups = []
    for actor in rack_actors:
        assert actor['transform'] == IDENTITY and actor['attachment_parent'] is None
        assert not actor['hidden'] and not actor['tick_enabled']
        components = [c for c in actor['components'] if 'instance_transforms' in c]
        assert len(components) == 1
        c = components[0]
        assert c['transform'] == IDENTITY and c['num_custom_data_floats'] == 0
        assert c['mesh'] in MESHES.values()
        assert c['instance_count'] == len(c['instance_transforms'])
        groups.append(dict(actor_guid=actor['guid'], actor_label=actor['label'],
                           component_name=c['name'], mesh=c['mesh'], materials=c['materials'],
                           instance_count=c['instance_count'], actor_transform=actor['transform'],
                           component_transform=c['transform']))
        for index, tr in enumerate(c['instance_transforms']):
            instances[position_key(tr['translation_cm'])].append((actor, c, index, tr))
    assert sum(len(v) for v in instances.values()) == 2867
    assert all(len(v) == 1 for v in instances.values()), 'Duplicate live rack centres'
    mapping, seen, seen_handles = [], set(), set()
    maxima = dict(translation_cm=0., quaternion=0., scale=0., footprint_aabb_cm=0.)
    for row in layout['racks']:
        expected = expected_pose(row)
        found = instances.get(position_key(expected['translation_cm']), [])
        assert len(found) == 1, ('Missing/ambiguous exact CAD centre', row['id'])
        actor, component, index, actual = found[0]
        identity = (actor['guid'], component['name'], index)
        assert identity not in seen, ('Scene instance assigned twice', identity)
        seen.add(identity)
        assert len(row['source_handles']) == 1
        handle = row['source_handles'][0]
        assert handle not in seen_handles
        seen_handles.add(handle)
        assert component['mesh'] == MESHES[row['block']], ('Footprint block uses wrong mesh', row['id'])
        errors = dict(translation_cm=error(actual['translation_cm'], expected['translation_cm']),
                      quaternion=quaternion_error(actual['rotation_xyzw'], expected['rotation_xyzw']),
                      scale=error(actual['scale'], [1., 1., 1.]))
        assert errors['translation_cm'] < .001 and errors['quaternion'] < 1e-8 and errors['scale'] < 1e-8
        source = source_rows[row['id']]
        assert source['block'] == row['block'] and source['source_handles'] == row['source_handles']
        lo, hi = source['bounds_dxf']
        ox, oy = layout['origin_dxf_xy']
        unit_cm = layout['units_to_m']*100
        cad_bounds = [[(lo[0]-ox)*unit_cm, -(hi[1]-oy)*unit_cm],
                      [(hi[0]-ox)*unit_cm, -(lo[1]-oy)*unit_cm]]
        declared_bounds = frame_bounds(actual, row['size_m'][1], row['size_m'][0])
        errors['footprint_aabb_cm'] = max(error(a, b) for a, b in zip(cad_bounds, declared_bounds))
        assert errors['footprint_aabb_cm'] < .001, ('Frame footprint differs from source bounds', row['id'], errors)
        for key, value in errors.items():
            maxima[key] = max(maxima[key], value)
        mapping.append(dict(source_handle=handle, cad_id=row['id'], source_handles=row['source_handles'],
                            source_block=row['block'], source_position_m=row['position_m'],
                            source_size_m=row['size_m'], source_rotation_deg=row['rotation_deg'],
                            actor_guid=actor['guid'], actor_label=actor['label'], actor_path=actor['path'],
                            component_name=component['name'], instance_index=index,
                            existing_mesh=component['mesh'], original_transform=deepcopy(actual),
                            expected_transform=expected, cad_footprint_bounds_ue_cm=cad_bounds,
                            declared_frame_bounds_ue_cm=declared_bounds, errors=errors,
                            elevation_family=None, passage_variant=None))
    assert len(seen) == len(seen_handles) == len(mapping) == 2867
    inputs = {str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p): sha(p)
              for p in (baseline_path, BASE/'racks.json', LAYOUT, EXTRACTED, SOURCE)}
    report = dict(schema_version=1, success=True, map=MAP, map_sha256=baseline['map_file_sha256'],
                  baseline_actor_count=len(baseline['actors']), rack_group_count=len(groups),
                  rack_instance_count=len(mapping), unique_cad_handles=len(seen_handles),
                  unique_scene_instances=len(seen), source_block_counts=dict(Counter(r['source_block'] for r in mapping)),
                  existing_mesh_counts=dict(Counter(r['existing_mesh'] for r in mapping)), maximum_errors=maxima,
                  inputs_sha256=inputs,
                  scope='Offline analysis only; no UE editor/runtime or content package writes.',
                  bounds_validation='Declared frame footprint versus extracted CAD block AABB; not a native mesh geometry validation.',
                  remaining_semantics='Elevation family and passage variants require separate source-CAD annotation evidence; no family is guessed from footprint block.')
    OUT.mkdir(parents=True, exist_ok=True)
    for name, value in [('instance_mapping.json', dict(report=report, groups=groups, instances=mapping)),
                        ('mapping_report.json', report)]:
        (OUT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == '__main__':
    run()
