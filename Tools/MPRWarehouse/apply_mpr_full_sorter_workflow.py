"""Upgrade the existing MPR simulation and its private assets in place.

Requires an owned full editor for LOD import. No new map, no replacement Actor.
"""
from pathlib import Path
import sys,json,shutil
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).parent))
import rebuild_preservation as guard
import mpr_scene_patch_guard as patch
import apply_mpr_sorter_simulation as first
import mpr_private_mesh_import as importer

MAP=first.MAP;SRC=ROOT/'SourceAssets/MPR/sorter_simulation'
OUT=ROOT/'Saved/MPR/full_workflow_20261107/sorter_application'
DEST='/Game/MPRWarehouse/SorterSimulation'
CLASS='/Script/Test.MPRSorterSimulationActor'
DEFAULT_NAMES={'MovingColumns','LiftTrays','MovingParcels','CollectedParcels','ActiveCells','FullCells',
               'InfeedParcels','OperatorClothing','OperatorSkin','OperatorHelmets','OperatorBoots'}
WORKER_ROLES={'worker_skin_material':'Skin','worker_cloth_material':'Navy',
              'worker_helmet_material':'Helmet','worker_boot_material':'Rubber'}


def props(actor):
    p=first.controller_properties(actor)
    p['cart_meshes']=sorted(m.get_path_name() for m in actor.get_editor_property('cart_meshes'))
    for name in WORKER_ROLES:p[name]=first.asset_path(actor.get_editor_property(name))
    return p


def worker_material(u,name,role,new):
    src='/Game/GHSNormalWarehouse/MannedForklift/Materials/M_MF_WorkerV3_'+role
    mat=u.EditorAssetLibrary.load_asset(src);assert mat
    usage=u.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES
    if u.MaterialEditingLibrary.has_material_usage(mat,usage):return mat
    path=DEST+'/Materials/M_MPR_Worker_'+role
    assert not u.EditorAssetLibrary.does_asset_exist(path)
    clone=u.EditorAssetLibrary.duplicate_asset(src,path);assert clone
    if isinstance(clone,u.MaterialInstanceConstant):
        u.MaterialEditingLibrary.set_material_usage_override(clone,usage,True,True)
        u.MaterialEditingLibrary.update_material_instance(clone)
    else:
        u.MaterialEditingLibrary.set_base_material_usage(clone,usage,True)
        u.MaterialEditingLibrary.recompile_material(clone)
    assert u.MaterialEditingLibrary.has_material_usage(clone,usage)
    new[path]=clone;return clone


def validate_other_actors(before,after,guid):
    a={r['guid']:patch.normalize(r,commandlet_compat=True) for r in before['actors']}
    b={r['guid']:patch.normalize(r,commandlet_compat=True) for r in after['actors']}
    assert set(a)==set(b),'Unexpected actor addition/deletion'
    for key,row in a.items():
        if key==guid:continue
        diff=patch.differences(row,b[key]);assert not diff,(row['label'],diff[:8])
    for key in ('transform','class','folder','label','tags','tick_enabled','collision_enabled','hidden','attachment_parent'):
        assert a[guid][key]==b[guid][key],key
    assert before['world_settings']==after['world_settings']
    assert patch.normalized_coverage(before['world_actor_coverage'],commandlet_compat=True)==patch.normalized_coverage(after['world_actor_coverage'],commandlet_compat=True)


def validate_preview(u,actor,layout):
    defaults=[c for c in actor.get_components_by_class(u.InstancedStaticMeshComponent) if c.get_name() in DEFAULT_NAMES]
    assert len(defaults)==11 and all(c.get_instance_count()==0 for c in defaults)
    carts=[c for c in actor.get_components_by_class(u.InstancedStaticMeshComponent) if c.get_name().startswith('RuntimeCart_')]
    assert sum(c.get_instance_count() for c in carts)==96 and len(carts)==10
    expected={}
    for machine in layout['machines']:
        m=machine['world_transform'];assert m['rotation_xyzw']==[0,0,0,1] and m['scale']==[1,1,1]
        for cart in layout['profiles'][machine['profile']]['carts']:
            expected.setdefault(cart['mesh'].split('.')[-1].split('/')[-1],[]).append([a+b for a,b in zip(m['translation_cm'],cart['local_origin_cm'])])
    for c in carts:
        assert c.get_collision_enabled()==u.CollisionEnabled.NO_COLLISION
        actual=[]
        for i in range(c.get_instance_count()):
            t=c.get_instance_transform(i,world_space=True);actual.append([t.translation.x,t.translation.y,t.translation.z])
        name=c.static_mesh.get_name();assert not patch.differences(sorted(actual),sorted(expected[name]))


