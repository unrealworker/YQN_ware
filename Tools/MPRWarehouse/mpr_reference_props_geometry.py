"""Deterministic opaque foliage and yard vehicles for MPR reference v3.

Geometry helpers only. All coordinates are metres; +X is a vehicle's front.
No existing GHS sources, editor state, or UE assets are written.
"""
import math
import random
from mathutils import Vector
import bmesh


PALETTE = {
 'LeafSage':(.29,.355,.255),'LeafLight':(.40,.46,.34),'LeafDark':(.18,.235,.155),
 'Bark':(.205,.18,.135),'TrailerWhite':(.88,.90,.91),'TrailerBlue':(.012,.16,.43),
 'TrailerCoral':(.65,.055,.035),'VehicleMetal':(.38,.41,.41),'VehicleDark':(.065,.075,.08),
 'VehicleRubber':(.026,.030,.031),'VehicleGlass':(.10,.16,.20),
 'VehicleWhite':(.70,.73,.74),'VehicleGray':(.31,.35,.38),
 'VehicleSeam':(.25,.28,.29),'ReflectWhite':(.88,.89,.85),'ReflectRed':(.65,.035,.025),
 'ReflectAmber':(.78,.37,.035),'FreightWhite':(.67,.69,.68),'FreightRoof':(.57,.60,.61),
}


class Mesh:
 def __init__(self):self.vertices=[];self.faces=[];self.roles=[];self.smooth=[]
 def emit(self,role,vertices,faces,smooth=False):
  off=len(self.vertices);self.vertices.extend(tuple(v) for v in vertices)
  self.faces.extend(tuple(i+off for i in f) for f in faces);self.roles.extend([role]*len(faces));self.smooth.extend([smooth]*len(faces))
 def box(self,role,center,size,bevel=0):
  if bevel:
   bm=bmesh.new();bmesh.ops.create_cube(bm,size=1)
   for v in bm.verts:v.co=Vector((v.co.x*size[0]+center[0],v.co.y*size[1]+center[1],v.co.z*size[2]+center[2]))
   bmesh.ops.bevel(bm,geom=list(bm.edges),offset=bevel,segments=1,affect='EDGES')
   bm.verts.ensure_lookup_table();bm.verts.index_update();vv=[tuple(v.co) for v in bm.verts];ff=[tuple(v.index for v in f.verts) for f in bm.faces]
   self.emit(role,vv,ff);bm.free();return
  x,y,z=center;a,b,h=[s/2 for s in size]
  vv=[(x+u*a,y+v*b,z+w*h) for u,v,w in [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]]
  self.emit(role,vv,[(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)])
 def branch(self,role,a,b,r0,r1,sides=8):
  a,b=Vector(a),Vector(b);axis=(b-a).normalized();ref=Vector((0,0,1)) if abs(axis.z)<.9 else Vector((1,0,0));u=axis.cross(ref).normalized();v=axis.cross(u)
  vv=[tuple(p+(u*math.cos(i*math.tau/sides)+v*math.sin(i*math.tau/sides))*r) for p,r in [(a,r0),(b,r1)] for i in range(sides)]
  ff=[tuple(reversed(range(sides))),tuple(range(sides,2*sides))]+[(i,(i+1)%sides,(i+1)%sides+sides,i+sides) for i in range(sides)]
  self.emit(role,vv,ff,True)
 def leaf(self,role,center,u,v,size,thickness=.11):
  center,u,v=Vector(center),Vector(u).normalized(),Vector(v).normalized();n=u.cross(v).normalized();a,b=size
  vv=[tuple(center+u*a),tuple(center+v*b),tuple(center-u*a*.83),tuple(center-v*b),tuple(center+n*b*thickness),tuple(center-n*b*thickness*.7)]
  self.emit(role,vv,[(0,1,4),(1,2,4),(2,3,4),(3,0,4),(1,0,5),(2,1,5),(3,2,5),(0,3,5)],True)
 def round_leaf(self,role,center,u,v,size):
  center,u,v=Vector(center),Vector(u).normalized(),Vector(v).normalized();n=u.cross(v).normalized();a,b=size
  vv=[tuple(center+u*(math.cos(i*math.tau/8)*a)+v*(math.sin(i*math.tau/8)*b)) for i in range(8)]
  vv.extend([tuple(center+n*b*.26),tuple(center-n*b*.18)])
  ff=[]
  for i in range(8):ff.extend([(i,(i+1)%8,8),((i+1)%8,i,9)])
  self.emit(role,vv,ff,True)
 def lobe(self,role,center,radii,seed=0,sides=7):
  rng=random.Random(seed);vv=[(center[0],center[1],center[2]+radii[2])]
  for z in (.48,-.48):
   for i in range(sides):
    a=i*math.tau/sides;scale=.84+rng.uniform(-.09,.09)
    vv.append((center[0]+math.cos(a)*radii[0]*scale,center[1]+math.sin(a)*radii[1]*scale,center[2]+z*radii[2]))
  vv.append((center[0],center[1],center[2]-radii[2]));last=len(vv)-1
  ff=[]
  for i in range(sides):
   j=(i+1)%sides;ff.extend([(0,1+i,1+j),(1+i,1+sides+i,1+sides+j,1+j),(last,1+sides+j,1+sides+i)])
  self.emit(role,vv,ff,True)
 def core(self,role,center,radii,seed):
  bm=bmesh.new();bmesh.ops.create_icosphere(bm,subdivisions=1,radius=1)
  bm.verts.ensure_lookup_table();bm.verts.index_update();rng=random.Random(seed)
  vv=[]
  for vert in bm.verts:
   p=vert.co;noise=1+rng.uniform(-.075,.075)
   vv.append((center[0]+p.x*radii[0]*noise,center[1]+p.y*radii[1]*noise,center[2]+p.z*radii[2]*noise))
  self.emit(role,vv,[tuple(v.index for v in f.verts) for f in bm.faces],True);bm.free()


