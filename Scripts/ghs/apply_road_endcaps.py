"""Replace only GHSPark_Curbs geometry; preserve all current scene bindings.

Run after stopping PIE through live_dispatcher, or a Python commandlet while
the editor is closed. The parent integration task owns when this is executed.
"""
from pathlib import Path
import copy
import hashlib
import json
import runpy
import traceback
import unreal

ROOT=Path('D:/UEPro/Test')
SOURCE=ROOT/'SourceAssets/GHS/RoadEndcaps'
OUT=ROOT/'Saved/SceneControls/RoadEndcaps'
MAP='/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
DEST='/Game/GHSZcoolSmartFactory/RoadEndcaps/Meshes'
NAME='SM_GHSRoadEndcaps_Curbs'
ORIGINAL='/Game/GHSZcoolSmartFactory/Park/Meshes/SM_GHSPark_Curbs.SM_GHSPark_Curbs'
REPLACEMENT=DEST+'/'+NAME+'.'+NAME
LABEL='GHSPark_Curbs'
LIB=unreal.EditorAssetLibrary


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    report=dict(success=False)
    component=None;old_mesh=None;old_overrides=None
    try:
        levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        commandlet='-run=pythonscript' in unreal.SystemLibrary.get_command_line().lower()
        if commandlet:
            assert unreal.EditorLoadingAndSavingUtils.load_map(MAP)
        else:
            assert not levels.is_in_play_in_editor(),'Stop PIE before replacing the curb mesh'
        assert editor.get_editor_world().get_path_name().split('.')[0]==MAP
        manifest=json.loads((SOURCE/'road_endcaps.json').read_text(encoding='utf-8'))
        assert manifest['success'] and manifest['scope']=='glen:start and glen:end only'
        for path,value in manifest['protected_source_sha256'].items():
            assert sha(ROOT/path)==value,('A protected source changed; rebuild/review before importing',path)
        fbx=(ROOT/manifest['fbx']).resolve()
        assert fbx.is_relative_to(SOURCE.resolve()) and sha(fbx)==manifest['sha256']
        snapshot=runpy.run_path(str(ROOT/'Scripts/ghs/validate_park_expansion.py'))['snapshot']
        current=actors.get_all_level_actors()
        before={a.get_actor_label():snapshot(a,unreal) for a in current}
        assert len(before)==len(current),'Duplicate actor labels make preservation comparison ambiguous'
        by={a.get_actor_label():a for a in current}
        component=by[LABEL].get_component_by_class(unreal.StaticMeshComponent)
        old_mesh=component.static_mesh
        assert old_mesh.get_path_name() in (ORIGINAL,REPLACEMENT),old_mesh.get_path_name()
        assert component.get_num_materials()==1
        old_overrides=list(component.get_editor_property('override_materials'))
        old_slots=list(old_mesh.get_editor_property('static_materials'))
        dirty={p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()}
        assert not any(p.startswith(DEST+'/') for p in dirty),'Replacement asset has unsaved changes'
        (OUT/'before.json').write_text(json.dumps(dict(map=MAP,actors=before),ensure_ascii=False,indent=2),encoding='utf-8')
        LIB.make_directory(DEST)
        task=unreal.AssetImportTask()
        task.filename=str(fbx);task.destination_path=DEST;task.destination_name=NAME
        task.automated=True;task.replace_existing=True;task.replace_existing_settings=True;task.save=False
        options=unreal.FbxImportUI()
        options.import_mesh=True;options.import_as_skeletal=False
        options.import_materials=False;options.import_textures=False;options.import_animations=False
        options.automated_import_should_detect_type=False
        options.mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH
        data=options.static_mesh_import_data
        data.combine_meshes=True;data.generate_lightmap_u_vs=False;data.auto_generate_collision=False
        data.normal_import_method=unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
        task.options=options
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        mesh=LIB.load_asset(DEST+'/'+NAME)
        assert isinstance(mesh,unreal.StaticMesh)
        assert len(mesh.get_editor_property('static_materials'))==len(old_slots)==1
        mesh.set_editor_property('static_materials',old_slots)
        bound=mesh.get_bounds()
        for key,value in [('min',bound.origin-bound.box_extent),('max',bound.origin+bound.box_extent)]:
            assert max(abs(a-b) for a,b in zip((value.x,value.y,value.z),manifest['bounds_ue_cm'][key]))<2.,key
        assert LIB.save_loaded_asset(mesh,only_if_is_dirty=False)
        component.set_static_mesh(mesh)
        component.set_editor_property('override_materials',old_overrides)
        after={a.get_actor_label():snapshot(a,unreal) for a in actors.get_all_level_actors()}
        expected=copy.deepcopy(before)
        target=[c for c in expected[LABEL]['components'] if c['name']==component.get_name()]
        assert len(target)==1
        target[0]['mesh']=REPLACEMENT
        assert after==expected,'Only the Curbs mesh reference may change; restoring it on failure'
        assert levels.save_current_level()
        assert {p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()}==dirty
        (OUT/'after.json').write_text(json.dumps(dict(map=MAP,actors=after),ensure_ascii=False,indent=2),encoding='utf-8')
        report.update(success=True,saved=True,actor=LABEL,previous_mesh=old_mesh.get_path_name(),mesh=REPLACEMENT,
            source_fbx_sha256=manifest['sha256'],all_other_actors_preserved=True,
            actor_count=len(before),material_assignments_preserved=True,transforms_preserved=True,
            ground_preserved=after['GHSPark_Ground'],studio_ground_preserved=after['GHN_StudioGround'],
            source_geometry_report=str(SOURCE/'road_endcaps.json'),
            map_sha256=sha(ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'))
    except Exception:
        if component is not None and old_mesh is not None:
            component.set_static_mesh(old_mesh)
            if old_overrides is not None:
                component.set_editor_property('override_materials',old_overrides)
        report['error']=traceback.format_exc()
        unreal.log_error(report['error'])
    (OUT/'apply.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    assert report['success'],report.get('error')
    unreal.log('GHS_ROAD_ENDCAPS_APPLIED')


if __name__=='__main__':
    main()
