"""Check exact retained faces, clipped footprint and actual rail/deck clearance."""
import gzip,json
from collections import Counter
import build_mpr_crossing_surface as build
import numpy as np
import shapely
from shapely.geometry import Polygon,Point
from shapely.ops import unary_union
from validate_mpr_transport_revision import tris,Surface

def fingerprint(role,points):return(role,tuple(sorted(tuple(float(v)for v in p)for p in points)))
def projected(faces):return unary_union([Polygon(np.asarray(p)[:,:2])for role,p in faces if Polygon(np.asarray(p)[:,:2]).area>1e-11])
def unpack(roles):return[(role,[vv[i]for i in face])for role,(vv,ff)in roles.items()for face in ff]
def triangles(faces):
    return np.asarray([[points[0],points[i],points[i+1]]for role,points in faces for i in range(1,len(points)-1)],float)

def main():
    with gzip.open(build.OUT/'geometry_payload.json.gz','rt',encoding='utf8')as f:payload=json.load(f)
    audit=payload['audit'];scope=shapely.geometry.shape(audit['scope']);rows=build.current_rows()
    prior=build.transport.revision.read(build.OUT/'geometry_validation.json')if (build.OUT/'geometry_validation.json').exists()else{}
    residual=build.transport.revision.read(build.OUT/'residual_material_validation.json')if (build.OUT/'residual_material_validation.json').exists()else None
    ballast=build.transport.revision.read(build.OUT/'residual_ballast_validation.json')if (build.OUT/'residual_ballast_validation.json').exists()else None
    ballast_mask=shapely.geometry.shape(ballast['mask'])if ballast else None
    allowed=set(residual['approved_material_only_face_geometry_keys'])if residual else set()
    if residual:
        from finish_mpr_crossing_material import face_key
        assert residual['success']and residual['positions_and_faces_exact']and residual['uv_exact']and residual['edge_fade_colors_exact']
    report=dict(success=False,initial_phase_retained_faces={},clip_checks={})
    for path,digest in audit['source_hashes'].items():assert build.transport.revision.sha(build.ROOT/path)==digest,path
    assert set(payload['geometry'])==set(build.NAMES)and not payload['instances']
    painted=[]
    for name,roles in payload['geometry'].items():
        old=build.read_faces(rows[name]);new=unpack(roles);counter=Counter(fingerprint(role,p)for role,p in new)
        kept=0
        for role,p in old:
            outside,inside=build.split_face(p,scope)
            if inside:continue
            assert counter[fingerprint(role,p)]>0,('Untouched face missing or changed',name)
            counter[fingerprint(role,p)]-=1;kept+=1
        report['initial_phase_retained_faces'][name]=kept
        old_surface=projected(old);new_surface=projected(new)
        delta=old_surface.difference(scope).symmetric_difference(new_surface.difference(scope))
        assert delta.buffer(-.00001).area<1e-8,(name,'Nonlocal surface changed',delta.area)
        paint=name.startswith(('SM_MPRR_CrossingDeck_','SM_MPRR_CrossingRamp_'))
        if paint:
            assert old_surface.symmetric_difference(new_surface).buffer(-.00001).area<1e-8
            remaining=projected([(r,p)for r,p in new if r!=build.ROAD_ROLE]).intersection(scope.buffer(-.00001)).area
            assert remaining<1e-7,(name,'Old white surface remains',remaining)
            painted.extend([(r,p)for r,p in new if r==build.ROAD_ROLE])
            assert all(np.cross(np.asarray(p[1])-p[0],np.asarray(p[2])-p[0])[2]>0 for r,p in new),('Downward surface',name)
        else:
            remaining=new_surface.intersection(scope.buffer(-.00001)).area
            assert remaining<1e-7,(name,'Ballast/sleepers remain in road',remaining)
        report['clip_checks'][name]=dict(outside_scope_difference_m2=delta.area,inside_unwanted_surface_m2=remaining)
    if (build.OUT/'manifest.json').exists():
        manifest=build.transport.revision.read(build.OUT/'manifest.json')
        assert manifest['source_generated_triangles']==sum(r['triangles']for r in manifest['meshes']),'Stale final source triangle total'
        assert {r['name']for r in manifest['meshes']}==set(payload['geometry'])
        native_painted=[];native_kept=0;material_updates=[];ballast_updates=[]
        final_hashes={row['name']:row['sha256']for row in manifest['meshes']}
        if residual:assert final_hashes[residual['mesh_name']]==residual['final_fbx_sha256']
        if ballast:assert ballast['success']and final_hashes[ballast['mesh_name']]==ballast['final_fbx_sha256']
        for row in manifest['meshes']:
            new=build.read_faces(row)
            counter=Counter(fingerprint(role,p)for role,p in new)
            for original_face_index,(role,p) in enumerate(build.read_faces(rows[row['name']])):
                outside,inside=build.split_face(p,scope)
                if inside:continue
                if counter[fingerprint(role,p)]>0:
                    counter[fingerprint(role,p)]-=1;native_kept+=1
                elif ballast and row['name']==ballast['mesh_name']:
                    outside,inside=build.split_face(p,ballast_mask)
                    assert inside,('Unapproved ballast face change',row['name'],original_face_index)
                    ballast_updates.append(dict(mesh=row['name'],original_source_face_index=original_face_index,
                        reason='Explicit residual ballast clip under the approved C08 ramp faces',material_unchanged=True))
                else:
                    assert residual and row['name']==residual['mesh_name']and role=='MPR3_Asphalt'and face_key(p)in allowed
                    assert counter[fingerprint(build.ROAD_ROLE,p)]>0,('Unapproved nonlocal face change',row['name'],original_face_index)
                    counter[fingerprint(build.ROAD_ROLE,p)]-=1
                    material_updates.append(dict(mesh=row['name'],original_source_face_index=original_face_index,
                        geometry_key=face_key(p),old_material=role,new_material=build.ROAD_ROLE,positions_and_face_exact=True))
            wanted=unpack(payload['geometry'][row['name']])
            migrated=unary_union([Polygon(np.asarray(p)[:,:2])for role,p in new if residual and row['name']==residual['mesh_name']and face_key(p)in allowed])
            for role in row['material_roles']:
                expected=projected([(r,p)for r,p in wanted if r==role])
                if residual and row['name']==residual['mesh_name']:
                    if role=='MPR3_Asphalt':expected=expected.difference(migrated)
                    if role==build.ROAD_ROLE:expected=expected.union(migrated)
                if ballast and row['name']==ballast['mesh_name']:expected=expected.difference(ballast_mask)
                delta=expected.symmetric_difference(projected([(r,p)for r,p in new if r==role]))
                assert delta.buffer(-.0002).area<1e-7,('FBX material-region mismatch',row['name'],role)
            if row['name'].startswith(('SM_MPRR_CrossingDeck_','SM_MPRR_CrossingRamp_')):
                native_painted.extend([(r,p)for r,p in new if r==build.ROAD_ROLE])
            if ballast and row['name']==ballast['mesh_name']:
                assert projected(new).intersection(ballast_mask.buffer(-.000001)).area<1e-9,'Residual ballast remains under the approved ramp patch'
        painted=native_painted
        report['native_fbx_validation']=dict(meshes=len(manifest['meshes']),untouched_faces_exact=native_kept,
            triangles=sum(r['triangles']for r in manifest['meshes']),all_material_regions_match=True,
            initial_phase_source_triangles=manifest.get('initial_phase_source_generated_triangles',manifest['source_generated_triangles']),
            phase='Final crossing plan including explicitly approved adjacent C08 material faces'if residual else'Initial F97 crossing scope',
            original_retained_faces_with_approved_material_changes=material_updates,
            original_retained_faces_with_approved_ballast_clips=ballast_updates,final_fbx_sha256=final_hashes)
    surface=Surface(triangles(painted));clearances=[]
    for tile in build.TILES:
        name=f'SM_MPRR_Rail_{tile[0]}_{tile[1]}_Rails'
        for role,points in build.read_faces(rows[name]):
            if role!='MPR3_RailSteel':continue
            for i in range(1,len(points)-1):
                p=np.asarray([points[0],points[i],points[i+1]],float)
                n=np.cross(p[1]-p[0],p[2]-p[0])
                if n[2]<=.5*np.linalg.norm(n):continue
                poly=Polygon(p[:,:2]).intersection(scope)
                for index in surface.index.query(poly,predicate='intersects'):
                    q=surface.triangles[index];qn=surface.normals[index]
                    overlap=poly.intersection(surface.shapes[index])
                    # The difference between two triangle planes is linear;
                    # checking every overlap-polygon vertex proves its minimum.
                    for part in build.pieces(overlap):
                        for x,y in part.exterior.coords:
                            rail_z=p[0,2]-(n[0]*(x-p[0,0])+n[1]*(y-p[0,1]))/n[2]
                            road_z=q[0,2]-(qn[0]*(x-q[0,0])+qn[1]*(y-q[0,1]))/qn[2]
                            clearances.append(rail_z-road_z)
    clearance=np.asarray(clearances)
    assert len(clearance)>50 and float(clearance.min())>.005,('Rails would sink into crossing surface',float(clearance.min()))
    report.update(success=True,source_bytes_unchanged=True,steel_meshes_unmodified=True,old_surface_heights_preserved=True,
        rail_top_clearance_m=dict(samples=len(clearance),minimum=float(clearance.min()),maximum=float(clearance.max())),
        payload_sha256=build.transport.revision.sha(build.OUT/'geometry_payload.json.gz'))
    if residual:
        report['residual_material_cleanup']=residual
        report['initial_phase_native_fbx_validation']=prior.get('initial_phase_native_fbx_validation',{})
    if ballast:report['residual_ballast_cleanup']=ballast
    if (build.OUT/'ramp_normals_validation.json').exists():report['ramp_normals_refinement']=build.transport.revision.read(build.OUT/'ramp_normals_validation.json')
    build.transport.revision.write(build.OUT/'geometry_validation.json',report)
    print('CROSSING_SURFACE_VALIDATED',report.get('native_fbx_validation',{}).get('untouched_faces_exact'),
        'approved material updates',len(report.get('native_fbx_validation',{}).get('original_retained_faces_with_approved_material_changes',[])),report['rail_top_clearance_m'])

if __name__=='__main__':main()
