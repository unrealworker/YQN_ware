"""Remove the reviewed outer city road; retain live actors and exact outside faces.

No Unreal/Git calls. Works on the live 860-actor baseline and current crossing
FBX sources. The 18 already-deleted user actors are never recreated.
"""
import copy,gzip,json,shutil,hashlib,math
from collections import Counter
import finish_mpr_crossing_material as binary
import numpy as np
from shapely.geometry import LineString,Point,Polygon,box,mapping
from shapely.ops import unary_union

base=binary.base;build=base.build;ROOT=base.ROOT
OUT=ROOT/'SourceAssets/MPR/city_road_removal_20261106'
DEST='/Game/MPRWarehouse/CityRoadRemoval20261106/Meshes/'
BASELINE=ROOT/'Saved/MPR/road_solar_20261106/live_before.json.gz'
RESTORE_NAMES={f'SM_MPRR_RailCorridor_{x}_{y}'for x,y in build.TILES}|{f'SM_MPRR_Rail_{x}_{y}_Sleepers'for x,y in build.TILES}

def key(p):return tuple(sorted(tuple(float(v)for v in q)for q in p))
def sha(p):return build.transport.revision.sha(p)

def mesh(row):
    path=ROOT/row['fbx'];faces=base.native(path,row['material_roles']);names,uv=base.native_attributes(path)
    assert names==row['material_roles']
    obj=next(n for n in build.reader.fbx_nodes(path)if n[0]==b'Objects');geo=next(n for n in obj[2]if n[0]==b'Geometry')
    smoothing=next(n for n in geo[2]if n[0]==b'LayerElementSmoothing');smooth=next(n[1][0]for n in smoothing[2]if n[0]==b'Smoothing')
    colors=binary.colors(path)if any(n[0]==b'LayerElementColor'for n in geo[2])else None
    result=[];offset=0
    for i,(role,p,n)in enumerate(faces):
        count=len(p);result.append(dict(role=role,p=p,n=n,uv=uv[offset:offset+count],color=colors[offset:offset+count]if colors is not None else None,smooth=int(smooth[i])))
        offset+=count
    return result

def part(face,points):
    p=face['p'];q=np.asarray(points,float)
    if np.array_equal(p,q):return face
    # Pieces from a non-planar quad follow the generator's original triangle fan.
    if len(p)>3:
        center=q.mean(0)
        for k in range(1,len(p)-1):
            ids=[0,k,k+1];tri=p[ids]
            if Polygon(tri[:,:2]).area>1e-12 and Polygon(tri[:,:2]).buffer(1e-7).covers(Point(center[:2])):
                return part({**face,'p':tri,'n':face['n'][ids],'uv':face['uv'][ids],
                             'color':face['color'][ids]if face['color']is not None else None},points)
    weights=np.linalg.lstsq(np.vstack([p.T,np.ones(len(p))]),np.vstack([q.T,np.ones(len(q))]),rcond=None)[0].T
    normals=weights@face['n'];normals/=np.maximum(np.linalg.norm(normals,axis=1)[:,None],1e-15)
    return dict(role=face['role'],p=q,n=normals,uv=weights@face['uv'],
                color=weights@face['color']if face['color']is not None else None,smooth=face['smooth'])

def clip(faces,mask,keep_inside=False):
    result=[];affected=[];retained=[]
    for i,f in enumerate(faces):
        outside,inside=build.split_face(f['p'].tolist(),mask)
        if inside:affected.append(i)
        if not inside and not keep_inside:result.append(f);retained.append(i);continue
        for p in inside if keep_inside else outside:result.append(part(f,p))
    return result,affected,retained

def projection(faces):
    return unary_union([Polygon(f['p'][:,:2])for f in faces if Polygon(f['p'][:,:2]).area>1e-11])

