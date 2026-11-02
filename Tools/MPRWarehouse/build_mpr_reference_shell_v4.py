"""Reference-v4 MPR external shell only. Run: blender -b -t 1 --python this.py.

CAD footprint/apertures and floor interfaces are invariant. Generated imagery is
appearance/layout evidence, not a survey. No old architecture or UE writes.
"""
import sys,json,math,hashlib
from pathlib import Path
import bpy,numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).parent))
from mpr_reference_shell_v4_lib import Geometry,make_textures

OUT=ROOT/'SourceAssets/MPR/reference_v4/architecture'
REF=ROOT/'SourceAssets/MPR/reference_v4/references'
CAD=json.loads((ROOT/'SourceAssets/MPR/mpr_cad_layout.json').read_text(encoding='utf8'))
fp=CAD['footprint_outline_m'];ROOF=13.4;HEIGHT=13.6
OUT.mkdir(parents=True,exist_ok=True)
textures=make_textures(OUT/'textures')
materials={
 'MPR4_FacadeWhite':dict(color=[.80,.82,.85],roughness=.72,uv_tile_m=2,textures=textures['paint'],normal_strength=.12),
 'MPR4_IndustrialBlue':dict(color=[.009,.155,.43],roughness=.46,metallic=.18,uv_tile_m=2,textures=textures['paint'],normal_strength=.08),
 'MPR4_RoofMembrane':dict(color=[.91,.935,.97],roughness=.76,uv_tile_m=3,textures=textures['paint'],normal_strength=.14),
 'MPR4_RoofSeam':dict(color=[.39,.46,.54],roughness=.88),
 'MPR4_JointSeal':dict(color=[.23,.27,.31],roughness=.87),
 'MPR4_Aluminium':dict(color=[.61,.66,.72],roughness=.31,metallic=.78),
 'MPR4_RollerSilver':dict(color=[.55,.59,.65],roughness=.43,metallic=.63,uv_tile_m=1,textures=textures['paint'],normal_strength=.06),
 'MPR4_DockFabric':dict(color=[.036,.043,.052],roughness=.86,uv_tile_m=.75,textures=textures['fabric'],normal_strength=.35),
 'MPR4_Rubber':dict(color=[.018,.022,.026],roughness=.92),
 'MPR4_GlassBlue':dict(color=[.032,.087,.15],roughness=.16,metallic=.42),
 'MPR4_SafetyYellow':dict(color=[1.0,.63,.015],roughness=.44,metallic=.08),
 'MPR4_ReflectiveWhite':dict(color=[.89,.92,.95],roughness=.28,metallic=.10),
 'MPR4_CheckerSteel':dict(color=[.48,.54,.60],roughness=.48,metallic=.80,uv_tile_m=.45,textures=textures['checker'],normal_strength=.75),
 'MPR4_SolarCells':dict(color=[.70,.88,1.0],roughness=.31,metallic=.72,uv_tile_m=1,textures=textures['solar'],normal_strength=.08,
                       uv_note='Each 1.0528 x 1.872 m module repeats UV 0..1; texture contains 6x12 visual cells.'),
 'MPR4_LampLens':dict(color=[.86,.91,1.0],roughness=.21,emission=.7),
}
for m in materials.values():
 m.setdefault('metallic',0);m['color_space']='linear RGB tint; albedo PNG sRGB, normal PNG NonColor';m['texture_blend']='multiply albedo by color'
 if 'normal' in m.get('textures',{}):m['normal_convention']='OpenGL';m['ue_flip_green_channel']=True
g=Geometry(materials);instances={};apertures=[]
def add(n,p,yaw=0,scale=(1,1,1),**extra):
 instances.setdefault(n,[]).append(dict(position_m=[round(v,6) for v in p],rotation_deg=yaw,scale=list(scale),**extra))

def inside(x,y):
 hit=False
 for a,b in zip(fp,fp[1:]+fp[:1]):
  if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:hit=not hit
 return hit

def clear(x,y,dx,dy):return all(inside(x+sx*dx,y+sy*dy) for sx in (-1,1) for sy in (-1,1))

def line_intervals(axis,fixed):
 vals=[]
 for a,b in zip(fp,fp[1:]+fp[:1]):
  j=1-axis
  if (a[j]<=fixed<b[j]) or (b[j]<=fixed<a[j]):vals.append(a[axis]+(fixed-a[j])/(b[j]-a[j])*(b[axis]-a[axis]))
 vals.sort();return list(zip(vals[::2],vals[1::2]))

