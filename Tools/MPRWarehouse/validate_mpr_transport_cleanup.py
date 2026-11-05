"""Validate payload triangles and the effective old+new crossing surfaces."""
import gzip,json
import build_mpr_transport_cleanup as cleanup
import numpy as np
import shapely
from shapely.geometry import shape,box
from shapely.ops import unary_union
from validate_mpr_transport_revision import tris
import validate_mpr_rebuild_surface_clearance as reader

def projected(roles):
    triangles=tris(roles)
    return shapely.union_all(shapely.polygons(triangles[:,:,:2]))

def exported_triangles(row):
    path=(cleanup.ROOT/row['fbx']).resolve()
    assert path.is_relative_to(cleanup.OUT.resolve())and cleanup.revision.sha(path)==row['sha256']
    objects=next(n for n in reader.fbx_nodes(path)if n[0]==b'Objects')
    geometries=[n for n in objects[2]if n[0]==b'Geometry'];assert len(geometries)==1
    fields={n[0]:n for n in geometries[0][2]}
    vertices=np.asarray(fields[b'Vertices'][1][0],dtype=np.float64).reshape(-1,3)
    raw=fields[b'PolygonVertexIndex'][1][0];faces=[];face=[]
    for index in raw:
        face.append(int(index)if index>=0 else int(-index-1))
        if index<0:
            faces.extend((face[0],face[i],face[i+1])for i in range(1,len(face)-1));face=[]
    assert not face and len(faces)==row['triangles']
    actual_bounds=np.stack((vertices.min(0),vertices.max(0)),axis=1)
    error=float(np.max(np.abs(actual_bounds-np.asarray(row['bounds_m']))))
    assert error<.0001,(row['name'],'FBX bounds differ',error)
    return vertices[np.asarray(faces,dtype=np.int64)],error

