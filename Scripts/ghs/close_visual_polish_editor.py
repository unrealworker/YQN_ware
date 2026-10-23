"""Verify the restored scene, save only owned work, and close for a rebuild."""
from pathlib import Path
import builtins
import json
import runpy
import unreal

ROOT=Path('D:/UEPro/Test');OUT=ROOT/'Saved/VisualPolish'
helper=runpy.run_path(str(ROOT/'Scripts/ghs/apply_visual_polish.py'))
read=helper['read'];write=helper['write']
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert not levels.is_in_play_in_editor()
assert editor.get_editor_world().get_path_name().split('.')[0]==helper['MAP']
inspection=read(OUT/'inspection.json')
assert inspection['dirty_content']==[] and inspection['dirty_maps']==[],'Initial user work was not clean'
previous=read(OUT/'apply_report.json')
assert previous.get('bindings_and_lighting_restored_in_memory') and not previous['success']
before=read(Path(previous['run_directory'])/'before_scene.json')
assert helper['scene_snapshot'](actors.get_all_level_actors())==before,'Scene differs from restored pre-apply state'
state=getattr(builtins,helper['STATE'],None);assert state
owned=set(state['owned'])
dirty=helper['dirty']()
assert dirty.issubset(owned),('Unrelated dirty content',sorted(dirty-owned))
dirty_maps={p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()}
assert dirty_maps.issubset({helper['MAP']}),('Unrelated dirty maps',sorted(dirty_maps))
location,rotation=editor.get_level_viewport_camera_info()
session={'map':helper['MAP'],'viewport_location':[location.x,location.y,location.z],
    'viewport_rotation':[rotation.pitch,rotation.yaw,rotation.roll],
    'selected_actor_labels':[a.get_actor_label() for a in actors.get_selected_level_actors()],
    'owned_assets':sorted(owned),'saved_assets':[],'scene_matches_before':True,
    'camera_pitch':next(a for a in actors.get_all_level_actors() if a.get_actor_label()=='GHS_WarehouseCamera').get_editor_property('overview_pitch')}
assert session['camera_pitch']==previous['camera_before']['overview_pitch']
for path in sorted(owned):
    assert path.startswith(helper['DEST']+'/')
    obj=unreal.EditorAssetLibrary.load_asset(path)
    assert obj and unreal.EditorAssetLibrary.get_metadata_tag(obj,helper['OWNER'])==helper['VERSION']
    assert unreal.EditorAssetLibrary.save_loaded_asset(obj,only_if_is_dirty=False)
    session['saved_assets'].append(path)
if helper['MAP'] in dirty_maps:assert levels.save_current_level()
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
session['map_sha256']=helper['sha'](helper['MAP_FILE'])
write(OUT/'editor_rebuild_session.json',session)
unreal.log('GHS_VISUAL_POLISH_EDITOR_READY_FOR_REBUILD')
unreal.SystemLibrary.quit_editor()
