"""Vectorize the user's road-boundary drawing without centreline buffering.

Requires NumPy/Pillow and the existing isolated GEOS Python. Outputs independent V5 data/diagnostics;
never edits existing site, context, CAD, Blender or Unreal sources.
"""
from pathlib import Path
import argparse,hashlib,json,math,subprocess,sys
import numpy as np
from PIL import Image,ImageDraw,ImageFont,ImageFilter
ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'SourceAssets/MPR/reference_v4/references/building-road-outline-20261103.png'
OUT=ROOT/'SourceAssets/MPR/reference_v4/site/road_outline_v5.json'
DIAG=ROOT/'Saved/MPR/road_v5'

# Gate strokes are only segmentation aids across explicit open plot entrances.
# They are exported as open portals, never proposed as permanent kerbs.
GATES=[dict(id='NeighborEntranceWest',ends_px=[[598,352],[621,352]],status='segmentation_only'),
       dict(id='NeighborEntranceEast',ends_px=[[948,352],[971,352]],status='segmentation_only'),
       dict(id='NorthBlockEntrance',ends_px=[[499,135],[526,135]],status='segmentation_only'),
       dict(id='NorthRoadBoundaryBreak',ends_px=[[767,157],[793,157]],status='thin_line_repair')]

SEMANTIC_SEEDS=[('WestAndCampusRoads','road_network',[500,150]),('EastRailLocalRoads','road_network',[1400,590]),
 ('UnoutlinedRailCorridor','excluded_rail_and_open_land',[1200,400]),('MainWarehouseParcel','warehouse_parcel',[700,675]),
 ('NorthWarehouseParcel','warehouse_parcel',[700,340]),('MainWarehouseBuilding','building_footprint',[760,490]),
 ('NorthWarehouseBuilding','building_footprint',[770,240]),
 ('SouthWestPond','pond',[395,710]),('PondEnclosingRing','pond_walk_or_bank',[353,700]),
 ('SouthWestTrafficIsland','landscape_island',[410,767])]

def label_runs(mask):
 """Exact four-connected components via scanline run union, no image dilation."""
 parents=[0];runs=[];previous=[]
 def find(a):
  while parents[a]!=a:parents[a]=parents[parents[a]];a=parents[a]
  return a
 for y,row in enumerate(mask):
  delta=np.diff(np.r_[False,row,False].astype(np.int8));starts=np.flatnonzero(delta==1);ends=np.flatnonzero(delta==-1)-1;current=[];j=0
  for x1,x2 in zip(starts,ends):
   i=len(parents);parents.append(i)
   while j<len(previous) and previous[j][1]<x1:j+=1
   k=j
   while k<len(previous) and previous[k][0]<=x2:
    a,b=find(i),find(previous[k][2]);parents[max(a,b)]=min(a,b);k+=1
   current.append((int(x1),int(x2),i));runs.append((y,int(x1),int(x2),i))
  previous=current
 roots={};labels=np.zeros(mask.shape,np.int32)
 for y,x1,x2,i in runs:
  r=find(i)
  if r not in roots:roots[r]=len(roots)+1
  labels[y,x1:x2+1]=roots[r]
 return labels

def signed_area(points):return sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(points,points[1:]+points[:1]))/2

def simplify_open(points,tolerance):
 if len(points)<3:return points
 p=np.asarray(points,float);a,b=p[0],p[-1];d=b-a
 t=np.clip(((p-a)@d)/(d@d),0,1) if d@d else np.zeros(len(p));dist=np.linalg.norm(p-(a+t[:,None]*d),axis=1);i=int(dist.argmax())
 if dist[i]<=tolerance:return [points[0],points[-1]]
 return simplify_open(points[:i+1],tolerance)[:-1]+simplify_open(points[i:],tolerance)

def simplify_ring(points,tolerance=.55):
 start=min(range(len(points)),key=lambda i:(points[i][0],points[i][1]));p=points[start:]+points[:start]
 opposite=max(range(len(p)),key=lambda i:(p[i][0]-p[0][0])**2+(p[i][1]-p[0][1])**2)
 return simplify_open(p[:opposite+1],tolerance)[:-1]+simplify_open(p[opposite:]+p[:1],tolerance)[:-1]

