"""Restore the user's recorded editor view after performance verification.

Only changes the open editor view and selection; never saves map assets.
"""
import datetime
import hashlib
import json
import time
from pathlib import Path
import unreal

ROOT = Path(r'D:/UEPro/Test')
STATE = json.loads((ROOT / 'Saved/PerformanceP0P1/editor_state_latest.json').read_text(encoding='utf-8'))
START = time.monotonic()
HANDLE = None


def restore(delta):
    global HANDLE
    if time.monotonic() - START < 3:
        return
    unreal.unregister_slate_post_tick_callback(HANDLE)
    editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    assert not levels.is_in_play_in_editor()
    assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
    assert not unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
    assert editor.get_editor_world().get_path_name() == STATE['map']
    rotation = STATE['viewport_rotation']
    editor.set_level_viewport_camera_info(unreal.Vector(*STATE['viewport_position']),
        unreal.Rotator(pitch=rotation[0], yaw=rotation[1], roll=rotation[2]))
    names = set(STATE['selected_actors'])
    all_actors = actors.get_all_level_actors()
    actors.set_selected_level_actors([actor for actor in all_actors if actor.get_name() in names])
    hashes = {name: hashlib.sha256((ROOT/'Content/Maps'/name).read_bytes()).hexdigest()
              for name in STATE['map_sha256']}
    assert hashes == STATE['map_sha256'], 'Map assets changed during performance work'
    assert len(all_actors) == STATE['actor_count']
    result = dict(success=True, utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  map=STATE['map'], actor_count=len(all_actors), map_sha256=hashes,
                  selected_actors=[actor.get_name() for actor in actors.get_selected_level_actors()],
                  assets_saved=False)
    (ROOT/'Saved/PerformanceP0P1/editor_restored.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    unreal.log('GHS_PERFORMANCE_EDITOR_RESTORED')


HANDLE = unreal.register_slate_post_tick_callback(restore)
