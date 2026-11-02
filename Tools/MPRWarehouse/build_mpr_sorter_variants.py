"""CAD-sized sorter variants; dimensions in plan follow CAD, heights estimated.

The 96-bin manual model is kept separately. These variants follow the actual
8-column / 15-column / 5-column branch linework, not the manual's 12 columns.
Run using isolated background Blender with factory startup.
"""
import bpy,sys,math,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).resolve().parent))
import build_mpr_sorter as g
OUT=g.OUT
SPECS=[
 {'name':'SM_MPR_SorterCAD64','columns':8,'levels':4,'length':6.2623,'width':2.096,'height':2.35,'end':.49,'source':'2C9A89'},
 {'name':'SM_MPR_SorterCAD120','columns':15,'levels':4,'length':7.3465363278,'width':2.1920020006,'height':2.35,'end':.42,'source':'2C9AE5'},
 {'name':'SM_MPR_SorterShort10','columns':5,'levels':1,'length':2.75,'width':1.80,'height':1.12,'end':.22,'source':'2D41B7'},
]

def bin_shell(name,x,y,z,w,d,h,col,lod):
 t=.008;verts=[]
 for rw,rd,rz in [(w*.9,d*.9,0),(w,d,h),(w-t*2,d-t*2,h),(w*.9-t*2,d*.9-t*2,t)]:
  verts.extend([(x-rw/2,y-rd/2,z+rz),(x+rw/2,y-rd/2,z+rz),(x+rw/2,y+rd/2,z+rz),(x-rw/2,y+rd/2,z+rz)])
 faces=[(0,3,2,1),(12,13,14,15)]
 for a,b in [(0,4),(4,8),(8,12)]:faces.extend([(a+i,a+(i+1)%4,b+(i+1)%4,b+i) for i in range(4)])
 g.mesh(name,verts,faces,'SoftBlue',col)
 if lod==0:
  for side in [-1,1]:g.box(name+'_Rim',(x,y+side*d*.49,z+h),(w,.012,.012),'SoftBlue',col)

def machine(s,lod):
 g.PARTS=[];name=s['name'];L=s['length'];W=s['width'];H=s['height'];N=s['columns'];levels=s['levels'];end=s['end'];active=L-2*end
 col=bpy.data.collections.new(name+'_Editable_LOD'+str(lod));bpy.context.scene.collection.children.link(col)
 pitch=active/N;binw=min(.395,pitch*.91);bind=min(.505,W*.24);cy=W/2-bind/2-.015
 beltwidth=W-2*bind-.20;rail_y=beltwidth*.5+.015
 base=.12 if levels==4 else .79
 for side in [-1,1]:
  for i in range(N):
   x=-active/2+(i+.5)*pitch
   for lev in range(levels):
    z=base+lev*.445
    bin_shell(f'Bin_{side}_{i+1}_{lev+1}',x,side*cy,z,binw,bind,.18,col,lod)
    depth=abs(cy)-bind/2-rail_y+.08
    g.box('Chute',(x,side*(rail_y+depth/2),z+.23),(binw+.01,depth,.015),'Porcelain',col,rx=-side*math.radians(20))
    if lod<2:
     g.box('ChuteIndicator',(x,side*(cy-bind*.49),z+.21),(binw*.85,.012,.023),'Cobalt',col)
     for xs in [-1,1]:g.box('ChuteRim',(x+xs*binw/2,side*(rail_y+depth/2),z+.275),(.012,depth,.075),'Porcelain',col,rx=-side*math.radians(20))
  for lev in range(levels):
   z=base+lev*.445
   g.box('CartRail',(0,side*(cy-bind/2),z-.025),(active,.028,.035),'Metal',col)
   g.box('OuterCartRail',(0,side*(cy+bind/2),z-.025),(active,.028,.035),'Metal',col)
   g.box('BeltRail',(0,side*rail_y,z+.28),(L-.08,.04,.08),'Metal',col)
  supports=range(0,N+1,max(1,round(N/4)))
  for idx in supports:
   x=-active/2+idx*pitch
   for y in [side*(cy-bind/2),side*(cy+bind/2)]:
    g.box('D28Leg',(x,y,(H-.10)/2),(.028,.028,H-.10),'Metal',col)
    if lod==0:
     wheel_y=y-math.copysign(.021,y)
     g.rod('Caster',(x-.012,wheel_y,.035),(x+.012,wheel_y,.035),.035,'Rubber',col,sides=6)
  if levels==4:g.box('Header',(0,side*(rail_y+.04),H-.13),(active,.045,.18),'Porcelain',col)
 for lev in range(levels):
  g.box('MainBelt',(0,0,base+lev*.445+.30),(L-.10,beltwidth-.06,.025),'Cobalt',col)
  if lod==0:
   for i in range(6):g.box('BeltSeam',(-active/2+(i+.5)*active/6,0,base+lev*.445+.316),(.008,beltwidth-.08,.003),'Charcoal',col)
 for side in [-1,1]:
  x=side*(L/2-end*.5)
  g.box('EndMachinery',(x,0,H*.50),(end*.94,beltwidth+.06,H-.10),'Porcelain',col)
  g.box('EndCobaltBand',(x,-(beltwidth+.073)/2,H*.80),(end*.85,.012,.06),'Cobalt',col)
  g.box('InspectionWindow',(x,-(beltwidth+.076)/2,H*.48),(end*.60,.013,H*.30),'Glass',col)
  if lod<2:
   g.box('MonitorBody',(x,0,H+.015),(end*.76,.055,.18),'Charcoal',col)
   g.box('MonitorGlass',(x,-.031,H+.015),(end*.69,.007,.145),'Glass',col)
   g.box('ServiceHandle',(x+end*.33,-(beltwidth+.08)/2,H*.50),(.018,.018,.15),'Metal',col)
  g.box('BaseShoe',(x,0,.05),(end*.94,beltwidth+.08,.06),'Charcoal',col)
 return col

