"""Apply ground-pivot camera and long truck mesh to Normal only, preserving user placements."""
import copy
import hashlib
import json
import sys
import traceback
from pathlib import Path
import unreal

ROOT=Path(r'D:\UEPro\Test')
sys.path.insert(0,str(ROOT/'Scripts/ghs'))
from sync_wall_heights import snapshot
MAP='/Game/Maps/GHS_CAD_NormalWarehouse'
DEST='/Game/GHSNormalWarehouse/TrucksLong'
MESH=DEST+'/SM_GHN_LongDockTruck'
BP='/Game/GHSNormalWarehouse/Camera/BP_GHS_WarehouseCamera'
REPORT=ROOT/'Saved/GHS_GroundCameraLongTrucks.json'
lib=unreal.EditorAssetLibrary
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)

def read(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def write(p,v): Path(p).write_text(json.dumps(v,indent=2,ensure_ascii=False),encoding='utf8')
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def content_hashes(): return {p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'Content').rglob('*') if p.is_file()}

def truck_bounds(actor, mesh):
    b=mesh.get_bounds(); t=actor.get_actor_transform()
    points=[unreal.MathLibrary.transform_location(t,b.origin+unreal.Vector(x*b.box_extent.x,y*b.box_extent.y,z*b.box_extent.z))
            for x in [-1,1] for y in [-1,1] for z in [-1,1]]
    return [[min(getattr(p,k) for p in points),max(getattr(p,k) for p in points)] for k in 'xyz']

def inspect_trucks(by, mesh):
    names=sorted(k for k in by if k.startswith('GHS_DockTruck_'))
    boxes={k:truck_bounds(by[k],mesh) for k in names}
    overlaps=[]
    for i,a in enumerate(names):
        for b in names[i+1:]:
            if all(min(boxes[a][d][1],boxes[b][d][1])-max(boxes[a][d][0],boxes[b][d][0])>0.1 for d in range(3)):
                overlaps.append([a,b])
    assert not overlaps, overlaps
    assert min(b[2][0] for b in boxes.values()) > -0.02, 'Truck below ground'
    # The +600 cm extension is outward from the unchanged rear docking origin.
    assert all(abs(by[k].get_actor_rotation().pitch)<.001 and abs(by[k].get_actor_rotation().roll)<.001 for k in names)
    return dict(count=len(names),pairwise_overlaps=overlaps,bounds_cm=boxes)

