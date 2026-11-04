"""Build the reference-v3 outdoor site in isolated Blender. CAD metres, +Y.

The existing survey alignment provides topology only. Every output mesh is new;
the reference images define surface hierarchy, planting and estimated occupancy.
"""
import sys,json,math,random,hashlib,struct,zlib
from pathlib import Path
from collections import defaultdict,Counter
import bpy,numpy as np
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'Tools/MPRWarehouse'),str(ROOT/'Saved/ParkRefinement/python_deps'),str(ROOT/'Scripts/ghs')]
from mpr_blender_common import Geometry
from mpr_site_roads import build_site_roads,emit_shape,polygons,ribbon
from mpr_context_buildings import build_context_buildings
from mpr_railway_detail import build_railways
from park_curves import dash_segments,offset_path,sample_along
from shapely.geometry import Polygon,Point,LineString,box
from shapely.ops import unary_union
from shapely.affinity import rotate,translate
import shapely

OUT=ROOT/'SourceAssets/MPR/reference_v3/site'
G=-1.2;GEO=Geometry();RNG=random.Random(11021001)
SOURCE=json.loads((ROOT/'SourceAssets/MPR/environment/environment_local.json').read_text())
CAD=json.loads((ROOT/'SourceAssets/MPR/mpr_cad_layout.json').read_text())
MAIN=Polygon(CAD['footprint_outline_m']);INSTANCES=defaultdict(list);COUNTS=Counter();REJECT=Counter()
MATERIALS={
 'MPR3_Asphalt':dict(base_color=[.23,.265,.29],roughness=.94,texture='asphalt'),
 'MPR3_Concrete':dict(base_color=[.57,.59,.57],roughness=.91,texture='concrete'),
 'MPR3_Curb':dict(base_color=[.69,.71,.68],roughness=.9,texture='concrete'),
 'MPR3_Grass':dict(base_color=[.36,.43,.345],roughness=.98,texture='grass'),
 'MPR3_GrassFar':dict(base_color=[.40,.455,.39],roughness=.98,texture='grass'),
 'MPR3_WhiteLine':dict(base_color=[.81,.82,.78],roughness=.85),
 'MPR3_YellowLine':dict(base_color=[.78,.55,.13],roughness=.85),
 'MPR3_PavingJoint':dict(base_color=[.37,.40,.39],roughness=.98),
 'MPR3_PondWater':dict(base_color=[.045,.18,.22],roughness=.26,metallic=.15,texture='water'),
 'MPR3_ContextWall':dict(base_color=[.72,.735,.725],roughness=.88,texture='concrete'),
 'MPR3_ContextRoof':dict(base_color=[.65,.68,.70],roughness=.84),
 'MPR3_ContextTrim':dict(base_color=[.52,.55,.56],roughness=.86),
 'MPR3_ContextGlass':dict(base_color=[.22,.26,.28],roughness=.48),
 'MPR3_Ballast':dict(base_color=[.36,.365,.36],roughness=.98,texture='ballast'),
 'MPR3_Sleepers':dict(base_color=[.24,.235,.22],roughness=.95),
 'MPR3_RailSteel':dict(base_color=[.40,.43,.45],roughness=.5,metallic=.65),
}
ROLE_MAP={r:'MPR3_'+r for r in ['ContextWall','ContextRoof','ContextTrim','ContextGlass','Ballast','Sleepers','RailSteel']}

def zone(x,y):
 if -290<x<285 and -220<y<355:return 'Near'
 return 'Far_'+('W' if x<-290 else 'E' if x>285 else 'N' if y>355 else 'S')