TREE_SPECS = [
 ('Broadleaf',8.8,3.35,1.0,450),('Upright',10.4,2.75,.92,430),('Spreading',7.6,3.65,1.07,470),
]


def foliage(variant,lod,shrub=False):
 name,height,radius,spread,leaves=TREE_SPECS[variant%3]
 if shrub:height,radius,leaves=(1.35,1.1,180) if variant==0 else (1.9,1.65,220)
 rng=random.Random(7381+variant*701+(1100 if shrub else 0));m=Mesh();lobes=[]
 if shrub:
  for i in range(7):
   a=i*2.399963;r=radius*(.25+.27*rng.random());z=height*(.45+.18*rng.random())
   lobes.append(((math.cos(a)*r,math.sin(a)*r,z),(radius*.52,radius*.48,height*.45)))
   m.branch('Bark',(0,0,.02),(math.cos(a)*r,math.sin(a)*r,z),.035,.009,5)
 else:
  # Visible trunk and true bifurcating scaffold, with crown bases above eye level.
  p0=(0,0,0);p1=(.08,-.06,height*.26);p2=(-.12,.1,height*.53);p3=(.05,.0,height*.83)
  for a,b,r0,r1 in [(p0,p1,.18,.13),(p1,p2,.13,.075),(p2,p3,.075,.025)]:m.branch('Bark',a,b,r0,r1,10 if lod==0 else 7)
  for i in range(12):
   angle=i*2.399963+rng.uniform(-.15,.15);tier=i%3
   z=height*(.42+tier*.16);rad=radius*(.63 if tier<2 else .40)
   center=(math.cos(angle)*rad,math.sin(angle)*rad,z+height*.08)
   sizes=(radius*(.39 if tier<2 else .35),radius*.37,height*(.17 if tier<2 else .18))
   lobes.append((center,sizes))
   base=(.04,-.02,z*.73);mid=(center[0]*.55,center[1]*.55,z-.1)
   m.branch('Bark',base,mid,.075 if tier<2 else .05,.035,7 if lod==0 else 5)
   if lod<2:
    m.branch('Bark',mid,center,.035,.011,5)
    for k in (-1,1):
     tip=(center[0]+math.cos(angle+k*.65)*sizes[0]*.65,center[1]+math.sin(angle+k*.65)*sizes[1]*.65,center[2]+sizes[2]*.34)
     m.branch('Bark',mid,tip,.021,.005,5 if lod==0 else 3)
  lobes.append(((0,0,height*.83),(radius*.48,radius*.44,height*.16)))
 # Many small opaque micro-clumps support the exterior leaflets. Groups of
 # four 20-triangle clumps make an 80-triangle compound twig cluster. There
 # are 32 small pieces per main branch lobe, not four large exposed balls.
 if lod<2:
  for i,(center,sizes) in enumerate(lobes):
   for k in range((16 if shrub else 32) if lod==0 else 2):
    crng=random.Random(variant*5101+i*97+k*13)
    direction=Vector((crng.gauss(0,1),crng.gauss(0,1),crng.gauss(0,1))).normalized();rho=crng.random()**.33*.80
    offset=tuple(direction[j]*sizes[j]*rho for j in range(3))
    p=tuple(center[j]+offset[j] for j in range(3));rr=tuple(s*(crng.uniform(.26,.35) if lod==0 else .72) for s in sizes)
    role=('LeafSage','LeafSage','LeafLight','LeafDark')[k%4]
    if lod==0:m.core(role,p,rr,variant*110+i*4+k)
    else:m.lobe(role,p,rr,variant*110+i*4+k,7)
 if lod==0:
  # Opaque rounded micro-clusters: dense irregular texture without alpha cards
  # or large smooth sphere canopies. Each closed cluster is 16 real triangles.
  for i in range(leaves):
   center,sizes=lobes[i%len(lobes)];direction=Vector((rng.gauss(0,1),rng.gauss(0,1),rng.gauss(0,1))).normalized()
   rho=.82+rng.random()*.20
   p=Vector((center[0]+direction.x*sizes[0]*rho,center[1]+direction.y*sizes[1]*rho,center[2]+direction.z*sizes[2]*rho))
   tilt=rng.uniform(-.65,.65);az=rng.uniform(0,math.tau);u=Vector((math.cos(az),math.sin(az),tilt)).normalized();v=Vector((-math.sin(az),math.cos(az),rng.uniform(-.45,.45)))
   v=(v-u*v.dot(u)).normalized();sz=(.18+.08*rng.random())*(.64 if shrub else 1)
   role=('LeafDark','LeafSage','LeafSage','LeafLight')[rng.randrange(4)]
   m.round_leaf(role,p,u,v,(sz,sz*(.60+.16*rng.random())))
 elif lod==1:
  count=56 if not shrub else 38
  for i in range(count):
   center,sizes=lobes[i%len(lobes)];d=Vector((rng.gauss(0,1),rng.gauss(0,1),rng.gauss(0,1))).normalized();rho=rng.random()**.45
   p=Vector((center[0]+d.x*sizes[0]*rho,center[1]+d.y*sizes[1]*rho,center[2]+d.z*sizes[2]*rho))
   size=(.72 if not shrub else .36)*rng.uniform(.8,1.2)
   m.lobe(('LeafSage','LeafLight','LeafDark')[i%3],p,(size,size*.85,size*.90),variant*31+i,3)
 else:
  for i,(center,sizes) in enumerate(lobes):m.lobe(('LeafSage','LeafLight','LeafDark')[i%3],center,sizes,variant*21+i,5 if shrub else 7)
 # Each LOD is pinned to the same intended biological dimensions. Bounds stay
 # stable as density changes; trunk base remains the actor placement origin.
 zmax=max(v[2] for v in m.vertices);xymax=max(math.hypot(v[0],v[1]) for v in m.vertices)
 m.vertices=[(v[0]*radius/xymax,v[1]*radius/xymax,max(0,v[2]*height/zmax)) for v in m.vertices]
 return m,dict(kind='shrub' if shrub else 'tree',variant=name if not shrub else ('LowMound' if variant==0 else 'MixedCluster'),height_m=height,crown_radius_m=radius,
               opacity='opaque solid foliage',wind_tick=False,alpha_cards=False,seed=7381+variant*701+(1100 if shrub else 0))


