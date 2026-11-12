"""Apply GHS cargo detail and exact CAD windows without touching sorter logic."""
from copy import deepcopy
from pathlib import Path
import hashlib,importlib,json,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).parent))
import apply_mpr_interior_cad_20261112 as base
base=importlib.reload(base)  # The editor keeps Python modules cached across asset passes.
guard=base.guard;patch=base.patch
OUT=base.OUT/'refinement'


def sim_properties(u):
    actors=u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors()
    actor=next(a for a in actors if isinstance(a,u.MPRSorterSimulationActor))
    keys=['layout_json','tower_mesh','tray_mesh','cart_meshes','parcel_material','active_material','full_material',
          'worker_skin_material','worker_cloth_material','worker_helmet_material','worker_boot_material',
          'worker_mesh','worker_idle','auto_start']
    result={}
    for key in keys:
        value=actor.get_editor_property(key)
        if isinstance(value,str):result[key]=hashlib.sha256(value.encode()).hexdigest()
        elif isinstance(value,bool):result[key]=value
        elif key=='cart_meshes':result[key]=[v.get_path_name() if v else None for v in value]
        else:result[key]=value.get_path_name() if value else None
    return result


def viewport(u):
    p,r=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_level_viewport_camera_info()
    return [p.x,p.y,p.z,r.pitch,r.yaw,r.roll]


def validate(before,after,expected,new_guid,new_mesh,materials):
    actual={a['guid']:patch.normalize(a) for a in after['actors']}
    assert set(actual)==set(expected)|{new_guid}
    for guid,row in expected.items():
        diff=patch.differences(row,actual[guid]);assert not diff,(row['label'],diff[:5])
    a=actual[new_guid]
    assert a['folder']=='MPR/Architecture/CADCorrections'
    assert a['transform']==dict(translation_cm=[0.,0.,0.],rotation_xyzw=[0.,0.,0.,1.],scale=[1.,1.,1.])
    c=next(c for c in a['components'] if c.get('mesh'))
    assert c['mesh']==new_mesh and c['materials']==materials
    assert c['collision_profile']=='NoCollision'
    assert before['world_settings']==after['world_settings']
    assert patch.normalized_coverage(before['world_actor_coverage'])==patch.normalized_coverage(after['world_actor_coverage'])


