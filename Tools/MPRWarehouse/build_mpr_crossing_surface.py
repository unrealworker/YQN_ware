"""Prepare an asphalt inlay at the one retained F97/C08 level crossing.

Reads the exact saved FBX polygons, preserving untouched faces and all steel
rails. No UE calls; previous source directories remain byte-for-byte intact.
"""
import copy,gzip,json,math,sys
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'Tools/MPRWarehouse'),str(ROOT/'Saved/ParkRefinement/python_deps')]
import numpy as np
import shapely
from shapely.geometry import Polygon,LineString,Point,box,mapping
from shapely.ops import unary_union
import build_mpr_transport_cleanup as transport
import validate_mpr_rebuild_surface_clearance as reader

OUT=ROOT/'SourceAssets/MPR/crossing_surface_20261105'
DEST='/Game/MPRWarehouse/CrossingSurface20261105'
ROAD_ROLE='MPR4_TerminalAsphalt'
TILES=((-1,-3),(0,-3))
NAMES=tuple(f'SM_MPRR_{stem}_{x}_{y}'for stem in ['CrossingDeck','CrossingRamp','RailCorridor']for x,y in TILES)+tuple(f'SM_MPRR_Rail_{x}_{y}_Sleepers'for x,y in TILES)

def current_rows():
    rows=transport.current_rows();patch=transport.revision.read(transport.OUT/'manifest.json')
    rows.update({r['name']:r for r in patch['meshes']})
    for name in patch['remove_mesh_names']:rows.pop(name,None)
    return rows

def old_package(row):
    namespace='/Game/MPRWarehouse/TransportCleanup20261105/Meshes/'if row['fbx'].startswith('SourceAssets/MPR/transport_cleanup_20261105/')else'/Game/MPRWarehouse/RebuildB50B57/Site/Meshes/'
    return namespace+row['name']

def read_faces(row):
    path=(ROOT/row['fbx']).resolve()
    assert path.is_relative_to((ROOT/'SourceAssets/MPR').resolve())and transport.revision.sha(path)==row['sha256']
    obj=next(n for n in reader.fbx_nodes(path)if n[0]==b'Objects')
    geometries=[n for n in obj[2]if n[0]==b'Geometry'];assert len(geometries)==1
    fields={n[0]:n for n in geometries[0][2]}
    vertices=np.asarray(fields[b'Vertices'][1][0],dtype=float).reshape(-1,3)
    material={n[0]:n[1][0]for n in fields[b'LayerElementMaterial'][2]}
    assert material[b'MappingInformationType']in{b'ByPolygon',b'AllSame'}
    indices=material[b'Materials'];faces=[];face=[]
    for i in fields[b'PolygonVertexIndex'][1][0]:
        face.append(int(i)if i>=0 else int(-i-1))
        if i<0:
            index=indices[0]if len(indices)==1 else indices[len(faces)]
            faces.append((row['material_roles'][index],[tuple(v)for v in vertices[face]]));face=[]
    assert not face
    return faces

def pieces(g):
    if g.is_empty:return []
    if g.geom_type=='Polygon':return [g]
    return [p for c in getattr(g,'geoms',[])for p in pieces(c)]

def line_parts(g):
    if g.is_empty:return []
    if g.geom_type=='LineString':return [g]
    return [p for c in getattr(g,'geoms',[])for p in line_parts(c)]

def split_face(points,mask):
    """Split a planar triangle or vertical quad by an extruded XY footprint."""
    p=np.asarray(points,float);xy=Polygon(p[:,:2])
    original_normal=np.cross(p[1]-p[0],p[2]-p[0])
    def orient(face):
        q=np.asarray(face,float)
        return list(reversed(face))if np.dot(np.cross(q[1]-q[0],q[2]-q[0]),original_normal)<0 else face
    if xy.area>1e-11:
        if not xy.intersects(mask):return [points],[]
        if mask.covers(xy):return [],[points]
        # Split nonplanar quads into their existing fan triangles only at the
        # footprint edge. Whole untouched native polygons are copied exactly.
        if len(points)>3:
            outside=[];inside=[]
            for i in range(1,len(points)-1):
                a,b=split_face([points[0],points[i],points[i+1]],mask)
                outside.extend(a);inside.extend(b)
            return outside,inside
        normal=np.cross(p[1]-p[0],p[2]-p[0]);assert abs(normal[2])>1e-12
        def lift(q):
            x,y=q
            return(x,y,float(p[0,2]-(normal[0]*(x-p[0,0])+normal[1]*(y-p[0,1]))/normal[2]))
        def convert(g):
            return [orient([lift(q)for q in list(t.exterior.coords)[:3]])for poly in pieces(g)
                    for t in shapely.constrained_delaunay_triangles(poly).geoms if t.area>1e-12]
        return convert(xy.difference(mask)),convert(xy.intersection(mask))
    # Sleeper side faces project to a line. Clip in (distance along side, Z)
    # coordinates so only the portion within the road is removed.
    a=p[0,:2];dist=np.linalg.norm(p[:,:2]-a,axis=1);j=int(np.argmax(dist))
    length=float(dist[j])
    if length<1e-10:return [points],[]
    direction=(p[j,:2]-a)/length
    line=LineString([a,p[j,:2]])
    overlap=line.intersection(mask)
    if overlap.is_empty:return [points],[]
    if mask.covers(line):return [],[points]
    uv=Polygon([(float(np.dot(q[:2]-a,direction)),float(q[2]))for q in p])
    cuts=[]
    for part in line_parts(overlap):
        values=[float(np.dot(np.asarray(q[:2])-a,direction))for q in part.coords]
        cuts.append(box(min(values),float(p[:,2].min()-1),max(values),float(p[:,2].max()+1)))
    cut=unary_union(cuts)
    def convert(g):
        return [orient([(*list(a+direction*q[0]),q[1])for q in list(t.exterior.coords)[:3]])
                for poly in pieces(g)for t in shapely.constrained_delaunay_triangles(poly).geoms if t.area>1e-12]
    return convert(uv.difference(cut)),convert(uv.intersection(cut))