def wheel(m,x,y,z,radius,width,lod=0,steel=False):
 n=(20,12,8)[lod];ring=[(-width/2,.84*radius),(-width*.30,radius),(width*.30,radius),(width/2,.84*radius)] if lod<2 else [(-width/2,radius),(width/2,radius)]
 vv=[(x+math.cos(i*math.tau/n)*r,y+off,z+math.sin(i*math.tau/n)*r) for off,r in ring for i in range(n)]
 ff=[tuple(range(n))]
 for k in range(len(ring)-1):ff.extend((k*n+i,(k+1)*n+i,(k+1)*n+(i+1)%n,k*n+(i+1)%n) for i in range(n))
 ff.append(tuple(reversed(range((len(ring)-1)*n,len(ring)*n))))
 m.emit('VehicleMetal' if steel else 'VehicleRubber',vv,ff,True)
 for sign in (-1,1):
  face_y=y+sign*(width/2+.004);r=radius*(.58 if steel else .55)
  pts=[(x+math.cos(i*math.tau/n)*r,face_y,z+math.sin(i*math.tau/n)*r) for i in range(n)]
  m.emit('VehicleMetal',pts,[tuple(reversed(range(n))) if sign>0 else tuple(range(n))],True)
  if lod==0:
   m.branch('VehicleDark',(x,face_y,z),(x,face_y+sign*.025,z),r*.29,r*.29,10)
   for i in range(6):
    a=i*math.tau/6;bx=x+math.cos(a)*r*.65;bz=z+math.sin(a)*r*.65
    m.branch('VehicleDark',(bx,face_y,bz),(bx,face_y+sign*.014,bz),.025,.025,5)


