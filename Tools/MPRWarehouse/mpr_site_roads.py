"""Photo-led near-campus surfaces with tangent curves and shared exclusion geometry.

Positions remain in the aligned CAD metre frame. Photographs determine surface
hierarchy and landscape bands; these are not civil-engineering survey drawings.
"""
from pathlib import Path
import sys,math
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Scripts/ghs'))
from park_curves import rounded_path,offset_path,dash_segments,sample_along
from shapely.geometry import Polygon,LineString,Point,box
from shapely.ops import unary_union
import shapely

MATERIALS={
 'SiteAsphalt':dict(color=[.105,.142,.18],roughness=.95,parent='Roads'),
 'SiteConcrete':dict(color=[.48,.52,.54],roughness=.93,parent='Hardstand'),
 'SiteCurb':dict(color=[.62,.67,.69],roughness=.88,parent='Curbs'),
 'SiteGrass':dict(color=[.27,.345,.285],roughness=1.,parent='Landscape'),
 'SiteBackdrop':dict(color=[.43,.50,.54],roughness=1.,parent='Ground'),
 'LaneWhite':dict(color=[.78,.81,.79],roughness=.9,parent='Markings'),
 'LaneYellow':dict(color=[.72,.53,.18],roughness=.9,parent='Markings'),
 'SiteWater':dict(color=[.115,.22,.26],roughness=.55,parent='Ground'),
}
REPLACED_ROADS={'139b','1392','16c6','1580','16d4','16fe','1393','1396','1559'}


def polygons(g):
 if g.is_empty:return []
 if g.geom_type=='Polygon':return [g]
 return [p for child in getattr(g,'geoms',[]) for p in polygons(child)]


def emit_shape(api,name,role,shape,z):
 shape=shapely.make_valid(shape)
 for p in polygons(shape):
  for tri in shapely.constrained_delaunay_triangles(p).geoms:
   if tri.area>1e-8:api['poly'](name,role,list(tri.exterior.coords)[:-1],z)


def ribbon(api,name,role,points,width,z):
 for a,b in zip(points,points[1:]):api['strip'](name,role,a,b,width,z)


