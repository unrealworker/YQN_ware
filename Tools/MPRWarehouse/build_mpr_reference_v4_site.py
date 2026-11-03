"""Reconstruct the approved reference's external layout, independent of CAD roads.

The original interior and main CAD shell remain unchanged. External layout is
measured in the latest plan. Render-camera calibration is never used for plan geometry.
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
import mpr_plan_site as plan
from mpr_plan_layout import plan_to_world,load_registration

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

def terminal_fade_at(name,point):
 # Widths vary by source mouth. Nearest centreline could select an adjacent
 # narrow street while a vertex still belongs to a broad ribbon.
 p=Point(point[:2]);row,_=min(TERMINAL_SUPPORT,key=lambda pair:pair[1].distance(p))
 return plan.terminal_fade(row,point)

TERMINAL_ROWS=[]
TERMINAL_SUPPORT=[]

def terminal_surfaces(asphalt,curb,edge,rows):
 """Three batched, vertex-faded meshes, clipped and sampled at <=2m steps."""
 TERMINAL_ROWS[:]=rows;TERMINAL_SUPPORT[:]=[(r,plan.terminal_shape(r))for r in rows]
 bounds=plan.pixel_box(*plan.read('outside_road_connections_v5.json')['canvas_px'])
 for row in rows:
  origin=np.asarray(row['origin_m']);direction=np.asarray(row['direction']);normal=np.array([-direction[1],direction[0]])
  support=plan.terminal_shape(row).buffer(.5,quad_segs=8).difference(bounds)
  surfaces=[('RoadTerminalRoads','MPR4_TerminalAsphalt',asphalt.intersection(support),G+.08),
            ('RoadTerminalCurbs','MPR4_TerminalCurb',curb.intersection(support),G+.21),
            ('RoadTerminalEdges','MPR4_TerminalWhiteLine',edge.intersection(support),G+.106)]
  # A flat road triangle over the whole fade would interpolate only its two
  # endpoints. Real 2m sections preserve the GHS smoothstep in vertex colors.
  points=np.vstack([shapely.get_coordinates(geometry)for _,_,geometry,_ in surfaces if not geometry.is_empty])
  projected=(points-origin)@direction;start=min(0.,float(projected.min()));end=max(row['length_m'],float(projected.max()))
  stations=sorted(set([start,0.,row['fade_start_m'],row['length_m'],end,*np.arange(start,end,2.)]))
  half=row['width_m']+3.
  for a,b in zip(stations,stations[1:]):
   clip=Polygon([origin+direction*a-normal*half,origin+direction*b-normal*half,origin+direction*b+normal*half,origin+direction*a+normal*half])
   for name,role,geometry,z in surfaces:shape(name,role,geometry.intersection(clip),z)

def build_roads():
 roads=plan.road_geometry();details=plan.plan_details();portals=plan.portal_clearance()
 context=json.loads((ROOT/'SourceAssets/MPR/reference_v4/context/manifest.json').read_text(encoding='utf8'))
 buildings=unary_union([MAIN,*[Polygon(p) for p in context.get('footprints_m',[])]])
 roads,continuations=plan.extend_road_tails(roads,blockers=buildings)
 main_parcel=plan.named_region('MainWarehouseParcel',False)
 north_parcel=plan.named_region('NorthWarehouseParcel',False)
 # Leave planted perimeter strips; apron depths follow the new plan boundaries.
 # Reference campus perimeter is a darker planted strip, with all measured
 # access portals left open. Do not cover parking, aprons or road lanes.
 campus_planting=main_parcel.difference(main_parcel.buffer(-4.2,quad_segs=16)).difference(portals.buffer(1.0)).difference(roads)
 campus_planting=unary_union([campus_planting,plan.landscape_islands().intersection(main_parcel.buffer(12))]).difference(roads).difference(MAIN.buffer(.10))
 # North is an active loading face, not an external landscaping boundary.
 # Preserve the continuous CAD dock apron, full tractor envelopes and a 5m
 # forward buffer. Do not remove trucks to make a decorative ring fit.
 cad=json.loads((ROOT/'SourceAssets/MPR/mpr_cad_layout.json').read_text(encoding='utf8'))
 north_docks=[d['position_m']for d in cad['dock_doors']if d['outward_normal_xy'][1]>.8]
 north_work=box(min(p[0]for p in north_docks)-12.,min(p[1]for p in north_docks)-.2,
                max(p[0]for p in north_docks)+12.,max(p[1]for p in north_docks)+22.).intersection(main_parcel).difference(MAIN.buffer(.10))
 campus_planting=campus_planting.difference(north_work)
 main_paved=unary_union([main_parcel.buffer(-1.3,quad_segs=12),north_work]).difference(MAIN.buffer(.10)).difference(campus_planting)
 north_paved=north_parcel.buffer(-1.3,quad_segs=12).difference(buildings.buffer(.1))
 west=plan.pixel_box(406,382,443,618).intersection(main_paved)
 east=plan.pixel_box(1022,373,1088,524).intersection(main_paved)
 neighbor_east=plan.pixel_box(1097,161,1173,326).intersection(north_paved)
 south=main_paved.intersection(plan.pixel_box(425,598,1045,743))
 north=main_paved.intersection(plan.pixel_box(435,362,1021,389))
 neighbor=north_paved.intersection(plan.pixel_box(444,315,1102,350))
 # Connect the actual access openings; segmentation gates must not become curbs.
 connectors=portals.intersection(main_parcel.union(north_parcel).union(roads).buffer(.5))
 concrete=unary_union([main_paved.difference(west.union(east)),neighbor,connectors]).difference(roads).difference(buildings.buffer(.1))
 asphalt=unary_union([roads,west,east,neighbor_east]).difference(buildings.buffer(.1)).difference(concrete)
 allpaved=unary_union([concrete,asphalt])
 drawing=plan.pixel_box(*plan.read('outside_road_connections_v5.json')['canvas_px'])
 # Smoothed original crop mouths can extend a fraction beyond the raster
 # rectangle. Preserve those original faces too, rather than dropping them.
 source_surface=drawing.union(plan.road_geometry())
 shape('Roads','MPR3_Asphalt',asphalt.intersection(source_surface),G+.08);shape('Courts','MPR3_Concrete',concrete,G+.10)
 curb=allpaved.buffer(.28,quad_segs=16).difference(allpaved).difference(buildings.buffer(.45)).difference(portals)
 # Outer canvas edges are intentionally open for future surrounding scenery.
 extent=drawing.buffer(70);curb=curb.intersection(extent)
 core.raised_edge('RaisedCurbs',curb.intersection(drawing),G+.03,.18)
 edge=roads.buffer(-.55,quad_segs=16).boundary.intersection(extent.buffer(-2)).difference(portals.buffer(1))
 paint=edge.buffer(.075,quad_segs=8)
 shape('RoadEdges','MPR3_WhiteLine',paint.intersection(drawing),G+.106)
 terminal_surfaces(asphalt.difference(source_surface),curb.difference(drawing),paint.difference(drawing),continuations)
 for r in details['paint_guides']:
  pts=rounded_path(plan.xy(r['points']),radius=r['radius_m'],max_step=.4)
  ROAD_DATA.append(dict(name=r['name'],path=pts,geometry=LineString(pts),marking='center'))
  for dash in dash_segments(pts,3.0,6.5):
   line('RoadCenter','MPR3_WhiteLine',LineString(dash).intersection(roads.buffer(-1.5)),.16,G+.107)
 for x in np.arange(-220,300,6.1):line('CourtSeams','MPR3_PavingJoint',LineString([(x,-220),(x,130)]).intersection(concrete),.065,G+.125)
 for y in np.arange(-220,131,6.1):line('CourtSeams','MPR3_PavingJoint',LineString([(-250,y),(300,y)]).intersection(concrete),.065,G+.125)
 courts=dict(SouthLoadingCourt=south,NorthLoadingCourt=north,WestParking=west,EastParking=east,NeighborLoadingCourt=neighbor,NeighborEastParking=neighbor_east)
 for row in details['parking_rows']:
  court=courts[row['name']]
  for i,y in enumerate(np.arange(row['start_y'],row['end_y']+.01,row['pitch_px'])):
   q=plan_to_world([row['x'],float(y)],G+.08)
   line('ParkingBayLines','MPR3_WhiteLine',LineString([(q[0]-3.2,q[1]-1.55),(q[0]+3.2,q[1]-1.55)]).intersection(court),.14,G+.106)
   if i%6==4:continue
   car=footprint(q,4.5,1.85,row['yaw_deg'])
   if not court.buffer(.25).contains(car) or car.intersects(buildings):continue
   instance('SM_MPR4_Car_'+str(i%2),q,row['yaw_deg'],reference_pixel=[row['x'],float(y)])
   VEHICLE_SHAPES.append(car)
 COUNTS['road_boundary_components']=len(plan.read('road_outline_v5.json')['polygons_px'])
 assert roads.intersection(MAIN).area<.01,'Plan road intersects preserved warehouse'
 return dict(roads=roads,paved=allpaved,concrete=concrete,asphalt=asphalt,courts=courts,buildings=buildings,main_parcel=main_parcel,north_parcel=north_parcel,road_continuations=continuations,campus_planting=campus_planting,north_dock_apron=north_work)

def build_water(site):
 pond=plan.named_region('SouthWestPond',False)
 # The measured pond parcel shares the road edge; clip its walkway to the
 # final smoothed road surface to avoid thin coplanar strips at rounded bends.
 source_ring=plan.named_region('PondEnclosingRing',False)
 # Fill raster-derived inward notches and tiny grass wedges, then clip to
 # the real neighbouring pavement. The water outline itself is unchanged.
 walk_envelope=source_ring.convex_hull.buffer(.8,quad_segs=24)
 ring=walk_envelope.difference(pond).difference(site['paved'])
 assert pond.intersection(site['paved']).area<.01,'Plan pond overlaps road'
 shape('RetentionPond','MPR3_PondWater',pond,G+.015)
 bank=pond.buffer(.9,quad_segs=16).difference(pond).intersection(ring)
 shape('RetentionBank','MPR3_Grass',bank,G+.035)
 path=ring.difference(bank);core.raised_edge('PondWalk',path,G+.025,.08)
 site.update(pond=pond,pond_walk=path,pond_walk_repair=dict(source_area_m2=source_ring.area,filled_envelope_area_m2=walk_envelope.area,walk_area_m2=path.area,water_outline_changed=False,paved_overlap_m2=path.intersection(site['paved']).area))


def extend_track(points):
 # Continue only drawing-border endpoints; internal turnout ends stay exact.
 from mpr_plan_layout import world_to_plan
 result=list(points)
 for index,neighbor,insert in [(0,1,0),(-1,-2,None)]:
  p=points[index];q=points[neighbor];pixel=world_to_plan(p)
  if not (pixel[1]<1 or pixel[1]>908):continue
  length=math.dist(p,q);end=(p[0]+(p[0]-q[0])/length*160,p[1]+(p[1]-q[1])/length*160)
  if insert==0:result.insert(0,end)
  else:result.append(end)
 return result

def build_rail(site):
 row=plan.read('plan_railway_v5.json');assert row['status'].startswith('ready'),'Railway requires source-image review'
 # Restore a physically readable section at the real 1435mm inner gauge.
 rail_detail.HEAD_WIDTH_M=.09;rail_detail.RAIL_OFFSET_M=(rail_detail.GAUGE_M+rail_detail.HEAD_WIDTH_M)/2
 ballast=unary_union([Polygon(extend_track(plan.xy(bed['west']))+list(reversed(extend_track(plan.xy(bed['east']))))).buffer(0) for bed in row['ballast_beds_px']])
 ballast=ballast.difference(site['roads']).difference(site['buildings'])
 shape('RailYardContinuousBallast','MPR3_Ballast',ballast,G+.11)
 lines=[]
 for track in row['tracks']:
  pts=list(LineString(rounded_path(extend_track(plan.xy(track['path_px'])),radius=60,max_step=.8)).simplify(.035).coords)
  lines.append(dict(id=str(track['id']),layer='railways',vertices=[[*p,0] for p in pts]))
 rail=core.build_railways(core.API,lines,G)
 rail['stats']['source_policy']='Latest all-elements plan measured track paths; real 1.435m gauge; no legacy perspective inverse'
 props=json.loads((ROOT/'SourceAssets/MPR/reference_v4/props/manifest.json').read_text(encoding='utf8'))
 meta={r['name']:r for r in props['meshes']};stock=row['rolling_stock']
 curves={r['id']:LineString(r['vertices']) for r in rail['centerlines']};occupied=[];consists=[]
 # Keep the occupied source intervals, replacing isolated image-symbol centres
 # with coupled 20.76m stock. Every coupling joint lies on the same track curve.
 for track_id in stock['track_ids']:
  curve=curves[track_id]
  observed=[curve.project(Point(plan.xy([r['position_px']])[0])) for r in stock['placements_px'] if r['track_id']==track_id]
  assert observed,('Missing occupied interval',track_id)
  start=max(0,min(observed)-10.38);end=min(curve.length,max(observed)+10.38)
  joints=[start]
  while joints[-1]+20.76<end:
   lo=joints[-1]+20.76;hi=min(end,lo+5.)
   origin=curve.interpolate(joints[-1])
   if origin.distance(curve.interpolate(hi))<20.76:break
   for _ in range(35):
    mid=(lo+hi)/2
    if origin.distance(curve.interpolate(mid))<20.76:lo=mid
    else:hi=mid
   joints.append((lo+hi)/2)
  assert len(joints)>=3,('Too short train interval',track_id)
  cars=[]
  for i,(da,db) in enumerate(zip(joints,joints[1:])):
   a=curve.interpolate(da);b=curve.interpolate(db);p=((a.x+b.x)/2,(a.y+b.y)/2)
   yaw=math.degrees(math.atan2(b.y-a.y,b.x-a.x));ang=math.radians(yaw)
   name='SM_MPR4_Locomotive' if i==len(joints)-2 else 'SM_MPR4_FreightBoxcar'
   bb=meta[name]['metadata']['collision_body_bounds_m']
   f=translate(rotate(box(bb[0][0],bb[1][0],bb[0][1],bb[1][1]),yaw,origin=(0,0)),*p)
   assert not f.intersects(site['roads']) and not f.intersects(site['buildings']),('Train clearance',track_id,i)
   assert not any(f.intersection(q).area>.01 for q in occupied),('Train bodies overlap',track_id,i)
   # Rail-head top is G+.39+.055; prototype wheel low point is exactly zero.
   z=G+.445
   # Check both physical wheel treads, including their lateral offset from the
   # chord. A 0.16m wheel has a 0.096m full-radius contact band; the 0.09m rail
   # head must retain at least 5mm of contact at the tightest curved axle.
   wheel_path_errors=[abs(curve.distance(Point(p[0]+math.cos(ang)*x-math.sin(ang)*y,p[1]+math.sin(ang)*x+math.cos(ang)*y))-rail_detail.RAIL_OFFSET_M)
                      for x in (-7.2,-5.4,5.4,7.2) for y in (-rail_detail.RAIL_OFFSET_M,rail_detail.RAIL_OFFSET_M)]
   contact_limit=.16*.30+rail_detail.HEAD_WIDTH_M/2-.005
   assert max(wheel_path_errors)<contact_limit,('Wheel loses rail-head contact',track_id,i,wheel_path_errors,contact_limit)
   occupied.append(f)
   instance(name,[*p,z],yaw,plan_track_id=track_id,consist_id=track_id,consist_index=i,
            track_distance_m=(da+db)/2,coupling_joint_distances_m=[da,db],
            rail_contact_world_z_m=z,wheel_path_error_m=max(wheel_path_errors))
   cars.append(dict(mesh=name,index=i,position_m=[*p,z],rotation_deg=yaw,coupling_joint_distances_m=[da,db],wheel_path_error_m=max(wheel_path_errors)))
  consists.append(dict(id=track_id,occupied_source_interval_m=[start,end],cars=cars,coupler_joint_gap_m=0.,
                       note='Continuous train inferred within approved occupied track interval; individual schematic roof symbols are no longer placement targets.'))
 COUNTS['locomotives']=len(INSTANCES['SM_MPR4_Locomotive'])
 site['rail_consist_audit']=dict(policy='Continuous shared-module consists; exact chord-length coupler joints, raised rail contact, measured track curves',consists=consists)
 site['rail']=rail;return rail


def place_trailers(site):
 props=json.loads((ROOT/'SourceAssets/MPR/reference_v4/props/manifest.json').read_text(encoding='utf8'))
 vehicle_bounds={r['name']:r['bounds_m'] for r in props['meshes']}
 used_docks=set();placed=[];omitted=[];stand_adjustments=[];contact_checks=[]
 def actual_shape(name,p,yaw,scale):
  b=vehicle_bounds[name];local=box(b[0][0]*scale[0],b[1][0]*scale[1],b[0][1]*scale[0],b[1][1]*scale[1])
  return translate(rotate(local,yaw,origin=(0,0)),*p[:2])
 def tractor_pose(p,yaw,scale):
  angle=math.radians(yaw);k=6.55*scale[0]
  return [p[0]+math.cos(angle)*k,p[1]+math.sin(angle)*k,p[2]]
 def combination_shape(name,p,yaw,scale):
  return actual_shape(name,p,yaw,scale).union(actual_shape('SM_MPR4_Tractor',tractor_pose(p,yaw,scale),yaw,[1,1,1]))
 def valid(f):
  return (not f.intersects(site['buildings']) and f.intersection(site['roads']).area<.01
          and f.intersection(site['campus_planting']).area<.01
          and not any(f.intersection(q).area>.01 for q in VEHICLE_SHAPES))
 for row in plan.plan_details()['trailer_rows']:
  for i,pixel in enumerate(row['centers']):
   p=plan_to_world(pixel,G+.10);mode=row['mode'];name='SM_MPR4_Trailer_'+row['colors'][i%len(row['colors'])]
   yaw=-90 if mode=='south_cad' else 90 if mode=='north_cad' else row['yaw_deg']
   scale=[.80 if mode=='north_cad' else 1.,1.,1.];meta=dict(reference_row=row['name'],reference_index=i,reference_pixel=pixel)
   if mode.endswith('_cad'):
    normal=1 if mode=='north_cad' else -1
    choices=sorted([(j,d) for j,d in enumerate(core.CAD['dock_doors']) if d['outward_normal_xy'][1]*normal>.8 and j not in used_docks],key=lambda jd:abs(jd[1]['position_m'][0]-p[0]))
    chosen=None
    for j,d in choices:
     offset=16.15*scale[0]/2+.42
     q=[d['position_m'][0],d['position_m'][1]+normal*offset,G+.10]
     f=combination_shape(name,q,yaw,scale)
     if valid(f):chosen=(j,d,q,f);break
    if chosen is None:omitted.append(dict(row=row['name'],index=i,reason='No clear free CAD dock'));continue
    j,d,p,f=chosen;used_docks.add(j);meta.update(cad_dock_index=j,cad_dock_position_m=d['position_m'])
   else:
    f=combination_shape(name,p,yaw,scale)
    if not valid(f):
     original=list(p);chosen=None
     # Full articulated vehicles need more depth than the reference's trailer
     # symbols. Find the nearest clear stand within 14m, never move CAD docks.
     for dx,dy in sorted([(a,b) for a in np.arange(-14,14.01,.5) for b in np.arange(-14,14.01,.5) if a*a+b*b<=14*14],key=lambda ab:ab[0]**2+ab[1]**2):
      q=[original[0]+dx,original[1]+dy,original[2]];qf=combination_shape(name,q,yaw,scale)
      if valid(qf) and site['main_parcel'].contains(qf):chosen=(q,qf);break
     if chosen is None:omitted.append(dict(row=row['name'],index=i,reason='Image stand fails physical road/building clearance'));continue
     p,f=chosen;meta['stand_shift_m']=[p[k]-original[k] for k in range(2)];stand_adjustments.append(meta)
   assembly_id=row['name']+'_'+str(i);meta['assembly_id']=assembly_id
   tractor_p=tractor_pose(p,yaw,scale)
   VEHICLE_SHAPES.append(f);instance(name,p,yaw,scale=scale,**meta)
   instance('SM_MPR4_Tractor',tractor_p,yaw,assembly_id=assembly_id,coupled_trailer=name,reference_row=row['name'],reference_index=i,wheel_contact_world_z_m=G+.10)
   placed.append(dict(name=name,tractor_mesh='SM_MPR4_Tractor',tractor_position_m=tractor_p,position_m=p,rotation_deg=yaw,**meta))
   contact_checks.append(dict(assembly_id=assembly_id,ground_z_m=G+.10,trailer_wheel_min_z_m=p[2]+vehicle_bounds[name][2][0],tractor_wheel_min_z_m=tractor_p[2]+vehicle_bounds['SM_MPR4_Tractor'][2][0]))
   # Mark each occupied stall in its real frame and clip paint to the apron.
   angle=math.radians(yaw);t=(math.cos(angle),math.sin(angle));n=(-t[1],t[0]);half=16.15*scale[0]/2
   for sign in (-1,1):
    a=(p[0]-t[0]*half+n[0]*1.8*sign,p[1]-t[1]*half+n[1]*1.8*sign);b=(p[0]+t[0]*half+n[0]*1.8*sign,p[1]+t[1]*half+n[1]*1.8*sign)
    line('TrailerStands','MPR3_YellowLine',LineString([a,b]).intersection(site['concrete']),.15,G+.13)
 pads=[]
 for name,items in INSTANCES.items():
  if 'Trailer' not in name and 'Tractor' not in name:continue
  for item in items:pads.append(actual_shape(name,item['position_m'],item['rotation_deg'],item['scale']).buffer(.5).difference(site['paved']).difference(MAIN))
 if pads:
  patch=unary_union(pads).difference(site['campus_planting']).difference(site['roads']).difference(site['buildings'])
  shape('DockApronInfill','MPR3_Concrete',patch,G+.10);site['paved']=site['paved'].union(patch)
 COUNTS['tractors']=len(INSTANCES['SM_MPR4_Tractor'])
 assert all(abs(c[k]-c['ground_z_m'])<.001 for c in contact_checks for k in ('trailer_wheel_min_z_m','tractor_wheel_min_z_m')),'Vehicle wheel-ground mismatch'
 COUNTS['south_dock_trailers']=sum(r['reference_row']=='DockSouth' for r in placed)
 COUNTS['trailer_stands_adjusted']=len(stand_adjustments)
 site['trailer_layout_audit']=dict(policy='Latest plan positions with grounded GHS-derived tractor cabs; fixed CAD interfaces; 42ft north trailers and 53ft south trailers; combined footprints checked',placed=placed,omitted=omitted,stand_adjustments=stand_adjustments,wheel_contact_checks=contact_checks)

def landscape(site):
 context=json.loads((ROOT/'SourceAssets/MPR/reference_v4/context/manifest.json').read_text(encoding='utf8'))
 pads=[Polygon(p) for p in context.get('paved_footprints_m',[])]
 if pads:site['paved']=unary_union([site['paved'],*pads])
 buildings=site['buildings'];rail=site['rail']['exclusion']
 data=plan.read('plan_vegetation_v5.json');sx,sy=load_registration()['scale_m_per_px'];radius_scale=math.sqrt(abs(sx*sy))
 assert 'pending' not in data['status'],'Vegetation must pass source-image review'
 accepted=[];rejected=[];adjustments=[];tree_islands=[]
 hard=unary_union([site['roads'].buffer(.35),site['pond'],site['pond_walk'],rail,buildings,*VEHICLE_SHAPES])
 for row in data['trees']:
  source_position=plan_to_world(row['center_px'],G+.01)
  source_radius=max(1.8,min(10.,row['radius_px']*radius_scale))
  candidates=[];minimum_radius=max(1.8,source_radius*.45)
  # Deterministic nearest fitting point/crown, preserving measured density.
  # Small changes reconcile the two drawings; never populate unmeasured trees.
  offsets=[(0.,0.)]+sorted([(float(a),float(b)) for a in np.arange(-5,5.01,.5) for b in np.arange(-5,5.01,.5) if .01<a*a+b*b<=25],key=lambda ab:ab[0]**2+ab[1]**2)
  for dx,dy in offsets:
   q=[source_position[0]+dx,source_position[1]+dy,source_position[2]];point=Point(q[:2])
   if point.buffer(.8,quad_segs=12).intersects(hard):continue
   radius=min(source_radius,point.distance(buildings)/.85-.04,point.distance(rail)/.85-.04,point.distance(site['roads'])/.40-.04)
   if radius<minimum_radius:continue
   if any(math.dist(q[:2],r[:2])<min(radius,rr)*.4 for r,rr in accepted):continue
   shift=math.hypot(dx,dy);cost=shift*1.3+(source_radius-radius)*.6
   candidates.append((cost,q,radius,shift))
   if shift==0 and abs(radius-source_radius)<1e-6:break
  if not candidates:
   rejected.append(dict(id=row['id'],center_px=row['center_px'],reason='No physical fit within 5m and crown radius >=45% / 1.8m'));continue
  _,p,radius,shift=min(candidates,key=lambda a:a[0])
  if shift>.001 or abs(radius-source_radius)>.001:
   adjustments.append(dict(id=row['id'],source_center_px=row['center_px'],source_radius_m=source_radius,position_m=p,radius_m=radius,shift_m=shift))
  accepted.append((p,radius));TREE_ROWS.append(dict(position_m=p,crown_radius_m=radius,rotation_deg=RNG.uniform(0,360),reference_pixel=row['center_px'],source_id=row['id'],region=row.get('region','PlanMeasured')))
  # Visible planting islands belong to this source tree, never random decoration.
  island=Point(p[:2]).buffer(min(1.8,radius*.45),quad_segs=12).difference(hard)
  if island.intersection(site['paved']).area>.1:tree_islands.append(island)
 bounds=plan.pixel_box(-600,-500,2350,1450)
 ground=box(-1800,-1800,1800,1800);shape('FarGround','MPR3_GrassFar',ground,G-.08)
 # Keep real grass beneath fading road ends; the opaque terminal surface
 # lowers smoothly toward it. The source drawing's paved areas stay cut out.
 drawing=plan.pixel_box(*plan.read('outside_road_connections_v5.json')['canvas_px'])
 terrain=bounds.difference(site['paved'].intersection(drawing)).difference(site['pond']).difference(site['pond_walk']).difference(buildings).difference(site['campus_planting'])
 shape('ContinuousTerrain','MPR3_Grass',terrain,G)
 shape('CampusPlanting','MPR4_CampusPlanting',site['campus_planting'],G+.012)
 if tree_islands:
  islands=unary_union(tree_islands);shape('PlanTreeIslands','MPR3_Grass',islands,G+.115)
  core.raised_edge('PlanTreeIslandCurbs',islands.buffer(.16).difference(islands),G+.10,.14)
 COUNTS['reference_trees']=len(TREE_ROWS);COUNTS['tree_rejected_clearance']=len(rejected)
 return dict(exclusion_policy='Measured latest-plan centers; physical road/rail/building clearance, no stochastic population.',tree_positions=TREE_ROWS,rejected=rejected,fit_adjustments=adjustments,source_sha256=data['source_sha256'])


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
 core.MATERIALS['MPR3_Asphalt']['base_color']=[.13,.155,.19]
 core.MATERIALS['MPR3_Concrete']['base_color']=[.46,.43,.43]
 core.MATERIALS['MPR3_Grass']['base_color']=[.34,.37,.28]
 core.MATERIALS['MPR3_GrassFar']['base_color']=[.34,.37,.28]
 for role in ('MPR3_Grass','MPR3_GrassFar'):core.MATERIALS[role]['normal_strength']=.06
 core.MATERIALS['MPR4_CampusPlanting']=dict(base_color=[.22,.30,.16],roughness=.98,texture='grass',normal_strength=.06)
 for source,target in [('MPR3_Asphalt','MPR4_TerminalAsphalt'),('MPR3_Curb','MPR4_TerminalCurb'),('MPR3_WhiteLine','MPR4_TerminalWhiteLine')]:
  core.MATERIALS[target]=dict(core.MATERIALS[source],vertex_color_fade=dict(attribute='EdgeFade',channel='R',ground_role='MPR3_Grass',ground_base_color=core.MATERIALS['MPR3_Grass']['base_color'],ground_texture='grass',ground_roughness=.98,opaque=True))
 core.MATERIALS['MPR3_PavingJoint']['base_color']=[.42,.44,.42]
 core.MATERIALS['MPR3_Ballast']['base_color']=[.18,.19,.21]
 core.MATERIALS['MPR3_Sleepers']['base_color']=[.12,.13,.14]
 core.MATERIALS['MPR3_RailSteel']['base_color']=[.07,.08,.10]
 core.MATERIALS['MPR3_RailSteel']['metallic']=.25
 core.MATERIALS['MPR3_PondWater']['base_color']=[.018,.075,.095]
 core.MATERIALS['MPR3_PondWater'].update(normal_strength=.08,roughness=.42,metallic=0.)
 site=build_roads();build_water(site);build_rail(site);place_trailers(site);planting=landscape(site)
 # All newly authored meshes are version-four names, even while sharing the
 # deterministic low-level exporter with the previous experiment.
 GEO.data={name.replace('SM_MPR3_','SM_MPR4_'):roles for name,roles in GEO.data.items()}
 COUNTS.update(trailers=sum(len(v) for k,v in INSTANCES.items() if 'Trailer' in k),boxcars=len(INSTANCES['SM_MPR4_FreightBoxcar']))
 core.export(reference_surface_textures(),dict(reference_layout=plan.plan_details(),plan_registration=load_registration(),railway_layout=plan.read('plan_railway_v5.json'),road_boundary_source_sha256=plan.read('road_outline_v5.json')['source_sha256'],outside_plan_continuations=site['road_continuations'],road_terminal_fade=dict(config=plan.read('outside_road_connections_v5.json'),attribute='EdgeFade',encoding='LINEAR_RGB_EQUAL',zero='source surface',one='actual grass albedo and tint',opaque=True,max_longitudinal_vertex_spacing_m=2.,ground_z_m=G,terminal_height_fraction=.01),pond_walk_repair=site['pond_walk_repair'],campus_planting=dict(area_m2=site['campus_planting'].area,role='MPR4_CampusPlanting',access_portals_preserved=True),landscape_semantics=plan.read('plan_landscape_islands_v5.json'),planting=planting,trailer_layout_audit=site['trailer_layout_audit'],rail_consist_audit=site['rail_consist_audit'],surface_texture_policy='V4 grass mean 234 +/-2 random multiscale variation; water albedo 245 with weak random normal; no checker/diagonal sine trains',reference_match_policy='Latest plan road boundaries and measured building/tree/rail placements. Colored render defines material style; main interior CAD is invariant.'),vertex_fade=terminal_fade_at)
 print('MPR_REFERENCE_V4_SITE',dict(COUNTS))

if __name__=='__main__':main()
