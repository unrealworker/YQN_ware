"""Apply the requested blue palette and real 70% cargo occupancy to Zcool only.

Run in the clean live editor using the local dispatcher, after generating the
private FBX variants. Shared original meshes/maps and their metadata remain valid.
"""
import copy
import importlib
import hashlib
import json
import shutil
import sys
import traceback
from pathlib import Path
import unreal

ROOT = Path('D:/UEPro/Test')
OUT = ROOT/'Saved/SceneRefinements'
DEST = '/Game/GHSZcoolSmartFactory/Occupancy'
MAP = '/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
LIB = unreal.EditorAssetLibrary
ASSETS = unreal.AssetToolsHelpers.get_asset_tools()
ACTORS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
LEVELS = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
EDITOR = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
unreal.load_module('StaticMeshEditor')
MESH_EDITOR = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
sys.path.insert(0,str(ROOT/'Scripts/ghs'))
import refine_zcool_palette
importlib.reload(refine_zcool_palette)
apply_palette=refine_zcool_palette.apply_palette

def read(path): return json.loads(path.read_text(encoding='utf-8'))
def write(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def owned_hashes():
    paths = [ROOT/'Content/Maps/GHS_CAD_NormalWarehouse.umap']
    for folder in ['GHSRefinementV2','GHSNormalWarehouse','GHSDigitalTwin']:
        paths.extend((ROOT/'Content'/folder).rglob('*.uasset'))
    return {p.relative_to(ROOT).as_posix():sha(p) for p in paths}
def xyz(v): return [v.x,v.y,v.z]
def source_name(mesh): return mesh.get_name().removesuffix('_Occ70')
def instance_rows(component):
    return [component.get_instance_transform(i,world_space=True) for i in range(component.get_instance_count())]
def assert_binding(component, entries):
    assert component.get_instance_count()==len(entries)
    for i, row in enumerate(entries):
        x,y,z=row['position_m']
        location=component.get_instance_transform(i,world_space=True).translation
        assert (location-unreal.Vector(x*100,-y*100,z*100)).length()<.1,(component.get_name(),i)

def import_rack(spec, original, materials):
    name=spec['name']; target=DEST+'/'+name
    assert name.endswith('_Occ70') and name.startswith('SM_GHS_V2Rack_')
    if not LIB.does_asset_exist(target):
        task=unreal.AssetImportTask()
        task.filename=spec['fbx']; task.destination_path=DEST; task.destination_name=name
        task.automated=True; task.replace_existing=False; task.save=False
        options=unreal.FbxImportUI(); options.import_mesh=True; options.import_as_skeletal=False
        options.mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH
        options.automated_import_should_detect_type=False
        options.import_materials=False; options.import_textures=False; options.import_animations=False
        data=options.static_mesh_import_data
        data.combine_meshes=True; data.generate_lightmap_u_vs=False; data.auto_generate_collision=False
        data.normal_import_method=unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
        data.normal_generation_method=unreal.FBXNormalGenerationMethod.BUILT_IN
        task.options=options; ASSETS.import_asset_tasks([task])
    mesh=LIB.load_asset(target); assert mesh
    roles=[str(s.get_editor_property('imported_material_slot_name')).rsplit('_',1)[-1] for s in original.static_materials]
    palette=dict(zip(roles,materials)); slots=mesh.static_materials
    assert len(slots)==len(roles)==7
    for i,slot in enumerate(slots):
        role=str(slot.get_editor_property('imported_material_slot_name')).rsplit('_',1)[-1]
        assert role in palette,role
        slot.material_interface=palette[role]; slots[i]=slot
    mesh.set_editor_property('static_materials',slots)
    reduction=unreal.StaticMeshReductionOptions(); reduction.auto_compute_lod_screen_size=False
    reduction.reduction_settings=[unreal.StaticMeshReductionSettings(percent_triangles=p,screen_size=s)
        for p,s in [(1.,1.),(.55,.25),(.30,.08),(.18,.025)]]
    assert MESH_EDITOR.set_lods(mesh,reduction)==4
    before,after=original.get_bounds(),mesh.get_bounds()
    assert (before.origin-after.origin).length()<.2,(name,'origin')
    assert (before.box_extent-after.box_extent).length()<.2,(name,'bounds')
    assert LIB.save_loaded_asset(mesh,only_if_is_dirty=False)
    return mesh

def main():
    report=dict(success=False,groups=[],assets_saved=[])
    try:
        assert EDITOR.get_editor_world().get_path_name().split('.')[0]==MAP
        assert not LEVELS.is_in_play_in_editor()
        dirty_maps=unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
        dirty_assets=unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
        if dirty_maps or dirty_assets:
            # A failed attempt may leave only our backed-up private packages dirty.
            previous=read(OUT/'apply_report.json')
            assert previous.get('success') is False and 'error' in previous and (OUT/'Backup').is_dir()
            assert all(p.get_path_name()==MAP for p in dirty_maps)
            assert all(p.get_path_name().startswith('/Game/GHSZcoolSmartFactory/') for p in dirty_assets)
        OUT.mkdir(parents=True,exist_ok=True)
        backup=OUT/'Backup'
        if not backup.exists():
            shutil.copytree(ROOT/'Content/GHSZcoolSmartFactory',backup/'Content/GHSZcoolSmartFactory')
            for rel in ['Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap',
                'Content/GHSTwinUI/data/scene-bindings.json','Content/GHSTwinUI/data/rack-slots.json']:
                target=backup/rel; target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(ROOT/rel,target)
        source_hashes=owned_hashes()
        write(OUT/'source_hashes_before.json',source_hashes)
        registry=read(ROOT/'Content/GHSTwinUI/data/scene-bindings.json')
        slots=read(ROOT/'Content/GHSTwinUI/data/rack-slots.json')
        manifest=read(ROOT/'SourceAssets/GHS/ZcoolOccupancy/zcool_occupancy.json')
        specs={s['name'].removesuffix('_Occ70'):s for s in manifest['meshes']}
        original_groups={g['mesh']:g for g in registry['groups'] if not g['mesh'].endswith('_Occ70')}
        registry['groups']=[g for g in registry['groups'] if not g['mesh'].endswith('_Occ70')]
        slots['meshes']=[s for s in slots['meshes'] if not s['name'].endswith('_Occ70')]
        by={a.get_actor_label():a for a in ACTORS.get_all_level_actors()}
        before_actor_names=sorted(a.get_name() for a in by.values())
        report['palette']=apply_palette(by)
        LIB.make_directory(DEST)
        rack_total=rack_occupied=floor_total=floor_occupied=0
        for actor in by.values():
            component=actor.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
            if not component or not component.static_mesh: continue
            source=source_name(component.static_mesh)
            if source not in specs and not source.startswith('SM_GHS_Presentation_Cargo'): continue
            original=original_groups[source]
            group=copy.deepcopy(original); group['mesh']=source+'_Occ70'
            materials=[component.get_material(i) for i in range(component.get_num_materials())]
            if source in specs:
                spec=specs[source]
                old=LIB.load_asset('/Game/GHSRefinementV2/Meshes/'+source)
                assert old
                mesh=import_rack(spec,old,materials)
                component.set_static_mesh(mesh)
                for i,slot in enumerate(mesh.static_materials): component.set_material(i,slot.material_interface)
                assert_binding(component,group['instances'])
                source_slots=next(s for s in slots['meshes'] if s['name']==source)
                capacity=len(source_slots['cargo_stacks'])*component.get_instance_count()
                occupied=len(spec['cargo_stacks'])*component.get_instance_count()
                rack_total+=capacity; rack_occupied+=occupied
                model=copy.deepcopy(source_slots)
                model.update(name=spec['name'],cargo_stacks=spec['cargo_stacks'])
                slots['meshes'].append(model)
            else:
                capacity=original['count']; occupied=round(capacity*.7)
                # Stable sampling makes visible holes throughout every floor group.
                ranked=sorted(range(capacity),key=lambda i:hashlib.sha256(
                    ('ghs-70-floor:'+original['instances'][i]['id']).encode()).hexdigest())
                kept=sorted(ranked[:occupied]); entries=[original['instances'][i] for i in kept]
                if not component.static_mesh.get_name().endswith('_Occ70'):
                    assert_binding(component,original['instances'])
                    transforms=instance_rows(component)
                    mesh_path=DEST+'/'+source+'_Occ70'
                    mesh=LIB.load_asset(mesh_path) if LIB.does_asset_exist(mesh_path) else LIB.duplicate_asset(
                        component.static_mesh.get_path_name().split('.')[0],mesh_path)
                    assert mesh and LIB.save_loaded_asset(mesh,only_if_is_dirty=False)
                    component.clear_instances(); component.set_static_mesh(mesh)
                    for i in kept: component.add_instance(transforms[i],world_space=True)
                    for i,mat in enumerate(materials): component.set_material(i,mat)
                assert_binding(component,entries)
                group.update(count=occupied,instances=entries)
                floor_total+=capacity; floor_occupied+=occupied
            actor.tags=[t for t in actor.tags if not str(t).startswith(('InstanceCount=','OccupancyCapacity=','OccupancyOccupied='))]+[
                unreal.Name('InstanceCount='+str(component.get_instance_count())),
                unreal.Name('OccupancyCapacity='+str(capacity)),unreal.Name('OccupancyOccupied='+str(occupied))]
            registry['groups'].append(group)
            report['groups'].append(dict(actor=actor.get_actor_label(),mesh=group['mesh'],
                capacity=capacity,occupied=occupied,instances=component.get_instance_count(),
                lod_triangles=[component.static_mesh.get_num_triangles(i) for i in range(MESH_EDITOR.get_lod_count(component.static_mesh))]))
        assert rack_total==25056 and abs(rack_occupied/rack_total-.7)<.005,(rack_total,rack_occupied)
        assert floor_total==7530 and floor_occupied==5271,(floor_total,floor_occupied)
        report['occupancy']=dict(racks=dict(capacity=rack_total,occupied=rack_occupied,ratio=rack_occupied/rack_total),
            floor=dict(capacity=floor_total,occupied=floor_occupied,ratio=floor_occupied/floor_total))
        write(ROOT/'Content/GHSTwinUI/data/scene-bindings.json',registry)
        write(ROOT/'Content/GHSTwinUI/data/rack-slots.json',slots)
        eye,rot=EDITOR.get_level_viewport_camera_info()
        assert LEVELS.save_current_level()
        assert LEVELS.load_level(MAP)
        EDITOR.set_level_viewport_camera_info(eye,rot)
        reloaded={a.get_actor_label():a for a in ACTORS.get_all_level_actors()}
        assert sorted(a.get_name() for a in reloaded.values())==before_actor_names
        for row in report['groups']:
            c=reloaded[row['actor']].get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
            assert c.static_mesh.get_name()==row['mesh'] and c.get_instance_count()==row['instances']
            assert_binding(c,next(g for g in registry['groups'] if g['mesh']==row['mesh'])['instances'])
        for row in report['palette']['labels']:
            c=reloaded[row['actor']].get_component_by_class(unreal.TextRenderComponent)
            color=c.text_render_color
            assert [color.r,color.g,color.b,color.a]==row['after_color']
        final_hashes=owned_hashes()
        assert source_hashes==final_hashes,'Original shared content modified'
        report.update(success=True,saved_and_reloaded=True,original_shared_assets_unchanged=True,
            actor_count=len(reloaded),map=MAP,map_sha256=sha(ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'))
        unreal.log('GHS_SCENE_REFINEMENTS_SAVED '+json.dumps(report['occupancy']))
    except Exception:
        report['error']=traceback.format_exc(); unreal.log_error(report['error']); raise
    finally:
        write(OUT/'apply_report.json',report)

if __name__=='__main__': main()