def build_site_roads(api,source,ground_z):
 g=ground_z;road_data=[]
 # North of the campus the real Port Reading Avenue bends east. Preserve
 # CADMapper road 16c6 there instead of extending the near-view control line
 # straight through the residential footprints.
 port_source=next(m for m in source['meshes'] if m['id']=='16c6')
 port_vertices=port_source['vertices']
 port_shape=unary_union([Polygon([port_vertices[i][:2] for i in f]) for f in port_source['faces']])
 port_section=port_shape.intersection(LineString([(-1000,355),(1000,355)]))
 port_left,_,port_right,_=port_section.bounds
 port_center=(port_left+port_right)/2
 port_width=port_right-port_left
 # Anchored to aligned CAD centre positions, rounded through the photograph's
 # continuous south/east bend. Dense tessellation removes the visible facets.
 definitions=[
  ('Prologis', [(-251,-269),(-212,-249),(-171,-224),(-124,-198),(-84,-174),(-43,-160),(25,-150),(86,-141),(122,-129),(155,-108),(181,-80),(207,-26),(235,30),(251,61)], 10.8,42,True),
  ('PortReading',[(-231,-320),(-235,-263),(-243,-207),(-247,-154),(-247,-75),(-248,24),(-250,144),(-251,240),(-255,335),(port_center,355)],13.0,55,True),
  ('WestAccess',[(-122,-203),(-169,-158),(-207,-120),(-215,-106),(-215,-55),(-214,44),(-213,110),(-212,205),(-211,322),(-155,323),(30,323),(180,320),(272,331),(374,334)],8.5,16,False),
  ('NorthCourt',[(-214,108),(-145,108),(40,108),(184,108),(264,108)],9,18,False),
  ('EastAccess',[(251,61),(211,-25),(195,-16),(195,43),(197,86),(215,87),(215,108)],7,12,False),
 ]
 for name,controls,width,radius,public in definitions:
  pts,meta=rounded_path(controls,radius=radius,max_step=.7,return_metadata=True)
  geometry=LineString(pts).buffer(width*.5,quad_segs=12)
  if name=='PortReading':
   # Twenty metres of pavement taper meet the exact source edges at y=355.
   section=geometry.intersection(LineString([(-1000,335),(1000,335)]))
   left,_,right,_=section.bounds
   taper=Polygon([(left,335),(right,335),(port_right,355),(port_left,355)])
   geometry=unary_union([geometry.intersection(box(-1800,-1800,1800,335)),taper])
  road_data.append(dict(name=name,path=pts,width=width,public=public,geometry=geometry,curve=meta))
 # Preserve the real outer street network. Round only tiny polygon junction
 # corners, retaining entrances and topology. Near replacements are explicit.
 context=[]
 for m in source['meshes']:
  if m['layer'] not in ('major_roads','minor_roads','paths') or m['id'] in REPLACED_ROADS:continue
  p=m['vertices'];faces=[Polygon([p[i][:2] for i in f]) for f in m['faces']]
  valid=[f for f in faces if f.is_valid and f.area>1e-6]
  if valid:context.append(unary_union(valid))
 context.append(port_shape.intersection(box(-1800,355,1800,1800)))
 road_union=unary_union([r['geometry'] for r in road_data]+context)
 # Smooth the small imported joins, not the measured building/site footprints.
 road_union=road_union.buffer(.8,quad_segs=8).buffer(-.8,quad_segs=8)
 main=Polygon(source['alignment']['targetFootprint_m'])
 north=box(-166.08,74.546,166.786,137.8)
 south=Polygon([(-166.08,-83.95),(135.36,-83.95),(145,-101),(146,-111),(132,-120),(94,-128),(49,-134),(-98,-146),(-162,-133),(-193,-119),(-184,-106),(-166.08,-104)])
 westpark=box(-211,-93,-182.2,83)
 eastpark=Polygon([(183.3,-17),(211,-17),(211,83),(183.3,83)])
 # Entrance islands, mid-row planting and end islands break parking into rows.
 islands=[]
 for lo,hi,ys in [(-211,-182.2,[-85,-48,-11,26,63,78]),(183.3,211,[-9,29,67,78])]:
  for y in ys:
   for x in (lo+3.6,hi-3.6):islands.append(box(x-3.1,y-1.65,x+3.1,y+1.65).buffer(.65,quad_segs=8))
 # Parking planting belongs inside its parking parcel. The same cut geometry
 # drives the grass, paving holes and tree-centre candidates, so islands cannot
 # cover WestAccess or the bend of Prologis Way.
 parking_parcels=unary_union([westpark,eastpark])
 islands=[piece for island in islands for piece in polygons(island.intersection(parking_parcels).difference(road_union.buffer(.25))) if piece.area>2]
 tree_islands=unary_union(islands)
 campus=unary_union([north,south,westpark,eastpark]).difference(main.buffer(.1)).difference(tree_islands)
 paved=unary_union([road_union,campus])
 # One unified asphalt surface avoids z-fighting and arbitrary seam strips.
 regions={'Near':box(-290,-220,285,355),'Far_E':box(285,-1800,1800,1800),
          'Far_W':box(-1800,-1800,-290,1800),'Far_N':box(-290,355,285,1800),'Far_S':box(-290,-1800,285,-220)}
 for region,clip in regions.items():
  surface=paved.intersection(clip)
  emit_shape(api,'SM_MPR_Env_'+region+'_Roads','SiteAsphalt',surface,g+.075)
 # Muted continuous curbs, with openings wherever road and court surfaces join.
 curb=paved.buffer(.22,quad_segs=6).difference(paved).difference(main.buffer(.35))
 emit_shape(api,'SM_MPR_Env_Near_Curbs','SiteCurb',curb.intersection(box(-280,-220,280,150)),g+.16)
 # Concrete loading bands match the two dock facades. Cutouts remain asphalt.
 aprons=unary_union([box(-166.08,74.546,166.786,93.4),box(-166.08,-103.5,135.36,-83.95)]).difference(main)
 emit_shape(api,'SM_MPR_Env_Near_DockAprons','SiteConcrete',aprons,g+.095)
 # Trailer standing strip faces the southern dock line, bounded by grass.
 trailer=Polygon([(-162,-128),(-85,-139),(40,-131),(40,-121),(-88,-129),(-162,-119)])
 emit_shape(api,'SM_MPR_Env_Near_TrailerStands','SiteConcrete',trailer.intersection(campus),g+.095)
 for x in range(-156,36,4):
  y=-128 if x<-85 else -129+(x+85)*.065
  line=LineString([(x,y-7),(x,y+4)]).intersection(trailer)
  if line.geom_type=='LineString':ribbon(api,'SM_MPR_Env_Near_Markings','LaneWhite',list(line.coords),.1,g+.115)
 # Main public road: paired yellow centre lines and restrained white edges.
 marking_count=0
 for r in road_data:
  pts=r['path'];w=r['width']
  if r['public']:
   # The supplied aerial photo shows a yellow hatched median on Prologis,
   # not a third traffic lane. Port Reading retains a double centre line.
   median_half=.85 if r['name']=='Prologis' else .17
   for off in (-median_half,median_half):
    ribbon(api,'SM_MPR_Env_Near_Centerlines','LaneYellow',offset_path(pts,off),.12,g+.101)
   for off in (-w/2+.45,w/2-.45):
    edges=offset_path(pts,off)
    if r['name']=='PortReading':
     normals=offset_path(pts,1)
     sign=-1 if off<0 else 1
     edges=[(p[0]+(n[0]-p[0])*sign*((w+(port_width-w)*max(0,min(1,(p[1]-335)/20)))/2-.45),
             p[1]+(n[1]-p[1])*sign*((w+(port_width-w)*max(0,min(1,(p[1]-335)/20)))/2-.45)) for p,n in zip(pts,normals)]
    ribbon(api,'SM_MPR_Env_Near_Edgelines','LaneWhite',edges,.10,g+.101)
   # Diagonal strokes connect the two median boundaries at 45 degrees.
   if r['name']=='Prologis':
    for p,t,arc in sample_along(pts,5.,start=3.):
     n=(-t[1],t[0]);h=median_half-.06
     a=(p[0]-n[0]*h-t[0]*h,p[1]-n[1]*h-t[1]*h)
     b=(p[0]+n[0]*h+t[0]*h,p[1]+n[1]*h+t[1]*h)
     ribbon(api,'SM_MPR_Env_Near_ShoulderHatch','LaneYellow',[a,b],.13,g+.103);marking_count+=1
  else:
   for d in dash_segments(pts,3,7):
    ribbon(api,'SM_MPR_Env_Near_AccessLines','LaneWhite',d,.11,g+.105);marking_count+=1
 # Parking lines and cars use identical exclusion islands and pavement tests.
 cars=[];parking_count=0
 for lo,hi,ylo,yhi in [(-211,-182.2,-93,83),(183.3,211,-17,83)]:
  for side,x in enumerate((lo+3.3,hi-3.3)):
   for k in range(int((yhi-ylo)/2.8)):
    y=ylo+1.1+k*2.8;slot=box(x-2.55,y,x+2.55,y+2.7)
    if tree_islands.intersects(slot.buffer(.15)):continue
    ribbon(api,'SM_MPR_Env_Near_Markings','LaneWhite',[(x-2.55,y),(x+2.55,y)],.1,g+.108);parking_count+=1
    if k%6 in (1,3) and (k+side)%3:
     cars.append(dict(position_m=[x,y+1.35,g+.075],rotation_deg=0 if side==0 else 180,scale=[1,1,1]))
 # North truck court has lane edges and individual dock guidance segments.
 for x in range(-160,166,7):
  ribbon(api,'SM_MPR_Env_Near_Markings','LaneWhite',[(x,77),(x,91)],.10,g+.12)
 for y in (98,119):
  for d in dash_segments([(-160,y),(161,y)],4,6):ribbon(api,'SM_MPR_Env_Near_Markings','LaneWhite',d,.10,g+.115)
 # Preserve the triangular retention pond seen beside the west entrance.
 pond=Polygon([(-231,-165),(-231,-197),(-198,-191)]).buffer(4,quad_segs=12).buffer(-3,quad_segs=12)
 pond=pond.difference(paved.buffer(3))
 emit_shape(api,'SM_MPR_Env_Near_Retention','SiteWater',pond,g-.015)
 # Broad quieter planting ground, cut by all paved surfaces. No random grass
 # ribbons cross roads or overlap the warehouse footprint.
 greens=box(-285,-220,283,345).difference(paved.buffer(.4)).difference(main).difference(pond)
 emit_shape(api,'SM_MPR_Env_Near_Landscape','SiteGrass',greens,g+.025)
 emit_shape(api,'SM_MPR_Env_Near_ParkingIslands','SiteGrass',tree_islands,g+.19)
 audit={
  'source_replaced_road_ids':sorted(REPLACED_ROADS),'reference_images':['Snipaste_2026-10-30_16-02-59.png','Snipaste_2026-10-30_16-04-43.png','Snipaste_2026-10-30_16-13-26.png'],
  'source_road_restored':{'id':'16c6','north_of_y_m':355,'transition_y_m':[335,355],'source_join_center_m':[port_center,355],'source_join_width_m':port_width},
  'parking_island_policy':'Clipped to parking parcels and 0.25m clear of the road union before grass, pavement holes and tree centres are generated.',
  'curves':[dict(name=r['name'],width_m=r['width'],max_sample_step_m=.7,samples=len(r['path'])) for r in road_data],
  'parking_spaces_drawn':parking_count,'line_dash_groups':marking_count,
  'boundary_policy':'Photographic reconstruction anchored to aligned CAD roads; not survey accuracy.'}
 return dict(paved=paved,roads=road_union,main=main,islands=tree_islands,pond=pond,
             tree_island_centers=[list(p.centroid.coords)[0] for p in islands],cars=cars,
             paths={r['name']:r['path'] for r in road_data},audit=audit)