# 16 original CAD edges; exact apertures remain holes through the full wall.
openings=CAD['dock_doors']+CAD['drive_in_doors']
for side,(a,b) in enumerate(zip(fp,fp[1:]+fp[:1])):
 dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy);ux,uy=dx/length,dy/length
 nx,ny=-uy,ux
 if inside((a[0]+b[0])/2+nx,(a[1]+b[1])/2+ny):nx,ny=-nx,-ny
 name=f'SM_MPR4_Facade_{side:02}'
 def pt(t,offset=0):return a[0]+ux*t+nx*offset,a[1]+uy*t+ny*offset
 cuts=[]
 for d in openings:
  p=d['position_m'];t=(p[0]-a[0])*ux+(p[1]-a[1])*uy
  if 0<t<length and abs((p[0]-a[0])*uy-(p[1]-a[1])*ux)<.4:
   dock=d in CAD['dock_doors'];h=4.2 if dock else 4.5
   cuts.append((t-d['opening_width_m']/2,t+d['opening_width_m']/2,h,d,dock))
   apertures.append(dict(id=d['id'],side=side,opening_width_m=d['opening_width_m'],height_m=h,
                        wall_position_m=[*pt(t),0],cad_position_m=p,dock=dock))
 cuts.sort(key=lambda c:c[0]);xs=sorted(set([0.,length]+[min(length,i*6.1) for i in range(1,math.ceil(length/6.1))]+[v for c in cuts for v in c[:2]]))
 for lo,hi in zip(xs,xs[1:]):
  if hi-lo<.003:continue
  mid=(lo+hi)/2;cut=next((c for c in cuts if c[0]-.001<mid<c[1]+.001),None)
  for za,zb in zip([-1.2,0,1.4,4.2,4.5,7.7,11.4], [0,1.4,4.2,4.5,7.7,11.4,13.6]):
   if cut and za>=(-.001 if cut[4] else -1.201) and zb<=cut[2]+.001:continue
   role='MPR4_IndustrialBlue' if zb<=1.4001 else 'MPR4_FacadeWhite'
   g.segment(name,role,pt(lo),pt(hi),.3048,(za+zb)/2,zb-za)
 # Shallow exterior panel expansion joints. Real aperture geometry stays open.
 for t in [i*6.1 for i in range(1,math.ceil(length/6.1))]:
  cut=next((c for c in cuts if c[0]-.02<t<c[1]+.02),None);start=cut[2] if cut else -1.19
  p=pt(t,.154);g.box(name,'MPR4_JointSeal',(p[0],p[1],(start+13.35)/2),(.014,.014,13.35-start))
 for z in [1.42,7.7,11.4]:
  intervals=[(0,length)]
  if z<4.5:
   intervals=[];cursor=0
   for l,r,h,_,_ in cuts:
    if h>z:intervals.append((cursor,l));cursor=r
   intervals.append((cursor,length))
  for lo,hi in intervals:g.segment(name,'MPR4_JointSeal',pt(lo,.156),pt(hi,.156),.012,z,.012)
 # Metallic cap and vivid thin blue roof outline, not a thick opaque box.
 g.segment(f'SM_MPR4_RoofEdge_{side:02}','MPR4_IndustrialBlue',pt(0),pt(length),.40,13.64,.16)
 g.segment(f'SM_MPR4_RoofEdge_{side:02}','MPR4_Aluminium',pt(0),pt(length),.42,13.735,.035)
 # Lighting follows doors on loading elevations, regular bays on solid walls.
 for t in ([((l+r)/2) for l,r,h,d,dock in cuts] if cuts else [4+i*12.2 for i in range(max(0,int((length-6)/12.2))) ]):
  p=pt(t,.16);yaw=math.degrees(math.atan2(nx,-ny))
  add('SM_MPR4_WallLamp',(*p,8.45),yaw,source='reference-spaced wall fixture')

assert len(apertures)==len(openings)==74,('CAD aperture mismatch',len(apertures))
apertures.sort(key=lambda ap:(ap['side'],ap['wall_position_m'][0],ap['wall_position_m'][1]))
# Roof skin is split into broad regions for culling/removal; exact footprint used.
# Clipping against X strips uses Sutherland-Hodgman, preserving stepped edges.
def clip_x(points,limit,keep_greater):
 result=[]
 for a,b in zip(points,points[1:]+points[:1]):
  ina=a[0]>=limit if keep_greater else a[0]<=limit;inb=b[0]>=limit if keep_greater else b[0]<=limit
  if ina:result.append(a)
  if ina!=inb:
   t=(limit-a[0])/(b[0]-a[0]);result.append([limit,a[1]+t*(b[1]-a[1])])
 return result