def write_mesh(row,faces,path):
    assert len(row['material_roles'])==1,'Changed multi-slot rows must be reviewed before export'
    shutil.copy2(ROOT/row['fbx'],path)
    vertices=np.concatenate([f['p']for f in faces]);normals=np.concatenate([f['n']for f in faces]);uv=np.concatenate([f['uv']for f in faces])
    counts=[len(f['p'])for f in faces];indices=np.arange(len(vertices));indices[np.cumsum(counts)-1]=-indices[np.cumsum(counts)-1]-1
    for field,values in [(b'Vertices',vertices),(b'PolygonVertexIndex',indices),(b'Normals',normals),
                         (b'NormalsIndex',np.arange(len(vertices))),(b'UV',uv),(b'UVIndex',np.arange(len(vertices))),
                         (b'Smoothing',[f['smooth']for f in faces])]:binary.patch_array(path,field,values)
    if faces[0]['color']is not None:
        colors=np.concatenate([f['color']for f in faces]);binary.patch_array(path,b'Colors',colors);binary.patch_array(path,b'ColorIndex',np.arange(len(vertices)))
    # Every retained written mesh has a single material and an AllSame mapping.
    binary.patch_array(path,b'Materials',[0])
    out=copy.deepcopy(row);out.update(fbx=path.relative_to(ROOT).as_posix(),sha256=sha(path),triangles=sum(n-2 for n in counts),vertices=len(vertices),
        bounds_m=[[float(vertices[:,i].min()),float(vertices[:,i].max())]for i in range(3)],approved_previous_sha256=row['sha256'])
    return out

def plan():
    layout=build.transport.revision.decode(build.transport.revision.read(build.transport.OUT/'layout.json'))
    c08=next(r for r in layout['road_centerlines']if r['id']=='TPX_ROADS_AXES_C08')
    be7=next(r for r in layout['road_centerlines']if r['id']=='TPX_ROADS_AXES_BE7')
    cut=min(range(len(be7['points_m'])),key=lambda i:Point(be7['points_m'][i]).distance(Point(275.58,-159.62)))
    assert cut==12
    lines=[LineString(c08['points_m']),LineString(be7['points_m'][:cut+1])]
    pavement=unary_union([line.buffer(3.25,cap_style=2,quad_segs=12)for line in lines])
    # 0.35m includes the existing 0.24m curbs and their native rounding. The
    # buffer only cleans the AA4 connection mouth; its lower branch is retained.
    mask=pavement.buffer(.35,quad_segs=12)
    initial=build.transport.revision.read(build.OUT/'geometry_audit.json')
    residual=build.transport.revision.read(build.OUT/'residual_ballast_validation.json')
    import shapely
    restore=shapely.geometry.shape(initial['scope']).union(shapely.geometry.shape(residual['mask']))
    assert restore.difference(mask).area<1e-7
    return layout,c08,be7,cut,pavement,mask,restore

