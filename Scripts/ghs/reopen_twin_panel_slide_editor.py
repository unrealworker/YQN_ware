"""Restore the clean editor view and editor selection captured before this build."""
import hashlib,json,os
from pathlib import Path
import unreal
ROOT=Path(r'D:/UEPro/Test')
saved=json.loads((ROOT/'Saved/PanelSlide_EditorState.json').read_text(encoding='utf-8'))
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert editor.get_editor_world().get_path_name()==saved['map']
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
for name,expected in saved['map_sha256'].items():
    assert hashlib.sha256((ROOT/'Content/Maps'/name).read_bytes()).hexdigest()==expected
all_actors=actors.get_all_level_actors()
assert len(all_actors)==saved['actor_count']
chosen={item['name'] for item in saved['selected_actors']}
selection=[a for a in all_actors if a.get_name() in chosen]
assert len(selection)==len(chosen)
actors.set_selected_level_actors(selection)
rot=saved['viewport_rotation']
editor.set_level_viewport_camera_info(unreal.Vector(*saved['viewport_position']),unreal.Rotator(pitch=rot[0],yaw=rot[1],roll=rot[2]))
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
result=dict(success=True,pid=os.getpid(),actor_count=len(all_actors),selected_actors=sorted(chosen),
    maps_preserved=True,viewport_restored=True,assets_saved=False,dirty_maps=[],dirty_assets=[])
(ROOT/'Saved/PanelSlide_EditorRestored.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
exec(compile((ROOT/'Scripts/ghs/live_dispatcher.py').read_text(),str(ROOT/'Scripts/ghs/live_dispatcher.py'),'exec'),globals())
unreal.log('GHS_PANEL_SLIDE_EDITOR_RESTORED')