def main():
    out=cleanup.OUT
    with gzip.open(out/'geometry_payload.json.gz','rt',encoding='utf8')as f:payload=json.load(f)
    geometry=payload['geometry'];audit=payload['audit']
    layout=cleanup.revision.decode(cleanup.revision.read(out/'layout.json'))
    assert cleanup.source_hashes()==audit['source_hashes']
    assert not payload['instances'] and all(cleanup.affected_name(n)for n in geometry)
    assert set(geometry)==set(audit['mesh_names'])
    old=cleanup.current_rows();affected={n for n in old if cleanup.affected_name(n)}
    assert set(audit['remove_mesh_names'])==affected-set(geometry)
    report=dict(success=False,checks={},surface_groups={},removed_mesh_names=audit['remove_mesh_names'])
    report['checks']['all_old_transport_sources_byte_identical']=True
    report['checks']['only_reviewed_tiles_and_transport_categories']=True
    deck,ramps=cleanup.crossing_surfaces(layout);crossing=deck.union(ramps)
    expected=dict(CrossingDeck=deck,CrossingRamp=ramps,Roads=layout['roads'].difference(crossing),
        Curblines=layout['curbs'],WhiteEdges=layout['white_edges'].difference(crossing),RoadDashes=layout['dash_lines'].difference(crossing),RailCorridor=layout['rail_corridor'])
    deltas={}
    for category,g in expected.items():
        tiles=cleanup.TAIL_TILES if category=='RailCorridor'else cleanup.SURFACE_TILES
        for tile in tiles:
            name=f'SM_MPRR_{category}_{tile[0]}_{tile[1]}'
            actual=projected(geometry[name])if name in geometry else shapely.GeometryCollection()
            want=g.intersection(cleanup.tile_box(tile))
            delta=want.symmetric_difference(actual)
            assert delta.buffer(-.0002).area<1e-7,(name,'polygon hole or surplus',delta.area)
            deltas[name]=delta.area
    report['checks']['surface_coverage_gap_wider_than_0_2mm']=False
    report['checks']['surface_boundary_rounding_area_m2']=deltas
    # Read the actual previously imported FBXs, not old metadata claims. Merge
    # the replacement geometry just as the UE patch will. Disconnected stale
    # white sections must disappear while all remaining crossings still match.
    old_decks=[];merged=[]
    for name,row in old.items():
        if not name.startswith('SM_MPRR_CrossingDeck_'):continue
        triangles,_=reader.mesh_data(row)
        old_shape=shapely.union_all(shapely.polygons(triangles[:,:,:2]));old_decks.append(old_shape)
        if name in audit['remove_mesh_names']:continue
        merged.append(projected(geometry[name])if name in geometry else old_shape)
    actual=unary_union(merged)
    delta=actual.symmetric_difference(deck)
    assert delta.buffer(-.0002).area<1e-7,('Merged crossing mismatch',delta.area)
    ghost_regions=[box(30,-296,58,-270),box(-98,-401,-89,-392)]
    ghost_report=[];original=unary_union(old_decks)
    for region in ghost_regions:
        old_ghost=original.intersection(region).difference(deck.buffer(.001))
        assert old_ghost.area>20
        remaining=actual.intersection(old_ghost.buffer(-.001)).area
        assert remaining<1e-7,remaining
        road_patch=unary_union([projected(roles)for name,roles in geometry.items()if name.startswith('SM_MPRR_Roads_')])
        hole=old_ghost.difference(road_patch).buffer(-.0002).area
        assert hole<1e-7,('Ghost deck removed without road refill',hole)
        ghost_report.append(dict(old_white_area_m2=old_ghost.area,remaining_white_area_m2=remaining,road_refill_hole_m2=hole))
    report['checks']['two_stale_crossings_removed_and_road_refilled']=ghost_report
    # Every interior and edge midpoint must stay above the saved terrain plane.
    base=cleanup.revision.read(cleanup.BASE/'manifest.json')
    terrain=reader.TriangleSurface([r for r in base['meshes']if r['name'].startswith(('SM_MPRR_Terrain_','SM_MPRR_Background'))])
    weights=np.asarray(((1/3,1/3,1/3),(.5,.5,0),(0,.5,.5),(.5,0,.5)))
    for category,minimum in [('RailCorridor',.179),('Roads',.079),('WhiteEdges',.104),('RoadDashes',.106),('Curblines',.199),('CrossingDeck',.374),('CrossingRamp',.079)]:
        low=float('inf');samples=0;missing=0;bad=0
        for name,roles in geometry.items():
            if not name.startswith('SM_MPRR_'+category+'_'):continue
            ts=tris(roles)
            points=np.einsum('sk,tkd->tsd',weights,ts).reshape(-1,3)
            heights,_=terrain.heights(points);clearance=points[:,2]-heights
            missing+=int(np.sum(~np.isfinite(heights)));bad+=int(np.sum(clearance<minimum))
            samples+=len(points);low=min(low,float(np.nanmin(clearance)))
        assert samples and not missing and not bad,(category,samples,missing,bad,low)
        report['surface_groups'][category]=dict(samples=samples,minimum_clearance_m=low,missing_terrain=missing,under_clearance=bad)
    report.update(success=True,payload_sha256=cleanup.revision.sha(out/'geometry_payload.json.gz'),
        patch_meshes=len(geometry),source_triangles=audit['source_triangles'])
    if (out/'manifest.json').exists():
        manifest=cleanup.revision.read(out/'manifest.json')
        assert {r['name']for r in manifest['meshes']}==set(geometry)
        errors={}
        for row in manifest['meshes']:
            ts,error=exported_triangles(row);errors[row['name']]=error
            if not row['name'].startswith('SM_MPRR_Rail_'):
                source=projected(geometry[row['name']])
                exported=shapely.union_all(shapely.polygons(ts[:,:,:2]))
                assert source.symmetric_difference(exported).buffer(-.0002).area<1e-7,('FBX polygon mismatch',row['name'])
        report['native_fbx_validation']=dict(meshes=len(errors),triangles=sum(r['triangles']for r in manifest['meshes']),
            maximum_bound_error_m=max(errors.values()),all_mesh_hashes_valid=True,all_surface_projections_match=True)
    cleanup.revision.write(out/'geometry_validation.json',report)
    print('MPR_TRANSPORT_CLEANUP_VALIDATED',len(geometry),audit['source_triangles'],ghost_report)

if __name__=='__main__':main()
