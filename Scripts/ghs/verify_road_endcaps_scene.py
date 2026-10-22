"""Read-only saved-scene validation after apply_road_endcaps.py."""
from pathlib import Path
import hashlib
import json
import runpy
import traceback
import unreal

ROOT=Path('D:/UEPro/Test')
OUT=ROOT/'Saved/SceneControls/RoadEndcaps'
MAP='/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    result=dict(success=False,writes_scene=False)
    try:
        commandlet='-run=pythonscript' in unreal.SystemLibrary.get_command_line().lower()
        if commandlet:
            assert unreal.EditorLoadingAndSavingUtils.load_map(MAP)
        else:
            assert not unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor()
        assert unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world().get_path_name().split('.')[0]==MAP
        assert MAP not in {p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()}
        receipt=json.loads((OUT/'apply.json').read_text(encoding='utf-8'))
        assert receipt['success'] and receipt['saved']
        expected=json.loads((OUT/'after.json').read_text(encoding='utf-8'))['actors']
        snapshot=runpy.run_path(str(ROOT/'Scripts/ghs/validate_park_expansion.py'))['snapshot']
        actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
        actual={a.get_actor_label():snapshot(a,unreal) for a in actors}
        # Parent integration can add storage components elsewhere. The whole
        # park/context and the user's studio ground remain a strict contract.
        protected={label for label in expected
                   if (label.startswith(('GHSPark_','GHSContextTransition_')) or label=='GHN_StudioGround')
                   and expected[label]['actor_class']!='/Script/Engine.CameraActor'}
        mismatches=[label for label in protected if actual.get(label)!=expected[label]]
        assert not mismatches,mismatches
        curb=actual['GHSPark_Curbs']
        assert any(c['mesh']==receipt['mesh'] for c in curb['components'])
        manifest=json.loads((ROOT/'SourceAssets/GHS/RoadEndcaps/road_endcaps.json').read_text(encoding='utf-8'))
        for path,value in manifest['protected_source_sha256'].items():
            assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==value,path
        result.update(success=True,saved_replacement_mesh=receipt['mesh'],protected_actor_count=len(protected),
            ground_materials_transforms_unchanged=True,road_marking_fence_foliage_context_unchanged=True,
            protected_source_hashes_verified=True,visual_review_required=True)
    except Exception:
        result['error']=traceback.format_exc();unreal.log_error(result['error'])
    (OUT/'scene-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    assert result['success'],result.get('error')
    unreal.log('GHS_ROAD_ENDCAPS_SCENE_VERIFIED')


if __name__=='__main__':
    main()
