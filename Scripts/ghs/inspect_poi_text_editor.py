import json
import hashlib
from pathlib import Path
import unreal
root=Path('D:/UEPro/Test')
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
loc,rot=editor.get_level_viewport_camera_info()
report=dict(map=editor.get_editor_world().get_path_name().split('.')[0],pie=levels.is_in_play_in_editor(),dirty_content=[p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()],dirty_maps=[p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()],viewport_location=[loc.x,loc.y,loc.z],viewport_rotation=[rot.pitch,rot.yaw,rot.roll],selected_actor_labels=[a.get_actor_label() for a in actors.get_selected_level_actors()])
(root/'Saved/VisualPolish/final_text_editor_state.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')