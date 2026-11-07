"""Apply the 111 source-proven conveyor/symbol corrections in the existing map.

Run apply(unreal) in the live editor after ending PIE, or verify(unreal) in an
owned process. The entire candidate is checked before any level is saved.
"""
from pathlib import Path
import sys
import shutil

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).parent))
import apply_mpr_conveyor_repair as old
import rebuild_preservation as guard
import mpr_scene_patch_guard as patch

MAP=old.MAP
SRC=ROOT/'SourceAssets/MPR/conveyor_audit_20261107'
OUT=ROOT/'Saved/MPR/full_workflow_20261107/conveyor_application'
DEST='/Game/MPRWarehouse/ConveyorAudit20261107/Meshes'


def reviewed_manifest():
    source=patch.read(SRC/'patch_manifest.json')
    assert source['map']==MAP and source['replacement_count']==111
    assert len(source['replace'])==111
    assert len({x['source_handle'] for x in source['replace']})==111
    result=dict(removals=[],replacements=[])
    old.DEST=DEST
    for row in source['replace']:
        r=row['remove']
        result['replacements'].append(dict(
            old_instances=[dict(actor_guid=r['actor_guid'],actor_label=r['actor_label'],
                component_name=r['component_name'],instance_index=r['instance_index'],
                original_transform=r['expected_transform'],old_pose=dict(mesh=r['expected_mesh_path'].split('.')[-1]))],
            new_instances=[row['add']]))
    return result


def import_meshes(u):
    meshes={}
    for row in patch.read(SRC/'MPR_CADConveyorAudit.json')['meshes']:
        path=DEST+'/'+row['name']
        assert not u.EditorAssetLibrary.does_asset_exist(path),'Refuse overwriting existing asset: '+path
        task=u.AssetImportTask()
        task.filename=str(ROOT/row['fbx']);task.destination_path=DEST;task.destination_name=row['name']
        task.automated=True;task.replace_existing=False;task.save=False
        opts=u.FbxImportUI();opts.import_mesh=True;opts.import_as_skeletal=False
        opts.import_materials=False;opts.import_textures=False;opts.import_animations=False
        opts.mesh_type_to_import=u.FBXImportType.FBXIT_STATIC_MESH;opts.automated_import_should_detect_type=False
        d=opts.static_mesh_import_data
        d.combine_meshes=True;d.auto_generate_collision=False;d.generate_lightmap_u_vs=False
        d.convert_scene=True;d.convert_scene_unit=True;d.force_front_x_axis=False
        d.vertex_color_import_option=u.VertexColorImportOption.IGNORE
        d.normal_import_method=u.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
        task.options=opts;task.factory=u.FbxFactory()
        u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        mesh=u.EditorAssetLibrary.load_asset(path);assert mesh
        slots=mesh.get_editor_property('static_materials')
        assert len(slots)==len(row['material_roles'])
        for i,s in enumerate(slots):
            role=str(s.get_editor_property('imported_material_slot_name')).removeprefix('M_Zcool_')
            assert role in row['material_roles']
            mat=None
            for p in [f'/Game/MPRWarehouse/Materials/MI_MPR_HISM_M_Zcool_{role}',f'/Game/GHSZcoolSmartFactory/Materials/M_Zcool_{role}']:
                candidate=u.EditorAssetLibrary.load_asset(p)
                if candidate and u.MaterialEditingLibrary.has_material_usage(candidate,u.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES):
                    mat=candidate;break
            assert mat,'No compatible existing material '+role
            s.material_interface=mat;slots[i]=s
        mesh.set_editor_property('static_materials',slots)
        b=mesh.get_bounds();actual=[[b.origin.x-b.box_extent.x,b.origin.x+b.box_extent.x],
            [b.origin.y-b.box_extent.y,b.origin.y+b.box_extent.y],[b.origin.z-b.box_extent.z,b.origin.z+b.box_extent.z]]
        src=row['bounds_m'];expected=[[src[0][0]*100,src[0][1]*100],[-src[1][1]*100,-src[1][0]*100],[src[2][0]*100,src[2][1]*100]]
        assert max(abs(a-b) for aa,bb in zip(actual,expected) for a,b in zip(aa,bb))<.1,(row['name'],actual,expected)
        meshes[mesh.get_path_name()]=mesh
    assert len(meshes)==4
    return meshes


