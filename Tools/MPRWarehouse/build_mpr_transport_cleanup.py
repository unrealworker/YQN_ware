"""Local terminal cleanup and stale crossing repair, without UE or Blender state.

Use standalone Blender Python 3.13. The current effective transport revision is
the input; older FBXs and manifests are read-only. Only four 150m tiles are
emitted, and only the two eastern tiles include rail replacements.
"""
from pathlib import Path
import copy,gzip,json,math,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'Tools/MPRWarehouse'),str(ROOT/'Saved/ParkRefinement/python_deps')]
import shapely
from shapely.geometry import LineString,Point,Polygon,box,mapping
from shapely.ops import unary_union
import build_mpr_transport_revision as revision
from run_mpr_rebuild_geometry import load_geometry_builder

BASE=ROOT/'SourceAssets/MPR/rebuild_b50b57'
CURRENT=BASE/'transport_revision_20261105'
OUT=ROOT/'SourceAssets/MPR/transport_cleanup_20261105'
TAIL_MASK=box(510.,-205.,590.,-115.)
TAIL_TILES=((3,-2),(3,-1))
GHOST_TILES=((-1,-3),(0,-2))
SURFACE_TILES=TAIL_TILES+GHOST_TILES
REMOVED_RAIL_IDS={'TPX_RAILWAYS_AXES_131E','TPX_RAILWAYS_AXES_1322'}
TRIMMED_RAIL_IDS={'TPX_RAILWAYS_AXES_F67','TPX_RAILWAYS_AXES_1317'}
REMOVED_ROAD_IDS={'TPX_ROADS_AXES_55D','TPX_ROADS_AXES_562','TPX_ROADS_AXES_56E'}
TRIMMED_ROAD_IDS={'TPX_ROADS_AXES_BE7','TPX_ROADS_AXES_DA0'}
SURFACE_PREFIXES=('SM_MPRR_CrossingDeck_','SM_MPRR_CrossingRamp_',
                  'SM_MPRR_Roads_','SM_MPRR_Curblines_',
                  'SM_MPRR_WhiteEdges_','SM_MPRR_RoadDashes_')

def tile_box(tile):
    x,y=tile
    return box(x*150.,y*150.,(x+1)*150.,(y+1)*150.)

def current_rows():
    rows={r['name']:r for r in revision.read(BASE/'manifest.json')['meshes']}
    patch=revision.read(CURRENT/'manifest.json')
    rows.update({r['name']:r for r in patch['meshes']})
    for name in patch['remove_mesh_names']:rows.pop(name,None)
    return rows

def source_hashes():
    sources=[BASE/'manifest.json',BASE/'layout.json',CURRENT/'manifest.json',CURRENT/'layout.json']
    sources += [ROOT/r['fbx'] for r in current_rows().values()
                if r['name'].startswith(revision.PREFIXES)]
    return {p.relative_to(ROOT).as_posix():revision.sha(p) for p in sources}

def clip_centerlines(rows,removed,trimmed):
    result=[];ends={}
    for item in rows:
        identity=item['id'];line=LineString(item['points_m'])
        if identity in removed:
            assert line.difference(TAIL_MASK).length<1e-7,identity
            continue
        if identity not in trimmed:
            assert line.intersection(TAIL_MASK).length<1e-7,('Unreviewed source intersects cut',identity)
            result.append(copy.deepcopy(item));continue
        clipped=line.difference(TAIL_MASK)
        assert clipped.geom_type=='LineString' and 0<clipped.length<line.length,identity
        record=copy.deepcopy(item)
        record.update(points_m=[list(p)for p in clipped.coords],length_m=clipped.length,
            revision='Remove reviewed east terminal crossing tail at CAD x=510m')
        ends[identity]=[list(clipped.coords[0]),list(clipped.coords[-1])]
        result.append(record)
    assert len(result)==len(rows)-len(removed)
    return result,ends

def crossing_surfaces(layout):
    tracks=[LineString(r['points_m'])for r in layout['rail_centerlines']]
    deck=unary_union([line.buffer(1.7,cap_style=2)for line in tracks]).intersection(layout['roads'])
    ramps=deck.buffer(2.4,quad_segs=8).difference(deck).intersection(layout['roads'])
    return deck,ramps

