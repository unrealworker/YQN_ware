"""Capture saved Zcool scene with actual UE rendering; never save assets.

Launch full editor with -RenderOffscreen and -ExecCmds="py <this file>".
ExecutePythonScript exits before asynchronous capture callbacks can run.
"""
import hashlib
import json
import struct
import time
import traceback
from pathlib import Path
import unreal

ROOT = Path('D:/UEPro/Test')
MAP = '/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
REPORT = ROOT / 'Saved/GHS_ZcoolCapture.json'
SIZE = (1920, 1080)
ACTORS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
LEVELS = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
EDITOR = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
started = time.monotonic()
handle = task = pending = None
index = 0
done = False
busy = False
views = []
result = dict(success=False, map=MAP, captures=[], assets_saved=False)
files = [ROOT / 'Content/Maps/GHS_CAD_NormalWarehouse.umap',
         ROOT / 'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap']
hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def write():
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


def finish(error=None):
    global done
    if done:
        return
    done = True
    if handle:
        unreal.unregister_slate_post_tick_callback(handle)
    try:
        for path, expected in hashes.items():
            assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected, path
        result['saved_maps_unchanged'] = True
    except Exception:
        error = (error or '') + traceback.format_exc()
    result.update(success=error is None, error=error,
                  elapsed_seconds=round(time.monotonic()-started, 2))
    write()
    unreal.log('GHS_ZCOOL_CAPTURE_COMPLETE' if error is None else 'GHS_ZCOOL_CAPTURE_FAILED ' + error)
    unreal.SystemLibrary.quit_editor()


def tick(delta):
    global index, task, pending, busy
    if done or busy:
        return
    busy = True
    try:
        elapsed = time.monotonic()-started
        assert elapsed < 360, 'Render timeout'
        if elapsed < 15:
            return
        if task:
            if not task.is_task_done():
                return
            path = pending['path']
            if not path.exists() or path.stat().st_mtime_ns == pending['old_mtime']:
                return
            with path.open('rb') as stream:
                header = stream.read(24)
            assert header[:8] == b'\x89PNG\r\n\x1a\n'
            assert struct.unpack('>II', header[16:24]) == SIZE
            result['captures'].append(dict(view=pending['view'], path=str(path), bytes=path.stat().st_size))
            task = pending = None
            write()
        if index == len(views):
            finish()
            return
        name, camera = views[index]
        index += 1
        EDITOR.set_level_viewport_camera_info(camera.get_actor_location(), camera.get_actor_rotation())
        path = ROOT / ('Saved/GHS_Zcool_Scene_' + name + '.png')
        pending = dict(path=path, view=name, old_mtime=path.stat().st_mtime_ns if path.exists() else 0)
        task = unreal.AutomationLibrary.take_high_res_screenshot(*SIZE, str(path), camera=camera, delay=2.0)
        assert task
    except Exception:
        finish(traceback.format_exc())
    finally:
        busy = False


try:
    assert LEVELS.load_level(MAP)
    labels = {a.get_actor_label(): a for a in ACTORS.get_all_level_actors()}
    for name in ['Overview', 'FloorStorage', 'RackAisles', 'AGV_Charger']:
        camera = labels.get('CAM_GHS_' + name)
        assert camera, 'Missing saved view ' + name
        views.append((name, camera))
    ACTORS.set_selected_level_actors([])
    EDITOR.set_level_viewport_camera_info(views[0][1].get_actor_location(), views[0][1].get_actor_rotation())
    unreal.SystemLibrary.execute_console_command(EDITOR.get_editor_world(), 'DisableAllScreenMessages')
    performance = unreal.get_default_object(unreal.load_class(None, '/Script/UnrealEd.EditorPerformanceSettings'))
    performance.set_editor_property('bThrottleCPUWhenNotForeground', False)
    write()
    handle = unreal.register_slate_post_tick_callback(tick)
except Exception:
    finish(traceback.format_exc())