def apply(u):
    assert not any(w.get_name().startswith('UEDPIE_') for w in u.ObjectIterator(u.World)),'End PIE first'
    before=guard.capture(u,ROOT,MAP);guard.assert_clean(before)
    baseline=patch.read(ROOT/'SourceAssets/MPR/sorter_simulation/validation/scene_after.json.gz')
    assert before['map_file_sha256']==baseline['map_file_sha256'],'Map changed since source review'
    assert not patch.differences([patch.normalize(a,commandlet_compat=True) for a in baseline['actors']],
                                [patch.normalize(a,commandlet_compat=True) for a in before['actors']]),'Scene changed since audit'
    plan=old.derive_plan(before,reviewed_manifest())
    OUT.mkdir(parents=True,exist_ok=True)
    assert not (OUT/'after.json.gz').exists(),'Already applied; use verify'
    patch.write(OUT/'before.json.gz',before)
    shutil.copy2(old.MAP_FILE,OUT/'before_MPR.umap')
    hashes=guard.content_hashes(ROOT)
    subsystem=u.get_editor_subsystem(u.EditorActorSubsystem)
    actors={u.GuidLibrary.conv_guid_to_string(a.get_editor_property('actor_guid')):a for a in subsystem.get_all_level_actors()}
    properties={r['guid']:old.render_properties(u,actors[r['guid']]) for r in plan}
    imported=import_meshes(u);materials={}
    for row in plan:
        for path in row['partitions']:
            mesh=u.EditorAssetLibrary.load_asset(path)
            materials[path]=[s.material_interface.get_path_name() for s in mesh.static_materials]
            if path==row['component']['mesh']:
                assert materials[path]==row['component']['materials'],'Preserve existing material override'
    created={};render_after=dict(properties)
    with u.ScopedEditorTransaction('依据原CAD修复供包坡段和误建桌面'):
        for row in plan:
            actor=actors[row['guid']];primary=row['primary'];assert primary
            props=properties[row['guid']]
            old.fill(u,actor,primary,row['partitions'][primary],old.updated_tags(row['old']['tags'],len(row['partitions'][primary])),props)
            for mesh_path,trs in row['partitions'].items():
                if mesh_path==primary:continue
                bp=u.EditorAssetLibrary.load_asset(old.BP)
                new=subsystem.spawn_actor_from_class(bp.generated_class(),u.Vector())
                label='MPR_CADAudit_'+mesh_path.split('.')[-1]+'_'+row['guid'][:8]
                new.set_actor_label(label);new.set_folder_path('MPR/Operations')
                new.set_actor_tick_enabled(False);new.set_actor_enable_collision(False)
                old.fill(u,new,mesh_path,trs,['MPRWarehouse','mpr-cad-scene-v1','InstanceCount='+str(len(trs))],props)
                new.get_component_by_class(u.HierarchicalInstancedStaticMeshComponent).set_collision_profile_name('NoCollision')
                guid=u.GuidLibrary.conv_guid_to_string(new.get_editor_property('actor_guid'))
                created[guid]=dict(label=label,mesh=mesh_path,transforms=trs)
                render_after[guid]=props
    candidate=guard.capture(u,ROOT,MAP);patch.write(OUT/'candidate.json.gz',candidate)
    old.validate(before,candidate,plan,created,materials)
    assert old.sha(old.MAP_FILE)==before['map_file_sha256']
    assert all(old.sha(ROOT/p)==h for p,h in hashes.items()),'Existing content mutated before save'
    for mesh in imported.values():assert u.EditorAssetLibrary.save_loaded_asset(mesh,only_if_is_dirty=False)
    assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level()
    after=guard.capture(u,ROOT,MAP);guard.assert_clean(after)
    old.validate(before,after,plan,created,materials)
    assert all(old.sha(ROOT/p)==h for p,h in hashes.items() if p!='Content/Maps/MPR_CAD_Warehouse_B50B57.umap')
    patch.write(OUT/'after.json.gz',after)
    patch.write(OUT/'scope_plan.json',dict(plan=plan,created=created,materials=materials,render_after=render_after))
    report=dict(success=True,replacements=111,changed_existing_groups=len(plan),new_groups=len(created),
        preserved_actors=len(before['actors'])-len(plan),map_before=before['map_file_sha256'],map_after=after['map_file_sha256'],
        preserved_content_files=len(hashes)-1,imported_assets=list(imported))
    patch.write(OUT/'apply_report.json',report)
    return report


def verify(u):
    assert '-own' in u.SystemLibrary.get_command_line().lower()
    assert u.EditorLoadingAndSavingUtils.load_map(MAP)
    actual=guard.capture(u,ROOT,MAP);guard.assert_clean(actual)
    before=patch.read(OUT/'before.json.gz');after=patch.read(OUT/'after.json.gz');contract=patch.read(OUT/'scope_plan.json')
    assert actual['map_file_sha256']==after['map_file_sha256']
    old.validate(before,actual,contract['plan'],contract['created'],contract['materials'],reload=True)
    actors={u.GuidLibrary.conv_guid_to_string(a.get_editor_property('actor_guid')):a for a in u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors()}
    for guid,properties in contract['render_after'].items():
        assert old.render_properties(u,actors[guid])==properties,(guid,'render settings changed after reload')
    patch.write(OUT/'reload_report.json',dict(success=True,map_sha256=actual['map_file_sha256'],actors=len(actual['actors'])))


if __name__=='__main__':
    import unreal as u
    if '-mprfullconveyorapply' in u.SystemLibrary.get_command_line().lower():
        assert u.EditorLoadingAndSavingUtils.load_map(MAP)
        print(apply(u))
    else:verify(u)
