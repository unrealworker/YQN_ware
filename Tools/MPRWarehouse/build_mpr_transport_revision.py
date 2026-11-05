"""Narrow 2026-11-05 MPR transport revision; standalone Python 3.13 only.

Reads the committed B50B57 scene sources and produces a separate patch payload.
It never rewrites the base scene, instances, source FBXs or UE packages.
"""
from pathlib import Path
import copy,gzip,hashlib,json,math,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'Tools/MPRWarehouse'),str(ROOT/'Saved/ParkRefinement/python_deps')]
import numpy as np
import shapely
from shapely.geometry import shape,mapping,LineString,Point,Polygon,GeometryCollection,box
from shapely.ops import unary_union,substring
from run_mpr_rebuild_geometry import load_geometry_builder
import validate_mpr_rebuild_surface_clearance as reader

SRC=ROOT/'SourceAssets/MPR/rebuild_b50b57'
OUT=ROOT/'Saved/MPR/cleanup_20261105/transport'
REMOVED={'TPX_RAILWAYS_AXES_E6F','TPX_RAILWAYS_AXES_E9C'}
PREFIXES=('SM_MPRR_Rail_','SM_MPRR_RailCorridor_','SM_MPRR_CrossingDeck_',
          'SM_MPRR_CrossingRamp_','SM_MPRR_Roads_','SM_MPRR_Curblines_',
          'SM_MPRR_WhiteEdges_','SM_MPRR_RoadDashes_')

def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8')
def decode(x):
    if isinstance(x,dict):
        if x.get('type') in {'Polygon','MultiPolygon','LineString','MultiLineString','GeometryCollection'}:return shape(x)
        return {k:decode(v) for k,v in x.items()}
    if isinstance(x,list):return [decode(v)for v in x]
    return x
def encode(x):
    if hasattr(x,'geom_type'):return mapping(x)
    if isinstance(x,dict):return {k:encode(v)for k,v in x.items()}
    if isinstance(x,list):return [encode(v)for v in x]
    return x
def polygons(g):
    if g.is_empty:return []
    if g.geom_type=='Polygon':return [g]
    return [p for c in getattr(g,'geoms',[])for p in polygons(c)]
def topological_signature(g):return [len(polygons(g)),sum(len(p.interiors)for p in polygons(g))]

def geometry_intersects_impact(roles, old_row, impact):
    """Include vanished parts: a rebuilt mesh's smaller bounds are insufficient."""
    points=np.asarray([v for vv,ff in roles.values() for v in vv])
    bounds=[]
    if len(points):
        bounds.append(box(points[:,0].min(),points[:,1].min(),points[:,0].max(),points[:,1].max()))
    if old_row is not None:
        old=old_row['bounds_m']
        bounds.append(box(old[0][0],old[1][0],old[0][1],old[1][1]))
    return any(region.intersects(impact) for region in bounds)

def curve(points,trim=5.):
    """Quadratic corner rounding without overshoot, exact chain endpoints."""
    points=[np.array(p[:2],float)for p in points];out=[points[0].tolist()]
    for a,b,c in zip(points,points[1:],points[2:]):
        la=np.linalg.norm(a-b);lc=np.linalg.norm(c-b)
        if min(la,lc)<1e-5:continue
        ta=min(trim,la*.42,lc*.42)
        p=b+(a-b)*ta/la;q=b+(c-b)*ta/lc
        out.extend([((1-t)**2*p+2*t*(1-t)*b+t*t*q).tolist()for t in np.linspace(0,1,17)])
    out.append(points[-1].tolist())
    return LineString(out)

