"""Two visible blue pallet bases within each original floor-load envelope.

Run in background Blender. Reuse the original pallet geometry and carton grid;
only shorten the two half-loads to make room for the middle pallet. Other storage
libraries remain untouched. Same mesh basenames retain the existing CAD keys.
"""
from pathlib import Path
import hashlib
import json
import sys
import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT/'Scripts/video_reference'))
import common

original_source = ROOT/'Scripts/video_reference/build_storage.py'
src = original_source.read_text(encoding='utf-8')
header = src[:src.index("begin_asset('SM_VR_PalletCargo')")]
header = header.replace('str(Path(__file__).resolve().parent)', 'str(ROOT/"Scripts/video_reference")')
exec(header, globals())
common.OUT = ROOT/'SourceAssets/GHS/DoublePallet'
common.OUT.mkdir(parents=True, exist_ok=True)
baseline = json.loads((ROOT/'SourceAssets/GHS/Presentation/presentation_storage.json').read_text(encoding='utf-8'))
specs = {row['name']:row for row in baseline['meshes'] if 'Cargo' in row['name']}
pallet_code = src[src.index('# Three continuous runners'):src.index('# A cubic cargo silhouette')]
metadata = {}

for suffix, layers in [('Low',2),('Mid',3),('High',4)]:
    name = 'SM_GHS_Presentation_Cargo'+suffix
    reference = specs[name]
    height = reference['bounds_m'][2][1]
    half = height/2
    collection = begin_asset(name)
    for tier, base in enumerate((0., half)):
        previous = set(collection.objects)
        exec(pallet_code, globals())
        for obj in set(collection.objects)-previous:
            obj.location.z += base
            obj.name = ('Lower' if tier == 0 else 'Upper')+' '+obj.name
        start = base+.173
        # Match the original perimeter seam's 3.031 mm vertical extent.
        top = base+half-.0030311603546143
        step = (top-start)/layers
        for ix in range(3):
            for iy in range(3):
                for iz in range(layers):
                    box('Tier%d cargo cube'%tier, ((ix-1)*1.16/3,(iy-1)*.96/3,start+(iz+.5)*step),
                        (1.16/3-.003,.96/3-.003,step-.003),cargo,.004)
        for z in [start+i*step for i in range(layers+1)]:
            curve('Tier%d horizontal seam'%tier,[(-.58,-.48,z),(.58,-.48,z),(.58,.48,z),(-.58,.48,z)],.0035,cyan,True)
        for x in [-.58,-.58+1.16/3,-.58+2*1.16/3,.58]:
            for y in [-.48,.48]:
                beam('Tier%d front seam'%tier,(x,y,start),(x,y,top),.0035,cyan,6)
            stripe('Tier%d top X grid'%tier,(x,-.48,top),(x,.48,top),.006,cyan)
        for y in [-.48,-.16,.16,.48]:
            for x in [-.58,.58]:
                beam('Tier%d side seam'%tier,(x,y,start),(x,y,top),.0035,cyan,6)
            stripe('Tier%d top Y grid'%tier,(-.58,y,top),(.58,y,top),.006,cyan)
    metadata[name] = dict(pallet_count=2, pallet_base_z_m=[0.,half], pallet_height_m=.17,
                          carton_layers_per_tier=layers, original_bounds_m=reference['bounds_m'])

save_library('double_pallet_storage')
manifest_path = common.OUT/'double_pallet_storage.json'
manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
for row in manifest['meshes']:
    row.update(metadata[row['name']])
    assert row['slots'] == specs[row['name']]['slots'], row['name']
    assert max(abs(a-b) for old,new in zip(row['original_bounds_m'],row['bounds_m']) for a,b in zip(old,new)) < 2.e-6, row
    row['sha256'] = hashlib.sha256(Path(row['fbx']).read_bytes()).hexdigest()
manifest.update(source='Scripts/video_reference/build_storage.py', source_sha256=hashlib.sha256(original_source.read_bytes()).hexdigest(),
                description='Two full-height blue pallet bases; original total height and XY envelope retained')
manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print('DOUBLE_PALLET_READY '+json.dumps([{k:r[k] for k in ('name','bounds_m','pallet_base_z_m')} for r in manifest['meshes']]))
