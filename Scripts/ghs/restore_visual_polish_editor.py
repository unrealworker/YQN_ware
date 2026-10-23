"""Restore editor view/selection and restart the local script dispatcher."""
import builtins
import json
from pathlib import Path
import unreal

ROOT=Path('D:/UEPro/Test');OUT=ROOT/'Saved/VisualPolish'
session=json.loads((OUT/'editor_rebuild_session.json').read_text(encoding='utf-8'))
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert not levels.is_in_play_in_editor()
if editor.get_editor_world().get_path_name().split('.')[0]!=session['map']:assert levels.load_level(session['map'])
pitch,yaw,roll=session['viewport_rotation']
editor.set_level_viewport_camera_info(unreal.Vector(*session['viewport_location']),unreal.Rotator(pitch=pitch,yaw=yaw,roll=roll))
by={a.get_actor_label():a for a in actors.get_all_level_actors()}
assert set(session['selected_actor_labels']).issubset(by)
actors.set_selected_level_actors([by[label] for label in session['selected_actor_labels']])
setattr(builtins,'_ghs_visual_polish_owned_v1',{'owned':set(session['owned_assets'])})
bridge_namespace={'__name__':'__main__','__file__':str(ROOT/'Scripts/ghs/live_dispatcher.py')}
exec(compile((ROOT/'Scripts/ghs/live_dispatcher.py').read_text(encoding='utf-8'),bridge_namespace['__file__'],'exec'),bridge_namespace)
request=ROOT/'Saved/GHS_LiveRequest.json'
if request.exists():bridge_namespace['bridge_last']=json.loads(request.read_text(encoding='utf-8'))['id']
unreal.log('GHS_VISUAL_POLISH_EDITOR_SESSION_RESTORED')
