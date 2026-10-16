"""GHS presentation variants; preserves storage kit materials and XY footprints."""
from pathlib import Path
import sys,json,bpy
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Scripts'/'video_reference'))
import common
src=(ROOT/'Scripts/video_reference/build_storage.py').read_text()
header=src[:src.index("begin_asset('SM_VR_PalletCargo')")]
header=header.replace('str(Path(__file__).resolve().parent)','str(ROOT/"Scripts/video_reference")')
exec(header,globals())
common.OUT=ROOT/'SourceAssets/GHS/Presentation';common.OUT.mkdir(parents=True,exist_ok=True)
pallet=src[src.index('# Three continuous runners'):src.index('# A cubic cargo silhouette')]
cargo_code=src[src.index('base_z=.173'):src.index("begin_asset('SM_VR_RackBay')")]
cargo_code=cargo_code.replace('cube=(1.16/3,.96/3,.90/3)','cube=(1.16/3,.96/3,.3)').replace('for iz in range(3):','for iz in range(layers):').replace('range(4)','range(layers+1)').replace('base_z+.9','base_z+layers*.3')
for suffix,layers in [('Low',4),('Mid',6),('High',8)]:
    begin_asset('SM_GHS_Presentation_Cargo'+suffix)
    exec(pallet+cargo_code,globals())
rack=src[src.index('# Four flange-like upright'):src.index("begin_asset('SM_VR_LM_Pad')")]
rack=rack.replace('1.4),(.024,.048,2.8)','2.4),(.024,.048,4.8)').replace('1.4),(.048,.018,2.8)','2.4),(.048,.018,4.8)')
rack=rack.replace('[.2,.5,.8,1.1,1.4,1.7,2.0,2.3,2.6]','[.2+i*.3 for i in range(15)]').replace('[(.10,1.37),(1.39,2.73)]','[(.10,1.27),(1.29,2.44),(2.46,3.61),(3.63,4.73)]')
rack=rack.replace('[.35,.95,1.55,2.15]','[.35,1.5,2.65,3.8]').replace('z+.20','z+.40').replace('depth,.40','depth,.80').replace('.024,.40','.024,.80').replace('z+.403','z+.803').replace('2.771','4.771').replace('2.799','4.799')
begin_asset('SM_GHS_Presentation_RackTall')
exec(rack,globals())
counts={}
for name,col in common.ASSETS:
    deps=bpy.context.evaluated_depsgraph_get();xs=[];ys=[];zs=[];triangles=0
    for obj in col.objects:
        ev=obj.evaluated_get(deps);me=bpy.data.meshes.new_from_object(ev,depsgraph=deps)
        me.calc_loop_triangles();triangles+=len(me.loop_triangles)
        for v in me.vertices:
            p=obj.matrix_world@v.co;xs.append(p.x);ys.append(p.y);zs.append(p.z)
        bpy.data.meshes.remove(me)
    expected=4.8 if 'Rack' in name else {'Low':1.376,'Mid':1.976,'High':2.576}[name.split('Cargo')[1]]
    assert abs(min(zs))<1e-5,(name,min(zs))
    assert abs(max(zs)-expected)<1e-4,(name,max(zs),expected)
    assert max(xs)-min(xs)<=(1.50001 if 'Rack' in name else 1.20001)
    assert max(ys)-min(ys)<=(.85201 if 'Rack' in name else 1.00001)
    counts[name]=triangles
save_library('presentation_storage')
p=common.OUT/'presentation_storage.json';d=json.loads(p.read_text())
for entry in d['meshes']:
    entry['triangles']=counts[entry['name']];entry['origin_m']=[0,0,0]
p.write_text(json.dumps(d,indent=2),encoding='utf-8')
print('PRESENTATION_VALIDATED',[(e['name'],e['bounds_m'],e['triangles']) for e in d['meshes']])


