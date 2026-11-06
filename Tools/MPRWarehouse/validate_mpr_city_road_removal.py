"""Independent source/layout/live-scope checks for the outer-road deletion."""
import gzip,json,hashlib
from collections import Counter
import build_mpr_city_road_removal as b
import numpy as np
import shapely
from shapely.geometry import Point,Polygon,LineString

def main():
    manifest=b.build.transport.revision.read(b.OUT/'manifest.json')
    audit=b.build.transport.revision.read(b.OUT/'geometry_validation.json')
    live=json.loads(gzip.decompress(b.BASELINE.read_bytes()));byguid={a['guid']:a for a in live['actors']}
    assert b.sha(b.BASELINE)==audit['baseline_sha256']and len(byguid)==860
    prior=b.build.current_rows();current=dict(prior)
    current.update({r['name']:r for r in b.build.transport.revision.read(b.build.OUT/'manifest.json')['meshes']})
    rows={r['name']:r for r in manifest['meshes']};mappings={m['name']:m for m in manifest['mesh_mappings']}
    removals={m['name']:m for m in manifest['removals']};mask=shapely.geometry.shape(audit['removal_mask']);restore=shapely.geometry.shape(audit['rail_restore_mask'])
    assert set(rows)==set(mappings)and set(removals)==set(manifest['remove_mesh_names'])and not set(rows)&set(removals)
    assert len(rows)==24 and len(removals)==6
    for path,digest in audit['old_source_hashes'].items():assert b.sha(b.ROOT/path)==digest,path
    checked=[];kept=0
    for name,m in {**mappings,**removals}.items():
        actor=byguid[m['guid']]
        assert actor['label']==name and actor['path']==m['actor_path']
        component=next(c for c in actor['components']if c['name']==m['component'])
        assert component['mesh'].split('.')[0]==m['old_mesh']
        old=b.mesh(current[name]);israil=name in b.RESTORE_NAMES;scope=restore if israil else mask
        if name in removals:
            assert b.projection(old).difference(mask).area<1e-8
            checked.append(dict(name=name,removed=True));continue
        row=rows[name];assert b.sha(b.ROOT/row['fbx'])==row['sha256']
        new=b.mesh(row);assert sum(len(f['p'])-2 for f in new)==row['triangles']
        assert m['new_mesh']==b.DEST+name and m['old_material_roles']==m['new_material_roles']==row['material_roles']
        assert all(np.isfinite(f[field]).all()for f in new for field in ['p','n','uv'])
        index={b.key(f['p']):f for f in new};exact=0
        for f in old:
            _,inside=b.build.split_face(f['p'].tolist(),scope)
            if inside:continue
            g=index[b.key(f['p'])]
            for field in ['p','n','uv','color']:
                assert (f[field]is None and g[field]is None)or np.array_equal(f[field],g[field]),(name,'Unchanged attribute',field)
            exact+=1
        kept+=exact
        outside=b.projection(old).difference(scope).symmetric_difference(b.projection(new).difference(scope)).area
        assert outside<1e-6,(name,'Outside area changed',outside)
        if israil:
            expected,_changed,_kept=b.clip(b.mesh(prior[name]),restore,True)
            actual,_changed,_kept=b.clip(new,restore,True)
            assert b.projection(expected).symmetric_difference(b.projection(actual)).area<1e-7
            # Exact 3D face membership also checks vertical sleeper sides and
            # non-planar native quads, which cannot use a single XY plane.
            native_counter=Counter(b.key(f['p'])for f in new)
            for f in expected:
                assert native_counter[b.key(f['p'])]>0,(name,'Restored source face/height missing')
                native_counter[b.key(f['p'])]-=1
        else:assert b.projection(new).intersection(mask.buffer(-1e-6)).area<1e-8
        checked.append(dict(name=name,unchanged_native_faces_with_exact_attributes=exact,triangles=row['triangles'],outside_difference_m2=outside))
    original,c08,be7,cut,_,_,_=b.plan();layout=b.build.transport.revision.decode(b.build.transport.revision.read(b.OUT/'layout.json'))
    assert c08['id']not in {r['id']for r in layout['road_centerlines']}
    assert next(r for r in layout['road_centerlines']if r['id']==be7['id'])['points_m']==be7['points_m'][cut:]
    assert original['rail_centerlines']==layout['rail_centerlines']
    aa4=next(r for r in original['road_centerlines']if r['id']=='TPX_ROADS_AXES_AA4')
    assert aa4==next(r for r in layout['road_centerlines']if r['id']==aa4['id'])
    mouth=LineString(aa4['points_m']).intersection(mask).length
    assert mouth<5.,'The downward AA4 branch was included by mistake'
    assert manifest['source_generated_triangles']==sum(r['triangles']for r in rows.values())
    report=dict(success=True,replacement_mesh_count=len(rows),removed_actor_count=len(removals),actor_additions=0,
        live_actor_count_before=860,expected_live_actor_count_after=854,user_deleted_actors_not_recreated=True,
        unchanged_native_faces_with_exact_attributes=kept,steel_source_hashes_unchanged=True,
        aa4_branch_source_unchanged=True,aa4_connection_mouth_cleaned_length_m=mouth,
        source_generated_triangles=manifest['source_generated_triangles'],meshes=checked,
        manifest_sha256=b.sha(b.OUT/'manifest.json'),limitation='Source validation; UE import and fixed-camera visual review are performed by the main task.')
    b.build.transport.revision.write(b.OUT/'validation.json',report)
    print('CITY_ROAD_REMOVAL_VALIDATED',len(rows),len(removals),'exact retained faces',kept,'AA4 mouth m',mouth)

if __name__=='__main__':main()
