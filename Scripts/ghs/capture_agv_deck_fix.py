"""Capture four close views of GHS_AGV_34 without saving any UE assets.

Run in a separate full editor with -RenderOffscreen -AGVDeckStyle=blue/normal.
Missing -RenderOffscreen aborts before any editor mutation or quit operation.
"""
import hashlib
import json
import re
import struct
import time
import traceback
from pathlib import Path

import unreal


COMMAND_LINE = unreal.SystemLibrary.get_command_line()
OFFSCREEN_OWNED = bool(re.search(r'(?:^|\s)-RenderOffscreen(?=\s|$)', COMMAND_LINE, re.IGNORECASE))
if not OFFSCREEN_OWNED:
    raise RuntimeError('AGV deck capture requires a separate -RenderOffscreen editor; no changes made and editor left open.')

ROOT = Path(r'D:\UEPro\Test')
MAPS = {'Blue': '/Game/Maps/GHS_CAD_DigitalTwin',
        'Normal': '/Game/Maps/GHS_CAD_NormalWarehouse'}
ACTOR_LABEL = 'GHS_AGV_34'
RESOLUTION = (1280, 960)
WARMUP_SECONDS = 20.0
CAPTURE_DELAY_SECONDS = 4.0
TIMEOUT_SECONDS = 240.0
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
started = time.monotonic()
done = False
busy = False
callback = None
task = None
task_finished_at = None
pending = None
index = 0
views = []
temporary_cameras = []
saved_cameras = []
original_viewport = None
original_selection = None
settings = None
original_throttle = None
original_keep_python_script_alive = None
protected_files = {}
report_path = ROOT / 'Saved/GHS_AGVDeckFix_Unknown_CaptureReport.json'
report = dict(success=False, status='initializing', actor=ACTOR_LABEL,
              resolution=list(RESOLUTION), screenshots=[], offscreen_required=True)


def vector_values(vector):
    return [float(vector.x), float(vector.y), float(vector.z)]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def protect_package(package_path):
    package_path = package_path.split('.')[0]
    if package_path.startswith('/Game/'):
        extension = '.umap' if package_path in MAPS.values() else '.uasset'
        path = ROOT / 'Content' / (package_path[len('/Game/'):] + extension)
        assert path.is_file(), 'Saved package missing: ' + str(path)
        protected_files[str(path)] = sha(path)


def camera_state(camera):
    component = camera.get_component_by_class(unreal.CameraComponent)
    rotation = camera.get_actor_rotation()
    return dict(position_cm=vector_values(camera.get_actor_location()),
                rotation_degrees=[float(rotation.pitch), float(rotation.yaw), float(rotation.roll)],
                fov=float(component.get_editor_property('field_of_view')),
                aspect_ratio=float(component.get_editor_property('aspect_ratio')),
                constrain_aspect_ratio=bool(component.get_editor_property('constrain_aspect_ratio')))


def write_report():
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')


def png_resolution(path):
    with path.open('rb') as stream:
        header = stream.read(24)
    assert len(header) == 24 and header[:8] == b'\x89PNG\r\n\x1a\n', 'Invalid PNG: ' + str(path)
    return struct.unpack('>II', header[16:24])