def mesh(name,role,verts,faces):GEO.mesh(name.replace('SM_MPR_Env_','SM_MPR3_Site_'),ROLE_MAP.get(role,role),verts,faces)
def poly(name,role,points,z):
 # Callers supply convex triangles or simple loops. A zero-height prism keeps
 # the common tessellator but only its top surface is emitted here.
 from mathutils.geometry import tessellate_polygon
 vv=[Vector((p[0],p[1],z)) for p in points]
 ff=[]
 for t in tessellate_polygon([vv]):
  ids=[v if isinstance(v,int) else min(range(len(vv)),key=lambda k:(vv[k]-v).length_squared) for v in t]
  if (vv[ids[1]]-vv[ids[0]]).cross(vv[ids[2]]-vv[ids[0]]).z<0:ids.reverse()
  ff.append(ids)
 mesh(name,role,[tuple(v) for v in vv],ff)
def block(name,role,center,size,yaw=0):GEO.box(name.replace('SM_MPR_Env_','SM_MPR3_Site_'),ROLE_MAP.get(role,role),center,size,math.degrees(yaw))
def strip(name,role,a,b,width,z):
 dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
 if length<1e-7:return
 nx,ny=-dy/length*width/2,dx/length*width/2
 poly(name,role,[(a[0]-nx,a[1]-ny),(b[0]-nx,b[1]-ny),(b[0]+nx,b[1]+ny),(a[0]+nx,a[1]+ny)],z)
API=dict(mesh=mesh,poly=poly,box=block,strip=strip,zone=zone,footprint=CAD['footprint_outline_m'],include_freight=False)
def shape(name,role,geometry,z):emit_shape(API,'SM_MPR3_Site_'+name,role,geometry,z)
def lines(name,role,geometry,width,z):
 if geometry.is_empty:return
 if geometry.geom_type=='LineString':ribbon(API,'SM_MPR3_Site_'+name,role,list(geometry.coords),width,z)
 else:
  for part in getattr(geometry,'geoms',[]):lines(name,role,part,width,z)
def raised_edge(name,geometry,z,height=.15):
 shape(name,'MPR3_Curb',geometry,z+height)
 for p in polygons(geometry):
  for ring in [p.exterior,*p.interiors]:
   for a,b in zip(ring.coords,list(ring.coords)[1:]):
    mesh('SM_MPR3_Site_'+name,'MPR3_Curb',[(a[0],a[1],z),(b[0],b[1],z),(b[0],b[1],z+height),(a[0],a[1],z+height)],[(0,1,2,3)])