def revised_layout(original):
    layout=copy.deepcopy(original)
    layout['rail_centerlines'],rail_ends=clip_centerlines(original['rail_centerlines'],REMOVED_RAIL_IDS,TRIMMED_RAIL_IDS)
    layout['road_centerlines'],road_ends=clip_centerlines(original['road_centerlines'],REMOVED_ROAD_IDS,TRIMMED_ROAD_IDS)
    layout['roads']=original['roads'].difference(TAIL_MASK)
    # Re-form just the cut end caps. Every remote curb and road marking retains
    # the saved geometry, including the earlier driveway refinements.
    local=TAIL_MASK.buffer(1.)
    paved=layout['roads']
    curbs=paved.buffer(.24,quad_segs=12).difference(paved).intersection(layout['frame']).difference(layout['building_protection'])
    edges=paved.buffer(-.42,quad_segs=12).boundary.buffer(.06,quad_segs=6).intersection(paved)
    layout['curbs']=original['curbs'].difference(local).union(curbs.intersection(local))
    layout['white_edges']=original['white_edges'].difference(local).union(edges.intersection(local))
    layout['dash_lines']=original['dash_lines'].difference(TAIL_MASK)
    tracks=[LineString(r['points_m'])for r in layout['rail_centerlines']]
    main=Polygon(revision.read(ROOT/'SourceAssets/MPR/mpr_cad_layout.json')['footprint_outline_m'])
    corridor=unary_union([line.buffer(3,cap_style=2,quad_segs=12)for line in tracks]).buffer(1.1,quad_segs=12).buffer(-1.1,quad_segs=12).intersection(layout['frame']).difference(main.buffer(.5))
    # The cap may extend sideways beyond x=510 by the 3m rail-bed width.
    local_corridor=TAIL_MASK.buffer(8.)
    layout['rail_corridor']=original['rail_corridor'].difference(local_corridor).union(corridor.intersection(local_corridor))
    layout['crossings']=[entry for entry in layout['crossings']if not TAIL_MASK.covers(Point(entry['point_m']))]
    layout['audit'].update(source_rail_axis_count=len(tracks),unique_rail_road_crossings=len(layout['crossings']),
        rail_corridor_area_m2=layout['rail_corridor'].area,roads_area_m2=paved.area,
        transport_cleanup='2026-11-05 east terminal crossing tail removed; stale E6F/E9C crossing surfaces repaired')
    audit=dict(tail_mask=mapping(TAIL_MASK),removed_rail_ids=sorted(REMOVED_RAIL_IDS),
        trimmed_rail_endpoints_m=rail_ends,removed_road_ids=sorted(REMOVED_ROAD_IDS),
        trimmed_road_endpoints_m=road_ends,removed_crossing_ids=sorted(set(e['id']for e in original['crossings'])-set(e['id']for e in layout['crossings'])),
        removed_pavement_area_m2=original['roads'].difference(paved).area,
        surface_tiles=[list(t)for t in SURFACE_TILES],rail_tiles=[list(t)for t in TAIL_TILES],
        ghost_crossing_tiles=['SM_MPRR_CrossingDeck_0_-2','SM_MPRR_CrossingDeck_-1_-3'])
    return layout,audit

def affected_name(name):
    if name.startswith(SURFACE_PREFIXES):
        return any(name.endswith(f'_{x}_{y}')for x,y in SURFACE_TILES)
    if name.startswith('SM_MPRR_RailCorridor_'):
        return any(name.endswith(f'_{x}_{y}')for x,y in TAIL_TILES)
    if name.startswith('SM_MPRR_Rail_'):
        return any(name.startswith(f'SM_MPRR_Rail_{x}_{y}_')for x,y in TAIL_TILES)
    return False

