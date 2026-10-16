"""CAD-exact slab and uncapped outward wall skin unit. Metres, CAD +Y unchanged."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'video_reference'))
import common as c
import bpy
from mathutils import Vector
from mathutils.geometry import tessellate_polygon
ROOT=Path(__file__).resolve().parents[2]
c.OUT=ROOT/'SourceAssets/GHS';c.reset()
layout=json.loads((c.OUT/'cad_layout.json').read_text())
points=layout['footprint_outline_m']
if points[0]==points[-1]:points=points[:-1]
signed=sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points,points[1:]+points[:1]))/2
if signed<0:points.reverse()
n=len(points);area=abs(signed)
floor=c.material('M_VR_Floor',(.012,.019,.034),.48,.15)
wm=next(m for m in json.loads((ROOT/'SourceAssets/VideoReference/walls.json').read_text())['materials'] if m['name']=='M_VR_WallVolume')
wall=c.material(wm['name'],wm['base_color'][:3],wm['roughness'],wm['metallic'],**{k:v for k,v in wm.items() if k not in ['name','base_color','roughness','metallic']})
c.begin_asset('SM_GHS_CAD_Floor')
vs=[(x,y,0) for x,y in points]+[(x,y,-.15) for x,y in points]
loop=[Vector(v) for v in vs[:n]]
tri=tessellate_polygon([loop]);lookup={tuple(v):i for i,v in enumerate(loop)}
top=[tuple(v if isinstance(v,int) else lookup[tuple(v)] for v in t) for t in tri]
faces=top+[tuple(i+n for i in reversed(t)) for t in top]+[(i,i+n,(i+1)%n+n,(i+1)%n) for i in range(n)]
ob=c.mesh('CAD_ExactFloorSlab',vs,faces,floor)
actual=sum(p.area for p in ob.data.polygons if p.normal.z>.99)
assert abs(actual-area)<.02,(actual,area)
assert all(p.normal.z>.99 for p in list(ob.data.polygons)[:len(top)])
c.begin_asset('SM_GHS_WallPanelUnit')
verts=[(-.5,-.1,-.5),(.5,-.1,-.5),(.5,-.1,.5),(-.5,-.1,.5),(-.5,.1,-.5),(.5,.1,-.5),(.5,.1,.5),(-.5,.1,.5)]
panel=c.mesh('UncappedOutwardWallSkins',verts,[(0,1,2,3),(7,6,5,4)],wall)
assert panel.data.polygons[0].normal.y<-.99 and panel.data.polygons[1].normal.y>.99
c.save_library('cad_architecture')
path=c.OUT/'cad_architecture.json';meta=json.loads(path.read_text());meta['verification']={'floor_outline_vertices':n,'floor_top_triangles':len(top),'floor_area_m2':area,'mesh_top_area_m2':actual,'floor_z_m':[-.15,0],'cad_positive_y_preserved':True,'wall_outward_normals_y':[-1,1],'wall_caps':False};path.write_text(json.dumps(meta,indent=2))
print('CAD_ARCHITECTURE_VERIFIED',json.dumps(meta['verification']),json.dumps(meta['meshes']))
