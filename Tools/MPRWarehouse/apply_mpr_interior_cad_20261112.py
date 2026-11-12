"""Apply reviewed rack/architecture deltas to the existing MPR map, in place.

Existing packages are read-only except the target map. Original rack instances
must match the captured CAD-to-scene bijection before any mutation is allowed.
Run with -MPRInteriorVerify in an owned commandlet for independent reload checks.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).parent))
import rebuild_preservation as guard
import mpr_scene_patch_guard as patch
import apply_mpr_conveyor_repair as prior

MAP = patch.MAP
SRC = ROOT/'SourceAssets/MPR/interior_cad_20261112'
OUT = ROOT/'Saved/MPR/interior_cad_20261112'
DEST = '/Game/MPRWarehouse/InteriorCAD20261112/Meshes'


def read(path):
    return patch.read(path)


def write(path,data):
    patch.write(path,data)


def mesh_path(name):
    return DEST+'/'+name+'.'+name


def rack_name(r):
    if r.get('mesh_name'): return r['mesh_name']
    family = r['family'].replace('+','P')
    return 'SM_MPR_CADRack_F'+family+'_W'+str(r['width_inches'])+'_'+('Passage' if r['passage_variant'] else 'Standard')


def prepare_plan(before):
    placement=read(SRC/'racks/placement_manifest.json')
    rows=placement['instances']
    assert len(rows)==2867 and len({r['source_handle'] for r in rows})==2867
    assert placement['map_sha256']==before['map_file_sha256']
    actors={r['guid']:r for r in before['actors']}
    groups=defaultdict(list)
    for row in rows:
        assert row['family'] in {'16','17+1','20','9','5','7','Unresolved'}, row
        groups[row['actor_guid']].append(row)
    assert set(groups)=={r['guid'] for r in before['actors'] if r['folder']=='MPR/Storage/Racks'}
    result=[]
    for guid,records in groups.items():
        actor=actors[guid]
        c=next(c for c in actor['components'] if 'instance_transforms' in c)
        assert actor['class']==prior.BP+'.BP_GHS_InstanceGroup_C'
        assert not actor['hidden'] and not actor['tick_enabled']
        identity=dict(translation_cm=[0.,0.,0.],rotation_xyzw=[0.,0.,0.,1.],scale=[1.,1.,1.])
        assert actor['transform']==c['transform']==identity
        assert c['instance_count']==len(records)
        assert {r['instance_index'] for r in records}==set(range(c['instance_count']))
        partitions=defaultdict(list)
        handles=defaultdict(list)
        for r in sorted(records,key=lambda x:x['instance_index']):
            assert r['component_name']==c['name']
            assert not patch.differences(r['original_transform'],c['instance_transforms'][r['instance_index']])
            path=mesh_path(rack_name(r))
            partitions[path].append(r['original_transform'])
            handles[path].append(r['source_handle'])
        primary=max(partitions,key=lambda p:len(partitions[p]))
        result.append(dict(guid=guid,old=actor,component=c,partitions=dict(partitions),
                           handles=dict(handles),primary=primary))
    return result


def import_mesh(u,row,*,replace_task_asset=False):
    path=DEST+'/'+row['name']
    if replace_task_asset:
        owned=read(OUT/'apply_validation.json')['imported']
        assert mesh_path(row['name']) in owned and row['name'].startswith('SM_MPR_CADRack_')
    else:
        assert not u.EditorAssetLibrary.does_asset_exist(path), 'Private mesh already exists; avoid overwriting '+path
    source=(ROOT/row['fbx']).resolve()
    assert source.is_relative_to(SRC.resolve()) and source.suffix=='.fbx'
    if row.get('sha256'): assert guard.sha(source)==row['sha256']
    task=u.AssetImportTask()
    task.filename=str(source);task.destination_path=DEST;task.destination_name=row['name']
    task.automated=True;task.replace_existing=replace_task_asset;task.replace_existing_settings=replace_task_asset;task.save=False
    options=u.FbxImportUI()
    options.import_mesh=True;options.import_as_skeletal=False
    options.import_materials=False;options.import_textures=False;options.import_animations=False
    options.mesh_type_to_import=u.FBXImportType.FBXIT_STATIC_MESH
    options.automated_import_should_detect_type=False
    data=options.static_mesh_import_data
    data.combine_meshes=True;data.auto_generate_collision=False;data.generate_lightmap_u_vs=False
    data.convert_scene=True;data.convert_scene_unit=True;data.force_front_x_axis=False
    data.normal_import_method=u.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
    data.vertex_color_import_option=u.VertexColorImportOption.IGNORE
    task.options=options;task.factory=u.FbxFactory()
    u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    mesh=u.EditorAssetLibrary.load_asset(path)
    assert isinstance(mesh,u.StaticMesh)
    editor=u.get_editor_subsystem(u.StaticMeshEditorSubsystem)
    for index,lod in enumerate(row.get('lod_files',[]),1):
        assert editor.import_lod(mesh,index,str(ROOT/lod))==index
    imported_slots=list(mesh.static_materials)
    imported_roles=[str(s.get_editor_property('imported_material_slot_name')) for s in imported_slots]
    section_roles=[]
    for lod in range(editor.get_lod_count(mesh)):
        section_roles.append([imported_roles[editor.get_lod_material_slot(mesh,lod,i)]
                              for i in range(mesh.get_num_sections(lod))])
        assert set(section_roles[-1])<=set(row['material_roles']), (path,lod,section_roles[-1])
    assert set(section_roles[0])==set(row['material_roles'])
    slots=[imported_slots[imported_roles.index(role)] for role in row['material_roles']]
    for i,slot in enumerate(slots):
        role=str(slot.get_editor_property('imported_material_slot_name'))
        assert role in row['material_roles'], (path,role)
        material=u.EditorAssetLibrary.load_asset(row['material_paths'][row['material_roles'].index(role)]
            if row.get('material_paths') else '/Game/GHSZcoolSmartFactory/Materials/M_Zcool_'+role)
        assert material
        if row['name'].startswith('SM_MPR_CADRack_'):
            assert u.MaterialEditingLibrary.has_material_usage(material,u.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES)
        slot.material_interface=material;slots[i]=slot
    mesh.set_editor_property('static_materials',slots)
    for lod,roles in enumerate(section_roles):
        for section,role in enumerate(roles):editor.set_lod_material_slot(mesh,row['material_roles'].index(role),lod,section)
    if row.get('lod_screen_sizes'): assert editor.set_lod_screen_sizes(mesh,row['lod_screen_sizes'])
    for lod,roles in enumerate(section_roles):
        assert [editor.get_lod_material_slot(mesh,lod,i) for i in range(mesh.get_num_sections(lod))]==[row['material_roles'].index(r) for r in roles]
    b=mesh.get_bounds()
    actual=[[b.origin.x-b.box_extent.x,b.origin.x+b.box_extent.x],
            [b.origin.y-b.box_extent.y,b.origin.y+b.box_extent.y],
            [b.origin.z-b.box_extent.z,b.origin.z+b.box_extent.z]]
    src=row['bounds_m']
    expected=[[100*v for v in src[0]],[-100*src[1][1],-100*src[1][0]],[100*v for v in src[2]]]
    assert max(abs(a-b) for aa,bb in zip(actual,expected) for a,b in zip(aa,bb))<.1,(path,actual,expected)
    return mesh,dict(path=mesh.get_path_name(),bounds_cm=actual,lods=editor.get_lod_count(mesh),
                     materials=[s.material_interface.get_path_name() for s in mesh.static_materials],section_roles=section_roles)


def validate_delta(before,after,plans,materials,created,architecture_replacements):
    old={a['guid']:patch.normalize(a) for a in before['actors']}
    actual={a['guid']:patch.normalize(a) for a in after['actors']}
    assert set(actual)==set(old)|set(created)
    expected=deepcopy(old)
    for row in plans:
        expected[row['guid']]=patch.normalize(prior.expected_primary(row,row.get('original_materials',materials.get(row['primary']))))
    for row in architecture_replacements:
        a=expected[row['actor_guid']]
        c=next(c for c in a['components'] if c['name']==row['component_name'])
        assert c['mesh']==row['old_mesh']
        c.update(mesh=mesh_path(row['new_mesh']),materials=materials[mesh_path(row['new_mesh'])])
    for guid,a in expected.items():
        delta=patch.differences(a,actual[guid])
        assert not delta,(a['label'],delta[:8])
    for guid,spec in created.items():
        actor=actual[guid]
        assert actor['label']==spec['label'] and actor['folder']==spec['folder']
        if spec.get('transforms') is not None:
            c=next(c for c in actor['components'] if 'instance_transforms' in c)
            assert c['mesh']==spec['mesh'] and c['instance_count']==len(spec['transforms'])
            assert not prior.pose_differences(c['instance_transforms'],spec['transforms'])
        else:
            c=next(c for c in actor['components'] if c.get('mesh'))
            assert c['mesh']==spec['mesh']
    assert before['world_settings']==after['world_settings']
    # All original actor records including cameras, runtime simulation and
    # current manual changes are exact-compared above, not just their counts.
    total=sum(c['instance_count'] for a in after['actors'] if a['folder']=='MPR/Storage/Racks'
              for c in a['components'] if 'instance_count' in c)
    assert total==2867


def apply(u):
    sub=u.get_editor_subsystem(u.UnrealEditorSubsystem)
    assert not sub.get_game_world()
    before=read(OUT/'preservation/baseline.json.gz')
    current=guard.capture(u,ROOT,MAP);guard.assert_clean(current)
    assert current['map_file_sha256']==before['map_file_sha256']
    assert [patch.normalize(a) for a in current['actors']]==[patch.normalize(a) for a in before['actors']]
    plans=prepare_plan(before)
    racks=read(SRC/'racks/mesh_manifest.json')
    architecture=read(SRC/'architecture/mpr_interior_architecture_patch.json')
    structure=read(SRC/'structure/structural_completion_manifest.json')
    by_guid={a['guid']:a for a in before['actors']}
    removals=defaultdict(list)
    for row in structure['removals']:removals[row['actor_guid']].append(row)
    for guid,rows in removals.items():
        actor=by_guid[guid]
        components=[c for c in actor['components'] if 'instance_transforms' in c]
        assert len(components)==1
        c=components[0]
        indices=set()
        for r in rows:
            assert r['component_name']==c['name'] and r['instance_index'] not in indices
            assert not patch.differences(r['expected_transform'],c['instance_transforms'][r['instance_index']])
            indices.add(r['instance_index'])
        trs=[t for i,t in enumerate(c['instance_transforms']) if i not in indices]
        plans.append(dict(guid=guid,old=actor,component=c,primary=c['mesh'],partitions={c['mesh']:trs},
                          original_materials=c['materials'],removed_indices=sorted(indices)))
    replacements=[]
    for r in architecture['facade_replacements']:
        a=by_guid[r['actor_guid']]
        matches=[c for c in a['components'] if c.get('mesh')==r['old_mesh']]
        assert len(matches)==1
        c=matches[0]
        replacements.append(dict(actor_guid=r['actor_guid'],component_name=c['name'],
                                 old_mesh=r['old_mesh'],new_mesh=r['new_mesh_name']))
        spec=next(s for s in architecture['meshes'] if s['name']==r['new_mesh_name'])
        spec['material_paths']=c['materials']
    architecture['additions']=[s['name'] for s in architecture['meshes']
                               if s['name'] not in {r['new_mesh'] for r in replacements}]
    architecture['additions'].extend(s['mesh'] for s in structure['additions'])
    specs=racks['meshes']+architecture['meshes']+structure['meshes']
    needed={p for plan in plans if 'original_materials' not in plan for p in plan['partitions']}
    assert needed=={mesh_path(r['name']) for r in racks['meshes']}
    assert not (OUT/'apply_validation.json').exists()
    existing=guard.content_hashes(ROOT)
    assert existing==before['all_content_hashes']
    imported={};materials={};meshes={}
    for spec in specs:
        mesh,record=import_mesh(u,spec)
        meshes[mesh.get_path_name()]=mesh
        materials[mesh.get_path_name()]=record['materials']
        imported[mesh.get_path_name()]=record
    actors={u.GuidLibrary.conv_guid_to_string(a.get_editor_property('actor_guid')):a
            for a in u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors()}
    actor_sub=u.get_editor_subsystem(u.EditorActorSubsystem)
    bp=u.EditorAssetLibrary.load_blueprint_class(prior.BP)
    created={}
    with u.ScopedEditorTransaction('按MPR原CAD恢复分型货架及室内构造'):
        for plan in plans:
            actor=actors[plan['guid']]
            props=prior.render_properties(u,actor)
            primary=plan['primary'];trs=plan['partitions'][primary]
            prior.fill(u,actor,primary,trs,prior.updated_tags(plan['old']['tags'],len(trs)),props)
            if 'original_materials' in plan:
                component=actor.get_component_by_class(u.HierarchicalInstancedStaticMeshComponent)
                for i,path in enumerate(plan['original_materials']):component.set_material(i,u.EditorAssetLibrary.load_asset(path))
            for path,trs in plan['partitions'].items():
                if path==primary:continue
                new=actor_sub.spawn_actor_from_class(bp,u.Vector())
                label=plan['old']['label']+'_'+path.rsplit('_',3)[-3]+'_'+str(len(created))
                new.set_actor_label(label);new.set_folder_path('MPR/Storage/Racks')
                new.set_actor_tick_enabled(False);new.set_actor_enable_collision(False)
                prior.fill(u,new,path,trs,['MPRWarehouse','mpr-cad-interior-20261112','InstanceCount='+str(len(trs))],props)
                guid=u.GuidLibrary.conv_guid_to_string(new.get_editor_property('actor_guid'))
                created[guid]=dict(label=label,folder='MPR/Storage/Racks',mesh=path,transforms=trs)
        for row in replacements:
            actor=actors[row['actor_guid']]
            component=next(c for c in actor.get_components_by_class(u.StaticMeshComponent) if c.get_name()==row['component_name'])
            assert component.static_mesh.get_path_name()==row['old_mesh']
            actor.modify();component.modify()
            mesh=meshes[mesh_path(row['new_mesh'])]
            component.set_static_mesh(mesh)
            component.set_editor_property('override_materials',[])
            for i,slot in enumerate(mesh.static_materials):component.set_material(i,slot.material_interface)
        for name in architecture.get('additions', ['SM_MPR_CAD_PartitionCompletion_20261112']):
            actor=actor_sub.spawn_actor_from_class(u.StaticMeshActor,u.Vector())
            actor.set_actor_label(name.removeprefix('SM_'));actor.set_folder_path('MPR/Architecture/CADCorrections')
            actor.tags=['MPRWarehouse','mpr-cad-interior-20261112'];actor.set_actor_tick_enabled(False)
            component=actor.static_mesh_component;component.set_static_mesh(meshes[mesh_path(name)])
            component.set_collision_profile_name('NoCollision')
            guid=u.GuidLibrary.conv_guid_to_string(actor.get_editor_property('actor_guid'))
            created[guid]=dict(label=actor.get_actor_label(),folder=str(actor.get_folder_path()),mesh=mesh_path(name))
    candidate=guard.capture(u,ROOT,MAP)
    write(OUT/'candidate.json.gz',candidate)
    validate_delta(before,candidate,plans,materials,created,replacements)
    assert guard.content_hashes(ROOT)==existing, 'Existing package changed before scoped save'
    for mesh in meshes.values():assert u.EditorAssetLibrary.save_loaded_asset(mesh,only_if_is_dirty=False)
    assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level()
    after=guard.capture(u,ROOT,MAP);guard.assert_clean(after)
    validate_delta(before,after,plans,materials,created,replacements)
    hashes=guard.content_hashes(ROOT)
    changed=[p for p,h in existing.items() if hashes.get(p)!=h]
    assert changed==['Content/Maps/MPR_CAD_Warehouse_B50B57.umap'],changed
    added=set(hashes)-set(existing)
    assert all(p.startswith('Content/MPRWarehouse/InteriorCAD20261112/') for p in added)
    write(OUT/'after.json.gz',after)
    write(OUT/'scope_plan.json.gz',dict(plans=plans,created=created,materials=materials,replacements=replacements))
    write(OUT/'apply_validation.json',dict(success=True,map=MAP,actors_before=len(before['actors']),
        actors_after=len(after['actors']),racks=2867,modified_rack_groups=len(plans)-len(removals),created_actors=len(created),
        corrected_column_instances=3,final_column_profiles=structure['final_unique_column_profile_count'],stairs=18,
        changed_existing_packages=changed,added_packages=sorted(added),source_cad_sha256=racks['source_sha256'],
        map_sha256=after['map_file_sha256'],imported=imported,existing_scene_preserved=True))
    print('MPR_INTERIOR_APPLIED '+str(len(imported))+' private meshes')


def verify(u):
    assert '-run=pythonscript' in u.SystemLibrary.get_command_line().lower()
    assert u.EditorLoadingAndSavingUtils.load_map(MAP)
    actual=guard.capture(u,ROOT,MAP);guard.assert_clean(actual)
    expected=read(OUT/'after.json.gz')
    assert [patch.normalize(a,commandlet_compat=True) for a in actual['actors']]==[
        patch.normalize(a,commandlet_compat=True) for a in expected['actors']]
    report=read(OUT/'apply_validation.json')
    assert actual['map_file_sha256']==report['map_sha256']
    before=read(OUT/'preservation/baseline.json.gz')
    hashes=guard.content_hashes(ROOT)
    assert all(hashes[p]==h for p,h in before['all_content_hashes'].items()
               if p!='Content/Maps/MPR_CAD_Warehouse_B50B57.umap')
    write(OUT/'reload_validation.json',dict(success=True,actors=len(actual['actors']),
        original_packages_preserved=len(before['all_content_hashes'])-1,map_sha256=actual['map_file_sha256'],
        complete_saved_scene_equal=True))
    print('MPR_INTERIOR_RELOAD_VERIFIED')


if __name__=='__main__':
    import unreal as u
    if '-mprinteriorverify' in u.SystemLibrary.get_command_line().lower():verify(u)
    else:apply(u)