def build_surfaces():
 # Pure geometry pass: retain the proven junction/curve coordinates, discard
 # its former asphalt courts, paint, tiny pond and planting appearance.
 quiet={k:(lambda *a,**kw:None) for k in ('mesh','poly','box','strip')};quiet.update(zone=zone)
 site=build_site_roads(quiet,SOURCE,G)
 north=box(-166.08,74.546,166.786,137.8)
 south=Polygon([(-166.08,-83.95),(135.36,-83.95),(145,-101),(146,-111),(132,-120),(94,-128),(49,-134),(-98,-146),(-162,-133),(-193,-119),(-184,-106),(-166.08,-104)])
 courts=unary_union([north,south]).difference(MAIN.buffer(.10)).difference(site['roads'])
 # The reference has a generous triangular pond and an uninterrupted pale path.
 pond=Polygon([(-234,-159),(-234,-212),(-189,-197)]).buffer(5,quad_segs=16).buffer(-6,quad_segs=16)
 pond=pond.difference(site['paved'].buffer(4))
 path=pond.buffer(2.8,quad_segs=16).difference(pond.buffer(.9,quad_segs=16))
 site.update(courts=courts,pond=pond,pond_path=path)
 regions={'Near':box(-290,-220,285,355),'Far_E':box(285,-1800,1800,1800),'Far_W':box(-1800,-1800,-290,1800),'Far_N':box(-290,355,285,1800),'Far_S':box(-290,-1800,285,-220)}
 asphalt=site['paved'].difference(courts)
 all_buildings=[]
 for m in SOURCE['meshes']:
  if m['layer']=='buildings' and m.get('footprintLoops'):
   all_buildings.append(Polygon([m['vertices'][i][:2] for i in m['footprintLoops'][0]]))
 buildings=unary_union(all_buildings)
 # Continuous ground outside the CAD context, avoiding the previous patchwork
 # of rectangular gray plates. Terrain is shared low-contrast grass material.
 for ix in range(-2,3):
  for iy in range(-2,3):
   bounds=box(ix*320-160,iy*320-160,ix*320+160,iy*320+160)
   shape('Ground_%d_%d'%(ix+2,iy+2),'MPR3_GrassFar',bounds,G-.08)
 landscape=box(-700,-700,700,700).difference(site['paved']).difference(buildings).difference(pond.buffer(3.1))
 for region,clip in regions.items():
  shape(region+'_Roads','MPR3_Asphalt',asphalt.intersection(clip),G+.075)
  shape(region+'_Lawns','MPR3_Grass',landscape.intersection(clip),G+.015)
 shape('LoadingCourts','MPR3_Concrete',courts,G+.083)
 curb=site['paved'].buffer(.25,quad_segs=8).difference(site['paved']).difference(MAIN.buffer(.35))
 raised_edge('Curbs',curb.intersection(box(-280,-225,280,155)),G+.03,.15)
 shape('ParkingIslands','MPR3_Grass',site['islands'],G+.18)
 shape('Pond','MPR3_PondWater',pond,G-.03)
 raised_edge('PondWalk',path,G+.01,.07)
 shape('PondBank','MPR3_Grass',pond.buffer(.9).difference(pond),G+.01)
 # Fine concrete expansion joints survive close cameras without a dense mesh.
 for x in range(-192,181,6):lines('CourtJoints','MPR3_PavingJoint',LineString([(x,-155),(x,145)]).intersection(courts),.028,G+.089)
 for y in range(-150,145,6):lines('CourtJoints','MPR3_PavingJoint',LineString([(-220,y),(220,y)]).intersection(courts),.028,G+.089)
 for name,pts in site['paths'].items():
  width={'Prologis':10.8,'PortReading':13,'WestAccess':8.5,'NorthCourt':9,'EastAccess':7}[name]
  for dash in dash_segments(pts,3.5,6.5):lines('RoadDashes','MPR3_WhiteLine',LineString(dash),.13,G+.092)
  if name in ('Prologis','PortReading','WestAccess'):
   for offset in (-width/2+.45,width/2-.45):lines('RoadEdges','MPR3_WhiteLine',LineString(offset_path(pts,offset)),.12,G+.092)
 for door in CAD['dock_doors']:
  p=door['position_m'];n=door['outward_normal_xy'];t=(-n[1],n[0]);width=3.15
  for sign in (-1,1):
   a=(p[0]+n[0]*1.0+t[0]*width/2*sign,p[1]+n[1]*1.0+t[1]*width/2*sign)
   b=(a[0]+n[0]*19,a[1]+n[1]*19)
   lines('DockGuidance','MPR3_YellowLine',LineString([a,b]).intersection(courts.buffer(.2)),.11,G+.096)
 for lo,hi,ylo,yhi in [(-211,-182.2,-93,83),(183.3,211,-17,83)]:
  for x in (lo+3.3,hi-3.3):
   for y in np.arange(ylo+1.1,yhi-2,2.8):
    slot=box(x-2.55,y,x+2.55,y+2.7)
    if site['islands'].intersects(slot.buffer(.15)):continue
    lines('ParkingLines','MPR3_WhiteLine',LineString([(x-2.55,y),(x+2.55,y)]),.09,G+.093)
 # A few transverse crossing stripes only at the two campus entrance throats.
 for cx,cy in [(-210,-109),(-214,106)]:
  for k in range(7):block('SM_MPR3_Site_Crosswalks','MPR3_WhiteLine',(cx-3+k*.95,cy,G+.09),(.40,3.1,.006))
 COUNTS['dock_guidance_bays']=len(CAD['dock_doors']);COUNTS['concrete_court_m2']=round(courts.area,1)
 return site

