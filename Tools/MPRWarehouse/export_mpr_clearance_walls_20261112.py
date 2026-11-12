"""Read current wall solids from existing blend libraries; no scene/source saves."""
from pathlib import Path
import gzip
import hashlib
import json
import re
import sys
import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Tools/MPRWarehouse'))
from build_mpr_cad_windows_20261112 import template_boxes

BASE = ROOT / 'Saved/MPR/optimization_20261112'
SOURCES = [ROOT / p for p in (
    'SourceAssets/MPR/interior_cad_20261112/windows/mpr_reference_shell.blend',
    'SourceAssets/MPR/interior_cad_20261112/architecture/mpr_reference_shell.blend',
    'SourceAssets/MPR/reference_v4/architecture/mpr_reference_shell.blend')]


def main():
    baseline = json.load(gzip.open(BASE / 'baseline.json.gz', 'rt', encoding='utf8'))
    available = {}
    for path in SOURCES:
        with bpy.data.libraries.load(str(path), link=False) as (source, target):
            for name in source.objects:
                available.setdefault(name, path)
    solids, sources, actors = [], {}, []
    identity = dict(translation_cm=[0., 0., 0.], rotation_xyzw=[0., 0., 0., 1.], scale=[1., 1., 1.])
    for actor in baseline['actors']:
        for component in actor['components']:
            mesh = component.get('mesh')
            if not mesh or not re.search(r'(Facade_\d|WindowPartitions|PartitionCompletion|PedestrianDoors)', mesh):
                continue
            name = mesh.rsplit('.', 1)[-1]
            assert name in available, (name, 'Missing read-only wall source')
            assert actor['transform'] == component['transform'] == identity
            assert 'instance_transforms' not in component
            path = available[name]
            sources[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
            with bpy.data.libraries.load(str(path), link=False) as (source, target):
                target.objects = [name]
            obj = target.objects[0]
            start = len(solids)
            for i, box in enumerate(template_boxes(obj)):
                solids.append(dict(id=actor['guid'] + ':' + component['name'] + ':' + str(i),
                    actor_guid=actor['guid'], actor_label=actor['label'], component_name=component['name'],
                    mesh=mesh, role=box['role'], bounds_m=box['bounds']))
            actors.append(dict(actor_guid=actor['guid'], mesh=mesh, solid_count=len(solids)-start))
            bpy.data.objects.remove(obj, do_unlink=True)
    assert len(actors) >= 18 and solids
    out = dict(schema_version=1, map_sha256=baseline['map_file_sha256'],
               coordinate_system='CAD metres, source +Y; no UE scene mutation',
               sources_sha256=sources, actors=actors, solids=solids)
    path = BASE / 'wall_solid_boxes.json'
    path.write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')), encoding='utf8')
    print('MPR_CLEARANCE_WALL_SOLIDS', len(actors), len(solids), str(path))


if __name__ == '__main__':
    main()
