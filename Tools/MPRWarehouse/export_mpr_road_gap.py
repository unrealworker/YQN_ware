"""Export only the approved A50 faces by losslessly subsetting binary FBX arrays."""
import shutil
import build_mpr_road_gap as build
import approve_mpr_crossing_normals as native
import finish_mpr_crossing_material as binary
import numpy as np

def main():
    plan=build.read(build.OUT/'plan.json');assert plan==build.plan()
    row=plan['source_mesh'];source=build.ROOT/row['fbx'];target=build.OUT/(build.NAME+'.fbx')
    faces=native.native(source,row['material_roles']);names,uv=native.native_attributes(source);colors=binary.colors(source)
    assert names==[build.ROLE]and all(len(p)==3 for role,p,n in faces)
    objects=next(n for n in build.base.reader.fbx_nodes(source)if n[0]==b'Objects')
    geometry=next(n for n in objects[2]if n[0]==b'Geometry')
    smoothing=next(n for n in geometry[2]if n[0]==b'LayerElementSmoothing')
    smooth=next(n[1][0]for n in smoothing[2]if n[0]==b'Smoothing')
    selected=plan['selected_source_faces'];corners=np.asarray([[i*3+j for j in range(3)]for i in selected]).reshape(-1)
    vv=np.concatenate([faces[i][1]for i in selected]);nn=np.concatenate([faces[i][2]for i in selected])
    indices=np.arange(len(vv));indices[2::3]=-indices[2::3]-1
    shutil.copy2(source,target)
    # Each selected source corner remains a distinct vertex. All corner
    # attributes retain their exact float64 values and original triangle order.
    for field,values in [(b'Vertices',vv),(b'PolygonVertexIndex',indices),(b'Edges',np.arange(len(vv))),
        (b'Normals',nn),(b'NormalsIndex',np.arange(len(vv))),(b'UV',uv[corners]),(b'UVIndex',np.arange(len(vv))),
        (b'Colors',colors[corners]),(b'ColorIndex',np.arange(len(vv))),(b'Smoothing',[smooth[i]for i in selected])]:
        binary.patch_array(target,field,values)
    assert build.sha(source)==build.SOURCE_SHA
    mesh=dict(name=build.NAME,fbx=target.relative_to(build.ROOT).as_posix(),sha256=build.sha(target),
        triangles=len(selected),vertices=len(vv),material_roles=[build.ROLE],bounds_m=[[float(vv[:,i].min()),float(vv[:,i].max())]for i in range(3)],
        vertex_color_fade=row.get('vertex_color_fade'),full_precision_uvs=True,instance_only=False)
    manifest=dict(schema_version=1,map=build.MAP,namespace=build.DEST,meshes=[mesh],source_hashes=plan['source_hashes'],
        road_gap=True,road_id=build.ROAD,actor_label=plan['actor_label'],transform=plan['transform'],
        material_reference_mesh=plan['material_reference_mesh'],expected_effective_material=plan['expected_effective_material'],
        expected_missing_source_package=plan['expected_missing_source_package'],expected_actor_count_change=1,
        selected_source_face_count=len(selected),restored_area_m2=plan['area_m2'],plan_sha256=build.sha(build.OUT/'plan.json'))
    build.write(build.OUT/'manifest.json',manifest)
    print('MPR_ROAD_GAP_EXPORTED',mesh['sha256'],len(selected))

if __name__=='__main__':main()