def run():
    assert '-run=pythonscript' in unreal.SystemLibrary.get_command_line().lower()
    assert not REPORT.exists(), 'Already applied: verify existing result before applying again'
    checkpoint=read(ROOT/'Saved/GHS_WarehouseCameraGroundRevision.json')
    backup=Path(checkpoint['backup_root'])
    baseline=read(backup/'live_before.json')
    before_hashes=content_hashes();write(backup/'content_hashes_before_apply.json',before_hashes)
    result=dict(success=False,map=MAP,backup_root=str(backup),new_mesh=MESH)
    try:
        assert levels.load_level(MAP)
        by={a.get_actor_label():a for a in actors.get_all_level_actors()}
        before=snapshot(by)
        # Native class defaults may already have migrated camera-only values.
        assert {k:v for k,v in before.items() if k!='GHS_WarehouseCamera'}=={k:v for k,v in baseline.items() if k!='GHS_WarehouseCamera'}
        spec=read(ROOT/'SourceAssets/GHS_Normal/TrucksLong/dock_truck_long.json')['meshes'][0]
        assert sha(spec['fbx'])==spec['fbx_sha256']
        assert not lib.does_asset_exist(MESH)
        task=unreal.AssetImportTask(); task.filename=spec['fbx'];task.destination_path=DEST;task.destination_name=spec['name']
        task.automated=True;task.replace_existing=False;task.save=False
        options=unreal.FbxImportUI();options.import_mesh=True;options.import_as_skeletal=False
        options.mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH;options.automated_import_should_detect_type=False
        options.import_materials=False;options.import_textures=False;options.import_animations=False
        imp=options.static_mesh_import_data;imp.combine_meshes=True;imp.generate_lightmap_u_vs=False;imp.auto_generate_collision=False
        imp.normal_import_method=unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
        imp.normal_generation_method=unreal.FBXNormalGenerationMethod.BUILT_IN
        task.options=options;unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        mesh=lib.load_asset(MESH);assert mesh
        slots=mesh.get_editor_property('static_materials')
        roles=[str(s.get_editor_property('imported_material_slot_name')).rsplit('_',1)[-1] for s in slots]
        assert set(roles)==set(spec['slot_roles'])
        names=sorted(k for k in by if k.startswith('GHS_DockTruck_'))
        assert len(names)==len([k for k in baseline if k.startswith('GHS_DockTruck_')])
        result['trucks']=[]
        for name in names:
            actor=by[name];assert actor.get_class()==unreal.StaticMeshActor.static_class()
            assert actor.get_attach_parent_actor() is None
            c=actor.get_component_by_class(unreal.StaticMeshComponent)
            old=c.get_editor_property('static_mesh');old_slots=old.get_editor_property('static_materials')
            role_mats={str(s.get_editor_property('imported_material_slot_name')).rsplit('_',1)[-1]:c.get_material(i) for i,s in enumerate(old_slots)}
            assert set(role_mats)==set(roles)
            assert c.set_static_mesh(mesh)
            for i,role in enumerate(roles):c.set_material(i,role_mats[role])
            result['trucks'].append(dict(name=name,materials_by_role={r:m.get_path_name() for r,m in role_mats.items()},transform=baseline[name]['transform']))
        for i,s in enumerate(slots):
            s.set_editor_property('material_interface',lib.load_asset(result['trucks'][0]['materials_by_role'][roles[i]]))
            slots[i]=s
        mesh.set_editor_property('static_materials',slots)
        unreal.load_module('StaticMeshEditor');mesh_editor=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        lods=unreal.StaticMeshReductionOptions();lods.auto_compute_lod_screen_size=False
        lods.reduction_settings=[unreal.StaticMeshReductionSettings(percent_triangles=p,screen_size=s) for p,s in [(1.,1.),(.55,.25),(.30,.08),(.18,.025)]]
        assert mesh_editor.set_lods(mesh,lods)==4
        mesh_bounds=mesh.get_bounds()
        expected=spec['bounds_m'];expected_center=[(a+b)*50 for a,b in expected];expected_center[1]*=-1
        assert max(abs(getattr(mesh_bounds.box_extent,k)-(hi-lo)*50) for k,(lo,hi) in zip('xyz',expected))<.15
        assert max(abs(getattr(mesh_bounds.origin,k)-v) for k,v in zip('xyz',expected_center))<.15
        bp=lib.load_asset(BP);cls=lib.load_blueprint_class(BP);native=unreal.load_class(None,'/Script/Test.GHSWarehouseCameraPawn')
        defaults=unreal.get_default_object(native)
        for obj in [unreal.get_default_object(cls)]:
            for key in ['overview_center','enabled_features','movement_lag_speed','location_constrain_type','constrain_location_minimum','constrain_location_maximum','minimum_location','maximum_location']:
                obj.set_editor_property(key,defaults.get_editor_property(key))
            obj.set_editor_property('desired_socket_offset',unreal.Vector())
            obj.set_editor_property('desired_target_offset',unreal.Vector())
        unreal.BlueprintEditorLibrary.compile_blueprint(bp)
        by={a.get_actor_label():a for a in actors.get_all_level_actors()}
        camera=by['GHS_WarehouseCamera']
        camera.set_editor_property('overview_center',defaults.get_editor_property('overview_center'))
        camera.disable_features(camera.get_editor_property('enabled_features'))
        camera.enable_features(defaults.get_editor_property('enabled_features'))
        by['GHS_WarehouseCamera'].reset_overview(True)
        result['truck_validation']=inspect_trucks(by,mesh)
        after=snapshot(by)
        for name in by:
            if name=='GHS_WarehouseCamera':continue
            expected_row=copy.deepcopy(baseline[name])
            if name in names:
                expected_row['mesh']=mesh.get_path_name()
                materials=result['trucks'][names.index(name)]['materials_by_role']
                expected_row['materials']=[materials[r] for r in roles]
            assert after[name]==expected_row, 'Unintended actor change: '+name
        assert lib.save_loaded_asset(mesh,only_if_is_dirty=False)
        assert lib.save_loaded_asset(bp,only_if_is_dirty=False)
        assert levels.save_current_level()
        write(backup/'expected_after.json',after)
        after_hashes=content_hashes()
        changed=sorted(k for k in set(before_hashes)|set(after_hashes) if before_hashes.get(k)!=after_hashes.get(k))
        allowed={'Content/Maps/GHS_CAD_NormalWarehouse.umap','Content/GHSNormalWarehouse/Camera/BP_GHS_WarehouseCamera.uasset','Content/GHSNormalWarehouse/TrucksLong/SM_GHN_LongDockTruck.uasset'}
        assert set(changed)<=allowed,changed
        result.update(success=True,actor_count=len(by),truck_count=len(names),modified_content=changed,
                      materials_and_placements_preserved=True,other_actors_preserved=len(by)-len(names)-1,
                      mesh_roles=roles,lod_triangles=[mesh.get_num_triangles(i) for i in range(4)],
                      content_hashes_after=after_hashes)
    except Exception:
        result['error']=traceback.format_exc();raise
    finally:write(REPORT,result)
    unreal.log('GROUND_CAMERA_LONG_TRUCKS_APPLIED')

if __name__=='__main__':run()