for i,(lo,hi) in enumerate([(-190,-100),(-100,0),(0,90),(90,190)]):
 ps=clip_x(clip_x(fp,lo,True),hi,False);n=f'SM_MPR4_RoofSkin_{i:02}'
 g.prism(n,'MPR4_RoofMembrane',ps,13.12,ROOF)
 # Reference-readable 6.1m grid; 150mm visual joint strip, not a construction joint dimension.
 for axis,fixeds in [(0,np.arange(-90,90,6.1)),(1,np.arange(math.ceil(lo/6.1)*6.1,hi,6.1))]:
  for fixed in fixeds:
   for v0,v1 in line_intervals(axis,fixed):
    if axis==0:
     v0=max(v0,lo);v1=min(v1,hi)
     if v1<=v0:continue
     verts=[(v0,fixed-.075,ROOF+.002),(v1,fixed-.075,ROOF+.002),(v1,fixed+.075,ROOF+.002),(v0,fixed+.075,ROOF+.002)]
    else:verts=[(fixed-.075,v0,ROOF+.002),(fixed+.075,v0,ROOF+.002),(fixed+.075,v1,ROOF+.002),(fixed-.075,v1,ROOF+.002)]
    g.mesh(n,'MPR4_RoofSeam',verts,[(0,1,2,3)])

# Modules use local -Y outward; z=0 is dock-floor height, matching CAD interiors.
W=2.9464;H=4.2
n='SM_MPR4_DockShelter'
for x in [-W/2-.11,W/2+.11]:
 g.box(n,'MPR4_IndustrialBlue',(x,-.20,H/2),(.22,.22,H+.24),bevel=.025)
 g.box(n,'MPR4_DockFabric',(x,-.43,H/2),(.36,.48,H-.08),bevel=.045)
 g.box(n,'MPR4_ReflectiveWhite',(x,-.677,1.8),(.044,.008,1.55))
g.box(n,'MPR4_IndustrialBlue',(0,-.20,H+.12),(W+.50,.24,.25),bevel=.02)
g.box(n,'MPR4_DockFabric',(0,-.45,H+.02),(W+.60,.53,.48),bevel=.045)
g.box(n,'MPR4_Rubber',(0,-.206,-.09),(W+.2,.16,.16),bevel=.015)
# Textile fold strips add shape at close range without an excessive cloth mesh.
for s in [-1,1]:
 for z in [.22,1.2,2.4,3.8]:
  g.mesh(n,'MPR4_DockFabric',[(s*(W/2-.07),-.684,z-.10),(s*(W/2+.24),-.684,z+.03),(s*(W/2+.11),-.701,z)],[(0,1,2)])

def roller(n,width,height):
 g.box(n,'MPR4_Rubber',(0,.075,height/2),(width,.10,height))
 count=round(height/.145)
 for i in range(count):
  z=(i+.5)*height/count
  g.box(n,'MPR4_RollerSilver',(0,-.005,z),(width-.12,.09,height/count-.008),bevel=.009)
 for x in [-width/2+.024,width/2-.024]:g.box(n,'MPR4_Aluminium',(x,-.09,height/2),(.055,.10,height))
 for x in [-width*.24,width*.24]:
  g.box(n,'MPR4_Rubber',(x,-.063,1.45),(.64,.028,.28),bevel=.025)
  g.box(n,'MPR4_GlassBlue',(x,-.083,1.45),(.56,.014,.20),bevel=.02)
 g.box(n,'MPR4_Aluminium',(0,-.08,.29),(.25,.045,.055),bevel=.012)
 g.box(n,'MPR4_Rubber',(0,-.018,.027),(width-.10,.13,.055))
roller('SM_MPR4_RollerDock',W,H)
roller('SM_MPR4_RollerDriveIn',3.8608,5.7)