def road_revision(layout):
    roads=layout['road_centerlines'];by={r['id'].split('_')[-1]:r for r in roads}
    for name in ['C27','CA8']:by[name]['width_m']=6.5;by[name]['road_class']='residential'
    # Two linked access segments form one continuous driveway, not two capped
    # ribbons with a sharp width step. Its actual source dead end remains open.
    chain=LineString([*by['CA8']['points_m'],*by['CB1']['points_m'][1:]])
    clean=LineString(chain.simplify(.55,preserve_topology=True).coords)
    smooth=curve(list(clean.coords),4.5)
    split=smooth.project(Point(by['CA8']['points_m'][-1][:2]))
    for name,line in [('CA8',substring(smooth,0,split)),('CB1',substring(smooth,split,smooth.length))]:
        by[name]['points_m']=[[*p,chain.interpolate(chain.project(Point(p))).z]for p in line.coords]
        by[name]['length_m']=line.length;by[name]['revision']='Continuous 6.5m driveway, local quadratic rounding'
    mask=unary_union([chain.buffer(12,quad_segs=24),LineString(by['C27']['points_m']).buffer(13,quad_segs=24)])
    rebuilt=unary_union([LineString(r['points_m']).buffer(r['width_m']/2,cap_style=2,join_style=1,quad_segs=32)for r in roads])
    # Source hatch union was preserving sub-metre cartographic teeth. In this
    # reviewed patch use the actual carriageway union and round inward corners.
    rounded=rebuilt.buffer(1.5,quad_segs=32).buffer(-3.,quad_segs=32).buffer(1.5,quad_segs=32)
    original=layout['roads']
    safe=rounded.difference(layout['building_protection']).intersection(layout['frame'])
    # The footprint safety cut itself can introduce sharp steps. A local
    # morphological opening rounds those toward the road interior, therefore
    # it cannot add pavement onto a protected building footprint.
    safe=safe.buffer(-1.2,quad_segs=32).buffer(1.2,quad_segs=32)
    paved=original.difference(mask).union(safe.intersection(mask)).difference(layout['building_protection']).intersection(layout['frame'])
    assert paved.is_valid
    # Exact road endpoints and unrelated roadway outside the mask stay fixed.
    assert original.symmetric_difference(paved).difference(mask.buffer(.00001)).area<1e-6
    assert len(polygons(paved))==len(polygons(original)),('Unexpected road component change',topological_signature(original),topological_signature(paved))
    for r in roads:
        for p in (r['source_points_m'][0],r['source_points_m'][-1]):
            point=Point(p[:2])
            assert paved.distance(point)<=original.distance(point)+.03,(r['id'],'Source road endpoint disconnected',paved.distance(point),original.distance(point))
    layout['roads']=paved
    # Recompute every outline from the unified surface: no seam across the
    # patched boundary and no overlapping transverse lines at the T junctions.
    layout['curbs']=paved.buffer(.24,quad_segs=12).difference(paved).intersection(layout['frame']).difference(layout['building_protection'])
    layout['white_edges']=paved.buffer(-.42,quad_segs=12).boundary.buffer(.06,quad_segs=6).intersection(paved)
    dashes=[]
    for r in roads:
        if r['width_m']<6:continue
        line=LineString(r['points_m'])
        for start in np.arange(2,line.length,10):dashes.append(substring(line,start,min(start+3,line.length)).buffer(.065,cap_style=2))
    layout['dash_lines']=unary_union(dashes).intersection(paved.buffer(-1.4))
    return dict(mask=mapping(mask),road_surface_change_m2=original.symmetric_difference(paved).area,
        old_topology=topological_signature(original),new_topology=topological_signature(paved),
        source_road_endpoints_remain_covered=True,unrelated_surface_exact=True,widths_changed=['C27','CA8'],
        continuous_driveway=['CA8','CB1'],device_or_building_changes=False)

