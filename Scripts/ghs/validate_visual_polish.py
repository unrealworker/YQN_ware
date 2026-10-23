"""Validate the live or freshly loaded saved map without saving anything."""
import copy
import json
from pathlib import Path
import runpy
import traceback
import unreal

ROOT=Path('D:/UEPro/Test');OUT=ROOT/'Saved/VisualPolish'
apply=runpy.run_path(str(ROOT/'Scripts/ghs/apply_visual_polish.py'))
report={'success':False}
try:
    previous=apply['read'](OUT/'apply_report.json');assert previous['success']
    current_map=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world().get_path_name().split('.')[0]
    levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    commandlet='-run=pythonscript' in unreal.SystemLibrary.get_command_line().lower()
    if commandlet:assert levels.load_level(apply['MAP'])
    else:assert current_map==apply['MAP'] and not levels.is_in_play_in_editor()
    disk_hash=apply['sha'](apply['MAP_FILE'])
    actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
    by={a.get_actor_label():a for a in actors}
    expected=apply['read'](Path(previous['run_directory'])/'after_scene.json')
    actual=apply['scene_snapshot'](actors)
    # Commandlets omit the editor-only Matinee camera display component.
    def without_preview(rows):
        rows=copy.deepcopy(rows)
        for row in rows:
            row['components']=[c for c in row['components'] if c['mesh']!='/Engine/EditorMeshes/MatineeCam_SM.MatineeCam_SM']
        return rows
    assert without_preview(expected)==without_preview(actual),'Saved scene differs from applied preservation snapshot'
    for binding in previous['bindings']:
        component=by[binding['actor']].get_component_by_class(unreal.StaticMeshComponent)
        mat=component.get_material(binding['slot'])
        assert mat.get_path_name()==binding['after']
        assert unreal.EditorAssetLibrary.get_metadata_tag(mat,apply['OWNER'])==apply['VERSION']
        assert mat.get_editor_property('blend_mode')==unreal.BlendMode.BLEND_OPAQUE
        assert mat.get_editor_property('shading_model')==unreal.MaterialShadingModel.MSM_DEFAULT_LIT
    texture=unreal.load_asset(apply['DEST']+'/T_VisualPolish_CampusMask')
    assert not texture.get_editor_property('srgb')
    assert texture.get_editor_property('compression_settings')==unreal.TextureCompressionSettings.TC_MASKS
    landscape=by['GHSPark_Landscape'].get_component_by_class(unreal.StaticMeshComponent).get_material(0)
    assert unreal.GHSVisualMaterialLibrary.has_world_position_offset(landscape),'Forest-pad WPO connection was not saved'
    camera=by['GHS_WarehouseCamera']
    assert abs(camera.get_editor_property('overview_pitch')-previous['camera_target_pitch'])<1e-5
    for path,digest in previous['protected_original_material_hashes'].items():assert apply['sha'](apply['asset_file'](path))==digest,path
    for actor in actors:
        if isinstance(actor,unreal.PostProcessVolume):
            assert apply['values'](actor.get_editor_property('settings'),apply['HEAVY_NAMES'])==previous['before_lighting']['heavy']
    assert apply['sha'](apply['MAP_FILE'])==disk_hash,'Validator changed map on disk'
    report.update(success=True,actor_count=len(actors),saved_map_loaded=commandlet,map_sha256=disk_hash,
        all_actor_component_instance_transforms_preserved=True,all_original_material_files_unchanged=True,
        roof_dissolve_parking_curbs_trucks_trees_preserved=True,gi_and_reflections_none=True,
        forest_pad_wpo_connection_saved=True,
        camera_pitch=camera.get_editor_property('overview_pitch'),validation_saved_map=False)
except Exception:
    report['error']=traceback.format_exc();unreal.log_error(report['error'])
apply['write'](OUT/('saved_validation.json' if '-run=pythonscript' in unreal.SystemLibrary.get_command_line().lower() else 'live_validation.json'),report)
assert report['success'],report.get('error')
unreal.log('GHS_VISUAL_POLISH_VALIDATED')
