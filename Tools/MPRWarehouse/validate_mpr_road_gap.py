"""Read the final FBX to verify the requested strip, source attributes and terrain clearance."""
import build_mpr_road_gap as build
import numpy as np
from shapely.geometry import Polygon,Point,shape
from shapely.ops import unary_union
import approve_mpr_crossing_normals as native
import finish_mpr_crossing_material as binary

def main():
    plan=build.read(build.OUT/'plan.json');manifest=build.read(build.OUT/'manifest.json');row=manifest['meshes'][0]
    assert plan==build.plan()and manifest['plan_sha256']==build.sha(build.OUT/'plan.json')
    for p,digest in manifest['source_hashes'].items():assert build.sha(build.ROOT/p)==digest
    assert build.sha(build.ROOT/row['fbx'])==row['sha256']
    source=build.ROOT/plan['source_mesh']['fbx'];target=build.ROOT/row['fbx'];selected=plan['selected_source_faces']
    before=native.native(source,[build.ROLE]);after=native.native(target,[build.ROLE])
    old_names,old_uv=native.native_attributes(source);names,uv=native.native_attributes(target)
    old_color=binary.colors(source);color=binary.colors(target)
    assert len(after)==181 and names==old_names==[build.ROLE]
    for j,i in enumerate(selected):
        assert before[i][0]==after[j][0]and np.array_equal(before[i][1],after[j][1])and np.array_equal(before[i][2],after[j][2])
        assert np.array_equal(old_uv[i*3:i*3+3],uv[j*3:j*3+3])and np.array_equal(old_color[i*3:i*3+3],color[j*3:j*3+3])
    footprint=unary_union([Polygon(p[:,:2])for role,p,n in after]);assert footprint.equals(shape(plan['footprint']))
    base=build.read(build.base.transport.BASE/'manifest.json')
    terrain=build.base.reader.TriangleSurface([r for r in base['meshes']if r['name'].startswith(('SM_MPRR_Terrain_','SM_MPRR_Background'))])
    minimum=float('inf');samples=0
    for role,p,n in after:
        normal=np.cross(p[1]-p[0],p[2]-p[0]);poly=Polygon(p[:,:2])
        for i in terrain.index.query(poly,predicate='intersects'):
            ground=terrain.triangles[i];gn=terrain.normals[i]
            for part in build.base.pieces(poly.intersection(terrain.shapes[i])):
                for x,y in part.exterior.coords:
                    z=p[0,2]-(normal[0]*(x-p[0,0])+normal[1]*(y-p[0,1]))/normal[2]
                    gz=ground[0,2]-(gn[0]*(x-ground[0,0])+gn[1]*(y-ground[0,1]))/gn[2]
                    minimum=min(minimum,float(z-gz));samples+=1
    assert samples>500 and minimum>.0799,(samples,minimum)
    # The two original neighboring tiles already contain the continuation.
    current=build.base.current_rows();neighbors=[]
    for name in ['SM_MPRR_Roads_-1_-3','SM_MPRR_Roads_0_-2']:
        r=current[name];patches=[Polygon(np.asarray(p)[:,:2])for role,p in build.base.read_faces(r)]
        part=unary_union(patches);distance=footprint.distance(part)
        assert distance<.0002,(name,distance)
        neighbors.append(dict(mesh=name,distance_m=distance))
    report=dict(success=True,source_sha256=build.SOURCE_SHA,final_fbx_sha256=row['sha256'],triangles=181,
        exact_source_positions_normals_uv_colors=True,footprint_exact=True,area_m2=footprint.area,
        terrain_clearance=dict(samples=samples,minimum_m=minimum,method='All road/terrain overlap polygon corners'),
        neighboring_road_edges=neighbors,other_deleted_tile_pieces_excluded=True,all_original_sources_unchanged=True)
    build.write(build.OUT/'validation.json',report);print('MPR_ROAD_GAP_VALIDATED',report)

if __name__=='__main__':main()
