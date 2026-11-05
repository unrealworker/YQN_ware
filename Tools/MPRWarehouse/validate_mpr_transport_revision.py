"""CPU validation of the isolated traffic revision against saved base FBXs.

No scene mutation or native applications. Checks actual triangle interiors,
outside-mask invariants and source connectivity, not only generator metadata.
"""
from pathlib import Path
import gzip,hashlib,json,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'Tools/MPRWarehouse'),str(ROOT/'Saved/ParkRefinement/python_deps')]
import numpy as np
import shapely
from shapely.geometry import shape,LineString,Point
import validate_mpr_rebuild_surface_clearance as reader
SOURCE=ROOT/'SourceAssets/MPR/rebuild_b50b57'
CACHE=ROOT/'Saved/MPR/cleanup_20261105/transport'

def read(p):return json.loads(p.read_text(encoding='utf8'))
def tris(roles):
    out=[]
    for verts,faces in roles.values():
        vv=np.asarray(verts,float)
        for face in faces:
            out.extend(vv[[face[0],face[i],face[i+1]]]for i in range(1,len(face)-1))
    return np.asarray(out,float)
class Surface(reader.TriangleSurface):
    def __init__(self,triangles):
        normals=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
        valid=np.abs(normals[:,2])>1e-10
        self.triangles,self.normals=triangles[valid],normals[valid]
        self.shapes=shapely.polygons(self.triangles[:,:,:2]);self.index=shapely.STRtree(self.shapes)