def main():
 assert bpy.data.filepath=='','Must use factory startup'
 bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
 bpy.context.scene.unit_settings.system='METRIC';bpy.context.scene.unit_settings.scale_length=1
 for role,color in zip(g.ROLES,g.COLORS):g.MATS[role]=g.material(role,color)
 # Exact short branch footprint is injected from child-block geometry.
 children_path=OUT/'sorter_child_bounds.json'
 if children_path.exists():
  children=json.loads(children_path.read_text(encoding='utf8')).get('short_branches',[])
  groups=[r for r in children if 2.3<r['size'][0]<3.6 and 1.4<r['size'][1]<2.3]
  if groups:
   SPECS[2]['length']=groups[0]['size'][0];SPECS[2]['width']=groups[0]['size'][1]
 meshes=[]
 for s in SPECS:
  for lod in range(3):
   col=machine(s,lod)
   r=g.export(col,s['name']+('' if lod==0 else '_LOD'+str(lod)))
   r.update(lod=lod,columns_per_side=s['columns'],levels=s['levels'],bin_count=s['columns']*2*s['levels'],source_handle=s['source']);meshes.append(r)
   for o in col.objects:o.hide_render=True;o.hide_set(True)
 blend=OUT/'MPR_SorterCADVariants.blend';bpy.ops.wm.save_as_mainfile(filepath=str(blend))
 for s in SPECS:
  rows=[r for r in meshes if r['name'].startswith(s['name'])]
  assert rows[0]['triangles']>rows[1]['triangles']>rows[2]['triangles']
 manifest={'schema_version':1,'units':'metres','axis':'X along length; CAD +Y; FBX -Y forward Z up','origin':'plan center, floor Z0',
  'blender':str(blend),'material_paths':{r:'/Game/GHSZcoolSmartFactory/Materials/M_Zcool_'+r for r in g.ROLES},'meshes':meshes,'specs':SPECS,
  'limitations':['Plan size and horizontal column counts come from the supplied CAD. The 8-column and 15-column machines are NOT the 96-bin manual model.',
  '4 vertical levels for long sorters and one level for short branches are presentation assumptions; supplied CAD is 2D. Equipment heights, end cabinets and interior mechanics require equipment vendor confirmation.',
  'Short branch bins retain the 5-columns-per-side plan pattern. The manual 96-bin model remains a separate unplaced library asset.'],
  'runtime_policy':'One static combined mesh per machine, seven shared GHS material slots; explicit LOD0/1/2. Parent uses HISM; no ticking or decorative collision.'}
 (OUT/'sorter_variants_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
 print('MPR_CAD_SORTER_VARIANTS '+json.dumps([{'name':r['name'],'triangles':r['triangles'],'bins':r['bin_count'],'bounds':r['bounds_m']} for r in meshes]))
if __name__=='__main__':main()