def apply(u, *, resume_imported=False):
    OUT.mkdir(parents=True,exist_ok=True)
    assert not u.get_editor_subsystem(u.UnrealEditorSubsystem).get_game_world(), 'Leave the running simulation intact; apply only in the editor world.'
    if resume_imported:
        assert not (OUT/'validation.json').exists()
        before=base.read(OUT/'before.json.gz')
        saved=base.read(OUT/'preserved_config.json')
        props,camera,hashes=saved['simulation'],saved['viewport'],saved['hashes']
        assert guard.content_hashes(ROOT)==hashes
        assert sim_properties(u)==props
        # A user may navigate the viewport between passes; preserve that latest view.
        camera=viewport(u)
        patch.write(OUT/'resume_viewport.json',camera)
    else:
        before=guard.capture(u,ROOT,base.MAP);guard.assert_clean(before)
        assert not (OUT/'before.json.gz').exists(),'Preserve original refinement checkpoint'
        props=sim_properties(u);camera=viewport(u)
        hashes=guard.content_hashes(ROOT)
        patch.write(OUT/'before.json.gz',before)
        patch.write(OUT/'preserved_config.json',dict(simulation=props,viewport=camera,hashes=hashes))
    windows=base.read(base.SRC/'windows/cad_windows_manifest.json')
    assert base.read(base.SRC/'windows/fbx_validation.json')['success']
    racks=base.read(base.SRC/'racks/mesh_manifest.json')
    expected={a['guid']:patch.normalize(a) for a in before['actors']}
    actors={u.GuidLibrary.conv_guid_to_string(a.get_editor_property('actor_guid')):a
            for a in u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors()}
    replacements=[]
    for r in windows['replacements']:
        old=expected[r['actor_guid']]
        assert old['label']==r['actor_label']
        c=next(c for c in old['components'] if c.get('mesh')==r['old_mesh'])
        assert c['materials']==r['preserve_material_overrides']
        spec=next(s for s in windows['meshes'] if s['name']==r['new_mesh_name'])
        spec['material_paths']=c['materials']
        replacements.append(dict(r,component_name=c['name']))
    for r in windows['removals']:
        a=expected[r['actor_guid']]
        assert a['label']==r['actor_label']
        assert [c['mesh'] for c in a['components'] if c.get('mesh')]==r['expected_meshes']
    glass=windows['additions'][0]['mesh_name']
    glass_spec=next(s for s in windows['meshes'] if s['name']==glass)
    glass_spec['material_paths']=[windows['material_bindings'][role] for role in glass_spec['material_roles']]
    meshes={};records={}
    for spec in racks['meshes']+windows['meshes']:
        if resume_imported:
            mesh=u.EditorAssetLibrary.load_asset(base.mesh_path(spec['name']))
            assert mesh
            roles=[str(s.get_editor_property('imported_material_slot_name')) for s in mesh.static_materials]
            materials=[s.material_interface.get_path_name() for s in mesh.static_materials]
            assert roles==spec['material_roles']
            paths=spec.get('material_paths') or ['/Game/GHSZcoolSmartFactory/Materials/M_Zcool_'+r for r in roles]
            assert materials==[u.EditorAssetLibrary.load_asset(p).get_path_name() for p in paths]
            editor=u.get_editor_subsystem(u.StaticMeshEditorSubsystem)
            b=mesh.get_bounds()
            record=dict(path=mesh.get_path_name(),materials=materials,lods=editor.get_lod_count(mesh),
                bounds_cm=[[b.origin.x-b.box_extent.x,b.origin.x+b.box_extent.x],
                           [b.origin.y-b.box_extent.y,b.origin.y+b.box_extent.y],
                           [b.origin.z-b.box_extent.z,b.origin.z+b.box_extent.z]],
                section_roles=[[roles[editor.get_lod_material_slot(mesh,lod,i)] for i in range(mesh.get_num_sections(lod))]
                               for lod in range(editor.get_lod_count(mesh))])
        else:
            mesh,record=base.import_mesh(u,spec,replace_task_asset=spec in racks['meshes'])
        meshes[mesh.get_path_name()]=mesh;records[mesh.get_path_name()]=record
    patch.write(OUT/'imported.json',records)
    actor_sub=u.get_editor_subsystem(u.EditorActorSubsystem)
    rack_groups=0
    with u.ScopedEditorTransaction('复用GHS小件货物并按CAD补齐窗位'):
        for guid,a in actors.items():
            old=expected[guid]
            if old['folder']!='MPR/Storage/Racks':continue
            c=a.get_component_by_class(u.HierarchicalInstancedStaticMeshComponent)
            path=c.static_mesh.get_path_name();assert path in meshes
            component_name=c.get_name()
            a.modify();c.modify()
            c.set_editor_property('override_materials',[s.material_interface for s in meshes[path].static_materials])
            next(x for x in old['components'] if x['name']==component_name)['materials']=records[path]['materials']
            rack_groups+=1
        for r in replacements:
            a=actors[r['actor_guid']]
            c=next(c for c in a.get_components_by_class(u.StaticMeshComponent) if c.get_name()==r['component_name'])
            a.modify();c.modify();path=base.mesh_path(r['new_mesh_name'])
            c.set_static_mesh(meshes[path])
            c.set_editor_property('override_materials',[s.material_interface for s in meshes[path].static_materials])
            ec=next(c for c in expected[r['actor_guid']]['components'] if c['name']==r['component_name'])
            ec.update(mesh=path,materials=records[path]['materials'])
        for r in windows['removals']:
            assert actor_sub.destroy_actor(actors[r['actor_guid']])
            del expected[r['actor_guid']]
        actor=actor_sub.spawn_actor_from_class(u.StaticMeshActor,u.Vector())
        actor.set_actor_label('MPR_CAD_WindowSystem_20261112');actor.set_folder_path('MPR/Architecture/CADCorrections')
        actor.tags=['MPRWarehouse','mpr-cad-interior-20261112'];actor.set_actor_tick_enabled(False)
        c=actor.static_mesh_component;c.set_static_mesh(meshes[base.mesh_path(glass)])
        c.set_collision_profile_name('NoCollision')
        guid=u.GuidLibrary.conv_guid_to_string(actor.get_editor_property('actor_guid'))
    after=guard.capture(u,ROOT,base.MAP)
    validate(before,after,expected,guid,base.mesh_path(glass),records[base.mesh_path(glass)]['materials'])
    assert sim_properties(u)==props and viewport(u)==camera
    assert guard.content_hashes(ROOT)==hashes,'Unexpected disk writes before validation'
    for mesh in meshes.values():assert u.EditorAssetLibrary.save_loaded_asset(mesh,only_if_is_dirty=False)
    assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level()
    after=guard.capture(u,ROOT,base.MAP);guard.assert_clean(after)
    validate(before,after,expected,guid,base.mesh_path(glass),records[base.mesh_path(glass)]['materials'])
    assert sim_properties(u)==props and viewport(u)==camera
    current=guard.content_hashes(ROOT)
    allowed={'Content/Maps/MPR_CAD_Warehouse_B50B57.umap'}|{
        'Content/'+base.DEST.removeprefix('/Game/')+'/'+r['name']+'.uasset' for r in racks['meshes']}
    changed={p for p,h in hashes.items() if current.get(p)!=h}
    assert changed<=allowed
    added=set(current)-set(hashes)
    assert added=={'Content/'+base.DEST.removeprefix('/Game/')+'/'+s['name']+'.uasset' for s in windows['meshes']}
    patch.write(OUT/'after.json.gz',after)
    patch.write(OUT/'validation.json',dict(success=True,actors=len(after['actors']),rack_groups=rack_groups,
        map_sha256=after['map_file_sha256'],cargo_provenance=racks['cargo_provenance'],windows=windows['pane_count'],
        deleted_schematic_glazing_actors=len(windows['removals']),corrected_wall_meshes=len(replacements),
        changed_existing_packages=sorted(changed),new_packages=sorted(added),simulation_properties_unchanged=True,
        viewport_unchanged=True,world_auxiliary_actors_unchanged=True,imported=records))
    print('MPR_INTERIOR_REFINEMENT_SAVED')


