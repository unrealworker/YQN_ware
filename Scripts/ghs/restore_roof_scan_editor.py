"""Restore the recorded clean editor view after roof verification; never save a map."""
import hashlib,json,os
from pathlib import Path
import unreal
ROOT=Path('D:/UEPro/Test');OUT=ROOT/'Saved/RoofScan'
saved=json.loads((OUT/'editor-before.json').read_text(encoding='utf8'))
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert editor.get_editor_world().get_path_name()==saved['world']
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
for name,digest in saved['map_hashes'].items():
    assert hashlib.sha256((ROOT/'Content/Maps'/name).read_bytes()).hexdigest()==digest,name
all_actors=actors.get_all_level_actors();assert len(all_actors)==saved['count']
selected=[a for a in all_actors if a.get_name() in saved['selected']]
assert len(selected)==len(saved['selected'])
actors.set_selected_level_actors(selected)
r=saved['rotation'];editor.set_level_viewport_camera_info(unreal.Vector(*saved['position']),unreal.Rotator(pitch=r[0],yaw=r[1],roll=r[2]))
(OUT/'editor-restored.json').write_text(json.dumps(dict(success=True,pid=os.getpid(),actor_count=len(all_actors),
    selection_restored=True,viewport_restored=True,map_preserved=True,assets_saved=False),indent=2),encoding='utf8')
exec(compile((ROOT/'Scripts/ghs/live_dispatcher.py').read_text(encoding='utf8'),'live_dispatcher.py','exec'),globals())
if bridge_request.is_file():bridge_last=json.loads(bridge_request.read_text(encoding='utf8'))['id']