def trailer(color,lod,coupled=False):
 m=Mesh();role={'White':'TrailerWhite','Blue':'TrailerBlue','Coral':'TrailerCoral'}[color]
 length,width=16.15,2.60;half=length/2;bottom,top=1.25,4.13
 m.box(role,(0,0,(bottom+top)/2),(length,width,top-bottom),.028 if lod==0 else 0)
 m.box('TrailerWhite',(0,0,top+.018),(length,2.60,.036),.012 if lod==0 else 0)
 # Box end frames and longitudinal rails remain visible at every LOD.
 for side in (-1,1):
  m.box('VehicleMetal',(0,side*1.306,bottom+.035),(length,.032,.085))
  m.box('VehicleMetal',(0,side*1.306,top-.025),(length,.03,.065))
 for x in (-half,half):
  for side in (-1,1):m.box('VehicleMetal',(x,side*1.275,(bottom+top)/2),(.055,.055,top-bottom))
 for side in (-1,1):m.box('VehicleDark',(-.3,side*.82,1.10),(15.4,.16,.22))
 m.box('VehicleDark',(-4.95,0,.92),(3.0,1.9,.18))
 for x in (-5.65,-4.32):
  for y in (-1.16,-.91,.91,1.16):wheel(m,x,y,.51,.51,.22,lod)
 # Connected combinations retract their landing gear above the pavement.
 for side in (-1,1):
  m.box('VehicleDark',(4.85,side*.84,.91 if coupled else .59),(.13,.13,.48 if coupled else 1.12))
  m.box('VehicleMetal',(4.85,side*.84,.67 if coupled else .025),(.48,.34,.05))
  if lod<2:m.branch('VehicleDark',(4.4,side*.84,1.05),(4.85,side*.84,.73 if coupled else .36),.035,.035,6)
 m.branch('VehicleMetal',(6.55,0,1.03),(6.55,0,.88),.055,.055,8)
 # Rear dual doors and hardware. -X is the loading end.
 for side in (-1,1):
  m.box('TrailerWhite' if color=='White' else role,(-half-.025,side*.637,2.70),(.045,1.25,2.72))
  if lod<2:
   m.branch('VehicleMetal',(-half-.072,side*.48,1.43),(-half-.072,side*.48,3.98),.021,.021,8 if lod==0 else 5)
   m.box('VehicleMetal',(-half-.095,side*.34,1.85),(.045,.28,.04))
   for z in (1.65,2.70,3.74):m.box('VehicleMetal',(-half-.065,side*1.20,z),(.045,.15,.065))
 m.box('VehicleSeam',(-half-.052,0,2.7),(.012,.012,2.72))
 m.box('VehicleMetal',(-half-.13,0,.48),(.14,2.32,.16))
 for y in (-.86,.86):m.box('VehicleDark',(-half+.01,y,.86),(.13,.10,.66))
 if lod<2:
  for side in (-1,1):
   m.box('VehicleRubber',(-6.35,side*1.06,.40),(.045,.55,.55))
   for i in range(29):
    x=-half+.25+i*.55
    m.box('ReflectRed' if i%2 else 'ReflectWhite',(x,side*1.326,1.40),(.30,.007,.055))
   for x in (-7.8,0,7.8):m.box('ReflectAmber',(x,side*1.326,1.56),(.09,.009,.05))
  for y in (-.85,-.60,.60,.85):m.box('ReflectRed',(-half-.209,y,.49),(.012,.14,.08))
 if lod==0:
  for side in (-1,1):
   for i in range(1,16):
    x=-half+i
    m.box('VehicleSeam',(x,side*1.302,2.72),(.006,.005,2.72))
    for k in range(7):
     z=1.47+k*.39
     m.branch('VehicleMetal',(x,side*1.305,z),(x,side*1.312,z),.008,.008,4)
  for x in (-6.9,-3.3,-.3,2.7,5.7):m.box('VehicleMetal',(x,0,1.12),(.08,2.40,.07))
 return m,dict(kind='semi_trailer',color=color,tractor_cab=False,coupled_to_separate_tractor=coupled,landing_gear='retracted' if coupled else 'extended',kingpin_x_m=6.55,wheel_contact_z_m=0.,front_axis='+X',loading_doors='-X',nominal_box_m=[length,width,top-bottom],overall_height_m=top+.036,ground_origin=True)


