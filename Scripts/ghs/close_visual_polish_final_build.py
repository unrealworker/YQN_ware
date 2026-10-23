"""Close only an unchanged, saved target map for the final HUD rebuild."""
from pathlib import Path
import json
import runpy
import unreal

ROOT=Path('D:/UEPro/Test'); OUT=ROOT/'Saved/VisualPolish'
helper=runpy.run_path(str(ROOT/'Scripts/ghs/apply_visual_polish.py'))
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert not levels.is_in_play_in_editor(), 'End preview before rebuilding'
assert editor.get_editor_world().get_path_name().split('.')[0]==helper['MAP']
previous=helper['read'](OUT/'apply_report.json'); assert previous['success']
expected=helper['read'](Path(previous['run_directory'])/'after_scene.json')
assert helper['scene_snapshot'](actors.get_all_level_actors())==expected, 'Preserve newer user scene edits'
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages(), 'Preserve unsaved content'
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages(), 'Preserve unsaved maps'
assert helper['sha'](helper['MAP_FILE'])==previous['after_map_sha256']
location,rotation=editor.get_level_viewport_camera_info()
session=dict(map=helper['MAP'],viewport_location=[location.x,location.y,location.z],
    viewport_rotation=[rotation.pitch,rotation.yaw,rotation.roll],
    selected_actor_labels=[a.get_actor_label() for a in actors.get_selected_level_actors()],
    owned_assets=previous['saved_owned_assets'],saved_assets=[],scene_matches_after=True,
    map_sha256=previous['after_map_sha256'])
helper['write'](OUT/'editor_rebuild_session.json',session)
unreal.log('GHS_VISUAL_POLISH_FINAL_REBUILD_READY')
unreal.SystemLibrary.quit_editor()