n='SM_MPR4_DockLeveller'
g.box(n,'MPR4_Rubber',(0,-.23,-.30),(W-.20,.23,.55),bevel=.02)
g.box(n,'MPR4_CheckerSteel',(0,-.39,-.27),(W-.55,.11,.43),bevel=.018)
g.box(n,'MPR4_CheckerSteel',(0,-.20,-.025),(W-.55,.48,.05))
for x in [-W/2+.09,W/2-.09]:
 g.box(n,'MPR4_Rubber',(x,-.40,-.26),(.24,.24,.64),bevel=.025)
 for z in [-.48,-.05]:g.box(n,'MPR4_Aluminium',(x,-.526,z),(.085,.012,.085),bevel=.008)

n='SM_MPR4_Bollard'
g.cylinder(n,'MPR4_Aluminium',(0,0,.03),.145,.06,12)
g.cylinder(n,'MPR4_SafetyYellow',(0,0,.64),.095,1.22,16)
g.cylinder(n,'MPR4_SafetyYellow',(0,0,1.258),.083,.045,16)
g.cylinder(n,'MPR4_SafetyYellow',(0,0,1.283),.048,.02,12)

n='SM_MPR4_WallLamp'
g.box(n,'MPR4_Aluminium',(0,-.035,0),(.19,.08,.29),bevel=.02)
g.box(n,'MPR4_Aluminium',(0,-.27,.055),(.62,.50,.15),bevel=.025)
g.box(n,'MPR4_Rubber',(0,-.28,-.036),(.55,.43,.025))
g.box(n,'MPR4_LampLens',(0,-.28,-.054),(.48,.34,.013))

# Number plate digits share 10 meshes rather than 72 unique door assets.
n='SM_MPR4_DockNumberPlate';g.box(n,'MPR4_ReflectiveWhite',(0,-.015,0),(.46,.025,.24),bevel=.01)
segments={'0':'abcedf','1':'bc','2':'abged','3':'abgcd','4':'fgbc','5':'afgcd','6':'afgecd','7':'abc','8':'abcdefg','9':'abfgcd'}
places={'a':(0,.079,.09,.012),'g':(0,0,.09,.012),'d':(0,-.079,.09,.012),'f':(-.046,.039,.012,.07),'b':(.046,.039,.012,.07),'e':(-.046,-.039,.012,.07),'c':(.046,-.039,.012,.07)}
for digit,ss in segments.items():
 for s in ss:
  x,z,w,h=places[s];g.box('SM_MPR4_Digit_'+digit,'MPR4_JointSeal',(x,-.033,z),(w,.006,h))

for idx,ap in enumerate(apertures):
 d=next(d for d in openings if d['id']==ap['id']);yaw=d['rotation_deg'];rad=math.radians(yaw);co,si=math.cos(rad),math.sin(rad)
 p=ap['wall_position_m']
 def world(x,y,z):return p[0]+co*x-si*y,p[1]+si*x+co*y,z
 if ap['dock']:
  for mesh in ['SM_MPR4_DockShelter','SM_MPR4_RollerDock','SM_MPR4_DockLeveller']:add(mesh,p,yaw,source_cad_id=d['id'])
  for x in [-W/2-.33,W/2+.33]:add('SM_MPR4_Bollard',world(x,-.72,-1.2),yaw,source_cad_id=d['id'])
 else:
  add('SM_MPR4_RollerDriveIn',(p[0],p[1],-1.2),yaw,source_cad_id=d['id'])
  for x in [-2.15,2.15]:add('SM_MPR4_Bollard',world(x,-.64,-1.2),yaw,source_cad_id=d['id'])
 add('SM_MPR4_DockNumberPlate',world(0,-.18,4.82),yaw)
 for offset,digit in zip([-.075,.075],f'{idx+1:02}'):
  add('SM_MPR4_Digit_'+digit,world(offset,-.18,4.82),yaw,number=idx+1)

# Exterior office glazing preserves prior end-office wall interfaces, not CAD new holes.
for x,y0,y1,nx in [(-181.93004,50,80,-1),(182.61076,62,80,1)]:
 n='SM_MPR4_OfficeGlazing_West' if nx<0 else 'SM_MPR4_OfficeGlazing_East'
 for y in range(y0,y1,3):
  g.box(n,'MPR4_JointSeal',(x+nx*.17,y,2.6),(.055,2.45,2.55))
  g.box(n,'MPR4_GlassBlue',(x+nx*.205,y,2.6),(.025,2.28,2.38))
  for off in [-1.22,0,1.22]:g.box(n,'MPR4_Aluminium',(x+nx*.225,y+off,2.6),(.045,.055,2.55))
  for zz in [1.34,3.87]:g.box(n,'MPR4_Aluminium',(x+nx*.225,y,zz),(.045,2.50,.055))

