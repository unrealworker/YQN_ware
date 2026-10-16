import sys,json,collections
sys.path.insert(0,'Scripts/_vendor/cad');import ezdxf
D=ezdxf.read(open(r'D:\EdgeDownload\平面布局图_GHS_0.23_20260710现状.dxf',encoding='utf8',errors='replace'))
for name in ['FL_PALLET_48W_40D_STD','RACK_42D_144B','FP-1000$0$col','PILLAR']:
 b=D.blocks.get(name);print('\nBLOCK',name,'base',b.base_point)
 for e in b:
  print(e.dxftype(),e.dxf.handle,e.dxf.layer, e.dxfattribs())
  if e.dxftype()=='LWPOLYLINE':print(list(e.get_points()))
