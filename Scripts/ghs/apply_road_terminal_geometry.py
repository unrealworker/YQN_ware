"""Import four scoped meshes that remove only two false internal road tails."""
import copy
import hashlib
import json
import runpy
import shutil
from datetime import datetime
from pathlib import Path
import unreal

ROOT=Path('D:/UEPro/Test')
SOURCE=ROOT/'SourceAssets/GHS/RoadTerminalFade'
OUT=ROOT/'Saved/RoadTerminalFade'
DEST='/Game/GHSZcoolSmartFactory/RoadTerminalFade/Meshes'
MAP='/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
ROLES={'ContextRoads','Curbs','Markings','Landscape'}
LIB=unreal.EditorAssetLibrary
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    assert not levels.is_in_play_in_editor()
    assert editor.get_editor_world().get_path_name().split('.')[0]==MAP
    assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
    assert not unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
    manifest=json.loads((SOURCE/'road_terminal_junction_fix.json').read_text(encoding='utf-8'))
    assert manifest['success']
    assert {r['role'] for r in manifest['meshes']}==ROLES
    for path,value in manifest['protected_source_sha256'].items():
        assert sha(ROOT/path)==value,('Protected source changed',path)
    snapshot=runpy.run_path(str(ROOT/'Scripts/ghs/validate_park_expansion.py'))['snapshot']
    by={a.get_actor_label():a for a in actors.get_all_level_actors()}
    before={k:snapshot(a,unreal) for k,a in by.items()}
    expected=copy.deepcopy(before)
    map_file=ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'
    OUT.mkdir(parents=True,exist_ok=True)
    backup=OUT/('before-junction-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.umap')
    shutil.copy2(map_file,backup)
    report={'success':False,'backup':str(backup),'before_map_sha256':sha(map_file),'changes':[]}
    original=[]
    LIB.make_directory(DEST)
    try:
        for row in manifest['meshes']:
            label='GHSContextTransition_'+row['role']
            c=by[label].get_component_by_class(unreal.StaticMeshComponent)
            old=c.static_mesh
            overrides=list(c.get_editor_property('override_materials'))
            original.append((c,old,overrides))
            slots=list(old.static_materials)
            assert len(slots)==c.get_num_materials()==1
            file=(ROOT/row['fbx']).resolve()
            assert file.is_relative_to(SOURCE.resolve()) and sha(file)==row['sha256']
            path=DEST+'/'+row['name']
            assert not LIB.does_asset_exist(path),'Never overwrite an imported user asset'
            task=unreal.AssetImportTask()
            task.filename=str(file);task.destination_path=DEST;task.destination_name=row['name']
            task.automated=True;task.replace_existing=False;task.save=False
            options=unreal.FbxImportUI()
            options.import_mesh=True;options.import_as_skeletal=False
            options.import_materials=False;options.import_textures=False;options.import_animations=False
            options.automated_import_should_detect_type=False
            options.mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH
            data=options.static_mesh_import_data
            data.combine_meshes=True;data.generate_lightmap_u_vs=False;data.auto_generate_collision=False
            data.normal_import_method=unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
            data.vertex_color_import_option=unreal.VertexColorImportOption.REPLACE
            task.options=options
            unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
            mesh=LIB.load_asset(path)
            assert isinstance(mesh,unreal.StaticMesh)
            mesh.set_editor_property('static_materials',slots)
            bounds=mesh.get_bounds()
            for key,value in [('min',bounds.origin-bounds.box_extent),('max',bounds.origin+bounds.box_extent)]:
                assert max(abs(a-b) for a,b in zip((value.x,value.y,value.z),row['bounds_ue_cm'][key]))<2.,row['role']
            assert LIB.save_loaded_asset(mesh,only_if_is_dirty=False)
            c.set_static_mesh(mesh)
            c.set_editor_property('override_materials',overrides)
            expected[label]['components'][0]['mesh']=mesh.get_path_name()
            report['changes'].append({'actor':label,'old_mesh':old.get_path_name(),'new_mesh':mesh.get_path_name()})
        after={a.get_actor_label():snapshot(a,unreal) for a in actors.get_all_level_actors()}
        assert after==expected,'Only the four approved extension mesh references may change'
        assert levels.save_current_level()
        assert not unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
        report.update(success=True,actor_count=len(after),transforms_and_materials_preserved=True,
                      after_map_sha256=sha(map_file))
        (OUT/'final_scene.json').write_text(json.dumps(after,ensure_ascii=False,indent=2),encoding='utf-8')
    except Exception:
        for c,old,overrides in original:
            c.set_static_mesh(old);c.set_editor_property('override_materials',overrides)
        raise
    finally:
        (OUT/'geometry_apply.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    unreal.log('GHS_ROAD_TERMINAL_GEOMETRY_APPLIED')

if __name__=='__main__':main()