def build_context():
 context=build_context_buildings(API,SOURCE,G)
 # Real neighbor footprint, substantially articulated light-gray dock facade.
 neighbor=next(m for m in SOURCE['meshes'] if m['id']=='1582')
 pts=[neighbor['vertices'][i][:2] for i in neighbor['footprintLoops'][0]]
 p=Polygon(pts);outline=list(shapely.orient_polygons(p).exterior.coords)[:-1]
 for a,b in zip(outline,outline[1:]+outline[:1]):
  length=math.dist(a,b)
  if length<200:continue
  tx,ty=(b[0]-a[0])/length,(b[1]-a[1])/length;nx,ny=ty,-tx
  if nx*(-p.centroid.x)+ny*(-p.centroid.y)<0:continue
  yaw=math.atan2(ty,tx)
  for k in range(28):
   s=5+(length-10)*(k+.5)/28;x=a[0]+tx*s;y=a[1]+ty*s
   block('SM_MPR3_Site_NeighborDocks','MPR3_ContextTrim',(x+nx*.3,y+ny*.3,G+3.15),(3.6,.55,4.25),yaw)
   block('SM_MPR3_Site_NeighborDocks','MPR3_ContextGlass',(x+nx*.60,y+ny*.60,G+2.9),(3.0,.06,3.7),yaw)
   block('SM_MPR3_Site_NeighborDocks','MPR3_ContextWall',(x+nx*.42-tx*2.1,y+ny*.42-ty*2.1,G+3.3),(.38,1.15,6.6),yaw)
   block('SM_MPR3_Site_NeighborDocks','MPR3_Concrete',(x+nx*2,y+ny*2,G+.12),(4.5,4,.18),yaw)
   COUNTS['neighbor_docks']+=1
 return context

def footprint(center,length,width,yaw):return translate(rotate(box(-length/2,-width/2,length/2,width/2),yaw,origin=(0,0)),center[0],center[1])
def add(name,x,y,z=G+.075,yaw=0,scale=1):
 INSTANCES[name].append(dict(position_m=[float(x),float(y),float(z)],rotation_deg=float(yaw),scale=[float(scale)]*3))

def place_vehicles(site,rail):
 occupied=[];palette=['White','White','Blue','White','Coral','Blue','White']
 for i,d in enumerate(CAD['dock_doors']):
  if i%5==3:continue
  p=d['position_m'];n=d['outward_normal_xy'];yaw=math.degrees(math.atan2(n[1],n[0]))
  x,y=p[0]+n[0]*8.38,p[1]+n[1]*8.38;f=footprint((x,y),16.15,2.6,yaw)
  if f.intersects(MAIN) or any(f.intersects(q) for q in occupied):REJECT['trailer']+=1;continue
  occupied.append(f);add('SM_MPR3_Trailer_'+palette[i%len(palette)],x,y,yaw=yaw)
 for i,x in enumerate(np.arange(-153,36,3.8)):
  y=-124 if x<-100 else -128+(x+100)*.05
  f=footprint((x,y),16.15,2.6,90)
  if not site['courts'].buffer(.3).covers(f) or any(f.buffer(.25).intersects(q) for q in occupied):continue
  occupied.append(f);add('SM_MPR3_Trailer_'+palette[(i+2)%len(palette)],x,y,yaw=90)
  for sx in (-1.8,1.8):lines('TrailerStandLines','MPR3_YellowLine',LineString([(x+sx,y-8),(x+sx,y+8)]),.1,G+.096)
 for i in range(3):
  x,y=127+i*2.6,-105+i*4.1;f=footprint((x,y),16.15,2.6,0)
  if site['paved'].covers(f) and not f.intersects(MAIN) and not any(f.intersects(q) for q in occupied):
   occupied.append(f);add('SM_MPR3_Trailer_Coral',x,y,yaw=0)
 for i,p in enumerate(site['cars']):add('SM_MPR3_Car_'+str(i%2),*p['position_m'][:2],yaw=p['rotation_deg'])
 # Boxcars stay on supplied railway centerlines. Estimate occupancy only.
 train_occupied=[]
 for index,track in enumerate(rail['centerlines']):
  if track['id'] not in ('1429','14e3','13e3','1428'):continue
  line=LineString(track['vertices']);start=max(20,line.project(Point(220,-50))-165)
  for d in np.arange(start,min(line.length-20,start+600),21.5):
   a,b=line.interpolate(d-8),line.interpolate(d+8);p=line.interpolate(d)
   yaw=math.degrees(math.atan2(b.y-a.y,b.x-a.x));f=footprint((p.x,p.y),20.8,3.296,yaw)
   if any(f.buffer(.08).intersects(q) for q in train_occupied):REJECT['boxcar_turnout_overlap']+=1;continue
   train_occupied.append(f);add('SM_MPR3_FreightBoxcar',p.x,p.y,G+.34,yaw=yaw)
 COUNTS['trailers']=sum(len(v) for k,v in INSTANCES.items() if 'Trailer' in k)
 COUNTS['cars']=sum(len(v) for k,v in INSTANCES.items() if '_Car_' in k)
 COUNTS['boxcars']=len(INSTANCES['SM_MPR3_FreightBoxcar'])
 return occupied