def boundary_rings(mask):
 """Follow foreground pixel edges; output holes as separate winding rings."""
 padded=np.pad(mask,1);h,w=mask.shape;edges={}
 for direction,neighbors in [('top',padded[:-2,1:-1]),('right',padded[1:-1,2:]),('bottom',padded[2:,1:-1]),('left',padded[1:-1,:-2])]:
  yy,xx=np.nonzero(mask & ~neighbors)
  for y,x in zip(yy.tolist(),xx.tolist()):
   if direction=='top':a,b=(x,y),(x+1,y)
   elif direction=='right':a,b=(x+1,y),(x+1,y+1)
   elif direction=='bottom':a,b=(x+1,y+1),(x,y+1)
   else:a,b=(x,y+1),(x,y)
   edges.setdefault(a,[]).append(b)
 rings=[]
 while edges:
  start=next(iter(edges));a=start;ring=[];last=None
  while True:
   ring.append([a[0]-.5,a[1]-.5]);choices=edges[a]
   if len(choices)==1:which=0
   else:
    incoming=(a[0]-last[0],a[1]-last[1]) if last else (1,0)
    # At a diagonal touch keep the foreground on the right of each edge.
    def turn(b):
     dx,dy=b[0]-a[0],b[1]-a[1];cross=incoming[0]*dy-incoming[1]*dx;dot=incoming[0]*dx+incoming[1]*dy
     return {1:0,0:1,-1:2}.get(cross,3)+(2 if dot<0 else 0)
    which=min(range(len(choices)),key=lambda i:turn(choices[i]))
   b=choices.pop(which)
   if not choices:del edges[a]
   last,a=a,b
   if a==start:break
  if len(ring)>3:rings.append(simplify_ring(ring))
 return sorted(rings,key=lambda r:abs(signed_area(r)),reverse=True)

def center_ink_ring(ring,gray):
 """Move white pixel edges to the centre of the actual antialiased stroke.

 Sample the normal across the 1-3px ink stroke, weighted by darkness. Do not
 move canvas clips or artificial entrance gates. This removes one-sided
 threshold offsets, so adjacent parcels and roads share the drawn boundary.
 """
 p=np.asarray(ring,float);out=[];h,w=gray.shape
 for i,q in enumerate(p):
  if q[0]<1 or q[1]<1 or q[0]>w-2 or q[1]>h-2:out.append(q.tolist());continue
  if any(abs(q[1]-g['ends_px'][0][1])<2 and g['ends_px'][0][0]-2<q[0]<g['ends_px'][1][0]+2 for g in GATES):out.append(q.tolist());continue
  tangent=p[(i+1)%len(p)]-p[i-1];normal=np.array([tangent[1],-tangent[0]]);normal/=max(np.linalg.norm(normal),1e-9)
  step=np.arange(-.75,3.51,.25);samples=q[None,:]+step[:,None]*normal
  x,y=samples[:,0],samples[:,1];x0=np.floor(x).astype(int);y0=np.floor(y).astype(int)
  x0=np.clip(x0,0,w-2);y0=np.clip(y0,0,h-2);fx=x-x0;fy=y-y0
  intensity=(gray[y0,x0]*(1-fx)*(1-fy)+gray[y0,x0+1]*fx*(1-fy)+gray[y0+1,x0]*(1-fx)*fy+gray[y0+1,x0+1]*fx*fy)
  weights=np.maximum(0,210-intensity)**2
  delta=float(step@weights/weights.sum()) if weights.sum()>100 else 0.
  out.append((q+normal*np.clip(delta,-.4,1.8)).round(3).tolist())
 return out

def boundary_agreement(regions,ink):
 distances=[];h,w=ink.shape
 for region in regions:
  for ring in region['rings_px']:
   for a,b in zip(ring,ring[1:]+ring[:1]):
    n=max(1,int(math.dist(a,b)/.75))
    for t in np.linspace(0,1,n,endpoint=False):
     x,y=np.array(a)*(1-t)+np.array(b)*t
     if x<2 or y<2 or x>w-3 or y>h-3:continue
     if any(abs(y-g['ends_px'][0][1])<2 and g['ends_px'][0][0]-2<x<g['ends_px'][1][0]+2 for g in GATES):continue
     ix,iy=round(x),round(y);ys,xs=np.nonzero(ink[iy-3:iy+4,ix-3:ix+4])
     distances.append(float(np.min(np.hypot(xs+ix-3-x,ys+iy-3-y))) if len(xs) else 5.)
 return dict(samples=len(distances),distance_to_ink_px_p95=float(np.percentile(distances,95)),distance_to_ink_px_max=max(distances),fraction_within_1px=float(np.mean(np.array(distances)<=1)))