def main():
    base=read(SOURCE/'manifest.json');before=read(SOURCE/'layout.json');after=read(CACHE/'layout.json')
    with gzip.open(CACHE/'geometry_payload.json.gz','rt',encoding='utf8')as f:payload=json.load(f)
    audit=payload['audit'];geometry=payload['geometry'];report=dict(success=False,checks={},surface_groups={})
    for name,expected in audit['source_hashes'].items():
        assert hashlib.sha256((SOURCE/name).read_bytes()).hexdigest()==expected,name
    report['checks']['source_bytes_unchanged']=True
    removed={'TPX_RAILWAYS_AXES_E6F','TPX_RAILWAYS_AXES_E9C'}
    old={r['id']:r for r in before['rail_centerlines']};new={r['id']:r for r in after['rail_centerlines']}
    assert set(old)-set(new)==removed and all(old[k]==new[k]for k in new)
    assert len(new)==28
    report['checks']['28_retained_rail_sources_exact']=True
    assert not payload['instances'] and not any(n.endswith('_RailBed')for n in geometry)
    report['checks']['no_instance_or_nontransport_payload']=all(n.startswith(('SM_MPRR_Rail_','SM_MPRR_RailCorridor_','SM_MPRR_CrossingDeck_','SM_MPRR_CrossingRamp_','SM_MPRR_Roads_','SM_MPRR_Curblines_','SM_MPRR_WhiteEdges_','SM_MPRR_RoadDashes_'))for n in geometry)
    mask=shape(audit['road']['mask']);oldroad=shape(before['roads']);road=shape(after['roads'])
    assert oldroad.symmetric_difference(road).difference(mask.buffer(1e-5)).area<1e-6
    assert audit['road']['old_topology']==audit['road']['new_topology']==[6,59]
    assert road.intersection(shape(before['building_protection'])).area<1e-6
    assert road.is_valid and shape(after['rail_corridor']).is_valid
    for key in ['frame','water','source_buildings','building_protection','source_road_hatches']:
        assert before[key]==after[key],key
    report['checks']['roads_outside_local_mask_exact']=True
    report['checks']['road_components_and_holes_unchanged']=[6,59]
    report['checks']['source_environment_layout_unchanged']=True
    report['checks']['uniform_2_25m_sleepers']=audit['rail_stats']['near_sleeper_spacing_m']==audit['rail_stats']['far_visual_sleeper_spacing_m']==2.25 and audit['rail_stats']['sleepers_far']==0
    terrain=reader.TriangleSurface([r for r in base['meshes']if r['name'].startswith(('SM_MPRR_Terrain_','SM_MPRR_Background'))])
    weights=np.asarray(((1/3,1/3,1/3),(.5,.5,0),(0,.5,.5),(.5,0,.5)))
    ranges=[('bed','SM_MPRR_RailCorridor_',.179),('roads','SM_MPRR_Roads_',.079),
        ('white','SM_MPRR_WhiteEdges_',.104),('dash','SM_MPRR_RoadDashes_',.106),
        ('curb','SM_MPRR_Curblines_',.199)]
    for category,prefix,minimum in ranges:
        samples=0;low=float('inf');missing=0;bad=0
        for name,roles in geometry.items():
            if not name.startswith(prefix):continue
            triangles=tris(roles)
            normal=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0]);triangles=triangles[np.abs(normal[:,2])>1e-10]
            points=np.einsum('sk,tkd->tsd',weights,triangles).reshape(-1,3)
            z,_=terrain.heights(points);clearance=points[:,2]-z;samples+=len(points)
            missing+=int(np.sum(~np.isfinite(z)));bad+=int(np.sum(clearance<minimum));low=min(low,float(np.nanmin(clearance)))
        report['surface_groups'][category]=dict(samples=samples,minimum_clearance_m=low,missing_terrain=missing,under_clearance=bad)
        assert not missing and not bad,(category,report['surface_groups'][category])
    # One unioned bed covers every remaining line. Interior triangle areas
    # equal the 2D corridor area so tile borders cannot hide diagonal gaps.
    bed=np.concatenate([tris(roles)for name,roles in geometry.items()if name.startswith('SM_MPRR_RailCorridor_')])
    projected=shapely.polygons(bed[:,:,:2]);expected=shape(after['rail_corridor'])
    union=shapely.union_all(projected)
    delta=expected.symmetric_difference(union)
    # Shared surface triangulation snaps XY to 0.1mm. Test gap thickness,
    # rather than adding kilometre-long boundary rounding into a false gap.
    assert delta.buffer(-.0002).area<1e-8
    excess=float(np.sum(shapely.area(projected)))-union.area
    assert abs(excess)<.001
    report['checks']['bed_gap_or_overlap_m2']={'xy_snap_tolerance_m':.0002,'gap_wider_than_tolerance':delta.buffer(-.0002).area,'boundary_rounding_area':delta.area,'overlap':excess}
    # Directly inspect sleeper boxes, not only constants: they share one
    # 0.23 x 2.6m footprint and 0.13m depth everywhere; no 300m profile cut.
    boxes=0;centers=[]
    for name,roles in geometry.items():
        if not name.endswith('_Sleepers'):continue
        for vv,ff in roles.values():
            assert len(vv)%8==0 and len(ff)==len(vv)//8*3
            for i in range(0,len(vv),8):
                p=np.asarray(vv[i:i+8]);assert np.max(np.abs(p[4:,2]-p[:4,2]-.13))<1e-8
                assert abs(np.linalg.norm(p[0,:2]-p[1,:2])-.23)<1e-7
                assert abs(np.linalg.norm(p[1,:2]-p[2,:2])-2.6)<1e-7
                centers.append(p.mean(0)[:2].tolist())
                boxes+=1
    assert boxes==audit['rail_stats']['sleepers_near']
    report['checks']['uniform_sleeper_boxes']=boxes
    tracks=[LineString(r['points_m'])for r in after['rail_centerlines']]
    nearest=shapely.STRtree(tracks).nearest(shapely.points(centers));deltas=[]
    for i,track in enumerate(tracks):
        positions=np.sort([track.project(Point(centers[j]))for j in np.flatnonzero(nearest==i)])
        deltas.extend(np.diff(positions).tolist())
    deltas=np.asarray(deltas)
    assert abs(float(np.median(deltas))-2.25)<1e-7 and np.quantile(deltas,.05)>2.20
    report['checks']['measured_sleeper_spacing_m']=dict(samples=len(deltas),median=float(np.median(deltas)),p05=float(np.quantile(deltas,.05)),p95=float(np.quantile(deltas,.95)))
    assert all(v for v in report['checks'].values())
    report.update(success=True,payload_sha256=hashlib.sha256((CACHE/'geometry_payload.json.gz').read_bytes()).hexdigest(),patch_meshes=len(geometry),removed_old_meshes=len(audit['remove_mesh_names']),preserved_transport_meshes=len(audit['unchanged_transport_mesh_names']))
    (CACHE/'geometry_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