def plant(site,rail,context,vehicles):
 buildings=unary_union([Polygon(p) for p in context['footprints']]+[MAIN])
 exclusion=unary_union([site['paved'],rail['exclusion'],site['pond'].buffer(3.2),buildings.buffer(.5),*vehicles])
 planted=[]
 def tree(x,y,scale=1):
  radius=3.9*scale;circle=Point(x,y).buffer(radius+.18,quad_segs=8)
  if circle.intersects(exclusion):REJECT['tree_exclusion']+=1;return
  if any(math.hypot(x-a,y-b)<(radius+r)*.78 for a,b,r in planted):REJECT['tree_spacing']+=1;return
  planted.append((x,y,radius));variant=len(planted)%3
  add('SM_MPR3_Tree_'+str(variant),x,y,G+.025,yaw=RNG.uniform(0,360),scale=scale)
 # Tight campus rows and broad irregular woodland, using one clearance rule.
 for y in np.arange(-120,332,9):tree(-227,y,.77)
 for x in np.arange(-195,180,9):tree(x,146,.80)
 for x,y in site['tree_island_centers']:tree(x,y,.40)
 for name,side in [('Prologis',-1),('Prologis',1),('EastAccess',-1)]:
  offset=13 if name=='Prologis' else 9
  pts=offset_path(site['paths'][name],side*offset)
  for p,t,s in sample_along(pts,10,start=4):tree(*p,RNG.uniform(.70,.90))
 patches=[(-210,-365,220,-160),(-540,-310,-290,400),(-230,335,190,510),(220,120,295,315),(300,-180,650,450),(-620,410,210,650)]
 for x0,y0,x1,y1 in patches:
  for x in np.arange(x0,x1,10):
   for y in np.arange(y0,y1,11):
    if RNG.random()<.56:tree(x+RNG.uniform(-3,3),y+RNG.uniform(-3,3),RNG.uniform(.69,1.02))
 # Smaller shrubs emphasize landscaped corners without filling truck clearances.
 for index,(x,y,r) in enumerate(planted):
  if index%4:continue
  q=(x+3.1,y-2.3);variant=(index//4)%2;scale=RNG.uniform(.7,1.1)
  if Point(q).buffer((1.10 if variant==0 else 1.65)*scale+.15).intersects(exclusion):continue
  add('SM_MPR3_Bush_'+str(variant),*q,G+.025,yaw=RNG.uniform(0,360),scale=scale)
 COUNTS['trees']=len(planted);COUNTS['bushes']=sum(len(v) for k,v in INSTANCES.items() if '_Bush_' in k)
 assert all(not Point(x,y).buffer(r+.18,quad_segs=8).intersects(exclusion) for x,y,r in planted)
 return dict(tree_crown_road_building_rail_intersections=0,all_candidates_checked=True,rejected=dict(REJECT))

def png(path,a):
 a=np.clip(a,0,255).astype(np.uint8)
 if a.ndim==2:a=np.repeat(a[:,:,None],3,2)
 h,w,c=a.shape
 def chunk(t,d):return struct.pack('>I',len(d))+t+d+struct.pack('>I',zlib.crc32(t+d)&0xffffffff)
 path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(b'\0'+r.tobytes() for r in a),7))+chunk(b'IEND',b''))