def finish(error=None):
    global done
    if done:
        return
    done = True
    cleanup_errors = []

    def cleanup(action):
        try:
            action()
        except Exception:
            cleanup_errors.append(traceback.format_exc())

    def remove_camera(camera):
        assert actors.destroy_actor(camera), 'Could not remove temporary camera'

    def check_saved_cameras():
        for camera, state in saved_cameras:
            assert camera_state(camera) == state, 'Saved camera changed: ' + camera.get_actor_label()
        report['saved_cameras_unchanged'] = True

    def check_packages():
        for filename, initial_hash in protected_files.items():
            assert sha(Path(filename)) == initial_hash, 'Saved package changed: ' + filename
        report['saved_packages_unchanged'] = True
        report['saved_package_sha256'] = protected_files

    if callback is not None:
        cleanup(lambda: unreal.unregister_slate_post_tick_callback(callback))
    for camera in temporary_cameras:
        cleanup(lambda camera=camera: remove_camera(camera))
    report['temporary_cameras_removed'] = not any(
        actor.get_actor_label().startswith('TEMP_AGV_DECK_FIX_') for actor in actors.get_all_level_actors())
    if not report['temporary_cameras_removed']:
        cleanup_errors.append('Temporary AGV deck cameras remain in the offscreen world.')
    cleanup(check_saved_cameras)
    if original_viewport is not None:
        cleanup(lambda: editor.set_level_viewport_camera_info(*original_viewport))
    if original_selection is not None:
        cleanup(lambda: actors.set_selected_level_actors(original_selection))
    if settings is not None and original_throttle is not None:
        cleanup(lambda: settings.set_editor_property('bThrottleCPUWhenNotForeground', original_throttle))
    cleanup(check_packages)
    if cleanup_errors:
        error = (error + '\n' if error else '') + '\nCleanup errors:\n' + '\n'.join(cleanup_errors)
    complete = error is None and len(report['screenshots']) == 4 and len(views) == 4
    report.update(success=complete, status='complete' if complete else 'failed',
                  screenshots_complete=len(report['screenshots']) == 4,
                  elapsed_seconds=round(time.monotonic() - started, 2))
    if error:
        report['error'] = error
        unreal.log_error('GHS_AGV_DECK_FIX_CAPTURE_FAILED ' + error)
    else:
        unreal.log('GHS_AGV_DECK_FIX_CAPTURE_COMPLETE ' + report['style'])
    try:
        write_report()
    finally:
        # No level, asset, material, dirty-package, or configuration save calls.
        if OFFSCREEN_OWNED:
            try:
                if original_keep_python_script_alive is not None:
                    unreal.EditorPythonScripting.set_keep_python_script_alive(original_keep_python_script_alive)
            finally:
                unreal.SystemLibrary.quit_editor()


def tick(delta):
    global busy, index, task, pending, task_finished_at
    if busy or done:
        return
    busy = True
    try:
        now = time.monotonic()
        assert now - started < TIMEOUT_SECONDS, 'Timed out waiting for AGV deck screenshots'
        if now - started < WARMUP_SECONDS:
            return
        if task is not None:
            if not task.is_task_done():
                return
            if task_finished_at is None:
                task_finished_at = now
            path = pending['path']
            valid = path.is_file() and path.stat().st_size > 0
            if valid and pending['previous_mtime_ns'] is not None:
                valid = path.stat().st_mtime_ns != pending['previous_mtime_ns']
            if not valid and now - task_finished_at < 10.0:
                return
            assert valid, 'Screenshot was not refreshed: ' + str(path)
            resolution = png_resolution(path)
            assert resolution == RESOLUTION, ('Unexpected screenshot resolution', resolution)
            report['screenshots'].append(dict(view=pending['view'], path=str(path),
                bytes=path.stat().st_size, resolution=list(resolution), camera=pending['camera'],
                sha256=sha(path)))
            task = None
            pending = None
            task_finished_at = None
            write_report()
        if index >= len(views):
            finish()
            return
        view = views[index]
        index += 1
        camera = view['camera']
        path = view['path']
        editor.set_level_viewport_camera_info(camera.get_actor_location(), camera.get_actor_rotation())
        pending = dict(view=view['view'], path=path, camera=camera_state(camera),
                       previous_mtime_ns=path.stat().st_mtime_ns if path.exists() else None)
        report['status'] = 'capturing_' + view['view']
        write_report()
        task = unreal.AutomationLibrary.take_high_res_screenshot(
            RESOLUTION[0], RESOLUTION[1], str(path), camera=camera, delay=CAPTURE_DELAY_SECONDS)
        assert task is not None, 'UE did not create a screenshot task'
    except Exception:
        finish(traceback.format_exc())
    finally:
        busy = False


def add_view(name, local_position_m, local_target_m, robot_transform, style):
    position = unreal.MathLibrary.transform_location(
        robot_transform, unreal.Vector(*(value * 100 for value in local_position_m)))
    target = unreal.MathLibrary.transform_location(
        robot_transform, unreal.Vector(*(value * 100 for value in local_target_m)))
    rotation = unreal.MathLibrary.find_look_at_rotation(position, target)
    camera = actors.spawn_actor_from_class(unreal.CameraActor, position, rotation)
    assert camera, 'Could not create temporary AGV deck camera'
    temporary_cameras.append(camera)
    camera.set_actor_label('TEMP_AGV_DECK_FIX_' + name)
    component = camera.get_component_by_class(unreal.CameraComponent)
    component.set_field_of_view(55.0)
    component.set_aspect_ratio(RESOLUTION[0] / RESOLUTION[1])
    component.set_editor_property('constrain_aspect_ratio', True)
    views.append(dict(view=name, camera=camera, target_cm=vector_values(target),
        local_position_m=list(local_position_m),
        path=ROOT / 'Saved' / ('GHS_AGVDeckFix_' + style + '_' + name + '.png')))


