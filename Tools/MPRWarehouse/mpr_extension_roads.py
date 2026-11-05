"""Additive MPR road transition geometry, with an immutable completed interior.

XY is CAD metres. This module never imports bpy/unreal or writes assets. Explicit
street correspondences were reviewed against the registered Topoexport axes;
they are deliberately not a nearest-road assignment. Cropped mouths can share
one source street. Only outer roads with no forward source corridor retain fade.
"""
import json,math
from pathlib import Path
import numpy as np
from shapely.geometry import Polygon,LineString,Point,GeometryCollection,mapping
from shapely.ops import unary_union,substring
import mpr_plan_site as plan

ROOT=Path(__file__).resolve().parents[2]
SOURCE_SHA256='9caf3439299f1b4f38d8ee88b6a5877e9a92c213ae926c99b40c5302583718d1'

# (source street handle, reviewed target vicinity, through/junction, evidence)
# IDs are the unchanged deterministic ordering of plan._road_outlets().
STREET_CORRESPONDENCES={
 0:('CC0',(-490,-375),'through','southwest cropped street continuing through bottom mouth 14; skirt preserved corner house'),
 1:('CF3',(-482,-229),'junction','short cropped mouth entering the same residential street as 02'),
 2:('CF3',(-493,-244),'through','southwest residential street continuation'),
 3:('CF3',(-482,-229),'junction','narrow cropped mouth entering the CF3 residential street'),
 4:('CE4',(-485,-116),'through','northwest residential cross street'),
 5:('D2D',(-507,-130),'through','southwest residential street next to CE4 junction'),
 6:('50F',(-515,-87),'junction','8FB access connects to the 50F cross street at its source junction'),
 7:('88F',(-493,138),'through','northwest cross street continuous with 4EE'),
 8:('8BD',(-493,156),'through','southwest residential street'),
 9:('4C7',(-503,276),'junction','cropped mouth reaches 494/4C7 source junction via its south approach'),
10:('4C7',(-505,272),'through','southwest street continuous with 4DC'),
14:('CC0',(-465,-340),'through','southwest street aligned to bottom edge crop'),
15:('D3B',(-383,-357),'junction','cropped cross street enters next source residential street'),
16:('D3B',(-371,-341),'through','southwest street, distinct from nearest CC0'),
17:('CCA',(-297,-378),'through','southwest street downstream of C3A junction'),
18:('C3A',(-269,-340),'through','main north-south road; CB1 and CA2 are adjacent parking accesses'),
19:('C08',(75,-331),'through','southwest road parallel to preserved railway'),
20:('DA0',(183,-344),'through','southwest industrial cross street'),
21:('DA0',(212,-327),'junction','cropped industrial access enters DA0; do not turn into AA4 parking'),
22:('725',(-405,411),'through','first northbound residential street; 551 is an unrelated western block'),
23:('719',(-331,385),'through','second northbound residential street'),
24:('735',(-244,411),'through','continuous main northbound road; 798 is an isolated industrial access stub'),
25:('5D4',(-91,448),'junction','north industrial access reaches its source south parking edge'),
26:('B27',(367,412),'through','east-side industrial access; nearest 9A5 runs inside frozen area'),
27:('B19',(402,399),'through','west-side source access connects onward to B27; A50 conflicts with preserved rail extension'),
28:('A84',(622,365),'through','through road east of the railway corridor'),
}
OUTER_TERMINALS={11:'original exit is outside the new project frame',
                 12:'original exit is outside the new project frame',
                 13:'east-facing outer exit has no forward source road; A84 lies behind it'}

def _read(path):return json.loads((ROOT/path).read_text(encoding='utf8'))
def _union(rows):return unary_union(rows)if rows else GeometryCollection()
def _parts(g):return list(g.geoms)if hasattr(g,'geoms')else[g]
def _xy(points,transform):
 return np.asarray(points,dtype=float)[:,:2]*float(transform['scale'])@np.asarray(transform['rotation_row_matrix'])+np.asarray(transform['offset_xy_m'])
def _mesh_polygon(o,transform):
 v=_xy(o['vertices'],transform);parts=[]
 for face in o['faces']:
  if len(face)<3:continue
  p=Polygon(v[face])
  if p.area>1e-5:parts.append(p if p.is_valid else p.buffer(0))
 return _union(parts)

