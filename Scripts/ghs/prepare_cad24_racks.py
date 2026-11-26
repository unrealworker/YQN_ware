"""Replace rack entries in the three packaged scene manifests from CAD and verified meshes."""
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / 'Content/GHSTwinUI/data'
SOURCE = ROOT / 'SourceAssets/GHS/CAD24/racks.json'
BUILT = ROOT / 'Saved/GHS_CAD24/Models/meshes.json'


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def save(path, data):
    path.write_bytes(json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf8'))


def prepare_racks():
    cad = read(SOURCE)
    built = read(BUILT)
    assert built['cad_sha256'] == hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    scene, slots, cap = [read(RUNTIME / name) for name in ['scene-bindings.json','rack-slots.json','storage-capacity.json']]
    scene['groups'] = [g for g in scene['groups'] if not g['mesh'].startswith('SM_GHS_V2Rack_')]
    slots['meshes'] = [g for g in slots['meshes'] if not g['name'].startswith('SM_GHS_V2Rack_')]
    cap['groups'] = [g for g in cap['groups'] if g['kind'] != 'rack']
    cap['meshes'] = [g for g in cap['meshes'] if g['kind'] != 'rack']
    base = 0
    represented = set()
    for mesh in built['meshes']:
        variant = mesh['variant']
        source = mesh['source_mesh']
        label = 'GHS_Rack_CAD24_' + variant
        instances = []
        for rack in cad['racks']:
            if rack['variant'] != variant:
                continue
            assert rack['id'] not in represented and rack['id'].startswith('CAD_24_')
            represented.add(rack['id'])
            xy = rack['position_m']
            instances.append(dict(id=rack['id'], position_m=[xy[0], xy[1], 0], rotation_deg=rack['rotation_deg'],
                scale=[1,1,1], row_code=rack['row_code'], bay_sequence=int(rack['bay_sequence'] or 0), variant=variant))
        count = len(instances)
        scene['groups'].append(dict(actor=label, mesh=source, count=count, instances=instances))
        cap['groups'].append(dict(actor=label, mesh=mesh['name'], source_mesh=source, kind='rack', count=count,
                                  base_slot=base, slots_per_instance=len(mesh['slots'])))
        cap['meshes'].append({key:mesh[key] for key in ('name','source_mesh','kind','cargo_width_m','cargo_depth_m','cargo_stacks','slots')})
        slots['meshes'].append(dict(name=source, cargo_width_m=mesh['cargo_width_m'], cargo_depth_m=mesh['cargo_depth_m'],
                                    cargo_stacks=mesh['cargo_stacks']))
        base += count * len(mesh['slots'])
    assert len(represented) == len(cad['racks']) and math.gcd(97, base) == 1 and base*97+17 < 2**24
    cap['rack_total_slots'] = base
    for data, filename in [(scene,'scene-bindings.json'),(slots,'rack-slots.json'),(cap,'storage-capacity.json')]:
        data['rackSource'] = 'SourceAssets/GHS/CAD24/racks.json'
        data['rackSourceSha256'] = built['cad_sha256']
        save(RUNTIME / filename, data)
    print('CAD24 rack bays, slots:', len(represented), base)


if __name__ == '__main__':
    prepare_racks()
