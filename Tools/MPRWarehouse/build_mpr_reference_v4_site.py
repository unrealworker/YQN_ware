"""Reconstruct the approved reference's external layout, independent of CAD roads.

The original interior and main CAD shell remain unchanged. External layout is
explicitly measured in reference pixels and back-projected by the fitted camera.
"""
import sys,json,math,random
from pathlib import Path
from collections import defaultdict,Counter
import bpy,numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'Tools/MPRWarehouse'))
import build_mpr_reference_site as core
import mpr_railway_detail as rail_detail
from calibrate_mpr_reference_camera import image_to_ground,project_world_to_image,load_calibration
from mpr_blender_common import Geometry
from park_curves import rounded_path,offset_path,dash_segments,sample_along
from shapely.geometry import Polygon,Point,LineString,box
from shapely.ops import unary_union
from shapely.affinity import rotate,translate
import shapely

OUT=ROOT/'SourceAssets/MPR/reference_v4/site';SOURCE=json.loads((OUT/'reference_site_pixels.json').read_text(encoding='utf8'))
CAL=load_calibration();G=-1.2;RNG=random.Random(110203);COUNTS=Counter();INSTANCES=defaultdict(list)
MAIN=core.MAIN;GEO=Geometry();TREE_ROWS=[];VEHICLE_SHAPES=[];ROAD_DATA=[]
def world(p,z=G):return image_to_ground(*p,z=z,calibration=CAL)
def poly_world(points,z=G):return Polygon([world(p,z)[:2] for p in points])
def meters(px,at,z=G):return math.dist(world(at,z)[:2],world((at[0]+px,at[1]),z)[:2])
def shape(name,role,p,z):core.shape(name,role,p,z)
def line(name,role,p,width,z):core.lines(name,role,p,width,z)
def instance(name,p,yaw=0,scale=(1,1,1),**meta):
 INSTANCES[name].append(dict(position_m=[float(v) for v in p],rotation_deg=float(yaw),scale=list(scale),**meta))
def round_polygon(p,r=.7):
 inner=p.buffer(-r,quad_segs=16)
 return inner.buffer(r,quad_segs=16) if not inner.is_empty else p
def footprint(p,l,w,yaw):return translate(rotate(box(-l/2,-w/2,l/2,w/2),yaw,origin=(0,0)),*p[:2])