def _existing_protection():
 cad=_read('SourceAssets/MPR/mpr_cad_layout.json');context=_read('SourceAssets/MPR/reference_v4/context/manifest.json')
 buildings=_union([Polygon(cad['footprint_outline_m']),*[Polygon(p)for p in context['footprints_m']]])
 manifest=_read('SourceAssets/MPR/reference_v4/site/manifest.json')
 trees=_union([Point(r['position_m'][:2]).buffer(r['crown_radius_m'],quad_segs=12)for r in manifest['planting']['tree_positions']])
 from mpr_plan_layout import world_to_plan
 rails=[]
 for row in plan.read('plan_railway_v5.json')['tracks']:
  pts=plan.xy(row['path_px']);result=list(pts)
  for i,j,first in [(0,1,True),(-1,-2,False)]:
   p=np.array(pts[i]);q=np.array(pts[j]);pixel=world_to_plan(p)
   if pixel[1]<1 or pixel[1]>908:
    v=(p-q)/np.linalg.norm(p-q);end=(p+v*160).tolist()
    if first:result.insert(0,end)
    else:result.append(end)
  rails.append(LineString(result).buffer(3.5,quad_segs=12))
 return buildings,trees,_union(rails)

def _bezier(p,q,direction,tangent,start_length,end_length):
 controls=[p,p+direction*start_length,q-tangent*end_length,q]
 length=math.dist(p,q);n=max(48,int(length/.65))
 return np.asarray([(1-t)**3*controls[0]+3*(1-t)**2*t*controls[1]+3*(1-t)*t*t*controls[2]+t**3*controls[3]for t in np.linspace(0,1,n+1)])

def _ribbon(points,start_width,end_width):
 # Low-frequency width change; no texture alpha/dither at the interface.
 deltas=np.gradient(points,axis=0);deltas/=np.linalg.norm(deltas,axis=1)[:,None]
 normals=np.column_stack([-deltas[:,1],deltas[:,0]])
 t=np.linspace(0,1,len(points));t=t*t*(3-2*t)
 half=(start_width+(end_width-start_width)*t)*.5
 left=points+normals*half[:,None];right=points-normals*half[:,None]
 p=Polygon(np.vstack([left,right[::-1]]))
 return p if p.is_valid else None

def _connection(row,line,hint,kind,native,oldframe,hard):
 origin=np.asarray(row['origin_m']);direction=np.asarray(row['direction']);station=line.project(Point(hint));choices=[]
 for delta in [0,-6,6,-12,12,-24,24,-40,40,-65,65]:
  at=max(0,min(line.length,station+delta));q=np.array(line.interpolate(at).coords[0]);distance=np.linalg.norm(q-origin)
  if distance<2 or oldframe.distance(Point(q))<2:continue
  tangent=np.array(line.interpolate(min(line.length,at+2)).coords[0])-np.array(line.interpolate(max(0,at-2)).coords[0]);tangent/=np.linalg.norm(tangent)
  if tangent@(q-origin)<0:tangent=-tangent
  if kind=='junction':tangent=(q-origin)/distance
  width=max(3.,min(18.,2*Point(q).distance(native.boundary)))
  for start in sorted(set([5.,10.,18.,min(32.,distance*.35)])):
   for end in [max(4.,distance*.22),max(6.,distance*.4)]:
    pts=_bezier(origin,q,direction,tangent,start,end);center=LineString(pts)
    if not center.is_simple or center.intersection(oldframe.buffer(-.02)).length>4.5:continue
    ribbon=_ribbon(pts,row['width_m'],width)
    if ribbon is None:continue
    # Source mouth is exact; changing an oblique strip to a perpendicular cap
    # would leave thin triangular holes at the old raster border.
    mouth=Polygon([*row['section_m'],*(pts[min(7,len(pts)-1)]+np.array([-direction[1],direction[0]])*s*row['width_m']*.5 for s in [-1,1])]).convex_hull
    surface=ribbon.union(mouth).difference(oldframe)
    overlap=surface.intersection(hard).area
    if overlap>1e-5:continue
    if surface.intersection(native.buffer(.1)).area<.05:continue
    curves=np.diff(np.unwrap(np.arctan2(np.diff(pts,axis=0)[:,1],np.diff(pts,axis=0)[:,0])))
    score=abs(delta)*.25+center.length+max(abs(curves),default=0)*100
    choices.append((score,surface,center,q,at,width))
 if not choices and row['id']=='SourceTerminal_00':
  # The cropped southwest mouth is only 3.1m wide. A preserved house straddles
  # the adjacent frame corner, so a direct Bezier would cross that house.
  # These are controls for this one source-street continuation, not collectors.
  for x in [-491.,-500.,-510.,-520.]:
   for y in [-282.,-290.,-300.]:
    q=np.array(line.interpolate(station).coords[0]);dist=np.linalg.norm(q-origin)
    endtan=np.array(line.interpolate(min(line.length,station+2)).coords[0])-np.array(line.interpolate(max(0,station-2)).coords[0]);endtan/=np.linalg.norm(endtan)
    if endtan@(q-origin)<0:endtan=-endtan
    controls=[origin,np.array([x,y]),np.array([x-3,-329.]),q]
    tangents=[direction,*[(controls[j+1]-controls[j-1])/np.linalg.norm(controls[j+1]-controls[j-1])for j in [1,2]],endtan]
    pts=np.vstack([_bezier(a,b,tangents[j],tangents[j+1],math.dist(a,b)*.25,math.dist(a,b)*.25)[:-1]for j,(a,b)in enumerate(zip(controls,controls[1:]))]+[q[None,:]])
    center=LineString(pts);width=max(3.,min(18.,2*Point(q).distance(native.boundary)));ribbon=_ribbon(pts,row['width_m'],width)
    if ribbon is None or not center.is_simple or center.intersection(oldframe.buffer(-.02)).length>4.5:continue
    mouth=Polygon([*row['section_m'],*(pts[7]+np.array([-direction[1],direction[0]])*s*row['width_m']*.5 for s in [-1,1])]).convex_hull
    surface=ribbon.union(mouth).difference(oldframe)
    if surface.intersection(hard).area>1e-5 or surface.intersection(native.buffer(.1)).area<.05:continue
    choices.append((center.length,surface,center,q,station,width))
 if not choices:return None
 _,surface,center,q,at,width=min(choices,key=lambda a:a[0])
 return dict(surface=surface,center=center,target=q.tolist(),source_station_m=at,target_width_m=width)

