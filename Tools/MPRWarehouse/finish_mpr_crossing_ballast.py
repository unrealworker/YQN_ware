"""Clip the proven residual Crossing04 ballast, preserving other native faces."""
import hashlib,json,shutil
from collections import Counter
import finish_mpr_crossing_material as material
import numpy as np
from shapely.geometry import Polygon,mapping
from shapely.ops import unary_union

base=material.base;build=base.build;ROOT=base.ROOT;SOURCE=base.SOURCE
NAME='SM_MPRR_RailCorridor_0_-3'
OLD_SHA='e3e9b1dc57773745a4f4f662796ca8f5612a81a557dcf79a495241d2458db341'

def fingerprint(p):return tuple(sorted(tuple(float(v)for v in q)for q in p))

def main():
    manifest=build.transport.revision.read(SOURCE/'manifest.json');rows={r['name']:r for r in manifest['meshes']};row=rows[NAME]
    if row.get('corridor_residual_cleanup'):
        assert build.transport.revision.sha(ROOT/row['fbx'])==row['sha256'];print('CROSSING_BALLAST_ALREADY_COMPLETE');return
    assert row['sha256']==OLD_SHA and build.transport.revision.sha(ROOT/row['fbx'])==OLD_SHA
    residual=build.transport.revision.read(SOURCE/'residual_material_validation.json');rr=rows[residual['mesh_name']]
    ramp=base.native(ROOT/rr['fbx'],rr['material_roles'])
    footprint=unary_union([Polygon(ramp[i][1][:,:2])for i in residual['selected_source_face_indices']])
    # A 0.2mm guard covers native float32 boundary rounding only.
    mask=footprint.buffer(.0002)
    layout,crossing,scope=build.plan()
    assert mask.difference(layout['roads'].buffer(.0005)).area<.001
    stage=ROOT/'Saved/MPR/crossing_surface_20261105/residual_ballast';stage.mkdir(parents=True,exist_ok=True)
    source=ROOT/row['fbx'];before_path=stage/(NAME+'.before.fbx');target=stage/(NAME+'.fbx')
    shutil.copy2(source,before_path);shutil.copy2(source,target)
    before=base.native(source,row['material_roles']);slot_names,uv=base.native_attributes(source)
    obj=next(n for n in build.reader.fbx_nodes(source)if n[0]==b'Objects');geo=next(n for n in obj[2]if n[0]==b'Geometry')
    smoothing=next(n for n in geo[2]if n[0]==b'LayerElementSmoothing');smooth=next(n[1][0]for n in smoothing[2]if n[0]==b'Smoothing')
    assert not any(n[0]==b'LayerElementColor'for n in geo[2]),'Preserve the existing absence of vertex colors'
    new=[];new_uv=[];new_normals=[];new_smooth=[];changed=[];retained=[]
    for i,(role,p,n)in enumerate(before):
        assert len(p)==3
        outside,inside=build.split_face(p.tolist(),mask)
        if not inside:
            new.append(p);new_uv.extend(uv[i*3:i*3+3]);new_normals.extend(n);new_smooth.append(smooth[i]);retained.append(i);continue
        changed.append(i)
        matrix=np.vstack([p.T,np.ones(3)])
        for face in outside:
            q=np.asarray(face,float)
            for k in range(1,len(q)-1):
                tri=q[[0,k,k+1]];weights=np.linalg.lstsq(matrix,np.vstack([tri.T,np.ones(3)]),rcond=None)[0].T
                normals=weights@n;normals/=np.linalg.norm(normals,axis=1)[:,None]
                new.append(tri);new_uv.extend(weights@uv[i*3:i*3+3]);new_normals.extend(normals);new_smooth.append(smooth[i])
    assert len(changed)==71 and all(i in changed for i in range(1038,1045))
    vertices=np.asarray(new).reshape(-1,3);indices=np.arange(len(vertices));indices[2::3]=-indices[2::3]-1
    for field,values in [(b'Vertices',vertices),(b'PolygonVertexIndex',indices),(b'Normals',new_normals),
                         (b'NormalsIndex',np.arange(len(vertices))),(b'UV',new_uv),(b'UVIndex',np.arange(len(vertices))),(b'Smoothing',new_smooth)]:
        material.patch_array(target,field,values)
    after=base.native(target,row['material_roles']);after_slots,after_uv=base.native_attributes(target)
    assert after_slots==slot_names==row['material_roles']
    actual=Counter(fingerprint(p)for role,p,n in after)
    for i in retained:assert actual[fingerprint(before[i][1])]>0
    old_shape=unary_union([Polygon(p[:,:2])for r,p,n in before]);new_shape=unary_union([Polygon(p[:,:2])for r,p,n in after])
    outside_error=old_shape.difference(mask).symmetric_difference(new_shape).area
    inside_remaining=new_shape.intersection(mask.buffer(-.000001)).area
    assert outside_error<1e-7 and inside_remaining<1e-9,(outside_error,inside_remaining)
    # Native decoded arrays must preserve every untouched corner attribute.
    by_geometry={fingerprint(p):(p,n,after_uv[j*3:j*3+3])for j,(r,p,n)in enumerate(after)}
    for i in retained:
        p,n,t=by_geometry[fingerprint(before[i][1])]
        assert np.array_equal(p,before[i][1])and np.array_equal(n,before[i][2])and np.array_equal(t,uv[i*3:i*3+3])
    report=dict(success=True,crossing_id='Crossing_04',road_id=crossing['road_id'],mesh_name=NAME,
        approved_previous_sha256=OLD_SHA,final_fbx_sha256=build.transport.revision.sha(target),
        mask=mapping(mask),mask_source='Union of the 115 approved adjacent C08 ramp faces; 0.2mm float guard',
        affected_previous_native_face_indices=changed,untouched_native_faces_exact=len(retained),
        untouched_faces_normals_uv_exact=True,vertex_color_layer_absent_before_and_after=True,
        triangles_before=len(before),triangles_after=len(after),removed_projected_area_m2=old_shape.difference(new_shape).area,
        outside_clip_difference_m2=outside_error,remaining_ballast_in_mask_m2=inside_remaining,
        surface_heights_unchanged=True,road_ramp_and_steel_files_unchanged=True,other_crossings_unchanged=True,
        source_before_backup=before_path.relative_to(ROOT).as_posix(),
        diagnosis=dict(ramp_face=293,terrain_below_ramp_range_m=[.11257197519993367,.37499834886775285],
                       ballast_above_ramp_max_m=.0664178932261068,penetrating_ballast_faces=list(range(1038,1045))))
    shutil.copy2(target,source)
    row.update(sha256=report['final_fbx_sha256'],approved_previous_sha256=OLD_SHA,corridor_residual_cleanup=True,
               triangles=len(after),vertices=len(vertices),bounds_m=[[float(vertices[:,i].min()),float(vertices[:,i].max())]for i in range(3)])
    manifest['corridor_residual_cleanup']=dict(audit='residual_ballast_validation.json',mesh_name=NAME,roads_ramps_rails_unchanged=True)
    manifest.setdefault('initial_phase_source_generated_triangles',manifest['source_generated_triangles'])
    manifest['source_generated_triangles']=sum(r['triangles']for r in manifest['meshes'])
    build.transport.revision.write(SOURCE/'manifest.json',manifest);build.transport.revision.write(SOURCE/'residual_ballast_validation.json',report)
    print('CROSSING_BALLAST_READY',row['sha256'],'triangles',len(after),'retained',len(retained),'removed_m2',report['removed_projected_area_m2'],flush=True)

if __name__=='__main__':main()