# Authority is the new overview and closeups. Old photo-traced banks are not reused.
overview=REF/'ChatGPT 图像 2026年11月2日 15_56_24.png'
control_cad=[[-181.93004,83.69038],[182.61076,83.58878],[135.36676,-83.94962],[-181.93004,-93.09362]]
control_px=[[458,330],[1036,328],[982,530],[421,544]]
eq=[];rhs=[]
for (x,y),(u,v) in zip(control_cad,control_px):
 eq.extend([[x,y,1,0,0,0,-u*x,-u*y],[0,0,0,x,y,1,-v*x,-v*y]]);rhs.extend([u,v])
hom=np.array(json.loads((ROOT/'SourceAssets/MPR/reference_v3/calibration/camera_calibration.json').read_text(encoding='utf8'))['roof_plane_camera_homography_world_to_image'])
im=bpy.data.images.load(str(overview),check_existing=False);iw,ih=im.size
pix=np.empty(iw*ih*4,dtype=np.float32);im.pixels.foreach_get(pix);pix=pix.reshape(ih,iw,4)[::-1,:,:3]*255
def blue(x,y):
 q=hom@np.array([x,y,1]);u,v=np.rint(q[:2]/q[2]).astype(int)
 if not 1<u<iw-2 or not 1<v<ih-2:return False
 r,gg,b=np.median(pix[v-1:v+2,u-1:u+2],axis=(0,1))
 return b-r>16 and b-gg>4 and (r+gg+b)/3<160

pitch_x=1.12;pitch_y=1.95;ox=-60;oy=-79
grid={}
for ix in range(210):
 x=ox+ix*pitch_x
 for iy in range(78):
  y=oy+iy*pitch_y
  if clear(x,y,2.1,2.1) and sum(blue(x+dx,y+dy) for dx,dy in [(0,0),(-.24,-.38),(.24,.38)])>=2:grid[(ix,iy)]=(x,y)
# Filter tiny blue roof vent/cap artifacts while preserving holes/white passages.
todo=set(grid);keep=set()
while todo:
 first=todo.pop();queue=[first];cluster=[]
 while queue:
  a,b=queue.pop();cluster.append((a,b))
  for key in [(a-1,b),(a+1,b),(a,b-1),(a,b+1)]:
   if key in todo:todo.remove(key);queue.append(key)
 if len(cluster)>=12:keep.update(cluster)