def ground(builder,manifest):
    vv=[];ff=[];polys=[]
    for row in manifest['meshes']:
        if not row['name'].startswith('SM_MPRR_Terrain_'):continue
        triangles,_=reader.mesh_data(row)
        for triangle in triangles:
            off=len(vv);vv.extend(triangle.tolist());ids=[off,off+1,off+2]
            ff.append(ids);poly=Polygon(triangle[:,:2])
            if poly.area>1e-9:polys.append(poly)
    sampler=builder.TriangleHeights(vv,ff);builder.GROUND_TRIANGLES=polys;builder.GROUND_INDEX=shapely.STRtree(polys)
    def height(x,y):
        z=sampler.at(x,y)
        return builder.G if z is None else z
    return height

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    manifest=read(SRC/'manifest.json');original=read(SRC/'layout.json');layout=decode(original)
    initial_hashes={name:sha(SRC/name)for name in ['manifest.json','layout.json','scene_ownership.json','MPR_B50B57_Rebuild.blend']}
    b=load_geometry_builder();height=ground(b,manifest)
    road_audit=road_revision(layout)
    old_rails=layout['rail_centerlines'];layout['rail_centerlines']=[r for r in old_rails if r['id'] not in REMOVED]
    assert len(old_rails)-len(layout['rail_centerlines'])==2
    remaining_crossings=[]
    for entry in layout['crossings']:
        entry['rail_ids']=[identity for identity in entry['rail_ids']if identity not in REMOVED]
        if entry['rail_ids']:remaining_crossings.append(entry)
    layout['crossings']=remaining_crossings
    kept=[LineString(r['points_m'])for r in layout['rail_centerlines']]
    main=Polygon(read(ROOT/'SourceAssets/MPR/mpr_cad_layout.json')['footprint_outline_m'])
    corridor=unary_union([line.buffer(3,cap_style=2,quad_segs=12)for line in kept]).buffer(1.1,quad_segs=12).buffer(-1.1,quad_segs=12).intersection(layout['frame']).difference(main.buffer(.5))
    layout['rail_corridor']=corridor
    layout['audit'].update(source_rail_axis_count=len(kept),unique_rail_road_crossings=len(remaining_crossings),
        rail_corridor_area_m2=corridor.area,roads_area_m2=layout['roads'].area,
        transport_revision='2026-11-05 reviewed branch removal, uniform sparse sleepers and two local road junctions')
    # One spacing and one physical profile everywhere; the old 300m hard switch
    # was the visible dense/sparse diagonal, not a runtime LOD decision.
    b.rail_detail.NEAR_SLEEPER_SPACING_M=2.25;b.rail_detail.FAR_SLEEPER_SPACING_M=2.25
    b.rail_detail.NEAR_DISTANCE_M=1e9;b.rail_detail.HEAD_WIDTH_M=.09
    b.rail_detail.RAIL_OFFSET_M=(b.rail_detail.GAUGE_M+.09)/2
    def sink(name,role,verts,faces):
        if name.endswith('_RailBed'):return
        b.GEO.mesh(name.replace('SM_MPR_Env_','SM_MPRR_Rail_'),'MPR3_'+role,
            [(x,y,z+height(x,y)-b.G)for x,y,z in verts],faces)
    tracks=[dict(id=r['id'],layer='railways',vertices=list(shapely.segmentize(LineString(r['points_m']),4.).coords))for r in layout['rail_centerlines']]
    rails=b.build_railways(dict(mesh=sink,zone=lambda x,y:f'{math.floor(x/b.TILE)}_{math.floor(y/b.TILE)}',regions={},include_freight=False),tracks,b.G)
    # A single continuous bedding surface conforms to the committed terrain
    # triangles. No old independent broad RailBed triangles survive to intersect.
    b.surface('SM_MPRR_RailCorridor','MPR3_Ballast',corridor,lambda x,y:height(x,y)+.18,step=3)
    deck=unary_union([line.buffer(1.7,cap_style=2)for line in kept]).intersection(layout['roads'])
    ramps=deck.buffer(2.4,quad_segs=8).difference(deck).intersection(layout['roads'])
    b.surface('SM_MPRR_CrossingDeck','MPR3_Concrete',deck,lambda x,y:height(x,y)+.375,step=.65)
    b.surface('SM_MPRR_CrossingRamp','MPR3_Asphalt',ramps,lambda x,y:height(x,y)+.08+.295*(1-min(1,Point(x,y).distance(deck)/2.4)),step=.65)
    mask=deck.union(ramps)
    for name,role,g,offset in [
        ('Roads','MPR4_TerminalAsphalt',layout['roads'].difference(mask),.08),
        ('Curblines','MPR4_TerminalCurb',layout['curbs'],.20),
        ('WhiteEdges','MPR4_TerminalWhiteLine',layout['white_edges'].difference(mask),.105),
        ('RoadDashes','MPR4_TerminalWhiteLine',layout['dash_lines'].difference(mask),.107)]:
        b.surface('SM_MPRR_'+name,role,g,lambda x,y,d=offset:height(x,y)+d)
    old_rows={r['name']:r for r in manifest['meshes']if r['name'].startswith(PREFIXES)}
    assert all(n.startswith(PREFIXES)for n in b.GEO.data)
    removed=sorted(set(old_rows)-set(b.GEO.data));added=sorted(set(b.GEO.data)-set(old_rows))
    # Keep pre-existing FBXs for every unrelated pavement tile. Rail geometry
    # is intentionally updated everywhere to remove the old density boundary.
    impact=unary_union([shape(road_audit['mask']).buffer(1.5),*[LineString(r['points_m']).buffer(7.)for r in old_rails if r['id']in REMOVED]])
    full_geometry=b.GEO.data;selected={};unchanged=[]
    for name,roles in full_geometry.items():
        if name.startswith(('SM_MPRR_Rail_','SM_MPRR_RailCorridor_'))or geometry_intersects_impact(roles,old_rows.get(name),impact):selected[name]=roles
        else:unchanged.append(name)
    audit=dict(success=True,source_hashes=initial_hashes,removed_rail_ids=sorted(REMOVED),
        retained_rail_ids=[r['id']for r in layout['rail_centerlines']],road=road_audit,
        sleepers_spacing_m=2.25,uniform_sleeper_profile=True,rail_stats=rails['stats'],
        ballast_method='One continuous surface on committed terrain triangle planes, clearance 0.18m',
        mesh_names=sorted(selected),remove_mesh_names=removed,new_mesh_names=added,
        unchanged_transport_mesh_names=sorted(unchanged),pavement_tile_impact=mapping(impact),
        preserved_instances=True,preserved_all_nontransport_meshes=True,
        source_triangles=sum(sum(len(f)-2 for f in faces)for groups in selected.values()for verts,faces in groups.values()))
    textures={v['texture']:v['textures']for v in manifest['materials'].values()if v.get('texture')}
    payload=dict(geometry=selected,instances={},materials=manifest['materials'],textures=textures,
        frame=original['frame'],counts={},input_hashes={},audit=audit,
        metadata=dict(rebuild_namespace='/Game/MPRWarehouse/RebuildB50B57',map='/Game/Maps/MPR_CAD_Warehouse_B50B57',transport_revision=True))
    with gzip.open(OUT/'geometry_payload.json.gz','wt',encoding='utf8')as f:json.dump(payload,f,separators=(',',':'))
    write(OUT/'layout.json',encode(layout));write(OUT/'geometry_audit.json',audit)
    assert initial_hashes=={name:sha(SRC/name)for name in initial_hashes}
    print('TRANSPORT_PATCH_READY',len(selected),audit['source_triangles'],len(removed),len(added),'preserved transport tiles',len(unchanged))

if __name__=='__main__':main()