def _trim_boundary_branches(axes,connections,frame,widths):
 """Remove source crop stubs back to real junctions or an explicit new join.

 Nothing is faded or capped at an arbitrary internal seam. Source cul-de-sacs
 which never touch the frozen frame remain source features, not crop artifacts.
 """
 import shapely
 kept=[];removed=[];records=[]
 targets={name:[Point(c['target_m'])for c in connections if c.get('source_axis')==name]for name in axes}
 for name,line in axes.items():
  others=_union([other for othername,other in axes.items()if othername!=name and line.distance(other)<.01])
  junctions=[Point(p)for p in shapely.get_coordinates(line.intersection(others))if not frame.covers(Point(p))]
  for part in _parts(line.difference(frame)):
   if part.geom_type!='LineString' or part.length<.001:continue
   start,end=0.,part.length;trim_rows=[]
   for which,endpoint in [('start',Point(part.coords[0])),('end',Point(part.coords[-1]))]:
    if endpoint.distance(frame.boundary)>.03:continue
    candidates=[]
    for kind,points in [('connection_target',targets[name]),('source_junction',junctions)]:
     for point in points:
      if point.distance(part)>.03:continue
      station=part.project(point);distance=station if which=='start'else part.length-station
      if distance>.5:candidates.append((distance,station,kind,list(point.coords[0])))
    if candidates:
     distance,station,kind,point=min(candidates,key=lambda r:r[0])
     if which=='start':start=max(start,station)
     else:end=min(end,station)
     trim_rows.append(dict(edge=which,length_m=distance,termination=kind,target_m=point))
    else:
     if which=='start':start=part.length
     else:end=0.
     trim_rows.append(dict(edge=which,length_m=part.length,termination='remove_unmatched_crop_branch_without_external_junction'))
   if start>0:removed.append(substring(part,0,min(start,part.length)).buffer(widths[name]*.5+.5,cap_style=2))
   if end<part.length:removed.append(substring(part,max(0,end),part.length).buffer(widths[name]*.5+.5,cap_style=2))
   if end-start>.1:kept.append(substring(part,start,end).buffer(widths[name]*.5,cap_style=2,quad_segs=16))
   if trim_rows:records.append(dict(source_axis=name,source_fragment_length_m=part.length,kept_length_m=max(0,end-start),trims=trim_rows))
 return _union(kept),_union(removed).difference(frame),records