try:
    # -ExecutePythonScript normally schedules QUIT_EDITOR on its next tick.
    # Hold the executor alive until all screenshot callbacks and cleanup finish.
    original_keep_python_script_alive = unreal.EditorPythonScripting.get_keep_python_script_alive()
    unreal.EditorPythonScripting.set_keep_python_script_alive(True)
    assert unreal.EditorPythonScripting.get_keep_python_script_alive(), 'Could not keep asynchronous Python capture alive'
    report['python_executor_kept_alive'] = True
    requested = re.findall(r'(?:^|\s)-AGVDeckStyle=(blue|normal)(?=\s|$)', COMMAND_LINE, re.IGNORECASE)
    assert len(requested) == 1, 'Pass exactly one -AGVDeckStyle=blue or -AGVDeckStyle=normal'
    style = requested[0].title()
    report_path = ROOT / 'Saved' / ('GHS_AGVDeckFix_' + style + '_CaptureReport.json')
    report.update(style=style, map=MAPS[style])
    for map_path in MAPS.values():
        protect_package(map_path)
    world = editor.get_editor_world()
    current = world.get_path_name().split('.')[0] if world else None
    del world
    if current != MAPS[style]:
        assert levels.load_level(MAPS[style]), 'Could not load ' + MAPS[style]
    original_viewport = editor.get_level_viewport_camera_info()
    original_selection = list(actors.get_selected_level_actors())
    existing = list(actors.get_all_level_actors())
    for actor in existing:
        if actor.get_component_by_class(unreal.CameraComponent):
            saved_cameras.append((actor, camera_state(actor)))
    matches = [actor for actor in existing if actor.get_actor_label() == ACTOR_LABEL]
    assert len(matches) == 1, 'Expected exactly one ' + ACTOR_LABEL
    robot = matches[0]
    component = robot.get_component_by_class(unreal.StaticMeshComponent)
    assert component, 'AGV has no StaticMeshComponent'
    mesh = component.get_editor_property('static_mesh')
    assert mesh and mesh.get_name() == 'SM_GHS_KukaLowProfileAGV', 'Unexpected AGV mesh'
    protect_package(mesh.get_path_name())
    materials = []
    for material_index in range(component.get_num_materials()):
        material = component.get_material(material_index)
        materials.append(material.get_path_name() if material else None)
        if material:
            protect_package(material.get_path_name())
    settings = unreal.get_default_object(unreal.load_class(None, '/Script/UnrealEd.EditorPerformanceSettings'))
    original_throttle = settings.get_editor_property('bThrottleCPUWhenNotForeground')
    settings.set_editor_property('bThrottleCPUWhenNotForeground', False)
    transform = robot.get_actor_transform()
    # Robot-local metre coordinates frame its 0.954 x 1.415 m body and all four
    # corner plates. Each pair varies the view slightly to expose coplanar flicker.
    target = (0.0, 0.0, 0.29)
    for name, position in [
        ('Top_A', (0.0, -0.025, 2.50)),
        ('Top_B', (0.035, -0.045, 2.47)),
        ('Oblique_A', (0.95, -0.85, 1.95)),
        ('Oblique_B', (1.00, -0.79, 1.98)),
    ]:
        add_view(name, position, target, transform, style)
    # Clear selection highlights while leaving AGV transforms and materials intact.
    actors.set_selected_level_actors([])
    report.update(status='waiting_for_shaders', mesh=mesh.get_path_name(), materials=materials,
                  actor_position_cm=vector_values(robot.get_actor_location()),
                  actor_scale=vector_values(robot.get_actor_scale3d()),
                  warmup_seconds=WARMUP_SECONDS, capture_delay_seconds=CAPTURE_DELAY_SECONDS,
                  camera_count=len(views), saved_camera_count=len(saved_cameras),
                  initial_saved_package_sha256=dict(protected_files),
                  view_plan=[dict(view=view['view'], camera=camera_state(view['camera']),
                      target_cm=view['target_cm'], local_position_m=view['local_position_m']) for view in views])
    write_report()
    started = time.monotonic()
    callback = unreal.register_slate_post_tick_callback(tick)
    unreal.log('GHS_AGV_DECK_FIX_CAPTURE_QUEUED ' + style + ': four 1280x960 captures')
except Exception:
    finish(traceback.format_exc())
    raise
