"""Open the delivered map without saving or discarding another dirty level."""
import json
from pathlib import Path
import unreal

report_path = Path(r'D:\UEPro\Test\Saved\GHS_NormalEditorOpened.json')
dirty = [p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()]
if dirty:
    report_path.write_text(json.dumps(dict(opened=False, dirty_maps=dirty), indent=2), encoding='utf-8')
    unreal.log_warning('New warehouse is ready; current unsaved level was left open: ' + str(dirty))
else:
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    assert levels.load_level('/Game/Maps/GHS_CAD_NormalWarehouse')
    editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actors.clear_actor_selection_set()
    camera = next(a for a in actors.get_all_level_actors() if a.get_actor_label() == 'CAM_GHS_RackAisles')
    editor.set_level_viewport_camera_info(camera.get_actor_location(), camera.get_actor_rotation())
    report_path.write_text(json.dumps(dict(opened=True, map='/Game/Maps/GHS_CAD_NormalWarehouse',
                                          camera='CAM_GHS_RackAisles', saved=False), indent=2), encoding='utf-8')
