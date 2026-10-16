"""Queue five real 1920x1080 captures in the full UE Editor using Slate ticks."""
import json
import struct
import time
import traceback
from pathlib import Path

import unreal

ROOT = Path(r'D:\UEPro\Test')
MAP = '/Game/Maps/VideoDigitalTwinWarehouse'
REPORT = ROOT / 'Saved/VideoWarehouse_CaptureReport.json'
VIEWS = ['Overview', 'Route', 'Racks', 'Alarm', 'Elevator']
RESOLUTION = (1920, 1080)
WARMUP_SECONDS = 15.0
CAPTURE_DELAY_SECONDS = 3.0
TIMEOUT_SECONDS = 480.0
vw_actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
vw_levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
vw_editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)


def vw_camera_state(camera):
    position = camera.get_actor_location()
    rotation = camera.get_actor_rotation()
    component = camera.get_component_by_class(unreal.CameraComponent)
    assert component, 'Expected a camera component'
    return dict(position_cm=[float(position.x), float(position.y), float(position.z)],
                rotation_degrees=[float(rotation.pitch), float(rotation.yaw), float(rotation.roll)],
                fov=float(component.get_editor_property('field_of_view')))


def vw_write_report():
    REPORT.write_text(json.dumps(vw_report, indent=2), encoding='utf-8')


def vw_restore_overview():
    if not vw_views:
        return
    overview = vw_views[0][1]
    # Fit the whole warehouse in the narrower editor panel as well as the
    # saved 16:9 presentation cameras.
    target = unreal.Vector(0, 0, 20)
    position = target + (overview.get_actor_location() - target) * 1.0
    rotation = unreal.MathLibrary.find_look_at_rotation(position, target)
    vw_editor.set_level_viewport_camera_info(position, rotation)
    vw_actors.set_selected_level_actors([])
    assert vw_levels.save_current_level(), 'Could not save final overview viewport'
    vw_report['final_editor_viewport'] = dict(position_cm=[float(position.x), float(position.y), float(position.z)], fov_assumption=90, distance_factor=1.0)


def vw_finish(error=None):
    global vw_done
    if vw_done:
        return
    vw_done = True
    if vw_handle is not None:
        unreal.unregister_slate_post_tick_callback(vw_handle)
    try:
        vw_restore_overview()
        for view, camera, path in vw_views:
            assert vw_camera_state(camera) == vw_original_cameras[view], 'Saved camera changed: ' + view
    except Exception:
        cleanup = traceback.format_exc()
        error = error + '\nCleanup error:\n' + cleanup if error else cleanup
    vw_report.update(success=error is None, status='failed' if error else 'complete',
                     screenshots_complete=error is None and len(vw_report['screenshots']) == 5,
                     elapsed_seconds=round(time.monotonic()-vw_started, 2))
    if error:
        vw_report['error'] = error
        unreal.log_error('VIDEO_WAREHOUSE_CAPTURE_FAILED ' + error)
    else:
        vw_report['saved_cameras_unchanged'] = True
        unreal.log('VIDEO_WAREHOUSE_CAPTURE_COMPLETE')
    vw_write_report()


def vw_png_resolution(path):
    with path.open('rb') as stream:
        header = stream.read(24)
    assert len(header) == 24 and header[:8] == b'\x89PNG\r\n\x1a\n', 'Not a PNG: ' + str(path)
    return struct.unpack('>II', header[16:24])