def freight(lod):
 m=Mesh();length,width=18.8,3.05;half=length/2
 m.box('FreightWhite',(0,0,2.70),(length,width,2.96),.055 if lod==0 else 0)
 # Very shallow pitched/curved roof gives a clean white-grey railcar silhouette.
 yz=[(-1.55,4.17),(-1.45,4.35),(-.7,4.43),(.7,4.43),(1.45,4.35),(1.55,4.17)]
 vv=[(x,y,z) for x in (-half,half) for y,z in yz]
 ff=[tuple(reversed(range(6))),tuple(range(6,12))]+[(i,i+1,i+7,i+6) for i in range(5)]+[(5,0,6,11)]
 m.emit('FreightRoof',vv,ff)
 for y in (-.85,.85):m.box('VehicleDark',(0,y,1.03),(19.15,.20,.30))
 for bx in (-6.3,6.3):
  m.box('VehicleDark',(bx,0,.95),(3.5,2.25,.30))
  for x in (bx-.9,bx+.9):
   m.branch('VehicleMetal',(x,-.95,.48),(x,.95,.48),.085,.085,8)
   for y in (-.85,.85):wheel(m,x,y,.48,.48,.16,lod,True)
 for side in (-1,1):
  m.box('VehicleMetal',(0,side*1.54,1.29),(18.8,.06,.14))
  m.box('FreightWhite',(0,side*1.555,2.72),(3.55,.055,2.64),.025 if lod==0 else 0)
  m.box('VehicleMetal',(0,side*1.59,1.44),(4.3,.09,.08))
  m.box('VehicleMetal',(0,side*1.59,4.05),(4.3,.09,.08))
  if lod<2:
   for i in range(19):
    x=-9+i
    if abs(x)<1.9:continue
    m.box('FreightRoof',(x,side*1.55,2.75),(.065,.065,2.74))
   m.box('VehicleDark',(.5,side*1.595,2.6),(.06,.025,.5))
   for x in (-8,-5,-2,2,5,8):m.box('ReflectAmber',(x,side*1.59,1.42),(.18,.01,.04))
  if lod==0:
   for x in (-8.9,8.9):
    for rail in (-.20,.20):m.branch('VehicleMetal',(x+rail,side*1.63,1.25),(x+rail,side*1.63,3.7),.018,.018,6)
    for z in (1.45,1.85,2.25,2.65,3.05,3.45):m.branch('VehicleMetal',(x-.20,side*1.63,z),(x+.20,side*1.63,z),.018,.018,6)
 for x in (-9.85,9.85):
  m.box('VehicleDark',(x,0,.86),(1.10,.32,.24))
  m.box('VehicleMetal',(x+(.40 if x>0 else -.40),0,.86),(.26,.45,.26))
 return m,dict(kind='rail_boxcar',body_length_m=18.8,overall_length_m=20.76,front_axis='+X',estimated_dimensions=True,source='reference multiview 01/06 white-grey freight cars')


