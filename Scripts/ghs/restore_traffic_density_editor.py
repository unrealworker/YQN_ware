"""Restore the exact clean view and selection after the traffic-only build."""
import hashlib,json,os
from pathlib import Path
import unreal
root=Path('D:/UEPro/Test')
saved=json.loads((root/'Saved/TrafficDensity/editor-before.json').read_text(encoding='utf8'))
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert editor.get_editor_world().get_path_name()==saved['map']
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
for name,sha in saved['map_sha256'].items():assert hashlib.sha256((root/'Content/Maps'/name).read_bytes()).hexdigest()==sha
all_actors=actors.get_all_level_actors()
assert len(all_actors)==saved['actor_count']
selected=[a for a in all_actors if a.get_name() in saved['selected']]
assert len(selected)==len(saved['selected'])
actors.set_selected_level_actors(selected)
r=saved['viewport_rotation']
editor.set_level_viewport_camera_info(unreal.Vector(*saved['viewport_position']),unreal.Rotator(pitch=r[0],yaw=r[1],roll=r[2]))
(root/'Saved/TrafficDensity/editor-restored.json').write_text(json.dumps(dict(success=True,pid=os.getpid(),map=saved['map'],actor_count=len(all_actors),selection_restored=True,viewport_restored=True,assets_saved=False)),encoding='utf8')
exec(compile((root/'Scripts/ghs/live_dispatcher.py').read_text(encoding='utf8'),'live_dispatcher.py','exec'),globals())