def build_geometry(b,layout,base_manifest):
    height=revision.ground(b,base_manifest)
    b.rail_detail.NEAR_SLEEPER_SPACING_M=2.25;b.rail_detail.FAR_SLEEPER_SPACING_M=2.25
    b.rail_detail.NEAR_DISTANCE_M=1e9;b.rail_detail.HEAD_WIDTH_M=.09
    b.rail_detail.RAIL_OFFSET_M=(b.rail_detail.GAUGE_M+.09)/2
    def sink(name,role,verts,faces):
        name=name.replace('SM_MPR_Env_','SM_MPRR_Rail_')
        if name.endswith('_RailBed')or not affected_name(name):return
        b.GEO.mesh(name,'MPR3_'+role,[(x,y,z+height(x,y)-b.G)for x,y,z in verts],faces)
    tracks=[dict(id=r['id'],layer='railways',vertices=list(shapely.segmentize(LineString(r['points_m']),4.).coords))for r in layout['rail_centerlines']]
    b.build_railways(dict(mesh=sink,zone=lambda x,y:f'{math.floor(x/150.)}_{math.floor(y/150.)}',regions={},include_freight=False),tracks,b.G)
    def surface(stem,role,geometry,z,tiles,step=3):
        for tile in tiles:
            part=geometry.intersection(tile_box(tile))
            b.surface(f'SM_MPRR_{stem}_{tile[0]}_{tile[1]}',role,part,z,step=step,tiled=False)
    surface('RailCorridor','MPR3_Ballast',layout['rail_corridor'],lambda x,y:height(x,y)+.18,TAIL_TILES)
    deck,ramps=crossing_surfaces(layout);crossing=deck.union(ramps)
    surface('CrossingDeck','MPR3_Concrete',deck,lambda x,y:height(x,y)+.375,SURFACE_TILES,.65)
    surface('CrossingRamp','MPR3_Asphalt',ramps,lambda x,y:height(x,y)+.08+.295*(1-min(1,Point(x,y).distance(deck)/2.4)),SURFACE_TILES,.65)
    for name,role,g,offset in [
        ('Roads','MPR4_TerminalAsphalt',layout['roads'].difference(crossing),.08),
        ('Curblines','MPR4_TerminalCurb',layout['curbs'],.20),
        ('WhiteEdges','MPR4_TerminalWhiteLine',layout['white_edges'].difference(crossing),.105),
        ('RoadDashes','MPR4_TerminalWhiteLine',layout['dash_lines'].difference(crossing),.107)]:
        surface(name,role,g,lambda x,y,d=offset:height(x,y)+d,SURFACE_TILES)
    assert all(affected_name(n)for n in b.GEO.data)
    return b.GEO.data

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    hashes=source_hashes();base=revision.read(BASE/'manifest.json')
    original=revision.decode(revision.read(CURRENT/'layout.json'))
    layout,audit=revised_layout(original)
    print('MPR_TRANSPORT_CLEANUP_LAYOUT_READY',audit,flush=True)
    geometry=build_geometry(load_geometry_builder(),layout,base)
    old=current_rows();old_affected={n for n in old if affected_name(n)}
    audit.update(success=True,source_hashes=hashes,mesh_names=sorted(geometry),
        remove_mesh_names=sorted(old_affected-set(geometry)),new_mesh_names=sorted(set(geometry)-set(old)),
        unchanged_transport_mesh_names=sorted(n for n in old if n.startswith(revision.PREFIXES)and n not in old_affected),
        source_triangles=sum(sum(len(f)-2 for f in faces)for roles in geometry.values()for verts,faces in roles.values()),
        preserved_all_nontransport_meshes=True,preserved_instances=True)
    textures={v['texture']:v['textures']for v in base['materials'].values()if v.get('texture')}
    payload=dict(geometry=geometry,instances={},materials=base['materials'],textures=textures,
        frame=mapping(layout['frame']),counts={},input_hashes={},audit=audit,
        metadata=dict(rebuild_namespace='/Game/MPRWarehouse/RebuildB50B57',map='/Game/Maps/MPR_CAD_Warehouse_B50B57',transport_cleanup=True))
    with gzip.open(OUT/'geometry_payload.json.gz','wt',encoding='utf8')as f:json.dump(payload,f,separators=(',',':'))
    revision.write(OUT/'layout.json',revision.encode(layout));revision.write(OUT/'geometry_audit.json',audit)
    assert hashes==source_hashes(),'An existing source asset changed during the build'
    print('MPR_TRANSPORT_CLEANUP_READY',len(geometry),audit['source_triangles'],'removed mesh names',audit['remove_mesh_names'],flush=True)

if __name__=='__main__':main()