def textures():
 out=OUT/'textures';out.mkdir(parents=True,exist_ok=True);result={};rng=np.random.default_rng(31102);n=1024
 y,x=np.mgrid[:n,:n];noise=rng.random((n,n))-.5
 for kind in ('asphalt','concrete','grass','ballast','water'):
  wave=np.sin(x*math.tau/n*9)*np.sin(y*math.tau/n*11)
  if kind=='grass':height=noise*.4+wave*.12;strength=1.1;albedo=234+height*26
  elif kind=='ballast':height=np.sin(x*.38+noise*.5)*np.sin(y*.41+noise*.5)*.3+noise*.4;strength=2.1;albedo=220+height*63
  elif kind=='water':height=np.sin((x*3+y*11)*math.tau/n)*.2+np.sin((x*7-y*4)*math.tau/n)*.11;strength=4;albedo=245+height*10
  else:height=noise*(.14 if kind=='concrete' else .32)+wave*.018;strength=1.8;albedo=240+height*35
  dx=(np.roll(height,-1,1)-np.roll(height,1,1))*strength;dy=(np.roll(height,-1,0)-np.roll(height,1,0))*strength
  normal=np.stack([-dx,dy,np.ones_like(dx)],2);normal/=np.linalg.norm(normal,axis=2,keepdims=True)
  result[kind]={}
  for channel,data in [('albedo',albedo),('normal',(normal*.5+.5)*255)]:
   path=out/('T_MPR3_'+kind+'_'+channel+'.png');png(path,data);result[kind][channel]=path.relative_to(ROOT).as_posix()
 return result