grid={k:grid[k] for k in sorted(keep)};strips=[]
for ix in range(210):
 rows=sorted(y for x,y in grid if x==ix);runs=[]
 for iy in rows:
  if not runs or iy>runs[-1][-1]+1:runs.append([iy])
  else:runs[-1].append(iy)
 for run in runs:
  x=ox+ix*pitch_x;y0=oy+run[0]*pitch_y-.936;y1=oy+run[-1]*pitch_y+.936;w=1.0528
  n=f'SM_MPR4_SolarBank_{0 if x<20 else 1 if x<80 else 2:02}_{0 if (y0+y1)<0 else 1}'
  z=ROOF+.24
  # The old top cap was only 6 mm below the blue cells and competed with
  # them at distant UE views. Keep the original bottom and four sides only.
  dx,dy,dz=w/2,(y1-y0)/2,.04
  base_vertices=[(x+vx,(y0+y1)/2+vy,z-.046+vz) for vx,vy,vz in
     [(-dx,-dy,-dz),(dx,-dy,-dz),(dx,dy,-dz),(-dx,dy,-dz),
      (-dx,-dy,dz),(dx,-dy,dz),(dx,dy,dz),(-dx,dy,dz)]]
  base_faces=[(0,3,2,1),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
  g.mesh(n,'MPR4_Aluminium',base_vertices,base_faces)
  # Far LOD uses the same open-top base and unchanged textured cell plane.
  lod=n+'_LOD1';g.mesh(lod,'MPR4_Aluminium',base_vertices,base_faces)
  g.mesh(lod,'MPR4_SolarCells',[(x-w/2+.02,y0+.02,z),(x+w/2-.02,y0+.02,z),(x+w/2-.02,y1-.02,z),(x-w/2+.02,y1-.02,z)],[(0,1,2,3)],
         [[(0,0),(1,0),(1,len(run)),(0,len(run))]])
  # Continuous blue cell plane repeats per module, with separate silver perimeter.
  g.mesh(n,'MPR4_SolarCells',[(x-w/2+.02,y0+.02,z),(x+w/2-.02,y0+.02,z),(x+w/2-.02,y1-.02,z),(x-w/2+.02,y1-.02,z)],[(0,1,2,3)],
         [[(0,0),(1,0),(1,len(run)),(0,len(run))]])
  for xx in [x-w/2+.006,x+w/2-.006]:g.box(n,'MPR4_Aluminium',(xx,(y0+y1)/2,z+.006),(.012,y1-y0,.02))
  for iy in run[:-1]:
   yy=oy+(iy+.5)*pitch_y
   g.mesh(n,'MPR4_Aluminium',[(x-w/2,yy-.013,z+.020),(x+w/2,yy-.013,z+.020),
     (x+w/2,yy+.013,z+.020),(x-w/2,yy+.013,z+.020),
     (x-w/2,yy-.013,z-.01),(x+w/2,yy-.013,z-.01),
     (x+w/2,yy+.013,z-.01),(x-w/2,yy+.013,z-.01)],[(0,1,2,3),(4,5,1,0),(3,2,6,7)])
  # Feet at strip ends and every 4 modules; geometry batched, not independent Actors.
  for yi in [y0+.12]+[oy+(r+.5)*pitch_y for r in run[3:-1:4]]+[y1-.12]:
   for xx in [x-w*.36,x+w*.36]:
    g.mesh(n,'MPR4_Aluminium',[(xx-.11,yi-.13,ROOF+.02),(xx+.11,yi-.13,ROOF+.02),
      (xx+.11,yi+.13,ROOF+.02),(xx-.11,yi+.13,ROOF+.02),
      (xx-.085,yi,ROOF+.02),(xx+.085,yi,ROOF+.02),(xx+.085,yi,ROOF+.195),(xx-.085,yi,ROOF+.195),
      (xx-.085,yi+.10,ROOF+.195),(xx+.085,yi+.10,ROOF+.195)],[(0,1,2,3),(4,5,6,7),(7,6,9,8)])
  strips.append(dict(x=x,y0=y0,y1=y1,width=w,modules=len(run)))
bpy.data.images.remove(im)

n='SM_MPR4_RoofLight'
g.box(n,'MPR4_IndustrialBlue',(0,0,.16),(1.85,1.35,.32),bevel=.025)
g.box(n,'MPR4_Aluminium',(0,0,.34),(1.79,1.29,.10),bevel=.02)
g.box(n,'MPR4_ReflectiveWhite',(0,0,.47),(1.60,1.1,.20),bevel=.05)
g.box(n,'MPR4_GlassBlue',(0,-.557,.47),(1.38,.015,.12))
n='SM_MPR4_RoofHVAC'
g.box(n,'MPR4_IndustrialBlue',(0,0,.14),(2.3,1.85,.28),bevel=.025)
g.box(n,'MPR4_FacadeWhite',(0,0,.63),(2.08,1.61,.70),bevel=.035)
g.box(n,'MPR4_Aluminium',(0,0,1.01),(2.14,1.67,.08),bevel=.018)
for x in [-.55,.55]:
 g.cylinder(n,'MPR4_Rubber',(x,0,1.06),.43,.02,16)
 g.cylinder(n,'MPR4_Aluminium',(x,0,1.075),.105,.025,10)
 for i in range(5):
  a=math.radians(i*72);g.box(n,'MPR4_Aluminium',(x+math.cos(a)*.22,math.sin(a)*.22,1.076),(.32,.075,.018),i*72)
for z in [.40,.50,.60,.70,.80]:g.box(n,'MPR4_JointSeal',(0,-.816,z),(1.75,.025,.024))
rooflights=[]
for ix,x in enumerate(np.arange(-161,174,28)):
 for iy,y in enumerate(np.arange(-66,74,23)):
  if not clear(x,y,5,5):continue
  if any(abs(x-s['x'])<s['width']/2+1.8 and s['y0']-1.8<y<s['y1']+1.8 for s in strips):continue
  rooflights.append([float(x),float(y)])
  add('SM_MPR4_RoofHVAC' if (ix+iy*2)%11==0 else 'SM_MPR4_RoofLight',(x,y,ROOF),scale=(2,2,2),source='reference enlarged rooftop fixture; visual size estimate')

# Plane preview is geometry-driven; copy-independent reference calibration is explicit.
svg=['<svg xmlns="http://www.w3.org/2000/svg" width="1500" height="850" viewBox="0 0 1500 850">',
 '<rect width="1500" height="850" fill="#dce6ed"/>','<text x="55" y="40" font-family="Arial" font-size="23" fill="#12334b">MPR Reference V3 - CAD shell / reference-image solar fields</text>']
def sx(x):return 60+(x+190)*3.6
def sy(y):return 85+(95-y)*3.6
svg.append('<polygon points="'+' '.join(f'{sx(x):.1f},{sy(y):.1f}' for x,y in fp)+'" fill="#f6f7f9" stroke="#2676ab" stroke-width="3"/>')
for s in strips:svg.append(f'<rect x="{sx(s["x"]-s["width"]/2):.2f}" y="{sy(s["y1"]):.2f}" width="{s["width"]*3.6:.2f}" height="{(s["y1"]-s["y0"])*3.6:.2f}" fill="#153d69"/>')
for x,y in rooflights:svg.append(f'<rect x="{sx(x)-3}" y="{sy(y)-2}" width="6" height="4" fill="#6198b4"/>')
for ap in apertures:
 x,y,z=ap['wall_position_m'];svg.append(f'<circle cx="{sx(x):.2f}" cy="{sy(y):.2f}" r="3" fill="#e5ab2f"/>')
svg.append(f'<text x="55" y="800" font-family="Arial" font-size="18" fill="#12334b">74 CAD apertures; {len(grid)} visual PV modules / {len(strips)} strips; {len(rooflights)} roof fixtures. Image layout estimate, not survey.</text></svg>')
(OUT/'roof_plan.svg').write_text('\n'.join(svg),encoding='utf8')
references=[]
for p in sorted(REF.glob('*.png')):references.append(dict(file=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),role='appearance authority supplied by user'))
metadata=dict(reference_version=4,roof_seam_visual_width_m=.15,roof_grid_pitch_m=6.1,scope='external main-building shell, roof and loading dock modules only; existing interior unchanged',
 footprint_outline_m=fp,footprint_area_m2=CAD['footprint_area_m2'],cad_apertures=apertures,
 interfaces=dict(interior_floor_z_m=0,external_ground_z_m=-1.2,roof_z_m=13.4,facade_top_z_m=13.6,
  preserved='CAD main footprint, 72 dock/2 drive-in opening widths/centres, existing internal floor/columns/partitions/equipment',
  replace_old_prefixes=['SM_MPR_Exterior_','SM_MPR_Roof','SM_MPR_OfficeGlazing'],
  module_front='local -Y; origin at wall centerline and dock floor, except ground bollard/roof modules'),
 references=references,roof_layout=dict(source=overview.name,cad_control_points_m=control_cad,image_control_points_px=control_px,
  homography=hom.tolist(),visual_module_count=len(grid),continuous_strip_count=len(strips),strips=strips,fixture_positions_m=rooflights),
 assumptions=['Reference-generated images govern appearance; CAD governs physical plan. No survey accuracy claimed for image-derived appearance.',
  'Dock/shell heights retain the existing 13.4m roof / 13.6m facade and -1.2m external-ground interfaces; the references do not establish engineering dimensions.',
  'PV module pitch, fixtures, fabric, lamps and number plates are visual estimates; numbers 01-74 are visualization ordering, not verified operating door IDs.',
  'New roof solar layout is sampled from the latest overview using four CAD-corresponding roof corners, cross-checked with images 01/05/06; cell counts are not a capacity inventory.',
  'Office glazing is an external facade layer at existing office interfaces; it does not create new CAD door openings.'],
 replaced_assets_are_not_modified=True)
manifest=g.export(OUT,metadata,instances)
manifest['schema_version']=4
byname={r['name']:r for r in manifest['meshes']}
for r in manifest['meshes']:
 r['lod']=1 if r['name'].endswith('_LOD1') else 0
 if r['name'].startswith('SM_MPR4_SolarBank') and r['lod']==0:
  lo=byname[r['name']+'_LOD1'];r.update(lod_files=[lo['fbx']],lod_triangles=[r['triangles'],lo['triangles']],lod_screen_sizes=[1,.30])
(OUT/'reference_shell_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,default=lambda v:v.item() if isinstance(v,np.generic) else str(v)),encoding='utf8')
print('MPR_REFERENCE_SHELL_COMPLETE',json.dumps(manifest['optimization']))