def car(variant,lod):
 from park_vehicles import build_car
 m=Mesh();roles={'Buildings':'VehicleWhite' if variant==0 else 'VehicleGray','Blue':'VehicleGray','Detail':'VehicleSeam','Markings':'VehicleMetal','Solar':'VehicleGlass','Rubber':'VehicleRubber','VehicleLights':'ReflectRed'}
 if lod==2:
  body=roles['Buildings'];height=1.68 if variant else 1.44
  m.box(body,(0,0,.60),(4.48,1.78,.55),.12)
  vv=[(-1.65,-.81,.87),(1.20,-.81,.87),(1.20,.81,.87),(-1.65,.81,.87),(-1.2,-.67,height),(.55,-.67,height),(.55,.67,height),(-1.2,.67,height)]
  m.emit('VehicleGlass',vv,[(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)])
  m.emit(body,vv,[(4,5,6,7)])
  for x in (-1.4,1.42):
   for y in (-.84,.84):wheel(m,x,y,.32,.32,.16,2)
  for side in (-1,1):
   m.box('ReflectWhite',(2.245,side*.53,.56),(.012,.3,.1))
   m.box('ReflectRed',(-2.245,side*.53,.62),(.012,.25,.1))
  return m,dict(kind='sedan' if variant==0 else 'compact_suv',source_generator='Scripts/ghs/park_vehicles.py silhouette',front_axis='+X',neutral_color=True)
 build_car({'mesh':lambda role,vv,ff:m.emit(roles[role],vv,ff)},0,0,variant=variant,blue=False)
 if lod==0:
  # Fine bright wheel spokes, hood shut lines and roof trim enrich the reused
  # GHS silhouettes while retaining their verified parking footprint.
  for x in (-1.40,1.42):
   for side in (-1,1):
    for i in range(5):
     a=i*math.tau/5
     m.branch('VehicleMetal',(x,side*.934,.36),(x+math.cos(a)*.142,side*.934,.36+math.sin(a)*.142),.012,.009,5)
  for side in (-1,1):
   m.box('VehicleMetal',(.05,side*.891,.93 if variant else .83),(2.45,.009,.018))
   m.box('VehicleSeam',(.15,side*.897,.62),(.009,.009,.38))
  m.box('ReflectWhite',(2.253,0,.49),(.008,.32,.09))
 zmin=min(v[2] for v in m.vertices);m.vertices=[(x,y,z-zmin) for x,y,z in m.vertices]
 return m,dict(kind='sedan' if variant==0 else 'compact_suv',source_generator='Scripts/ghs/park_vehicles.py',front_axis='+X',neutral_color=True)