def verify_reload(u):
    assert '-run=pythonscript' in u.SystemLibrary.get_command_line().lower(), 'Reload verification is commandlet-only'
    assert u.EditorLoadingAndSavingUtils.load_map(base.MAP)
    actual=guard.capture(u,ROOT,base.MAP);guard.assert_clean(actual)
    expected=base.read(OUT/'after.json.gz')
    assert [patch.normalize(a,commandlet_compat=True) for a in actual['actors']]==[
        patch.normalize(a,commandlet_compat=True) for a in expected['actors']]
    preserved=base.read(OUT/'preserved_config.json')
    assert sim_properties(u)==preserved['simulation']
    original=base.read(base.OUT/'preservation/baseline.json.gz')['all_content_hashes']
    now=guard.content_hashes(ROOT)
    assert all(now.get(p)==h for p,h in original.items() if p!='Content/Maps/MPR_CAD_Warehouse_B50B57.umap')
    patch.write(OUT/'reload_validation.json',dict(success=True,actor_count=len(actual['actors']),
        map_sha256=actual['map_file_sha256'],original_packages_preserved=len(original)-1,simulation_properties_unchanged=True))
    print('MPR_INTERIOR_FINAL_RELOAD_VERIFIED')


if __name__=='__main__':
    import unreal as u
    if '-mprinteriorverify' in u.SystemLibrary.get_command_line().lower():verify_reload(u)
    else:apply(u)
