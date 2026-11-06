"""Read native render-buffer FBX and explain precise UE import degeneracy.

No Unreal calls or asset writes. Every surviving native face is assigned to a
source polygon; only the exact source polygons rejected by UE's real float32
normal test may remain unmatched.
"""
from pathlib import Path
from collections import defaultdict, Counter
import hashlib
import json
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'Tools/MPRWarehouse'),str(ROOT/'Saved/ParkRefinement/python_deps')]
import shapely
from shapely.geometry import Polygon
from shapely.ops import unary_union
from mpr_site_completion_geometry import Ground,from_polygons
from validate_mpr_rebuild_surface_clearance import fbx_nodes

SOURCE=ROOT/'SourceAssets/MPR/landscape_layout_20261106/ground'
NATIVE=ROOT/'Saved/MPR/landscape_layout_20261106/native'
OUT=ROOT/'SourceAssets/MPR/landscape_layout_20261106/native_validation.json'
ENGINE=Path('D:/UE/UE_5.8/Engine/Source')

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def write(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def mesh(p,scale):
    obj=next(n for n in fbx_nodes(Path(p))if n[0]==b'Objects')
    geo=next(n for n in obj[2]if n[0]==b'Geometry')
    fields={n[0]:n for n in geo[2]}
    vertices=np.asarray(fields[b'Vertices'][1][0],dtype=np.float64).reshape(-1,3)*scale
    faces=[];current=[]
    for i in fields[b'PolygonVertexIndex'][1][0]:
        current.append(int(i)if i>=0 else int(-i-1))
        if i<0:faces.append(current);current=[]
    return vertices,faces

def area(p):
    return sum(float(np.linalg.norm(np.cross(p[i]-p[0],p[i+1]-p[0])))/2 for i in range(1,len(p)-1))

def run():
    manifest=read(SOURCE/'manifest.json');native=read(NATIVE/'manifest.json');plan=read(SOURCE/'plan.json')
    assert native['export_source_mesh'] is False
    assert manifest['plan_sha256']==sha(SOURCE/'plan.json')
    green=from_polygons(plan['surfaces'][0]['polygons'])
    hard=from_polygons(plan['protected_geometry']['hard'])
    ground=Ground(ROOT,read(ROOT/'SourceAssets/MPR/rebuild_b50b57/manifest.json'),green.union(hard).buffer(3),{})
    result=dict(success=False,ground_manifest_sha256=sha(SOURCE/'manifest.json'),
                coordinate_policy='Source FBX CAD metres; native render-buffer FBX CAD centimetres divided by 100.',
                method='Independent binary FBX decoding, float32 UE normal test, source-polygon capacity matching, footprint and terrain checks.',
                point_match_tolerance_m=.00005,thresholds=dict(ue_import_cross_squared_cm4=1e-8,ue_point_equality_cm=.00002),meshes=[])
    sources=[('Editor/UnrealEd/Private/Fbx/FbxStaticMeshImport.cpp',[365,372,879,881]),
             ('Developer/MeshBuilder/Private/StaticMeshBuilder.cpp',[1644,1674]),
             ('Runtime/Core/Public/Math/UnrealMathUtility.h',[130,201])]
    result['engine_evidence']=[dict(path=str(ENGINE/p),lines=lines,sha256=sha(ENGINE/p)) for p,lines in sources]
    for row in manifest['meshes']:
        nr=next(n for n in native['meshes']if n['name']==row['name'])
        source_path=ROOT/row['fbx'];native_path=Path(nr['fbx'])
        asset=ROOT/'Content/MPRWarehouse/LandscapeLayout20261106/Meshes'/(row['name']+'.uasset')
        assert sha(source_path)==row['sha256'] and sha(native_path)==nr['sha256'] and sha(asset)==nr['asset_sha256']
        v,faces=mesh(source_path,1.);nv,nfaces=mesh(native_path,.01)
        assert all(len(f)==3 for f in nfaces)
        assert sum(len(f)-2 for f in faces)==row['triangles'] and len(nfaces)==nr['native_triangles']
        # FbxStaticMeshImport converts to FVector3f centimetres, then tests the
        # first 3 corners via GetSafeNormal(SMALL_NUMBER): squared cross < 1e-8.
        rejected=[];normal_reject=[];point_reject=[];source_triangle_offset=0
        for i,f in enumerate(faces):
            p=v[f];cm=(p*100).astype(np.float32)
            cross=np.cross(cm[1]-cm[2],cm[0]-cm[2]);squared=float(np.dot(cross,cross))
            same=any(float(np.abs(cm[a]-cm[b]).max())<=.00002 for a,b in [(0,1),(0,2),(1,2)])
            if squared<1e-8 or same:
                assert len(f)==3,'Unexpected non-triangle source degeneracy'
                rejected.append(dict(source_polygon=i,source_triangle=source_triangle_offset,source_vertices_m=p.tolist(),
                                     source_area_m2=area(p),xy_area_m2=Polygon(p[:,:2]).area,
                                     ue_float32_cross_squared_cm4=squared,equal_corners=same,
                                     reason='zero-area source triangle'if area(p)==0 else 'UE GetSafeNormal squared-cross cutoff'))
                if squared<1e-8:normal_reject.append(i)
                if same:point_reject.append(i)
            source_triangle_offset+=len(f)-2
        rejected_ids={r['source_polygon']for r in rejected}
        assert len(nfaces)==row['triangles']-len(rejected)
        # Native float32 coordinates have <=0.031mm conversion error. Candidate
        # matching retains all nearby source corners, rather than choosing the
        # wrong side of a tiny original sliver from nearest-corner rounding.
        unique,inverse=np.unique(v,axis=0,return_inverse=True)
        tree=shapely.STRtree(shapely.points(unique[:,:2]))
        pairs=tree.query(shapely.points(nv[:,:2]),predicate='dwithin',distance=.00005)
        candidates=defaultdict(list);errors={}
        for ni,si in zip(*pairs):
            error=float(np.linalg.norm(nv[ni]-unique[si]))
            if error<=.00005:candidates[int(ni)].append(int(si));errors[int(ni)]=min(error,errors.get(int(ni),float('inf')))
        assert len(candidates)==len(nv),'Native vertex has no source corner'
        polygons_by_corner=defaultdict(set)
        for i,f in enumerate(faces):
            if i in rejected_ids:continue
            for corner in inverse[f]:polygons_by_corner[int(corner)].add(i)
        vertex_polygons={i:set().union(*(polygons_by_corner[s]for s in cand))for i,cand in candidates.items()}
        edges=[]
        for f in nfaces:
            parent=vertex_polygons[f[0]]&vertex_polygons[f[1]]&vertex_polygons[f[2]]
            assert parent,'Native triangle corners do not belong to any retained source polygon'
            edges.append(sorted(parent))
        # Each source triangle has one capacity and each original quad two.
        # Duplicate adjacent wheel-stop caps remain separate source polygons.
        slots={i:[(i,j)for j in range(len(f)-2)]for i,f in enumerate(faces)if i not in rejected_ids}
        assignment={};native_parent={}
        def claim(n,seen):
            for polygon in edges[n]:
                for slot in slots[polygon]:
                    if slot in seen:continue
                    seen.add(slot)
                    if slot not in assignment or claim(assignment[slot],seen):
                        assignment[slot]=n;native_parent[n]=polygon;return True
            return False
        for n in sorted(range(len(nfaces)),key=lambda n:len(edges[n])):
            assert claim(n,set()),'Native/source polygon capacities do not match'
        assert len(assignment)==sum(len(s)for s in slots.values())==len(nfaces)
        assert Counter(native_parent.values())==Counter({i:len(s)for i,s in slots.items()})
        source_projection=unary_union([Polygon(v[f][:,:2])for f in faces if Polygon(v[f][:,:2]).area>0])
        native_projection=unary_union([Polygon(nv[f][:,:2])for f in nfaces if Polygon(nv[f][:,:2]).area>0])
        hausdorff=source_projection.hausdorff_distance(native_projection)
        symmetric=source_projection.symmetric_difference(native_projection).area
        assert hausdorff<.00005 and symmetric<.04,(row['name'],hausdorff,symmetric)
        # Every source polygon receives its own native area budget, including
        # quads triangulated along the alternate FBX SDK diagonal.
        areas=defaultdict(float)
        for n,f in enumerate(nfaces):areas[native_parent[n]]+=area(nv[f])
        area_errors=[]
        for polygon,narea in areas.items():
            p=v[faces[polygon]];perimeter=sum(float(np.linalg.norm(p[i]-p[(i+1)%len(p)]))for i in range(len(p)))
            err=abs(narea-area(p));assert err<=perimeter*.0001+1e-7,(polygon,err,perimeter)
            area_errors.append(err)
        terrain_errors=[]
        for n,f in enumerate(nfaces):
            source_polygon=native_parent[n];p=v[faces[source_polygon]]
            normal=np.cross(p[1]-p[0],p[2]-p[0])
            if normal[2]<=0:continue
            expected=.045 if row['name'].endswith('CampusGreen') else (.175 if source_polygon<342 else .235)
            tri=nv[f]
            for q in [tri.mean(0),(tri[0]+tri[1])/2,(tri[1]+tri[2])/2,(tri[0]+tri[2])/2]:
                terrain_errors.append(abs(float(q[2])-ground.at(*q[:2])-expected))
        assert max(terrain_errors)<.00001,(row['name'],max(terrain_errors))
        result['meshes'].append(dict(name=row['name'],source_fbx_sha256=sha(source_path),native_fbx_sha256=sha(native_path),
            asset_sha256=sha(asset),native_fbx=str(native_path.relative_to(ROOT)),source_triangles=row['triangles'],native_triangles=len(nfaces),
            rejected_source_polygons=rejected,all_surviving_source_polygons_accounted=True,all_native_faces_mapped=True,
            maximum_native_vertex_distance_m=max(errors.values()),maximum_source_polygon_area_difference_m2=max(area_errors),
            maximum_terrain_height_error_m=max(terrain_errors),terrain_sample_count=len(terrain_errors),
            footprint_hausdorff_m=hausdorff,footprint_symmetric_difference_m2=symmetric,
            removed_triangle_surface_area_m2=sum(r['source_area_m2']for r in rejected),
            removed_triangle_xy_area_union_m2=unary_union([Polygon(r['source_vertices_m'])for r in rejected]).area))
    result['success']=True
    write(OUT,result)
    review=ROOT/'Saved/MPR/landscape_layout_20261106/review';review.mkdir(parents=True,exist_ok=True)
    write(review/'native_degeneracy.json',result)
    print(json.dumps(result,ensure_ascii=False))
    return result

if __name__=='__main__':run()
