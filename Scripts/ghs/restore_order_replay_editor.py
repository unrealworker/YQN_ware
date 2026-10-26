"""Restore the user's editor view without saving or changing the source scene."""
import hashlib,json,os
from pathlib import Path
import unreal
ROOT=Path('D:/UEPro/Test');OUT=ROOT/'Saved/OrderReplay'
session=json.loads((OUT/'editor_session.json').read_text(encoding='utf8'))
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert not levels.is_in_play_in_editor()
if editor.get_editor_world().get_path_name().split('.')[0]!=session['map']:assert levels.load_level(session['map'])
map_path=ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'
assert hashlib.sha256(map_path.read_bytes()).hexdigest()==session['map_sha256']
pitch,yaw,roll=session['rotation']
editor.set_level_viewport_camera_info(unreal.Vector(*session['location']),unreal.Rotator(pitch=pitch,yaw=yaw,roll=roll))
items=actors.get_all_level_actors();by={a.get_actor_label():a for a in items}
assert len(items)==session['actor_count']
actors.set_selected_level_actors([by[name] for name in session['selection']])
bridge_path=ROOT/'Scripts/ghs/live_dispatcher.py'
bridge_namespace=dict(__name__='__main__',__file__=str(bridge_path))
exec(compile(bridge_path.read_text(encoding='utf8'),str(bridge_path),'exec'),bridge_namespace)
request=ROOT/'Saved/GHS_LiveRequest.json'
if request.exists():bridge_namespace['bridge_last']=json.loads(request.read_text(encoding='utf8'))['id']
result=dict(success=True,pid=os.getpid(),map=session['map'],map_sha256=session['map_sha256'],actor_count=len(items),selection=session['selection'],camera_restored=True,dirty_maps=[p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()])
(OUT/'editor_restored.json').write_text(json.dumps(result,indent=2),encoding='utf8')
unreal.log('GHS_ORDER_REPLAY_EDITOR_RESTORED '+json.dumps(result))
