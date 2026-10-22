"""Read-only editor state before the traffic-only C++ rebuild."""
import json, os
from pathlib import Path
import unreal

root=Path('D:/UEPro/Test')
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
world=editor.get_editor_world()
result=dict(pid=os.getpid(),command_line=unreal.SystemLibrary.get_command_line(),
    map=world.get_path_name() if world else None,
    worlds=[w.get_path_name() for w in unreal.ObjectIterator(unreal.World)],
    in_pie=levels.is_in_play_in_editor(),
    dirty_maps=[p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()],
    dirty_assets=[p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()])
if world:
    eye,rotation=editor.get_level_viewport_camera_info()
    result.update(viewport_position=[eye.x,eye.y,eye.z],viewport_rotation=[rotation.pitch,rotation.yaw,rotation.roll],
        selected=[a.get_name() for a in actors.get_selected_level_actors()],actor_count=len(actors.get_all_level_actors()))
(root/'Saved/TrafficDensity').mkdir(exist_ok=True)
(root/'Saved/TrafficDensity/editor-probe.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
