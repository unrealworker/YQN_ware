"""Union measured CAD wall rectangles without snapping or closing door gaps."""
import sys,json,math,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'Scripts/_vendor/cad'))
from shapely.geometry import Polygon,mapping
from shapely.ops import unary_union
from shapely.geometry.polygon import orient
from shapely import constrained_delaunay_triangles
OUT=ROOT/'SourceAssets/GHS';cad=json.loads((OUT/'cad_layout.json').read_text(encoding='utf8'))
rects=[];sources=[];dups=collections.defaultdict(list)
for w in cad['walls']:
 a,b=w['points_m'];L=math.dist(a,b);n=[-(b[1]-a[1])/L*w['thickness_m']/2,(b[0]-a[0])/L*w['thickness_m']/2]
 ps=[(a[0]+n[0],a[1]+n[1]),(a[0]-n[0],a[1]-n[1]),(b[0]-n[0],b[1]-n[1]),(b[0]+n[0],b[1]+n[1])];p=Polygon(ps);rects.append(p);sources.append({'id':w['id'],'source_handles':w['source_handles'],'footprint_xy':ps});dups[tuple(sorted((round(x,6),round(y,6)) for x,y in ps))].append(w['id'])
u=unary_union(rects);assert u.is_valid
polys=list(u.geoms) if u.geom_type=='MultiPolygon' else [u]
# Negative buffer only: inside boundary strip never extends beyond measured volume.
inner=u.buffer(-.012,join_style='mitre');band=u.difference(inner);assert band.is_valid
meshes={name:{'vertices':[],'faces':[]} for name in ['SM_GHS_JoinedWallFaces','SM_GHS_JoinedWallSections','SM_GHS_JoinedWallEdges']}
loops=[]
for pi,p in enumerate(polys):
 p=orient(p,sign=1)
 for ri,ring in enumerate([p.exterior]+list(p.interiors)):
  coords=list(ring.coords);loops.append({'polygon':pi,'hole':ri>0,'points':coords,'closed':coords[0]==coords[-1]})
  m=meshes['SM_GHS_JoinedWallFaces']
  for a,b in zip(coords,coords[1:]):
   if math.dist(a,b)<1e-9:continue
   k=len(m['vertices']);m['vertices'] += [[a[0],a[1],0],[b[0],b[1],0],[b[0],b[1],2.8],[a[0],a[1],2.8]];m['faces'].append([k,k+1,k+2,k+3])
def cap(geom,key,z,up=True):
 m=meshes[key];ts=constrained_delaunay_triangles(geom);area=0
 for tri in ts.geoms:
  if tri.area<1e-14:continue
  assert tri.difference(geom).area<1e-8
  ps=list(orient(tri,sign=1 if up else -1).exterior.coords)[:3];k=len(m['vertices']);m['vertices'] += [[x,y,z] for x,y in ps];m['faces'].append([k,k+1,k+2]);area+=tri.area
 assert abs(area-geom.area)<1e-6,(area,geom.area)
 return area
cap(u,'SM_GHS_JoinedWallSections',0,False);toparea=cap(u,'SM_GHS_JoinedWallSections',2.8);bandarea=cap(band,'SM_GHS_JoinedWallEdges',2.8005)
report={'source_wall_count':len(sources),'all_source_ids_retained':len(set(s['id'] for s in sources))==330,'source_rectangle_area_sum_m2':sum(p.area for p in rects),'footprint_union_area_m2':u.area,'overlap_removed_area_m2':sum(p.area for p in rects)-u.area,'polygon_count':len(polys),'closed_loop_count':len(loops),'hole_count':sum(len(p.interiors) for p in polys),'all_loops_closed':all(l['closed'] for l in loops),'union_valid':u.is_valid,'edge_band_width_m':.012,'edge_band_area_m2':band.area,'edge_outside_wall_area_m2':band.difference(u).area,'top_triangle_area_m2':toparea,'edge_triangle_area_m2':bandarea,'wall_height_m':2.8,'edge_z_m':2.8005,'no_snapping_or_positive_buffer':True,'duplicate_groups':[v for v in dups.values() if len(v)>1],'mesh_counts':{k:{'vertices':len(v['vertices']),'faces':len(v['faces'])} for k,v in meshes.items()}}
assert report['edge_outside_wall_area_m2']<1e-10 and report['all_loops_closed']
for mesh in meshes.values():
 mesh['faces']=[tri for f in mesh['faces'] for tri in ([[f[0],f[1],f[2]],[f[0],f[2],f[3]]] if len(f)==4 else [f])]
 mesh['verts']=mesh['vertices']
 mesh['source_wall_ids']=[row['id'] for row in sources]
report['mesh_counts']={k:{'vertices':len(v['vertices']),'triangles':len(v['faces'])} for k,v in meshes.items()}
(OUT/'joined_walls_geometry.json').write_text(json.dumps({'meshes':meshes,'source_mapping':sources,'boundary_loops':loops,'footprint_geojson':mapping(u),'verification':report}),encoding='utf8');(OUT/'joined_walls_verification.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report,indent=2))