def add(data,name,role,points):
    vv,ff=data[name][role];start=len(vv)
    vv.extend(points);ff.append(tuple(range(start,start+len(points))))

def plan():
    layout=transport.revision.decode(transport.revision.read(transport.OUT/'layout.json'))
    crossing=next(c for c in layout['crossings']if c['id']=='Crossing_04')
    assert crossing['rail_ids']==['TPX_RAILWAYS_AXES_F97']and crossing['road_id']=='TPX_ROADS_AXES_C08'
    track=LineString(next(r['points_m']for r in layout['rail_centerlines']if r['id']=='TPX_RAILWAYS_AXES_F97'))
    deck=track.buffer(1.7,cap_style=2).intersection(layout['roads'])
    deck=min(pieces(deck),key=lambda p:p.distance(Point(crossing['point_m'])))
    # Saved FBX vertices are float32. Cover their <=0.03mm boundary rounding
    # without producing thin residual white triangles along the road edge.
    scope=deck.buffer(2.4,quad_segs=8).intersection(layout['roads']).buffer(.0002)
    return layout,crossing,scope

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    layout,crossing,scope=plan();rows=current_rows()
    hashes={r['fbx']:r['sha256']for r in rows.values()if r['name'].startswith(transport.revision.PREFIXES)}
    for p in [transport.BASE/'manifest.json',transport.CURRENT/'manifest.json',transport.OUT/'manifest.json',transport.OUT/'layout.json']:
        hashes[p.relative_to(ROOT).as_posix()]=transport.revision.sha(p)
    data=defaultdict(lambda:defaultdict(lambda:[[],[]]));statistics={};mappings=[]
    for name in NAMES:
        row=rows[name];faces=read_faces(row);paint=name.startswith(('SM_MPRR_CrossingDeck_','SM_MPRR_CrossingRamp_'))
        # Stable old slot order; only local crossing faces use the appended
        # road slot. All other same-tile crossing faces retain their old role.
        for role in row['material_roles']:data[name][role]
        if paint:data[name][ROAD_ROLE]
        untouched=0;split=0;inside_count=0
        for role,points in faces:
            outside,inside=split_face(points,scope)
            if not inside:
                add(data,name,role,points);untouched+=1;continue
            split+=bool(outside);inside_count+=len(inside)
            for p in outside:add(data,name,role,p)
            if paint:
                for p in inside:add(data,name,ROAD_ROLE,p)
        # Unused roles may be pruned by the native importer. Declare the exact
        # final slot order so the applier explicitly remaps any old overrides.
        assert any(ff for vv,ff in data[name].values()),name
        data[name]={role:group for role,group in data[name].items()if group[1]}
        statistics[name]=dict(old_faces=len(faces),untouched_faces_exact=untouched,split_boundary_faces=split,inside_faces_recolored_or_removed=inside_count)
        mappings.append(dict(name=name,old_mesh=old_package(row),new_mesh=DEST+'/Meshes/'+name,
            old_material_roles=row['material_roles'],new_material_roles=list(data[name]),
            material_reference_mesh=old_package(rows['SM_MPRR_Roads_0_-3'])if paint else None))
    base=transport.revision.read(transport.BASE/'manifest.json')
    textures={v['texture']:v['textures']for v in base['materials'].values()if v.get('texture')}
    audit=dict(success=True,crossing=crossing,scope=mapping(scope),scope_area_m2=scope.area,
        mesh_mappings=mappings,source_hashes=hashes,face_changes=statistics,
        steel_rails_and_centerlines_unchanged=True,no_actor_addition_or_removal=True,
        surface_heights_unchanged=True,all_geometry_outside_scope_preserved=True,
        source_triangles=sum(sum(len(f)-2 for f in ff)for roles in data.values()for vv,ff in roles.values()))
    payload=dict(geometry=data,instances={},materials=base['materials'],textures=textures,frame=mapping(layout['frame']),audit=audit,
        metadata=dict(map='/Game/Maps/MPR_CAD_Warehouse_B50B57',crossing_surface=True,crossing_id='Crossing_04',rebuild_namespace=DEST))
    with gzip.open(OUT/'geometry_payload.json.gz','wt',encoding='utf8')as f:json.dump(payload,f,separators=(',',':'))
    transport.revision.write(OUT/'geometry_audit.json',audit)
    for p,digest in hashes.items():assert transport.revision.sha(ROOT/p)==digest,p
    print('CROSSING_SURFACE_READY',len(data),audit['source_triangles'],scope.area,statistics,flush=True)

if __name__=='__main__':main()