def apply(u):
    assert '-own' in u.SystemLibrary.get_command_line().lower()
    assert u.get_editor_subsystem(u.StaticMeshEditorSubsystem),'Full editor required for LODs'
    assert u.EditorLoadingAndSavingUtils.load_map(MAP)
    before=guard.capture(u,ROOT,MAP);guard.assert_clean(before)
    baseline=patch.read(ROOT/'Saved/MPR/full_workflow_20261107/conveyor_application/after.json.gz')
    assert before['map_file_sha256']==baseline['map_file_sha256']
    actors=u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors()
    controllers=[a for a in actors if a.get_class().get_path_name()==CLASS];assert len(controllers)==1
    actor=controllers[0];guid=u.GuidLibrary.conv_guid_to_string(actor.get_editor_property('actor_guid'))
    validate_other_actors(baseline,before,guid)
    old_props=props(actor);layout=patch.read(SRC/'layout.json');manifest=patch.read(SRC/'manifest.json')
    assert layout['schema_version']==manifest['schema_version']==2 and len(layout['machines'])==22
    for row in layout['machines']:
        source=next(a for a in before['actors'] if a['guid']==row['actor_guid'])
        c=next(c for c in source['components'] if c['name']==row['component_name'])
        assert not patch.differences(c['instance_transforms'][row['instance_index']],row['world_transform'])
        assert c['mesh'].split('.')[-1]==('SM_MPR_SorterSimBody64' if row['profile']=='cad64' else 'SM_MPR_SorterSimBody120')
    OUT.mkdir(parents=True,exist_ok=True)
    assert not (OUT/'after.json.gz').exists(),'Already applied'
    patch.write(OUT/'before.json.gz',before);patch.write(OUT/'old_controller.json',old_props)
    shutil.copy2(first.MAP_FILE,OUT/'before_MPR.umap')
    hashes=guard.content_hashes(ROOT)
    reference=u.EditorAssetLibrary.load_asset(DEST+'/Meshes/SM_MPR_SorterSimBody64')
    slots=list(reference.get_editor_property('static_materials'))
    materials={first.slot_role(s):s.material_interface for s in slots};assert list(materials)==first.ROLES
    imported={};changed_paths=[]
    for row in manifest['meshes']:
        if row['lod'] or row['kind']=='dynamic_part':continue
        path=DEST+'/Meshes/'+row['name']
        mesh=importer.import_mesh(u,row,DEST+'/Meshes',replace=row['kind']=='static_body',reference_slots=slots,materials=materials)
        imported[path]=mesh
        if row['kind']=='static_body':changed_paths.append('Content/MPRWarehouse/SorterSimulation/Meshes/'+row['name']+'.uasset')
    assert len(imported)==12 and len(changed_paths)==2
    clones={};worker={name:worker_material(u,name,role,clones) for name,role in WORKER_ROLES.items()}
    carts=sorted({cart['mesh'] for profile in layout['profiles'].values() for cart in profile['carts']})
    with u.ScopedEditorTransaction('完善MPR输送接货和整组料框车换仓'):
        actor.modify()
        actor.set_editor_property('cart_meshes',[u.EditorAssetLibrary.load_asset(path) for path in carts])
        for name,mat in worker.items():actor.set_editor_property(name,mat)
        actor.set_editor_property('layout_json',json.dumps(layout,ensure_ascii=False,separators=(',',':')))
    # Python property setters do not always rerun C++ construction. A no-op
    # transform change requests the normal editor construction path explicitly.
    actor.set_actor_transform(actor.get_actor_transform(),False,False)
    validate_preview(u,actor,layout)
    after=guard.capture(u,ROOT,MAP);validate_other_actors(before,after,guid)
    new_props=props(actor)
    assert new_props['layout_json']==json.dumps(layout,ensure_ascii=False,separators=(',',':'))
    assert len(new_props['cart_meshes'])==10
    for key in ('auto_start','tower_mesh','tray_mesh','parcel_material','active_material','full_material'):assert old_props[key]==new_props[key]
    assert guard.sha(first.MAP_FILE)==before['map_file_sha256']
    assert all(guard.sha(ROOT/path)==sha for path,sha in hashes.items()),'Existing files changed before save'
    for asset in [*imported.values(),*clones.values()]:assert u.EditorAssetLibrary.save_loaded_asset(asset,only_if_is_dirty=False)
    assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level()
    final=guard.capture(u,ROOT,MAP);guard.assert_clean(final);validate_other_actors(before,final,guid)
    current=guard.content_hashes(ROOT)
    allowed=set(changed_paths)|{'Content/Maps/MPR_CAD_Warehouse_B50B57.umap'}
    assert all(current.get(p)==h for p,h in hashes.items() if p not in allowed),'Unrelated Content changed'
    assert all(p.startswith('Content/MPRWarehouse/SorterSimulation/') for p in set(current)-set(hashes))
    patch.write(OUT/'after.json.gz',final)
    patch.write(OUT/'controller.json',dict(guid=guid,properties=new_props))
    report=dict(success=True,map_before=before['map_file_sha256'],map_after=final['map_file_sha256'],
        preserved_actors=len(before['actors'])-1,edited_controller_guid=guid,machines=22,carts=96,
        imported_meshes=list(imported),private_worker_materials=list(clones),preserved_content=len(hashes)-len(allowed),
        changed_existing_packages=changed_paths,preview_cart_instances=96)
    patch.write(OUT/'apply_report.json',report);return report


def verify(u):
    assert '-own' in u.SystemLibrary.get_command_line().lower()
    assert u.EditorLoadingAndSavingUtils.load_map(MAP)
    baseline=patch.read(OUT/'before.json.gz');after=patch.read(OUT/'after.json.gz');contract=patch.read(OUT/'controller.json')
    actual=guard.capture(u,ROOT,MAP);guard.assert_clean(actual)
    assert actual['map_file_sha256']==after['map_file_sha256']
    validate_other_actors(baseline,actual,contract['guid'])
    actor=next(a for a in u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors() if a.get_class().get_path_name()==CLASS)
    assert props(actor)==contract['properties']
    if '-run=pythonscript' not in u.SystemLibrary.get_command_line().lower():validate_preview(u,actor,patch.read(SRC/'layout.json'))
    patch.write(OUT/'reload_report.json',dict(success=True,map_sha256=actual['map_file_sha256'],controller_preserved=True))


if __name__=='__main__':
    import unreal as u
    if '-mprfullworkflowapply' in u.SystemLibrary.get_command_line().lower():print(apply(u))
    else:verify(u)
