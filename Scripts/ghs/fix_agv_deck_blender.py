"""Separate the twelve corner details from the rubber deck, preserving all other geometry."""
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
import bpy

ROOT = Path(r'D:\UEPro\Test')
OUT = ROOT/'SourceAssets/GHS'
REPORT = ROOT/'Saved/GHS_AGVDeckFixSource.json'
assert not REPORT.exists(), 'Review the existing source repair before reapplying'
sys.path.insert(0, str(ROOT/'Scripts/video_reference'))
import common as c

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p, value): Path(p).write_text(json.dumps(value, indent=2), encoding='utf-8')
def state(obj):
    return dict(matrix=[list(row) for row in obj.matrix_world],
                vertices=[list(v.co) for v in obj.data.vertices],
                polygons=[(list(p.vertices),p.material_index) for p in obj.data.polygons],
                materials=[m.name for m in obj.data.materials],
                modifiers=[(m.name,m.type) for m in obj.modifiers])
def bounds(obj):
    ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get()); mesh=ev.to_mesh()
    points=[obj.matrix_world@v.co for v in mesh.vertices]
    value=[[min(v[i] for v in points),max(v[i] for v in points)] for i in range(3)]
    ev.to_mesh_clear(); return value

backup=ROOT/'Saved/Backups'/('GHS_AGVDeckFix_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
backup.mkdir(parents=True)
files=['SourceAssets/GHS/kuka_agv.blend','SourceAssets/GHS/SM_GHS_KukaLowProfileAGV.fbx',
       'SourceAssets/GHS/kuka_agv.json','Scripts/ghs/build_kuka_agv.py',
       'Content/GHSDigitalTwin/Meshes/SM_GHS_KukaLowProfileAGV.uasset']
saved={}
for relative in files:
    destination=backup/relative;destination.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(ROOT/relative,destination)
    saved[relative]=dict(before_sha256=sha(ROOT/relative),backup=str(destination))
write(backup/'content_hashes.json',{p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'Content').rglob('*') if p.is_file()})
write(backup/'history_hashes.json',{p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'Saved').glob('GHS_*.json')})
spec=json.loads((OUT/'kuka_agv.json').read_text(encoding='utf-8'))
bpy.ops.wm.open_mainfile(filepath=str(OUT/'kuka_agv.blend'))
collection=bpy.data.collections['SM_GHS_KukaLowProfileAGV']
before={o.name:state(o) for o in collection.objects if o.type=='MESH'}
plates=[o for o in collection.objects if o.name.startswith('Deck_panel_outline')]
screws=[o for o in collection.objects if o.name.startswith('Deck_screw')]
assert len(plates)==4 and len(screws)==8
rubber=bpy.data.objects['Rubber_load_surface'];rubber_top=bounds(rubber)[2][1]
assert all(abs(bounds(o)[2][1]-rubber_top)<1e-7 for o in plates), 'Expected original coplanar failure'
old_bounds={o.name:bounds(o) for o in plates+screws}
for o in plates:
    for vertex in o.data.vertices: vertex.co.z *= 4
    o.location.z=.3216
    o.modifiers['EdgeRadiuses'].width=.00032
for o in screws:
    for vertex in o.data.vertices: vertex.co.z *= 2
    o.location.z=.3229
bpy.context.view_layer.update()
changed={o.name for o in plates+screws}
assert all(state(o)==before[o.name] for o in collection.objects if o.type=='MESH' and o.name not in changed)
after_bounds={o.name:bounds(o) for o in plates+screws}
assert all(bounds(o)[2][0]-rubber_top>.00079 and abs(bounds(o)[2][1]-.3224)<1e-7 for o in plates)
assert all(bounds(o)[2][0]>.32259 and bounds(o)[2][1]<.32321 for o in screws)
assert all(after_bounds[name][:2]==old_bounds[name][:2] for name in changed)
c.OUT=OUT;c.ASSETS=[('SM_GHS_KukaLowProfileAGV',collection)]
c.MATERIALS={m['name']:m for m in spec['materials']}
bpy.context.preferences.filepaths.save_version=0
c.save_library('kuka_agv')
updated=json.loads((OUT/'kuka_agv.json').read_text(encoding='utf-8'))
assert updated==spec, 'Geometry counts, materials, origin and overall size must be unchanged'
builder=ROOT/'Scripts/ghs/build_kuka_agv.py';source=builder.read_text(encoding='utf-8')
old="box('Deck_panel_outline',(x,y,.3198),(.056,.083,.0004),gray,.001)"
new="box('Deck_panel_outline',(x,y,.3216),(.056,.083,.0016),gray,.001)"
assert source.count(old)==1;source=source.replace(old,new)
old="c.cylinder('Deck_screw',(x,y+dy,.32),.002,.0003,metal,16)"
new="c.cylinder('Deck_screw',(x,y+dy,.3229),.002,.0006,metal,16)"
assert source.count(old)==1;source=source.replace(old,new)
builder.write_text(source,encoding='utf-8')
for relative,item in saved.items(): item['after_source_sha256']=sha(ROOT/relative)
write(REPORT,dict(success=True,backup_root=str(backup),files=saved,changed_parts=sorted(changed),
                  original_corner_bounds_m=old_bounds,repaired_corner_bounds_m=after_bounds,
                  rubber_top_m=rubber_top,plate_bottom_clearance_m=.0008,plate_top_clearance_m=.0024,
                  screws_min_clearance_above_plate_m=.0002,other_parts_unchanged=True,
                  bounds_material_slots_and_mesh_counts_unchanged=True))
print('GHS_AGV_DECK_SOURCE_FIXED: four plates and eight screws; all other geometry preserved')
