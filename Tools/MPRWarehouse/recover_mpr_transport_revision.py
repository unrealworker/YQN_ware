"""Finish the reviewed import after its successful one-mesh compatibility probe.

Preserve both failed attempts and the original backup. Reuse the 66 verified
geometries; repair their saved import/collision settings, then import the last 23.
Only publish the canonical result after preservation and full file-scope checks.
"""
from pathlib import Path
import json
import sys
import traceback

sys.path.insert(0, str(Path(__file__).parent))
import apply_mpr_transport_revision as t
import probe_mpr_transport_colors as colors


def run():
    import unreal as u
    import import_mpr_scene as core
    root=t.ROOT; out=root/t.OUTPUT; report=out/'transport_recovery_complete.json'
    t.require(not report.exists(), 'Recovery already attempted; inspect its report')
    result=dict(success=False,phase='preflight',map=t.guard.MAP,namespace=t.guard.DEST,
                added_actor_guids=[],added_actors=[],changed_meshes=[],final_map_saved=False,
                source_files_modified=False,materials_modified=False,assets_deleted=False,
                maps_switched=False,imported_meshes=[],mesh_settings=[],mesh_assets_saved=[])
    old_core=None
    def progress(phase):
        result['phase']=phase; t.write(report,result)
    try:
        manifest=t.read(root/t.REVISION/'manifest.json')
        base=t.read(root/t.SOURCE/'manifest.json')
        ownership=t.read(root/t.SOURCE/'scene_ownership.json')
        rows,removed_names=t.validate_manifest(root,manifest,base)
        t.require(len(rows)==89, 'Unexpected revision size')
        probe=t.read(out/'transport_color_probe.json')
        t.require(probe['success'] and probe['vertex_colors']['matches_original_fade'], 'Single-mesh probe did not pass')
        first=t.read(out/'transport_apply.json'); second=t.read(out/'transport_resume_apply.json')
        t.require(not first['success'] and not second['success'] and second['completed_meshes']==65,
                  'Unexpected interrupted state')
        t.require(rows[65]['name']==probe['mesh_name']==second['current_mesh'], 'Probe does not match failed mesh')
        baseline=t.read(out/'transport_before.json')
        initial_files=t.read(out/'transport_content_before.json')
        sources=t.read(out/'transport_sources_before.json')
        t.require(t.source_inventory(root)==sources, 'Source files changed')
        expected_files=t.read(out/'transport_color_probe_content_after.json')
        current_files,_=t.retirement.inventory(root)
        prior_recovery=t.read(out/'transport_recovery_apply.json')
        t.require(not prior_recovery['success'] and prior_recovery['completed_meshes']==2
            and 'Triangle count differs: SM_MPRR_Rail_0_-3_Rails' in prior_recovery['error'], 'Unexpected recovery checkpoint')
        # The first attempt finalized exactly three metadata/collision records.
        partial_allowed={'Content/MPRWarehouse/RebuildB50B57/Site/Meshes/'+r['name']+'.uasset' for r in rows[:3]}
        t.content_scope(expected_files,current_files,partial_allowed)
        native_before={r['name']:r['metadata']['render_triangles'] for r in t.read(out/'transport_import_settings_audit.json')['meshes']}
        for name,info in t.read(out/'transport_backup/manifest.json').items():
            t.require(t.sha(out/'transport_backup'/name)==info['sha256']==initial_files[name]['sha256'],
                      'Original backup changed: '+name)
        observed,_,_,_=colors.current_scene_contract(u,root)
        material_changes=t.planned_effective_material_changes(baseline,rows,base,ownership)
        contract=dict(success=True,map_sha256_before=baseline['map_file_sha256'],
            map_sha256_after=observed['map_file_sha256'],removed_actor_guids=[],added_actor_guids=[],
            added_actors=[],actor_material_changes=material_changes)
        t.validation.compare_snapshot(baseline,observed,ownership,base,contract,manifest)
        removed,absent=t.plan_removals(baseline,removed_names,base,ownership)
        packages=[t.guard.DEST+'/Site/Meshes/'+row['name'] for row in rows]
        affected={a['guid'] for a in baseline['actors'] if any(c.get('mesh') and c['mesh'].split('.')[0] in packages for c in a['components'])}
        overrides=t.capture_overrides(u,core.A,affected)
        t.require(overrides==first['actor_material_overrides_before'], 'User material overrides changed')
        history={name:t.sha(out/name) for name in ['transport_apply.json','transport_resume_apply.json','transport_color_probe.json']}
        t.write(out/'transport_apply_failed_interchange_final.json',first)
        t.write(out/'transport_apply_failed_legacy_settings.json',second)
        result.update(map_sha256_before=baseline['map_file_sha256'],mesh_count=89,
            removed_actor_guids=removed,already_absent_removal_packages=absent,
            actor_material_changes=material_changes,actor_material_overrides_before=overrides,
            revision_manifest_sha256=t.sha(root/t.REVISION/'manifest.json'),
            geometry_audit_sha256=t.sha(root/t.REVISION/'geometry_audit.json'),
            recovery_evidence_hashes=history,color_probe_sha256=t.sha(out/'transport_color_probe.json'),completed_meshes=0)
        old_core={key:getattr(core,key) for key in ('ROOT','DEST','MATS','MESHES','result','material')}
        core.ROOT=root;core.DEST=t.guard.DEST;core.MESHES={};core.result=dict(meshes=[])
        materials={role:core.load(t.guard.DEST+'/Materials/MI_'+role) for row in rows for role in row['material_roles']}
        core.MATS=materials
        def readonly_material(role):
            t.require(role in materials,'Unexpected material role');return materials[role]
        core.material=readonly_material
        progress('finishing_meshes')
        with t.legacy_fbx_import(u):
            for index,row in enumerate(rows):
                package=packages[index];mesh=core.load(package)
                changes=t.configure_saved_import_data(u,mesh,row)
                if index>=66:
                    mesh=core.import_mesh(row,'Site')
                settings=t.finalize_transport_mesh(u,mesh)
                t.require(not t.configure_saved_import_data(u,mesh,row),'Import settings reverted')
                b=mesh.get_bounds()
                actual=[[b.origin.x-b.box_extent.x,b.origin.x+b.box_extent.x],
                    [b.origin.y-b.box_extent.y,b.origin.y+b.box_extent.y],
                    [b.origin.z-b.box_extent.z,b.origin.z+b.box_extent.z]]
                v=row['bounds_m'];expected=[[v[0][0]*100,v[0][1]*100],[-v[1][1]*100,-v[1][0]*100],[v[2][0]*100,v[2][1]*100]]
                t.require(max(abs(a-b) for aa,bb in zip(actual,expected) for a,b in zip(aa,bb))<2,'Geometry bounds differ')
                # UE may remove zero-area FBX triangles. Reused geometry must
                # match its independent pre-recovery native count exactly.
                if index<66:t.require(mesh.get_num_triangles(0)==native_before[row['name']], 'Reused geometry changed: '+row['name'])
                else:t.require(0<mesh.get_num_triangles(0)<=row['triangles'],'Invalid imported triangle count')
                t.require([s.material_interface.get_path_name() for s in mesh.static_materials]==
                    [materials[role].get_path_name() for role in row['material_roles']], 'Mesh materials differ')
                result['mesh_settings'].append(dict(name=row['name'],changes=changes,performance=settings))
                result['imported_meshes'].append(dict(name=row['name'],path=package,bounds_cm=actual,
                    source_triangles=row['triangles'],render_triangles=mesh.get_num_triangles(0),lod_count=core.SM.get_lod_count(mesh),
                    material_slots=len(mesh.static_materials),reused_verified_geometry=index<66))
                result['mesh_assets_saved'].append(package)
                result.update(completed_meshes=index+1,current_mesh=row['name']);progress('finishing_meshes')
        after=t.guard.capture(u,root,t.guard.MAP)
        t.validation.compare_snapshot(baseline,after,ownership,base,contract,manifest)
        t.require(t.capture_overrides(u,core.A,affected)==overrides,'Actor overrides changed')
        live={u.GuidLibrary.conv_guid_to_string(a.get_editor_property('actor_guid')):a for a in core.A.get_all_level_actors()}
        progress('removing_reviewed_transport_actors')
        for guid in removed:t.require(core.A.destroy_actor(live[guid]),'Cannot remove planned actor')
        contract['removed_actor_guids']=removed
        after=t.guard.capture(u,root,t.guard.MAP)
        t.validation.compare_snapshot(baseline,after,ownership,base,contract,manifest)
        t.guard.assert_clean(after,allow_new_map=True)
        t.require(t.source_inventory(root)==sources,'Source files changed during recovery')
        progress('saving_current_map')
        t.require(core.L.save_current_level(),'Cannot save map')
        result['final_map_saved']=True
        final=t.guard.capture(u,root,t.guard.MAP);t.guard.assert_clean(final)
        contract['map_sha256_after']=final['map_file_sha256']
        state=t.validation.compare_snapshot(baseline,final,ownership,base,contract,manifest)
        t.require(t.capture_overrides(u,core.A,affected)==overrides,'Final overrides changed')
        files,_=t.retirement.inventory(root)
        allowed={t.MAP_FILE}|{'Content/'+p.removeprefix('/Game/')+'.uasset' for p in packages}
        changes=t.content_scope(initial_files,files,allowed)
        t.validation.check_retirement(root,t.read(out/'legacy_delete.json'),{n:r['after_sha256'] for n,r in changes.items()})
        t.require(t.source_inventory(root)==sources,'Source files changed before final report')
        for name,value in history.items():t.require(t.sha(out/name)==value,'Recovery history changed')
        for package in packages:
            name='Content/'+package.removeprefix('/Game/')+'.uasset'
            result['changed_meshes'].append(dict(package=package,before_sha256=initial_files[name]['sha256'],after_sha256=files[name]['sha256']))
        t.write(out/'transport_after.json',final)
        result.update(success=True,phase='complete',map_sha256_after=final['map_file_sha256'],
            modified_files=changes,preservation=state,source_file_count=len(sources),
            source_files_sha256=t.guard.digest(sources),other_content_unchanged=True,
            before_snapshot_sha256=t.sha(out/'transport_before.json'),after_snapshot_sha256=t.sha(out/'transport_after.json'),
            removed_mesh_packages_retained=[t.guard.DEST+'/Site/Meshes/'+name for name in removed_names],
            fbx_importer=dict(mode='legacy_fbx',flag_restored=True),
            backup_directory=str(out/'transport_backup'))
    except Exception:
        result.update(success=False,failed_phase=result['phase'],phase='failed',error=traceback.format_exc())
        print(result['error'],flush=True)
    finally:
        if old_core:
            for key,value in old_core.items():setattr(core,key,value)
    t.write(report,result)
    if result['success']:t.write(out/'transport_apply.json',result)
    print('MPR_TRANSPORT_RECOVERY',result['success'],result['phase'],flush=True)
    return result


if __name__=='__main__':run()