def build_roads():
 for row in SOURCE['roads']:
  controls=[world(p)[:2] for p in row['points']];width=meters(row['width_px'],row['points'][len(row['points'])//2])
  pts=rounded_path(controls,radius=meters(row['radius_px'],row['points'][len(row['points'])//2]),max_step=.5)
  road=LineString(pts).buffer(width/2,quad_segs=16)
  ROAD_DATA.append(dict(name=row['name'],path=pts,width=width,geometry=road,marking=row['marking']))
 # Residential streets are explicitly measured too; context generator owns the
 # roof outlines, and can supply any additional street centerline traces.
 context=ROOT/'SourceAssets/MPR/reference_v4/context/reference_context_layout.json'
 if context.exists():
  data=json.loads(context.read_text(encoding='utf8'))
  for index,row in enumerate(data.get('streets',[])):
   pixels=row.get('points',row.get('centerline_px',[]))
   if len(pixels)<2:continue
   pts=rounded_path([world(p)[:2] for p in pixels],radius=5,max_step=.7);width=meters(row.get('width_px',12),pixels[len(pixels)//2])
   ROAD_DATA.append(dict(name='Residential_'+str(index),path=pts,width=width,geometry=LineString(pts).buffer(width/2,quad_segs=10),marking='none'))
 roads=unary_union([r['geometry'] for r in ROAD_DATA])
 courts={r['name']:round_polygon(poly_world(r['outline']),.8).difference(MAIN.buffer(.15)) for r in SOURCE['paving']}
 concrete=unary_union([courts[r['name']] for r in SOURCE['paving'] if r['role']=='Concrete']).difference(roads)
 asphalt=unary_union([roads]+[courts[r['name']] for r in SOURCE['paving'] if r['role']=='Asphalt'])
 allpaved=unary_union([concrete,asphalt]);asphalt=asphalt.difference(concrete)
 shape('Roads','MPR3_Asphalt',asphalt,G+.08);shape('Courts','MPR3_Concrete',concrete,G+.10)
 curb=allpaved.buffer(.32,quad_segs=12).difference(allpaved).difference(MAIN.buffer(.4))
 core.raised_edge('RaisedCurbs',curb,G+.03,.18)
 for r in ROAD_DATA:
  pts=r['path'];w=r['width']
  if 'center' in r['marking']:
   for dash in dash_segments(pts,4.0,7.8):line('RoadCenter','MPR3_WhiteLine',LineString(dash),.20,G+.102)
  if 'edge' in r['marking']:
   for offset in (-w/2+.6,w/2-.6):line('RoadEdges','MPR3_WhiteLine',LineString(offset_path(pts,offset)),.18,G+.102)
 for x in np.arange(-220,240,6.1):line('CourtSeams','MPR3_PavingJoint',LineString([(x,-260),(x,200)]).intersection(concrete),.12,G+.125)
 for y in np.arange(-260,201,6.1):line('CourtSeams','MPR3_PavingJoint',LineString([(-250,y),(250,y)]).intersection(concrete),.12,G+.125)
 for d in core.CAD['dock_doors']:
  p=d['position_m'];n=d['outward_normal_xy'];t=(-n[1],n[0])
  for sign in (-1,1):
   # Trailer width 2.60*1.20 plus the original 0.50m marking clearance.
   a=(p[0]+n[0]+t[0]*2.06*sign,p[1]+n[1]+t[1]*2.06*sign);b=(a[0]+n[0]*24.15,a[1]+n[1]*24.15)
   line('DockGuidance','MPR3_YellowLine',LineString([a,b]).intersection(concrete),.19,G+.13)
 # Parking bays in the same slanted plan frame as the calibrated main building.
 for key,side in [('WestParking',-1),('EastParking',1),('NeighborEastParking',1)]:
  p=courts[key];xmin,ymin,xmax,ymax=p.bounds
  for bay_index,y in enumerate(np.arange(ymin+2,ymax-1,3.1)):
   a=(xmin+.6,y);b=(xmin+6.0,y) if side<0 else (xmax-.6,y)
   if side>0:a=(xmax-6.0,y)
   seg=LineString([a,b]).intersection(p.buffer(-.2));line('ParkingBayLines','MPR3_WhiteLine',seg,.14,G+.102)
 for row in SOURCE.get('parking_rows',[]):
  for i in range(row['count']):
   if i%7==5:continue
   f=i/max(1,row['count']-1);pixel=[a*(1-f)+b*f for a,b in zip(row['start'],row['end'])]
   q=world(pixel,G+1.2);q[2]=G+.08;car=footprint(q,4.5,1.85,row['yaw_deg'])
   if car.intersects(MAIN):continue
   instance('SM_MPR4_Car_'+str(i%2),q,row['yaw_deg']);VEHICLE_SHAPES.append(car)
 return dict(roads=roads,paved=allpaved,concrete=concrete,asphalt=asphalt,courts=courts)

def build_water(site):
 row=SOURCE['pond'];pond=round_polygon(poly_world(row['outline']),meters(row['round_radius_px'],row['outline'][0]))
 assert pond.intersection(site['paved']).area<1.,'Reference pond overlaps the traced road'
 bank=meters(row['bank_width_px'],[350,660]);walk=meters(row['walk_width_px'],[350,660])
 inner=pond.buffer(bank);path=inner.buffer(walk).difference(inner).difference(site['paved'])
 shape('RetentionPond','MPR3_PondWater',pond,G+.015)
 shape('RetentionBank','MPR3_Grass',inner.difference(pond),G+.035)
 core.raised_edge('PondWalk',path,G+.025,.08)
 site.update(pond=pond,pond_walk=path)

def build_rail(site):
 # The aerial reference uses deliberately readable dark rail heads. Preserve
 # the track centrelines/gauge while avoiding subpixel disappearing highlights.
 rail_detail.HEAD_WIDTH_M=.24
 rail_detail.RAIL_OFFSET_M=(rail_detail.GAUGE_M+rail_detail.HEAD_WIDTH_M)/2
 row=SOURCE['railway'];west=[world(p)[:2] for p in row['west_edge']];east=[world(p)[:2] for p in row['east_edge']]
 lines=[]
 for lo,hi in [(0,.17),(.36,1.0)]:
  edge=lambda f:[(a[0]*(1-f)+b[0]*f,a[1]*(1-f)+b[1]*f) for a,b in zip(west,east)]
  shape('RailYardContinuousBallast','MPR3_Ballast',Polygon(edge(lo)+list(reversed(edge(hi)))),G+.11)
 for i in range(row['tracks']):
  f=row['track_fractions'][i];controls=[(a[0]*(1-f)+b[0]*f,a[1]*(1-f)+b[1]*f) for a,b in zip(west,east)]
  pts=list(LineString(rounded_path(controls,radius=45,max_step=1.)).simplify(.025).coords)
  lines.append(dict(id=str(i),layer='railways',vertices=[[*p,0] for p in pts]))
 rail=core.build_railways(core.API,lines,G)
 occupied=[]
 for track in rail['centerlines']:
  if int(track['id']) not in row['boxcar_track_indices']:continue
  curve=LineString(track['vertices'])
  for d in np.arange(16+int(track['id'])*4,curve.length-20,row['boxcar_spacing_m']):
   p=curve.interpolate(d);a=curve.interpolate(d-8);b=curve.interpolate(d+8);yaw=math.degrees(math.atan2(b.y-a.y,b.x-a.x))
   scale=row.get('boxcar_scale',[1,1,1]);f=footprint((p.x,p.y),20.8*scale[0],3.3*scale[1],yaw)
   if any(f.buffer(.05).intersects(q) for q in occupied):continue
   occupied.append(f);instance('SM_MPR4_FreightBoxcar',[p.x,p.y,G+.34],yaw,scale=scale)
 site['rail']=rail;return rail

def place_trailers(site):
 scale=(1.15,1.20,1.08);length=16.15*scale[0];width=2.60*scale[1]
 # CAD door centres sit 0.1524m inside the exterior wall; the model's rear
 # bumper extends 0.24725m beyond the scaled nominal box. A 0.075m clearance
 # correction keeps that actual bumper outside the wall by at least 0.02m.
 dock_offset=length/2+.345+.075;used_south_docks=set();stand_adjustments=[]
 props=json.loads((ROOT/'SourceAssets/MPR/reference_v4/props/manifest.json').read_text(encoding='utf8'))
 vehicle_bounds={r['name']:r['bounds_m'] for r in props['meshes']}
 def actual_shape(name,p,yaw,s):
  b=vehicle_bounds[name];local=box(b[0][0]*s[0],b[1][0]*s[1],b[0][1]*s[0],b[1][1]*s[1])
  return translate(rotate(local,yaw,origin=(0,0)),*p[:2])
 def valid(f):return not f.intersects(MAIN) and not any(f.intersection(q).area>.01 for q in VEHICLE_SHAPES)
 for row in SOURCE['trailer_rows']:
  centers=row.get('centers')
  if centers is None:
   a,b=row['start'];centers=[(a[0]+(b[0]-a[0])*i/max(1,len(row['colors'])-1),a[1]+(b[1]-a[1])*i/max(1,len(row['colors'])-1)) for i in range(len(row['colors']))]
  for i,pixel in enumerate(centers):
   p=world(pixel,G+4.18*scale[2]);p[2]=G+.10;yaw=-90 if row['yaw_hint']=='dock' else 90 if row['yaw_hint']=='north' else 0
   name='SM_MPR4_Trailer_'+row['colors'][i%len(row['colors'])];meta=dict(reference_row=row['name'],reference_index=i)
   if row['yaw_hint']=='dock':
    # Choose the nearest unused real CAD door. Repeated nearest-door snaps
    # previously discarded seven authored trailers as duplicate occupancy.
    choices=sorted([(j,d) for j,d in enumerate(core.CAD['dock_doors']) if d['outward_normal_xy'][1]<-.8 and j not in used_south_docks],key=lambda jd:abs(jd[1]['position_m'][0]-p[0]))
    chosen=None
    for j,d in choices:
     candidate=[d['position_m'][0],d['position_m'][1]-dock_offset,p[2]]
     if valid(actual_shape(name,candidate,yaw,scale)):chosen=(j,d,candidate);break
    assert chosen is not None,('No free south CAD dock',row['name'],i)
    j,d,p=chosen;used_south_docks.add(j);meta.update(cad_dock_index=j,cad_dock_position_m=d['position_m'])
   f=actual_shape(name,p,yaw,scale)
   if row['yaw_hint']!='dock' and (not valid(f) or f.intersection(site['roads']).area>.05):
    # Small local stand shifts only, ordered by minimum distance. Road control
    # points and the source row/palette ordering remain invariant.
    original=list(p);angle=math.radians(yaw);t=(math.cos(angle),math.sin(angle));n=(-t[1],t[0])
    offsets=sorted([(a,b) for a in np.arange(-3,3.01,.25) for b in np.arange(-5,5.01,.25)],key=lambda ab:ab[0]**2+ab[1]**2)
    chosen=None
    for along,across in offsets:
     q=[original[0]+t[0]*along+n[0]*across,original[1]+t[1]*along+n[1]*across,original[2]];qf=actual_shape(name,q,yaw,scale)
     if valid(qf) and qf.intersection(site['roads']).area<.05:chosen=(q,qf);break
    assert chosen is not None,('No clear nearby trailer stand',row['name'],i)
    p,f=chosen;meta['stand_shift_m']=[p[k]-original[k] for k in range(2)];stand_adjustments.append(dict(row=row['name'],index=i,delta_m=meta['stand_shift_m']))
   assert valid(f),('Trailer collision',row['name'],i)
   VEHICLE_SHAPES.append(f);instance(name,p,yaw,scale=scale,**meta)
   if row['yaw_hint']!='dock':
    for sign in (-1,1):
     angle=math.radians(yaw);t=(math.cos(angle),math.sin(angle));n=(-t[1],t[0]);half=length/2;side=width/2+.50
     a=(p[0]-t[0]*half+n[0]*side*sign,p[1]-t[1]*half+n[1]*side*sign);b=(p[0]+t[0]*half+n[0]*side*sign,p[1]+t[1]*half+n[1]*side*sign)
     line('TrailerStands','MPR3_YellowLine',LineString([a,b]).intersection(site['concrete']),.18,G+.13)
 # The far dock row is partly hidden by the main roof; keep its palette rhythm.
 for i,d in enumerate(d for d in core.CAD['dock_doors'] if d['outward_normal_xy'][1]>.8):
  if i%6 in (2,5):continue
  p=[d['position_m'][0],d['position_m'][1]+dock_offset,G+.10];name='SM_MPR4_Trailer_'+['White','Blue','Coral','White','Blue'][i%5]
  f=actual_shape(name,p,90,scale)
  assert valid(f),('North CAD dock trailer collision',i)
  VEHICLE_SHAPES.append(f);instance(name,p,90,scale=scale,reference_row='DockNorth',reference_index=i)
 # The preserved interior fixes actual dock interfaces. Fill the occluded
 # loading apron beneath those trailers, rather than leaving wheels on grass.
 truck_pads=[];car_pads=[]
 for name,items in INSTANCES.items():
  if 'Trailer' not in name and 'Car_' not in name:continue
  for item in items:
   truck='Trailer' in name
   pad=actual_shape(name,item['position_m'],item['rotation_deg'],item.get('scale',[1,1,1])).buffer(.7,quad_segs=8).difference(MAIN).difference(site['paved'])
   (truck_pads if truck else car_pads).append(pad)
 for patches,label,role in [(truck_pads,'DockApronInfill','MPR3_Concrete'),(car_pads,'ParkingInfill','MPR3_Asphalt')]:
  if patches:
   patch=unary_union(patches);shape(label,role,patch,G+.10)
   site['paved']=site['paved'].union(patch)
 COUNTS['south_dock_trailers']=len(used_south_docks);COUNTS['trailer_stands_adjusted']=len(stand_adjustments)
 site['trailer_layout_audit']=dict(scale=list(scale),body_dimensions_m=[length,width,4.18*scale[2]],dock_center_offset_m=dock_offset,south_dock_count=len(used_south_docks),stand_adjustments=stand_adjustments)

def landscape(site):
 # All major shape boundaries follow the image; detail noise only modulates
 # ground shading and never determines tree positions or road topology.
 context_file=ROOT/'SourceAssets/MPR/reference_v4/context/manifest.json'
 building_polys=[]
 if context_file.exists():
  context=json.loads(context_file.read_text(encoding='utf8'))
  building_polys=[Polygon(p) for p in context.get('footprints_m',[])]
  pads=[Polygon(p) for p in context.get('paved_footprints_m',[])]
  if pads:site['paved']=unary_union([site['paved'],*pads])
 buildings=unary_union([MAIN,*building_polys]);excluded=unary_union([site['paved'],site['pond'].buffer(1),site['pond_walk'],site['rail']['exclusion'],buildings,*VEHICLE_SHAPES])
 bounds=poly_world([[-400,-250],[2100,-250],[2100,1250],[-400,1250]])
 shape('ContinuousTerrain','MPR3_Grass',bounds.difference(site['paved']).difference(site['pond']).difference(site['pond_walk']).difference(MAIN),G)
 ground=box(-1500,-1600,1600,1600);shape('FarGround','MPR3_GrassFar',ground,G-.08)
 occupied=[]
 def add_tree(pixel,diameter,region):
  # Locate the crown centre at its visible canopy height, then back-project.
  p=world(pixel,G+10.0);radius=meters(diameter,pixel,G+10.0)/2
  radius=max(3.5,min(9,radius));disk=Point(p[:2]).buffer(min(1.4,radius*.25),quad_segs=10)
  if disk.intersects(excluded):COUNTS['tree_rejected_clearance']+=1;return
  crown=Point(p[:2]).buffer(radius*.85,quad_segs=12)
  if crown.intersects(buildings) or crown.intersects(site['rail']['exclusion']):COUNTS['tree_rejected_crown']+=1;return
  if Point(p[:2]).buffer(radius*.45,quad_segs=12).intersects(site['paved']):COUNTS['tree_rejected_road_clearance']+=1;return
  if any(math.dist(p[:2],q[:2])<(radius+r)*.70 for q,r in occupied):return
  occupied.append((p,radius));p[2]=G+.01
  TREE_ROWS.append(dict(position_m=p,crown_radius_m=radius,rotation_deg=RNG.uniform(0,360),reference_pixel=list(pixel),region=region))
 for row in SOURCE['planting_rows']:
  curve=LineString(row['path'])
  for d in np.arange(0,curve.length,row['spacing_px']):
   p=curve.interpolate(d);add_tree((p.x,p.y),row['crown_diameter_px']*RNG.uniform(.91,1.08),row['name'])
 measured_path=OUT/'reference_tree_canopies.json'
 measured=json.loads(measured_path.read_text(encoding='utf8')) if measured_path.exists() else {}
 for row in measured.get('canopies',[]):
  add_tree(row['center_px'],row['diameter_px'],row.get('region','ReferenceMeasured'))
 for row in SOURCE['woodland_regions']:
  if row['name'] in measured.get('replaced_regions',[]):continue
  region=Polygon(row['outline']);xmin,ymin,xmax,ymax=region.bounds;pitch=row['density_px']
  for y in np.arange(ymin,ymax,pitch*.85):
   for x in np.arange(xmin,xmax,pitch):
    pixel=(x+RNG.uniform(-pitch*.3,pitch*.3),y+RNG.uniform(-pitch*.3,pitch*.3))
    if region.contains(Point(pixel)) and RNG.random()<.86:add_tree(pixel,RNG.uniform(*row['crown_diameter_px']),row['name'])
 COUNTS['reference_trees']=len(TREE_ROWS)
 return dict(exclusion_policy='Projected crown positions; conservative trunk/crown envelope excludes buildings, roads, rail and water; intended canopy overlap is allowed.',tree_positions= TREE_ROWS)

def reference_surface_textures():
 """Override only V4 grass/water: no coherent checker or diagonal wave train.

 Gaussian-filtered seeded random fields give seamless multiscale detail. The
 FFT is only a blur implementation; no singled-out periodic frequencies are
 introduced. Geometry, metre UV periods and all other textures are unchanged.
 """
 textures=core.textures();n=1024;rng=np.random.default_rng(441108)
 k=np.fft.fftfreq(n);k2=k[:,None]**2+k[None,:]**2
 def field(scales):
  result=np.zeros((n,n))
  for sigma,weight in scales:
   a=np.fft.ifft2(np.fft.fft2(rng.standard_normal((n,n)))*np.exp(-2*math.pi**2*sigma*sigma*k2)).real
   a-=a.mean();result+=weight*a/max(a.std(),1e-12)
  return result
 def normal(height,max_slope):
  dx=(np.roll(height,-1,1)-np.roll(height,1,1))*.5;dy=(np.roll(height,-1,0)-np.roll(height,1,0))*.5
  factor=max_slope/max(float(np.max(np.hypot(dx,dy))),1e-12);dx*=factor;dy*=factor
  v=np.stack([-dx,dy,np.ones_like(dx)],2);v/=np.linalg.norm(v,axis=2,keepdims=True)
  return np.rint((v*.5+.5)*255)
 variation=np.tanh(field([(3,.6),(12,.3),(48,.1)])*.8);variation-=variation.mean();variation*=1.9/max(abs(variation.min()),abs(variation.max()))
 images={'grass':(np.rint(234+variation),normal(field([(1.5,.75),(6,.25)]),.06)),
         'water':(np.full((n,n),245.),normal(field([(4,.55),(18,.30),(64,.15)]),.045))}
 for kind,(albedo,normals) in images.items():
  for channel,data in [('albedo',albedo),('normal',normals)]:core.png(ROOT/textures[kind][channel],data)
 return textures


def main():
 OUT.mkdir(parents=True,exist_ok=True);bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
 core.OUT=OUT;core.GEO=GEO;core.INSTANCES=INSTANCES;core.COUNTS=COUNTS
 core.MATERIALS['MPR3_Asphalt']['base_color']=[.18,.205,.225]
 core.MATERIALS['MPR3_Concrete']['base_color']=[.60,.62,.61]
 core.MATERIALS['MPR3_Grass']['base_color']=[.33,.38,.32]
 core.MATERIALS['MPR3_GrassFar']['base_color']=[.33,.38,.32]
 for role in ('MPR3_Grass','MPR3_GrassFar'):core.MATERIALS[role]['normal_strength']=.06
 core.MATERIALS['MPR3_PavingJoint']['base_color']=[.42,.44,.42]
 core.MATERIALS['MPR3_Ballast']['base_color']=[.34,.35,.365]
 core.MATERIALS['MPR3_RailSteel']['base_color']=[.07,.08,.10]
 core.MATERIALS['MPR3_RailSteel']['metallic']=.25
 core.MATERIALS['MPR3_PondWater']['base_color']=[.018,.075,.095]
 core.MATERIALS['MPR3_PondWater'].update(normal_strength=.08,roughness=.42,metallic=0.)
 site=build_roads();build_water(site);build_rail(site);place_trailers(site);planting=landscape(site)
 # All newly authored meshes are version-four names, even while sharing the
 # deterministic low-level exporter with the previous experiment.
 GEO.data={name.replace('SM_MPR3_','SM_MPR4_'):roles for name,roles in GEO.data.items()}
 COUNTS.update(trailers=sum(len(v) for k,v in INSTANCES.items() if 'Trailer' in k),boxcars=len(INSTANCES['SM_MPR4_FreightBoxcar']))
 core.export(reference_surface_textures(),dict(reference_layout=SOURCE,calibration=CAL,planting=planting,trailer_layout_audit=site['trailer_layout_audit'],surface_texture_policy='V4 grass mean 234 +/-2 random multiscale variation; water albedo 245 with weak random normal; no checker/diagonal sine trains',reference_match_policy='External layout is traced directly from the user-approved image. Main interior CAD is invariant.'))
 print('MPR_REFERENCE_V4_SITE',dict(COUNTS))

if __name__=='__main__':main()