def main():
    assert not (OUT/'manifest.json').exists(),'Existing deliverable: validate it instead of overwriting'
    OUT.mkdir(parents=True,exist_ok=True)
    live=json.loads(gzip.decompress(BASELINE.read_bytes()));assert len(live['actors'])==860
    bylabel={r['label']:r for r in live['actors']};old_rows=build.current_rows();rows=dict(old_rows)
    crossing=build.transport.revision.read(build.OUT/'manifest.json');rows.update({r['name']:r for r in crossing['meshes']})
    layout,c08,be7,cut,pavement,mask,restore=plan()
    original_hashes={r['fbx']:r['sha256']for r in rows.values()if r['name'].startswith(build.transport.revision.PREFIXES)}
    result=[];mappings=[];removals=[];audit_rows=[]
    for name,row in rows.items():
        if name not in bylabel:continue
        rail=name in RESTORE_NAMES
        if not rail and not name.startswith(build.transport.SURFACE_PREFIXES):continue
        bounds=row['bounds_m'];bbox=box(bounds[0][0],bounds[1][0],bounds[0][1],bounds[1][1])
        if not rail and not bbox.intersects(mask):continue
        source=mesh(row)
        if rail:
            # Locally restore only the bed/sleeper pieces previously removed
            # for Crossing04. Steel, alignment and the rest of this tile stay.
            outside,affected,retained=clip(source,restore)
            inside,_,_=clip(mesh(old_rows[name]),restore,True)
            output=outside+inside;change_mask=restore
        else:
            output,affected,retained=clip(source,mask);change_mask=mask
            if not affected:continue
        actor=bylabel[name];component=next(c for c in actor['components']if c.get('mesh'))
        mapping_row=dict(name=name,guid=actor['guid'],actor_path=actor['path'],component=component['name'],
            old_mesh=component['mesh'].split('.')[0],old_material_roles=row['material_roles'],old_source_sha256=row['sha256'])
        if not output or projection(output).area<1e-8 and not rail:
            removals.append(mapping_row);audit_rows.append(dict(name=name,removed=True,affected_faces=affected));continue
        path=OUT/(name+'.fbx');new_row=write_mesh(row,output,path);decoded=mesh(new_row)
        before_out=projection(source).difference(change_mask);after_out=projection(decoded).difference(change_mask)
        error=before_out.symmetric_difference(after_out).area
        assert error<1e-6,(name,'Outside footprint changed',error)
        counter=Counter(key(f['p'])for f in decoded)
        decoded_map={key(f['p']):f for f in decoded}
        for i in retained:
            f=source[i];assert counter[key(f['p'])]>0;g=decoded_map[key(f['p'])]
            for field in ['p','n','uv','color']:
                assert (f[field]is None and g[field]is None)or np.array_equal(f[field],g[field]),(name,'Untouched attribute changed',i,field)
        if not rail:assert projection(decoded).intersection(mask.buffer(-1e-6)).area<1e-8
        else:
            expected=projection(mesh(old_rows[name])).intersection(restore)
            assert expected.symmetric_difference(projection(decoded).intersection(restore)).area<1e-7
        mapping_row.update(new_mesh=DEST+name,new_material_roles=new_row['material_roles'])
        result.append(new_row);mappings.append(mapping_row)
        audit_rows.append(dict(name=name,rail_bed_or_sleepers_restored=rail,affected_faces=affected,untouched_faces_exact=len(retained),
            outside_difference_m2=error,untouched_positions_normals_uv_colors_exact=True,triangles_before=row['triangles'],triangles_after=new_row['triangles']))
    assert all(sha(ROOT/p)==h for p,h in original_hashes.items()),'Old source changed'
    assert all(m['name']in bylabel for m in mappings+removals)
    audit=dict(success=True,baseline_sha256=sha(BASELINE),live_actor_count=860,removal_mask=mapping(mask),rail_restore_mask=mapping(restore),
        removed_road_ids=[c08['id']],trimmed_road_id=be7['id'],trimmed_road_new_start_m=be7['points_m'][cut],
        removal_centerline_length_m=LineString(c08['points_m']).length+LineString(be7['points_m'][:cut+1]).length,
        aa4_branch_preserved=True,rail_steel_and_centerlines_unchanged=True,old_source_hashes=original_hashes,meshes=audit_rows,
        user_deleted_actors_not_recreated=True,actor_additions=0,source_triangles=sum(r['triangles']for r in result))
    manifest=dict(schema_version=1,map='/Game/Maps/MPR_CAD_Warehouse_B50B57',namespace=DEST.rsplit('/Meshes/',1)[0],
        meshes=result,mesh_mappings=mappings,remove_mesh_names=[m['name']for m in removals],removals=removals,
        baseline='Saved/MPR/road_solar_20261106/live_before.json.gz',source_generated_triangles=audit['source_triangles'],audit='geometry_validation.json')
    revised=copy.deepcopy(layout);revised['road_centerlines']=[r for r in revised['road_centerlines']if r['id']!=c08['id']]
    for r in revised['road_centerlines']:
        if r['id']==be7['id']:r['points_m']=r['points_m'][cut:];r['length_m']=LineString(r['points_m']).length
    for field in ['roads','curbs','white_edges','dash_lines']:revised[field]=revised[field].difference(mask)
    revised['crossings']=[c for c in revised['crossings']if c['road_id']!=c08['id']]
    revised['audit']['city_road_removal']='2026-11-06 C08 and first BE7 segment removed; steel/AA4 branch retained'
    build.transport.revision.write(OUT/'layout.json',build.transport.revision.encode(revised))
    build.transport.revision.write(OUT/'geometry_validation.json',audit);build.transport.revision.write(OUT/'manifest.json',manifest)
    print('CITY_ROAD_REMOVAL_READY',len(result),'replacements',len(removals),'removals',audit['source_triangles'],'triangles',flush=True)

if __name__=='__main__':main()
