"""Read UE's real render mesh and account for every imported green triangle."""
from pathlib import Path
from collections import Counter, defaultdict
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'Tools/MPRWarehouse'),str(ROOT/'Saved/ParkRefinement/python_deps')]
import numpy as np
import shapely
from shapely.geometry import Polygon
from shapely.ops import unary_union
from plan_mpr_green_extension import OUT, read, sha, write
from validate_mpr_landscape_native import mesh, area
from mpr_site_completion_geometry import Ground, from_polygons


def run():
    plan,manifest=read(OUT/'plan.json'),read(OUT/'manifest.json')
    native_dir=ROOT/'Saved/MPR/green_extension_20261106/native'
    native=read(native_dir/'manifest.json')
    assert native['export_source_mesh'] is False
    assert manifest['plan_sha256']==sha(OUT/'plan.json')
    row=manifest['meshes'][0]
    source_path=ROOT/row['fbx'];native_path=Path(native['fbx'])
    asset=ROOT/'Content/MPRWarehouse/GreenExtension20261106/Meshes'/(row['name']+'.uasset')
    assert sha(source_path)==row['sha256']
    assert sha(native_path)==native['sha256'] and sha(asset)==native['asset_sha256']
    v,faces=mesh(source_path,1.)
    nv,nfaces=mesh(native_path,.01)
    assert all(len(f)==3 for f in faces+nfaces)
    assert len(faces)==row['triangles'] and len(nfaces)==native['triangles']
    counts=[len(s['triangles_m'])for s in plan['surfaces']]
    assert sum(counts)==len(faces)
    labels=[s['id']for s in plan['surfaces']]
    groups=np.repeat(np.arange(len(counts)),counts)
    oldv,oldfaces=mesh(ROOT/plan['source_green_fbx'],1.)
    key=lambda points:tuple(sorted(tuple(float(c)for c in p)for p in points))
    assert Counter(key(v[f])for f in faces[:counts[0]])==Counter(key(oldv[f])for f in oldfaces)
    # Match the engine's documented float32 centimetre normal/point tests.
    rejected=[]
    for i,f in enumerate(faces):
        p=v[f];cm=(p*100).astype(np.float32)
        cross=np.cross(cm[1]-cm[2],cm[0]-cm[2]);squared=float(np.dot(cross,cross))
        equal=any(float(np.abs(cm[a]-cm[b]).max())<=.00002 for a,b in [(0,1),(0,2),(1,2)])
        if squared<1e-8 or equal:
            rejected.append(dict(source_triangle=i,group=labels[groups[i]],source_vertices_m=p.tolist(),
                                 surface_area_m2=area(p),xy_area_m2=Polygon(p[:,:2]).area,
                                 ue_float32_cross_squared_cm4=squared,equal_corners=equal))
    excluded={r['source_triangle']for r in rejected}
    assert len(nfaces)==len(faces)-len(excluded)
    # Capacity matching proves no retained triangle was lost or replaced.
    unique,inverse=np.unique(v,axis=0,return_inverse=True)
    tree=shapely.STRtree(shapely.points(unique[:,:2]))
    pairs=tree.query(shapely.points(nv[:,:2]),predicate='dwithin',distance=.00005)
    candidates=defaultdict(list);vertex_errors={}
    for ni,si in zip(*pairs):
        err=float(np.linalg.norm(nv[ni]-unique[si]))
        if err<=.00005:
            candidates[int(ni)].append(int(si))
            vertex_errors[int(ni)]=min(err,vertex_errors.get(int(ni),float('inf')))
    assert len(candidates)==len(nv)
    by_corner=defaultdict(set)
    for i,f in enumerate(faces):
        if i not in excluded:
            for c in inverse[f]:by_corner[int(c)].add(i)
    vertex_parents={i:set().union(*(by_corner[c]for c in cc))for i,cc in candidates.items()}
    edges=[]
    for f in nfaces:
        cc=vertex_parents[f[0]]&vertex_parents[f[1]]&vertex_parents[f[2]]
        assert cc,'Native face is not a retained source face'
        edges.append(sorted(cc))
    assignment={};native_parent={}
    def claim(n,seen):
        for source in edges[n]:
            if source in seen:continue
            seen.add(source)
            if source not in assignment or claim(assignment[source],seen):
                assignment[source]=n;native_parent[n]=source;return True
        return False
    for n in sorted(range(len(nfaces)),key=lambda n:len(edges[n])):assert claim(n,set())
    assert set(assignment)==set(range(len(faces)))-excluded
    assert len(native_parent)==len(nfaces)
    extent=unary_union([from_polygons(s['polygons'])for s in plan['surfaces']])
    ground=Ground(ROOT,read(ROOT/'SourceAssets/MPR/rebuild_b50b57/manifest.json'),extent.buffer(3),{})
    reports=[]
    for group,s in enumerate(plan['surfaces']):
        native_ids=[n for n,parent in native_parent.items()if groups[parent]==group]
        ts=[nv[nfaces[n]]for n in native_ids]
        actual=unary_union([Polygon(t[:,:2])for t in ts])
        expected=from_polygons(s['polygons'])
        symmetric=actual.symmetric_difference(expected).area
        outside=actual.difference(expected.buffer(.0001)).area
        missing=expected.difference(actual.buffer(.0001)).area
        assert symmetric<.04 and outside<1e-9 and missing<1e-9,(s['id'],symmetric,outside,missing)
        height_errors=[];area_errors=[]
        for n in native_ids:
            p=v[faces[native_parent[n]]];t=nv[nfaces[n]]
            perimeter=sum(float(np.linalg.norm(p[j]-p[(j+1)%3]))for j in range(3))
            error=abs(area(p)-area(t));assert error<=perimeter*.0001+1e-7
            area_errors.append(error)
            for point in [t.mean(0),(t[0]+t[1])/2,(t[1]+t[2])/2,(t[2]+t[0])/2]:
                height_errors.append(abs(point[2]-ground.at(*point[:2])-s['offset_m']))
        assert max(height_errors)<.00001
        loss=[r for r in rejected if r['group']==s['id']]
        reports.append(dict(id=s['id'],source_triangles=counts[group],native_triangles=len(ts),
                            rejected_triangles=len(loss),rejected_surface_area_m2=sum(r['surface_area_m2']for r in loss),
                            source_area_m2=expected.area,native_area_m2=actual.area,
                            footprint_symmetric_difference_m2=symmetric,
                            missing_outside_point1mm_m2=missing,outside_point1mm_m2=outside,
                            max_terrain_height_error_m=max(height_errors),
                            max_triangle_area_difference_m2=max(area_errors)))
    result=dict(success=True,plan_sha256=sha(OUT/'plan.json'),manifest_sha256=sha(OUT/'manifest.json'),
                source_fbx_sha256=sha(source_path),native_fbx_sha256=sha(native_path),asset_sha256=sha(asset),
                native_fbx=native_path.relative_to(ROOT).as_posix(),export_source_mesh=False,
                method='Binary render-buffer FBX divided by 100; exact source triangle preservation, UE float32 degeneracy test, one-to-one retained-face mapping, terrain and footprint containment.',
                native_point_match_tolerance_m=.00005,footprint_tolerance_m=.0001,
                source_triangles=len(faces),native_triangles=len(nfaces),
                all_retained_source_faces_accounted=True,all_native_faces_mapped=True,
                original_source_triangles_preserved=counts[0],
                maximum_native_vertex_distance_m=max(vertex_errors.values()),
                rejected_surface_area_m2=sum(r['surface_area_m2']for r in rejected),
                rejected_xy_area_m2=sum(r['xy_area_m2']for r in rejected),
                groups=reports,rejected_source_triangles=rejected)
    write(OUT/'native_validation.json',result)
    print(__import__('json').dumps({k:v for k,v in result.items()if k!='rejected_source_triangles'},ensure_ascii=False))
    return result


if __name__=='__main__':run()