def normalize_topology(regions):
 """Use the already installed Blender-Python GEOS, without launching Blender."""
 request=DIAG/'topology_request.json';response=DIAG/'topology_response.json'
 request.write_text(json.dumps([dict(id=r['id'],rings=r['rings_px'])for r in regions]),encoding='utf8')
 code='''import sys,json
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from shapely.geometry import Polygon
rows=json.loads(Path(sys.argv[2]).read_text());out=[]
for row in rows:
 p=Polygon(row['rings'][0],row['rings'][1:]);area=p.area
 q=p.buffer(0).simplify(.35,preserve_topology=True)
 if q.geom_type=='MultiPolygon':
  parts=sorted(q.geoms,key=lambda p:p.area,reverse=True);assert sum(p.area for p in parts[1:])<3.,row['id'];q=parts[0]
 assert q.is_valid and q.geom_type=='Polygon',row['id']
 rings=[list(q.exterior.coords)[:-1]]+[list(r.coords)[:-1]for r in q.interiors]
 out.append(dict(id=row['id'],rings=rings,initial_valid=p.is_valid,area_delta_px2=q.area-area,valid=True))
Path(sys.argv[3]).write_text(json.dumps(out),encoding='utf8')
'''
 command=[str(Path('D:/WinAPP/Blender/5.2/python/bin/python.exe')),'-c',code,str(ROOT/'Saved/ParkRefinement/python_deps'),str(request),str(response)]
 subprocess.run(command,check=True,capture_output=True,text=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 normalized={r['id']:r for r in json.loads(response.read_text())}
 for region in regions:
  row=normalized[region['id']];region['rings_px']=[[[round(v,4)for v in p]for p in ring]for ring in row['rings']]
  region['topology_validation']={k:v for k,v in row.items()if k not in ('id','rings')}

def clean_semantic_polygons(regions):
 """Remove subpixel ink islands and enforce shared-region non-overlap.

 The one-pixel opening affects only raster slivers, not road width design.
 All original diagnostic regions are retained separately in the JSON.
 """
 request=DIAG/'semantic_request.json';response=DIAG/'semantic_response.json'
 request.write_text(json.dumps(regions),encoding='utf8')
 code='''import sys,json
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from shapely.geometry import Polygon
from shapely.ops import unary_union
rows=json.loads(Path(sys.argv[2]).read_text());roads=[];parcels=[];excluded=[];audit=[]
def output(row,p,suffix=''):
 assert p.is_valid
 return dict(id=row['id']+suffix,name=row['name'],category=row['category'],exterior=list(p.exterior.coords)[:-1],holes=[list(r.coords)[:-1]for r in p.interiors],touches_canvas=row['touches_canvas'])
for row in rows:
 if row['category']!='road_network':continue
 p=Polygon(row['rings_px'][0],row['rings_px'][1:]);holes=[list(r.coords)for r in p.interiors if Polygon(r).area>=12]
 q=Polygon(p.exterior,holes);before=q
 q=q.buffer(-1.,quad_segs=4).buffer(1.,quad_segs=4).simplify(.25,preserve_topology=True)
 assert q.geom_type=='Polygon' and q.is_valid
 assert q.symmetric_difference(before).area / before.area < .012
 roads.append(output(row,q));audit.append(dict(id=row['id'],removed_noise_holes=len(p.interiors)-len(holes),noise_hole_area_px2=before.area-p.area,raster_sliver_correction_area_px2=q.symmetric_difference(before).area))
 road_union=unary_union([Polygon(r['exterior'],r['holes'])for r in roads])
for row in rows:
 if row['category'] in ('road_network','building_footprint'):continue
 p=Polygon(row['rings_px'][0],row['rings_px'][1:])
 if row['name']=='NorthWarehouseParcel':
  ring=row['rings_px'][0]
  nearest=lambda xy:min(range(len(ring)),key=lambda i:(ring[i][0]-xy[0])**2+(ring[i][1]-xy[1])**2)
  start,end=nearest((1057.047,169.226)),nearest((1040.528,172.177));assert start<end
  outer=ring[:start+1]+[[1040.9,169.2]]+ring[end+1:]
  building=next(r for r in rows if r['name']=='NorthWarehouseBuilding')
  p=Polygon(outer,[building['rings_px'][0]])
  from shapely.geometry import Point
  assert p.is_valid and Polygon(outer).contains(Point(770,245))
  audit.append(dict(id=row['id'],semantic_repair='Restore parcel envelope across northern kerb/building contact; building stays a hole, road geometry unchanged',inferred_edge_px=[ring[start],[1040.9,169.2]],outer_area_px2=Polygon(outer).area))
 q=p.difference(road_union)
 target=excluded if row['category']=='excluded_rail_and_open_land' else parcels
 parts=list(q.geoms)if q.geom_type=='MultiPolygon' else [q]
 for i,part in enumerate(parts):
  if part.area>=100:target.append(output(row,part,'' if len(parts)==1 else '_'+str(i)))
assert all(Polygon(r['exterior'],r['holes']).intersection(road_union).area<1e-6 for r in parcels+excluded)
Path(sys.argv[3]).write_text(json.dumps(dict(polygons_px=roads,parcels_px=parcels,excluded_polygons_px=excluded,semantic_cleanup_audit=audit)),encoding='utf8')
'''
 subprocess.run(['D:/WinAPP/Blender/5.2/python/bin/python.exe','-c',code,str(ROOT/'Saved/ParkRefinement/python_deps'),str(request),str(response)],check=True,capture_output=True,text=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 return json.loads(response.read_text())

def main(source):
 DIAG.mkdir(parents=True,exist_ok=True);im=Image.open(source).convert('RGB');assert im.size==(1728,910)
 gray=np.array(im.convert('L'));ink=gray<110
 # New building/road image contains interrupted grey kerbs. Closing is used
 # only to label regions; final contours are resampled onto original ink.
 gate_image=Image.fromarray(((gray<210)*255).astype(np.uint8)).filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.MinFilter(7));draw=ImageDraw.Draw(gate_image)
 for row in GATES:draw.line([tuple(p) for p in row['ends_px']],fill=255,width=2)
 gated=np.array(gate_image)>0;raw=label_runs(~ink);labels=label_runs(~gated);regions=[]
 for i in range(1,int(labels.max())+1):
  yy,xx=np.nonzero(labels==i)
  if len(xx)<100:continue
  cx,cy=float(xx.mean()),float(yy.mean());near=int(np.argmin((xx-cx)**2+(yy-cy)**2));rings=boundary_rings(labels==i)
  regions.append(dict(id=f'region_{i:03}',label=i,area_px=int(len(xx)),bbox_px=[int(xx.min()),int(yy.min()),int(xx.max()),int(yy.max())],
                      seed_px=[int(xx[near]),int(yy[near])],touches_canvas=bool(xx.min()==0 or yy.min()==0 or xx.max()==1727 or yy.max()==909),
                      white_region_rings_px=rings,rings_px=[center_ink_ring(r,gray) for r in rings]))
 normalize_topology(regions)
 bylabel={r['label']:r for r in regions}
 for name,category,(x,y) in SEMANTIC_SEEDS:
  label=int(labels[y,x]);assert label in bylabel,(name,x,y,label)
  region=bylabel[label];assert 'category' not in region,(name,'Ambiguous semantic seed')
  region.update(name=name,category=category,classification_seed_px=[x,y])
 for r in regions:
  r.setdefault('name',r['id']);r.setdefault('category','bounded_land_parcel' if not r['touches_canvas'] else 'edge_clipped_land_parcel')
 roads=[r for r in regions if r['category']=='road_network'];assert len(roads)==2
 semantic_polygons=clean_semantic_polygons(regions)
 rng=np.random.default_rng(51);palette=np.vstack([np.array([[15,20,25]]),rng.integers(100,240,size=(int(labels.max()),3))]).astype(np.uint8)
 overlay=Image.fromarray(palette[labels]);draw=ImageDraw.Draw(overlay)
 try:font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',17)
 except OSError:font=ImageFont.load_default()
 for r in regions:
  x,y=r['seed_px'];draw.text((x-15,y-9),str(r['label']),fill='black',font=font,stroke_width=2,stroke_fill='white')
 for row in GATES:draw.line([tuple(p) for p in row['ends_px']],fill='red',width=4)
 overlay.save(DIAG/'segmented_regions.png')
 overlay=im.copy();draw=ImageDraw.Draw(overlay)
 for r in regions:
  for ring in r['rings_px']:draw.line([tuple(p) for p in ring+[ring[0]]],fill=(15,130,220),width=1)
 overlay.save(DIAG/'vector_overlay.png')
 semantic=im.copy().convert('RGBA');fills=Image.new('RGBA',im.size);fd=ImageDraw.Draw(fills)
 colors={'road_network':(34,130,225,145),'excluded_rail_and_open_land':(220,170,72,90),'warehouse_parcel':(65,180,100,75),'landscape_island':(40,170,70,120),'pond':(40,155,185,145),'pond_walk_or_bank':(140,90,180,110)}
 for r in semantic_polygons['polygons_px']+semantic_polygons['parcels_px']+semantic_polygons['excluded_polygons_px']:
  if r['category'] not in colors:continue
  fd.polygon([tuple(p)for p in r['exterior']],fill=colors[r['category']])
  for hole in r['holes']:fd.polygon([tuple(p)for p in hole],fill=(0,0,0,0))
 semantic=Image.alpha_composite(semantic,fills);dd=ImageDraw.Draw(semantic)
 for row in GATES:dd.line([tuple(p)for p in row['ends_px']],fill=(240,55,40,255),width=4)
 semantic.convert('RGB').save(DIAG/'road_semantics_overlay.png')
 portals=[]
 for gate in GATES:
  ends=gate['ends_px'];portals.append(dict(**gate,width_px=math.dist(*ends),
       connects=['WestAndCampusRoads','NorthWarehouseParcel'] if gate['id'].startswith('Neighbor') else ['WestAndCampusRoads','NorthBlock'],do_not_close_in_runtime=gate['status']=='segmentation_only'))
 agreement=boundary_agreement(roads,ink)
 result=dict(schema_version=1,status='ready_pixel_geometry_with_explicit_semantic_repairs',source_image=str(source),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
             image_size=[1728,910],coordinate_frame='pixel origin top-left; authoritative latest plan diagram, NOT legacy perspective camera',
             world_registration='Use mpr_plan_layout.plan_to_world and site/plan_registration_v5.json; no world coordinates baked into this extraction',
             method=dict(ink_threshold=110,segmentation_threshold=210,connectivity=4,morphology='7px square closing solely for label connectivity; final boundaries refined onto original dark ink',gate_width_px=2,polyline_simplify_tolerance_px=.55,
                         stroke_center_refinement='darkness-weighted cross-stroke sampling, clipped to 1.8px maximum; GEOS zero-distance topology repair and 0.35px topology-preserving simplification; no dilation or road-width buffer',
                         boundary_uncertainty_px=3.0,semantic_cleanup='Remove ink holes smaller than 12px2; 1px opening removes narrow raster slivers; subtract road polygons from adjacent semantic regions to eliminate subpixel overlap. Does not construct roads from centerline buffers.',notes='Consume polygons_px/parcels_px/excluded_polygons_px. regions retain diagnostic original contours. Small interrupted grey lines repaired during segmentation. Building footprints are diagnostic only; use independent building extraction.'),
             temporary_segmentation_gates=portals,raw_white_components=int(raw.max()),gated_white_components=int(labels.max()),regions=regions,
             road_region_ids=[r['id']for r in roads],excluded_region_ids=[r['id']for r in regions if r['category']=='excluded_rail_and_open_land'],
             closed_island_ids=[r['id']for r in regions if r['category']=='landscape_island'],boundary_agreement=agreement,
             **semantic_polygons,
             portals_px=portals,
             topology_questions=[dict(id='ClosedWestStub',location_px=[441,632],observation='Latest image retains a short west-facing stub; linework remains closed at its tip.',policy='Keep drawn boundary, do not invent driveway extension'),
                                 dict(id='PondRingMaterial',location_px=[353,700],observation='The pond has a separate enclosed ring, disconnected from the vehicle road region.',policy='Treat as bank/walkway, not asphalt vehicle road'),
                                 dict(id='RailBlankExcluded',observation='The large diagonal region is fully separated from both road networks by drawn boundaries.',policy='Exclude entire region; preserve the existing railway separately')])
 OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps([dict(id=r['id'],area=r['area_px'],bbox=r['bbox_px'],seed=r['seed_px'],holes=len(r['rings_px'])-1)for r in regions],indent=2))

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,default=SOURCE);args=parser.parse_args();main(args.source)