def build_extension_roads(source_geometry,transform,existing_buildings=None,
                          existing_tree_clearance=None,new_buildings=None):
 """Return pure Shapely surfaces and explicit, serializable transition audit.

 Native source geometry and old source surfaces remain read-only. The returned
 replacement terminal surfaces are newly owned mesh geometry; old packages are
 not rewritten. Caller must reject audit.unresolved before scene publication.
 """
 if source_geometry.get('sha256')!=SOURCE_SHA256:
  raise ValueError('Source blend changed: review street correspondences before generating transitions')
 default_buildings,default_trees,rail=_existing_protection()
 buildings=default_buildings if existing_buildings is None else existing_buildings
 trees=default_trees if existing_tree_clearance is None else existing_tree_clearance
 frame=plan.pixel_box(-.5,-.5,1727.5,909.5);raw=plan.road_geometry()
 oldroads,terminals=plan.extend_road_tails(raw,blockers=buildings)
 axes={};native_parts=[];frames=[]
 for o in source_geometry['objects']:
  if o['layer']=='TPX_ROADS_AXES':
   for i,spline in enumerate(o['splines']):
    if len(spline['points'])>1:axes[o['name']]=LineString(_xy(spline['points'],transform))
  elif o['layer']=='TPX_ROADS_HATCH':native_parts.append(_mesh_polygon(o,transform))
  elif o['layer']=='TPX_FRAME_PROJECT':
   frames.extend([Polygon(_xy(s['points'],transform))for s in o['splines']if len(s['points'])>2])
 sourceframe=_union(frames)
 # Topoexport road hatches are display ribbons, often just 2-3m across. Keep
 # their surveyed axes but make actual context streets usable at scene scale.
 # Width is inherited from a matching old street where one exists.
 widths={name:(3.5 if line.length<35 else 6.5)for name,line in axes.items()}
 for i,(handle,hint,kind,evidence)in STREET_CORRESPONDENCES.items():
  name='TPX_ROADS_AXES_'+handle;widths[name]=max(widths[name],min(12.,terminals[i]['width_m']))
 native=_union([*native_parts,*[line.buffer(widths[name]*.5,cap_style=2,quad_segs=16)for name,line in axes.items()]]).intersection(sourceframe)
 # Tree crowns already over existing road do not become a reason to edit trees
 # or erase the existing road mouth. All new added pavement clears the rest.
 hard=_union([buildings.buffer(.35),trees.difference(oldroads.buffer(.4)),rail])
 protected=_union([frame,buildings,trees,rail])
 surfaces=[];centerlines=[];connections=[];unresolved=[];preserved=[];stitches=[];stitch_audit=[]
 for i,row in enumerate(terminals):
  identity=row['id']
  if i in OUTER_TERMINALS:
   surface=plan.terminal_shape(row).difference(frame);surfaces.append(surface);preserved.append(row)
   connections.append(dict(id=identity,status='preserved_outer_terminal',reason=OUTER_TERMINALS[i],origin_m=row['origin_m'],end_m=row['end_m'],fade_allowed=True))
   continue
  handle,hint,kind,evidence=STREET_CORRESPONDENCES[i];source_id='TPX_ROADS_AXES_'+handle
  line=axes[source_id];result=_connection(row,line,hint,kind,native,frame,hard)
  if result is None:
   unresolved.append(dict(id=identity,source_axis=source_id,reason='no obstacle-free source-corresponding transition outside frozen frame'))
   continue
  # Explicit road-mouth exception authorized for the transition band: close
  # centimetre-scale raster/crop discrepancies up to 12cm inside the frame,
  # terminating at the real immutable road boundary. Never cover old asphalt.
  surface=result['surface'];mouth_front=surface.intersection(frame.boundary)
  local=Point(row['origin_m']).buffer(max(3.,row['width_m']))
  gap_before=raw.intersection(local).distance(surface.intersection(local))
  contact_before=surface.boundary.intersection(raw.buffer(.0001)).intersection(local).length
  if gap_before>.0001 or contact_before<.1:
   zone=mouth_front.buffer(.12,cap_style=2,quad_segs=12)
   patch=surface.buffer(.120001,quad_segs=12).intersection(raw.buffer(.120001,quad_segs=12)).intersection(zone).intersection(frame).difference(raw).difference(hard)
   patch=_union([p for p in _parts(patch)if p.area>1e-12 and p.distance(surface)<1e-7 and p.distance(raw)<1e-7])
   if not patch.is_empty:
    import shapely
    depth=max((Point(p).distance(frame.boundary)for p in shapely.get_coordinates(patch)),default=0.)
    assert depth<=.120001 and patch.intersection(raw).area<1e-8
    result['surface']=surface.union(patch);stitches.append(patch)
    stitch_audit.append(dict(id=identity,geometry=mapping(patch),area_m2=patch.area,max_in_frame_m=depth,gap_before_m=gap_before,
       gap_after_m=raw.intersection(local).distance(result['surface'].intersection(local))))
  surfaces.append(result['surface']);centerlines.append(result['center'])
  connections.append(dict(id=identity,status='connected',source_axis=source_id,evidence=evidence,kind=kind,
      origin_m=row['origin_m'],target_m=result['target'],path_m=[list(p)for p in result['center'].coords],
      source_station_m=result['source_station_m'],source_width_m=result['target_width_m'],start_width_m=row['width_m'],fade_allowed=False))
 replacement=_union(surfaces)
 mouth_stitches=_union(stitches)
 kept_native,removed_crop_stubs,branch_audit=_trim_boundary_branches(axes,connections,frame,widths)
 native=_union([native.difference(removed_crop_stubs),kept_native]).intersection(sourceframe)
 # Extra source buildings may be omitted by caller; immutable old content is
 # never displaced to make a new source road fit.
 native=native.difference(frame).difference(hard)
 tiny=[p for p in _parts(native)if p.area<3.]
 native=_union([p for p in _parts(native)if p.area>=3.])
 extension=native.difference(replacement)
 allroads=_union([raw,replacement,extension])
 added=replacement.union(extension)
 curb=allroads.buffer(.28,quad_segs=12).difference(allroads).difference(hard).difference(frame)
 white=allroads.buffer(-.55,quad_segs=12).boundary.buffer(.075,quad_segs=8).intersection(added)
 repl_support=replacement.buffer(.5)
 dashed=[]
 for center in centerlines:
  for station in np.arange(0,center.length,9.5):
   a=center.interpolate(station);b=center.interpolate(min(station+3.,center.length))
   if a.distance(b)>.2:dashed.append(LineString([a,b]).buffer(.08,cap_style=2))
 dash=_union(dashed).intersection(added.buffer(-1.4))
 exclusions=[]
 for b in new_buildings or []:
  geometry=b.get('geometry')
  if geometry is not None and geometry.intersects(added.buffer(.75)):exclusions.append(b['name'])
 crossing=[]
 connected=[c for c in connections if c['status']=='connected']
 for a_i,a in enumerate(connected):
  for b in connected[a_i+1:]:
   hit=LineString(a['path_m']).intersection(LineString(b['path_m']))
   if not hit.is_empty and a['source_axis']!=b['source_axis']:
    crossing.append(dict(ids=[a['id'],b['id']],geometry=hit.wkt))
 audit=dict(policy='explicit source streets; opaque joined interface; no new collector loops',source_sha256=SOURCE_SHA256,
     outlet_count=len(terminals),connected_count=len(connected),preserved_outer_count=len(preserved),
     unresolved=unresolved,transition_crossings=crossing,old_frame_overlap_m2=added.intersection(frame).difference(mouth_stitches).area,
     authorized_mouth_stitch_overlap_m2=added.intersection(frame).area,mouth_stitches=stitch_audit,
     fixed_building_overlap_m2=added.intersection(buildings).area,fixed_rail_overlap_m2=added.intersection(rail).area,
     fixed_tree_overlap_m2=added.intersection(trees.difference(oldroads.buffer(.4))).area,
     extension_road_area_m2=extension.area,replacement_terminal_area_m2=replacement.area,
     source_boundary_branch_treatments=branch_audit,
     removed_clipping_slivers=dict(count=len(tiny),area_m2=sum(p.area for p in tiny)),
     all_surfaces_valid=all(g.is_valid for g in [extension,replacement,curb,white,dash]))
 return dict(extension_roads=extension,replacement_terminal_roads=replacement,
     replacement_terminal_curbs=curb.intersection(repl_support),replacement_terminal_white_edges=white.intersection(repl_support),
     white_edges=white.difference(repl_support),curbs=curb.difference(repl_support),dash_lines=dash,
     replacement_terminal_footprints=replacement,connections=connections,
     source_axes=[dict(id=name,points_m=[list(p)for p in line.coords])for name,line in axes.items()],
     new_building_exclusions=exclusions,audit=audit,fade_terminals=preserved,
     mouth_stitches=mouth_stitches,protected_geometry=protected,frame_new=sourceframe,frame_old=frame,existing_rail_protection=rail)