def vw_tick(delta):
    global vw_busy, vw_index, vw_task, vw_pending, vw_task_finished_at
    if vw_busy or vw_done:
        return
    vw_busy = True
    try:
        now = time.monotonic()
        assert now-vw_started < TIMEOUT_SECONDS, 'Timed out waiting for UE screenshots'
        if now-vw_started < WARMUP_SECONDS:
            return
        if vw_task is not None:
            if not vw_task.is_task_done():
                return
            if vw_task_finished_at is None:
                vw_task_finished_at = now
            path = vw_pending['path']
            valid = path.is_file() and path.stat().st_size > 0
            if valid and vw_pending['previous_mtime_ns'] is not None:
                valid = path.stat().st_mtime_ns != vw_pending['previous_mtime_ns']
            if not valid and now-vw_task_finished_at < 10.0:
                return
            assert valid, 'Screenshot was not written or refreshed: ' + str(path)
            actual_resolution = vw_png_resolution(path)
            assert actual_resolution == RESOLUTION, 'Wrong screenshot resolution: ' + str(actual_resolution)
            vw_report['screenshots'].append(dict(view=vw_pending['view'], path=str(path),
                                                bytes=path.stat().st_size, resolution=list(actual_resolution),
                                                camera=vw_pending['camera_state']))
            vw_task = None
            vw_pending = None
            vw_task_finished_at = None
            vw_write_report()
        if vw_index >= len(vw_views):
            vw_finish()
            return
        view, camera, path = vw_views[vw_index]
        vw_index += 1
        vw_pending = dict(view=view, path=path, previous_mtime_ns=path.stat().st_mtime_ns if path.is_file() else None,
                          camera_state=vw_camera_state(camera))
        vw_report['status'] = 'capturing_' + view.lower()
        vw_write_report()
        vw_task = unreal.AutomationLibrary.take_high_res_screenshot(
            RESOLUTION[0], RESOLUTION[1], str(path), camera=camera, delay=CAPTURE_DELAY_SECONDS)
        assert vw_task is not None, 'UE did not create a screenshot task'
    except Exception:
        vw_finish(traceback.format_exc())
    finally:
        vw_busy = False


REPORT.parent.mkdir(parents=True, exist_ok=True)
# Retire a previous invocation's callback before resetting this script's globals.
if globals().get('vw_handle') is not None and not globals().get('vw_done', True):
    unreal.unregister_slate_post_tick_callback(vw_handle)
vw_views = []
vw_original_cameras = {}
vw_index = 0
vw_task = None
vw_pending = None
vw_task_finished_at = None
vw_busy = False
vw_done = False
vw_handle = None
vw_started = time.monotonic()
vw_report = dict(success=False, status='initializing', map=MAP, screenshots_complete=False,
                 screenshots=[], resolution=list(RESOLUTION), warmup_seconds=WARMUP_SECONDS,
                 capture_delay_seconds=CAPTURE_DELAY_SECONDS)
vw_write_report()
try:
    world = vw_editor.get_editor_world()
    current_package = world.get_path_name().split('.')[0] if world else None
    if current_package != MAP:
        assert vw_levels.load_level(MAP), 'Could not load the new blue warehouse map'
        vw_report['map_loaded_by_capture'] = True
    else:
        vw_report['map_loaded_by_capture'] = False
    existing = vw_actors.get_all_level_actors()
    for view in VIEWS:
        matches = [actor for actor in existing if actor.get_actor_label() == 'CAM_Video_' + view]
        assert len(matches) == 1, 'Expected one saved camera for ' + view
        camera = matches[0]
        vw_original_cameras[view] = vw_camera_state(camera)
        vw_views.append((view, camera, ROOT / 'Saved' / ('VideoWarehouse_UE_' + view + '.png')))
    vw_actors.set_selected_level_actors([])
    overview = vw_views[0][1]
    vw_editor.set_level_viewport_camera_info(overview.get_actor_location(), overview.get_actor_rotation())
    vw_started = time.monotonic()
    vw_report['status'] = 'waiting_for_shaders'
    vw_write_report()
    vw_handle = unreal.register_slate_post_tick_callback(vw_tick)
    unreal.log('VIDEO_WAREHOUSE_CAPTURE_QUEUED: 15-second warmup, then five 1920x1080 views')
except Exception:
    vw_finish(traceback.format_exc())
    raise