def export(tex,metadata,vertex_fade=None,flatten_fade=True):
 mats={}
 for role,spec in MATERIALS.items():
  mat=bpy.data.materials.new(role);mat.use_nodes=True;bs=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
  bs.inputs['Base Color'].default_value=(*spec['base_color'],1);bs.inputs['Roughness'].default_value=spec['roughness'];bs.inputs['Metallic'].default_value=spec.get('metallic',0)
  mat.diffuse_color=(*spec['base_color'],1)
  if spec.get('texture'):
   channels=tex[spec['texture']];spec['textures']=channels
   t=mat.node_tree.nodes.new('ShaderNodeTexImage');t.image=bpy.data.images.load(str(ROOT/channels['albedo']))
   mult=mat.node_tree.nodes.new('ShaderNodeMixRGB');mult.blend_type='MULTIPLY';mult.inputs[0].default_value=1;mult.inputs[2].default_value=(*spec['base_color'],1)
   mat.node_tree.links.new(t.outputs['Color'],mult.inputs[1]);mat.node_tree.links.new(mult.outputs['Color'],bs.inputs['Base Color'])
   nt=mat.node_tree.nodes.new('ShaderNodeTexImage');nt.image=bpy.data.images.load(str(ROOT/channels['normal']));nt.image.colorspace_settings.name='Non-Color'
   nm=mat.node_tree.nodes.new('ShaderNodeNormalMap');nm.inputs['Strength'].default_value=spec.get('normal_strength',.55);mat.node_tree.links.new(nt.outputs['Color'],nm.inputs['Color']);mat.node_tree.links.new(nm.outputs['Normal'],bs.inputs['Normal'])
  fade_spec=spec.get('vertex_color_fade')
  if fade_spec:
   # Optional MPR-owned terminal material. Existing callers and shared GHS
   # materials are unchanged; endpoints use actual grass albedo and no alpha.
   original=bs.inputs['Base Color'].links[0].from_socket if bs.inputs['Base Color'].is_linked else None
   color=mat.node_tree.nodes.new('ShaderNodeVertexColor');color.layer_name='EdgeFade'
   ground=mat.node_tree.nodes.new('ShaderNodeTexImage');ground.image=bpy.data.images.load(str(ROOT/tex['grass']['albedo']))
   ground_mult=mat.node_tree.nodes.new('ShaderNodeMixRGB');ground_mult.blend_type='MULTIPLY';ground_mult.inputs[0].default_value=1
   ground_mult.inputs[2].default_value=(*fade_spec['ground_base_color'],1);mat.node_tree.links.new(ground.outputs['Color'],ground_mult.inputs[1])
   mix=mat.node_tree.nodes.new('ShaderNodeMixRGB');mix.blend_type='MIX';mix.inputs[1].default_value=(*spec['base_color'],1)
   if original:mat.node_tree.links.new(original,mix.inputs[1])
   mat.node_tree.links.new(color.outputs['Color'],mix.inputs[0]);mat.node_tree.links.new(ground_mult.outputs[0],mix.inputs[2]);mat.node_tree.links.new(mix.outputs[0],bs.inputs['Base Color'])
   # Use the same world-space 6m grass tiling as continuous terrain.
   geometry=mat.node_tree.nodes.new('ShaderNodeNewGeometry');scale=mat.node_tree.nodes.new('ShaderNodeVectorMath');scale.operation='SCALE';scale.inputs['Scale'].default_value=1/6
   mat.node_tree.links.new(geometry.outputs['Position'],scale.inputs[0]);mat.node_tree.links.new(scale.outputs['Vector'],ground.inputs['Vector'])
   rough=mat.node_tree.nodes.new('ShaderNodeMapRange');rough.inputs['From Min'].default_value=0;rough.inputs['From Max'].default_value=1
   rough.inputs['To Min'].default_value=spec['roughness'];rough.inputs['To Max'].default_value=fade_spec['ground_roughness']
   mat.node_tree.links.new(color.outputs['Color'],rough.inputs['Value']);mat.node_tree.links.new(rough.outputs['Result'],bs.inputs['Roughness'])
   if bs.inputs['Normal'].is_linked:
    prior=bs.inputs['Normal'].links[0].from_socket;normal_mix=mat.node_tree.nodes.new('ShaderNodeMixRGB')
    mat.node_tree.links.new(color.outputs['Color'],normal_mix.inputs[0]);mat.node_tree.links.new(prior,normal_mix.inputs[1]);mat.node_tree.links.new(geometry.outputs['Normal'],normal_mix.inputs[2]);mat.node_tree.links.new(normal_mix.outputs[0],bs.inputs['Normal'])
  mats[role]=mat
 rows=[]
 for name,roles in GEO.data.items():
  verts=[];faces=[];face_roles=[]
  for role,(vv,ff) in roles.items():
   off=len(verts);verts.extend(vv);faces.extend(tuple(i+off for i in f) for f in ff);face_roles.extend([role]*len(ff))
  if not faces:continue
  used=sorted({i for f in faces for i in f});remap={v:i for i,v in enumerate(used)};verts=[verts[i] for i in used];faces=[tuple(remap[i] for i in f) for f in faces]
  if flatten_fade and vertex_fade is not None and any(MATERIALS[r].get('vertex_color_fade')for r in roles):
   verts=[(x,y,G+(z-G)*(1-.99*vertex_fade(name,(x,y,z))))for x,y,z in verts]
  data=bpy.data.meshes.new(name);data.from_pydata(verts,[],faces);data.update();obj=bpy.data.objects.new(name,data);bpy.context.collection.objects.link(obj)
  # Float32 storage can collapse tiny Shapely sliver triangles. Remove only
  # zero-area faces before export/statistics so FBX and source counts agree.
  valid=[(tuple(p.vertices),r) for p,r in zip(data.polygons,face_roles) if p.area>1e-10]
  if len(valid)!=len(faces):
   clean=bpy.data.meshes.new(name+'_Clean');clean.from_pydata([tuple(v.co) for v in data.vertices],[],[f for f,r in valid]);clean.update()
   obj.data=clean;bpy.data.meshes.remove(data);data=clean;face_roles=[r for f,r in valid]
  keys=list(roles)
  for r in keys:data.materials.append(mats[r])
  uv=data.uv_layers.new(name='UVMap')
  for f,r in zip(data.polygons,face_roles):
   f.material_index=keys.index(r);axis=max(range(3),key=lambda a:abs(f.normal[a]));a,b=[v for v in range(3) if v!=axis];period=6 if 'Grass' in r else 3
   for li in f.loop_indices:
    v=data.vertices[data.loops[li].vertex_index].co;uv.data[li].uv=(v[a]/period,v[b]/period)
  fade_range=None
  if vertex_fade is not None and any(MATERIALS[r].get('vertex_color_fade')for r in keys):
   colors=data.color_attributes.new(name='EdgeFade',type='FLOAT_COLOR',domain='POINT');data.color_attributes.active_color=colors
   values=[]
   for v in data.vertices:
    value=float(vertex_fade(name,tuple(v.co)));assert 0<=value<=1;colors.data[v.index].color=(value,value,value,1);values.append(value)
   fade_range=[min(values),max(values)]
  bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
  fbx=OUT/(name+'.fbx');bpy.ops.export_scene.fbx(filepath=str(fbx),use_selection=True,object_types={'MESH'},axis_forward='-Y',axis_up='Z',apply_unit_scale=True,bake_anim=False,mesh_smooth_type='FACE',add_leaf_bones=False,colors_type='LINEAR')
  data.calc_loop_triangles();row=dict(name=name,fbx=fbx.relative_to(ROOT).as_posix(),material_roles=keys,bounds_m=[[min(v[i] for v in verts),max(v[i] for v in verts)] for i in range(3)],vertices=len(verts),triangles=len(data.loop_triangles),sha256=hashlib.sha256(fbx.read_bytes()).hexdigest(),instance_only=False)
  if fade_range is not None:row.update(vertex_color_fade=dict(attribute='EdgeFade',channel='R',zero='original surface',one='ground surface',opaque=True),vertex_color_attribute='EdgeFade',vertex_color_domain='POINT',vertex_color_encoding='LINEAR_RGB_EQUAL',vertex_color_range=fade_range,disable_shadow_casting=True)
  rows.append(row)
 bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'MPR_ReferenceSite.blend'))
 manifest=dict(schema_version=3,coordinate_frame='CAD metres +Y; FBX -Y/Z; UE reflects Y once',ground_z_m=G,meshes=rows,instances=dict(INSTANCES),materials=MATERIALS,counts=dict(COUNTS),**metadata)
 (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
 print('MPR_REFERENCE_SITE',len(rows),sum(r['triangles'] for r in rows),dict(COUNTS))

def main():
 OUT.mkdir(parents=True,exist_ok=True);bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
 bpy.context.scene.unit_settings.system='METRIC';bpy.context.scene.unit_settings.scale_length=1
 site=build_surfaces();context=build_context();rail=build_railways(API,SOURCE['polylines'],G)
 vehicles=place_vehicles(site,rail);clearance=plant(site,rail,context,vehicles)
 export(textures(),dict(road_audit=site['audit'],context_building_audit=context['buildings'],railway_audit=rail['stats'],clearance=clearance,pond_area_m2=site['pond'].area,reference_policy='User-selected concept appearance on retained CAD topology; landscape, details and parked occupancy are visual reconstruction.'))

if __name__=='__main__':main()
