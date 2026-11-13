"""Precisely patch source 2D457E in the existing MPR map, then independently verify.

In an owned UE process use -MPRConnectionApply to apply; without that flag this
only reloads and verifies. Existing shared meshes and all unrelated Actors are
protected. Target indices are resolved from GUID + component + exact transform,
so preceding legitimate edits do not make archived HISM indices unsafe.
"""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).parent))
import apply_mpr_conveyor_repair as old
import rebuild_preservation as guard
import mpr_scene_patch_guard as patch

MAP=old.MAP
SRC=ROOT/'SourceAssets/MPR/conveyor_connection_20261113'
OUT=ROOT/'Saved/MPR/conveyor_connection_20261113/application'
DEST='/Game/MPRWarehouse/ConveyorConnection20261113/Meshes'
NAME='SM_MPR_CAD_2D457E_Connected'
LABEL='MPR_CAD_2D457E_Connected'
MESH=DEST+'/'+NAME+'.'+NAME


def digest(value):
    def stable(v):
        if isinstance(v,float):return round(v,6)
        if isinstance(v,list):return [stable(x) for x in v]
        if isinstance(v,dict):return {k:stable(x) for k,x in v.items()}
        return v
    return hashlib.sha256(json.dumps(stable(value),sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def signatures(snapshot):
    return {a['guid']:digest(patch.normalize(a,commandlet_compat=True)) for a in snapshot['actors']}


def plan_for(before):
    rows=patch.read(SRC/'replacement_targets.json')
    assert len(rows)==12 and all(r['source_handles']==['2D457E'] for r in rows)
    actors={a['guid']:a for a in before['actors']}
    removals=[]
    for row in rows:
        assert len(row['snapshot_matches'])==1
        target=row['snapshot_matches'][0]
        actor=actors[target['guid']]
        assert actor['label']==target['actor_label']
        components=[c for c in actor['components'] if c['name']==target['component']]
        assert len(components)==1
        component=components[0]
        assert component['mesh']==target['mesh_path']
        matches=[i for i,tr in enumerate(component['instance_transforms'])
                 if not old.pose_differences([tr],[target['transform']])]
        assert len(matches)==1,('Source instance changed or ambiguous; refusing automatic relocation',target,matches)
        removals.append(dict(actor_guid=target['guid'],actor_label=actor['label'],
            component_name=component['name'],instance_index=matches[0],
            original_transform=component['instance_transforms'][matches[0]],
            old_pose=dict(mesh='SM_MPR_Conveyor2m')))
    assert len({(r['actor_guid'],r['instance_index']) for r in removals})==12
    plan=old.derive_plan(before,dict(removals=removals,replacements=[]))
    assert len(plan)==2 and all(row['primary'] and len(row['partitions'])==1 for row in plan)
    return plan


def import_mesh(u):
    manifest=patch.read(SRC/'MPR_ConveyorConnection_20261113.json')
    assert manifest['source_handle']=='2D457E' and manifest['branch_count']==10
    assert len(manifest['meshes'])==1
    row=manifest['meshes'][0]
    assert row['name']==NAME and row['triangles']<25000
    assert not u.EditorAssetLibrary.does_asset_exist(DEST+'/'+NAME),'Private asset already exists; verify completed application before retrying'
    task=u.AssetImportTask()
    task.filename=str(ROOT/row['fbx']);task.destination_path=DEST;task.destination_name=NAME
    task.automated=True;task.replace_existing=False;task.save=False
    opts=u.FbxImportUI();opts.import_mesh=True;opts.import_as_skeletal=False
    opts.import_materials=False;opts.import_textures=False;opts.import_animations=False
    opts.mesh_type_to_import=u.FBXImportType.FBXIT_STATIC_MESH;opts.automated_import_should_detect_type=False
    data=opts.static_mesh_import_data
    data.combine_meshes=True;data.auto_generate_collision=False;data.generate_lightmap_u_vs=False
    data.convert_scene=True;data.convert_scene_unit=True;data.force_front_x_axis=False
    data.vertex_color_import_option=u.VertexColorImportOption.IGNORE
    data.normal_import_method=u.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
    task.options=opts;task.factory=u.FbxFactory()
    u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    mesh=u.EditorAssetLibrary.load_asset(DEST+'/'+NAME);assert mesh
    slots=mesh.get_editor_property('static_materials')
    assert len(slots)==len(row['material_roles'])
    for i,s in enumerate(slots):
        role=str(s.get_editor_property('imported_material_slot_name')).removeprefix('M_Zcool_')
        assert role in row['material_roles']
        mat=None
        for path in [f'/Game/MPRWarehouse/Materials/MI_MPR_HISM_M_Zcool_{role}',f'/Game/GHSZcoolSmartFactory/Materials/M_Zcool_{role}']:
            if not u.EditorAssetLibrary.does_asset_exist(path):
                continue
            candidate=u.EditorAssetLibrary.load_asset(path)
            if candidate and u.MaterialEditingLibrary.has_material_usage(candidate,u.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES):
                mat=candidate;break
        assert mat,'Missing existing HISM material '+role
        s.material_interface=mat;slots[i]=s
    mesh.set_editor_property('static_materials',slots)
    b=mesh.get_bounds();actual=[[b.origin.x-b.box_extent.x,b.origin.x+b.box_extent.x],
        [b.origin.y-b.box_extent.y,b.origin.y+b.box_extent.y],[b.origin.z-b.box_extent.z,b.origin.z+b.box_extent.z]]
    src=row['bounds_m'];expected=[[src[0][0]*100,src[0][1]*100],[-src[1][1]*100,-src[1][0]*100],[src[2][0]*100,src[2][1]*100]]
    assert max(abs(a-b) for aa,bb in zip(actual,expected) for a,b in zip(aa,bb))<.1,(actual,expected)
    return mesh,row


def apply(u):
    assert '-own' in u.SystemLibrary.get_command_line().lower(),'Use an owned process; preserve the live editor'
    assert not any(w.get_name().startswith('UEDPIE_') for w in u.ObjectIterator(u.World))
    assert not (OUT/'apply_report.json').exists(),'Already applied; use verify'
    before=guard.capture(u,ROOT,MAP);guard.assert_clean(before)
    baseline=patch.read(OUT/'dryrun_report.json')
    assert before['map_file_sha256']==baseline['map_sha256'],'Map changed after dry run; repeat dry run against current map'
    assert signatures(before)==patch.read(OUT/'before_actor_signatures.json'),'Live scene changed after dry run'
    assert not any(a['label']==LABEL for a in before['actors'])
    plan=plan_for(before)
    hashes=guard.content_hashes(ROOT)
    subsystem=u.get_editor_subsystem(u.EditorActorSubsystem)
    actors={u.GuidLibrary.conv_guid_to_string(a.get_editor_property('actor_guid')):a for a in subsystem.get_all_level_actors()}
    props={r['guid']:old.render_properties(u,actors[r['guid']]) for r in plan}
    materials={}
    for row in plan:
        mesh=u.EditorAssetLibrary.load_asset(row['primary'])
        materials[row['primary']]=[s.material_interface.get_path_name() for s in mesh.static_materials]
        assert materials[row['primary']]==row['component']['materials'],'Existing custom material override requires explicit preservation'
    mesh,geometry=import_mesh(u)
    materials[MESH]=[s.material_interface.get_path_name() for s in mesh.static_materials]
    identity=dict(translation_cm=[0.,0.,0.],rotation_xyzw=[0.,0.,0.,1.],scale=[1.,1.,1.])
    with u.ScopedEditorTransaction('恢复CAD入库摆轮中央主线和十条分流接驳'):
        for row in plan:
            trs=row['partitions'][row['primary']]
            old.fill(u,actors[row['guid']],row['primary'],trs,
                     old.updated_tags(row['old']['tags'],len(trs)),props[row['guid']])
        bp=u.EditorAssetLibrary.load_asset(old.BP)
        actor=subsystem.spawn_actor_from_class(bp.generated_class(),u.Vector())
        actor.set_actor_label(LABEL);actor.set_folder_path('MPR/Operations')
        actor.set_actor_tick_enabled(False);actor.set_actor_enable_collision(False)
        newprops=dict(props[plan[0]['guid']]);newprops['cast_shadow']=True
        old.fill(u,actor,MESH,[identity],['MPRWarehouse','mpr-cad-scene-v1','InstanceCount=1'],newprops)
        actor.get_component_by_class(u.HierarchicalInstancedStaticMeshComponent).set_collision_profile_name('NoCollision')
        guid=u.GuidLibrary.conv_guid_to_string(actor.get_editor_property('actor_guid'))
    created={guid:dict(label=LABEL,mesh=MESH,transforms=[identity])}
    candidate=guard.capture(u,ROOT,MAP)
    old.validate(before,candidate,plan,created,materials,reload=True)
    assert all(guard.sha(ROOT/p)==h for p,h in hashes.items()),'Existing content changed before save'
    assert u.EditorAssetLibrary.save_loaded_asset(mesh,only_if_is_dirty=False)
    assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level()
    after=guard.capture(u,ROOT,MAP);guard.assert_clean(after)
    old.validate(before,after,plan,created,materials,reload=True)
    existing_changes=[p for p,h in hashes.items() if guard.sha(ROOT/p)!=h]
    assert existing_changes==['Content/Maps/MPR_CAD_Warehouse_B50B57.umap'],existing_changes
    props[guid]=newprops
    # One compact verification contract; no frame sequences or duplicate dumps.
    patch.write(OUT/'verification_contract.json',dict(actor_signatures=signatures(after),
        world_settings=after['world_settings'],coverage=patch.normalized_coverage(after['world_actor_coverage'],commandlet_compat=True),
        render_properties=props,mesh=MESH,map_sha256=after['map_file_sha256'],
        resolved_targets=[dict(guid=r['guid'],label=r['old']['label'],indices=r['selected_indices']) for r in plan]))
    report=dict(success=True,source_handle='2D457E',removed_instances=12,changed_existing_actors=2,
        added_instances=1,added_actors=1,new_mesh_triangles=geometry['triangles'],
        untouched_actors=len(before['actors'])-2,preserved_content_files=len(hashes)-1,
        existing_packages_changed=existing_changes,map_before=before['map_file_sha256'],map_after=after['map_file_sha256'],
        new_asset=MESH,branches=10,kept_independent_lines=['2D4587','2D45D9'])
    patch.write(OUT/'apply_report.json',report)
    return report


def dryrun(u):
    before=guard.capture(u,ROOT,MAP);guard.assert_clean(before)
    plan=plan_for(before)
    assert not u.EditorAssetLibrary.does_asset_exist(MESH)
    report=dict(success=True,map_sha256=before['map_file_sha256'],actors=len(before['actors']),
        resolved_targets=[dict(guid=r['guid'],label=r['old']['label'],indices=r['selected_indices'],
            instances_before=r['component']['instance_count'],instances_after=len(r['partitions'][r['primary']])) for r in plan],
        new_asset=MESH,source_handle='2D457E',writes_to_scene=False)
    patch.write(OUT/'dryrun_report.json',report)
    patch.write(OUT/'before_actor_signatures.json',signatures(before))
    return report


def verify(u):
    assert '-own' in u.SystemLibrary.get_command_line().lower()
    assert u.EditorLoadingAndSavingUtils.load_map(MAP)
    actual=guard.capture(u,ROOT,MAP);guard.assert_clean(actual)
    expected=patch.read(OUT/'verification_contract.json')
    assert actual['map_file_sha256']==expected['map_sha256']
    assert signatures(actual)==expected['actor_signatures'],'Reload changed an actor or instance'
    assert actual['world_settings']==expected['world_settings']
    assert patch.normalized_coverage(actual['world_actor_coverage'],commandlet_compat=True)==expected['coverage']
    actors={u.GuidLibrary.conv_guid_to_string(a.get_editor_property('actor_guid')):a for a in u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors()}
    for guid,p in expected['render_properties'].items():
        assert old.render_properties(u,actors[guid])==p
    report=dict(success=True,map_sha256=actual['map_file_sha256'],actors_checked=len(actual['actors']),source_handle='2D457E')
    patch.write(OUT/'reload_report.json',report)
    return report


if __name__=='__main__':
    import unreal as u
    if '-mprconnectiondryrun' in u.SystemLibrary.get_command_line().lower():
        assert u.EditorLoadingAndSavingUtils.load_map(MAP)
        print('MPR_CONNECTION_DRYRUN',dryrun(u))
    elif '-mprconnectionapply' in u.SystemLibrary.get_command_line().lower():
        assert u.EditorLoadingAndSavingUtils.load_map(MAP)
        print('MPR_CONNECTION_APPLY',apply(u))
    else:
        print('MPR_CONNECTION_VERIFY',verify(u))
