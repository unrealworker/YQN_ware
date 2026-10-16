"""Capture three views of Normal warehouse floor stackers without saving UE assets.

Run in a separate full editor with -RenderOffscreen -NormalStackerCapture.
Missing -RenderOffscreen aborts before any editor mutation or quit operation.
"""
import hashlib
import json
import itertools
import math
import re
import struct
import time
import traceback
from pathlib import Path

import unreal


COMMAND_LINE = unreal.SystemLibrary.get_command_line()
OFFSCREEN_OWNED = bool(re.search(r'(?:^|\s)-RenderOffscreen(?=\s|$)', COMMAND_LINE, re.IGNORECASE))
CAPTURE_REQUESTED = bool(re.search(r'(?:^|\s)-NormalStackerCapture(?=\s|$)', COMMAND_LINE, re.IGNORECASE))
if not OFFSCREEN_OWNED or not CAPTURE_REQUESTED:
    raise RuntimeError('Stacker capture requires -RenderOffscreen and -NormalStackerCapture; editor left open.')

ROOT = Path(r'D:\UEPro\Test')
MAPS = {'Blue': '/Game/Maps/GHS_CAD_DigitalTwin',
        'Normal': '/Game/Maps/GHS_CAD_NormalWarehouse'}
ACTOR_LABEL = None
PLAN_PATH = ROOT / 'Saved/GHS_NormalStackerPlan.json'
MESH_PATH = '/Game/VideoDigitalTwin/Meshes/SM_VR_BlueStacker'
RESOLUTION = (1920, 1080)
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
report_path = ROOT / 'Saved/GHS_NormalStackers_CaptureReport.json'
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
        actor.get_actor_label().startswith('TEMP_NORMAL_STACKER_CAPTURE_') for actor in actors.get_all_level_actors())
    if not report['temporary_cameras_removed']:
        cleanup_errors.append('Temporary stacker cameras remain in the offscreen world.')
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
    complete = error is None and len(report['screenshots']) == 3 and len(views) == 3
    report.update(success=complete, status='complete' if complete else 'failed',
                  screenshots_complete=len(report['screenshots']) == 3,
                  elapsed_seconds=round(time.monotonic() - started, 2))
    if error:
        report['error'] = error
        unreal.log_error('GHS_NORMAL_STACKERS_CAPTURE_FAILED ' + error)
    else:
        unreal.log('GHS_NORMAL_STACKERS_CAPTURE_COMPLETE ' + report['style'])
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
        assert now - started < TIMEOUT_SECONDS, 'Timed out waiting for stacker screenshots'
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


def box_corners(bounds):
    return [[bounds[axis + 3 * side[axis]] for axis in range(3)]
            for side in itertools.product((0, 1), repeat=3)]


def fit_fov(position, target, framing_boxes, minimum):
    # Fit every corner of the complete vehicle and cargo bounds into the image.
    forward = [target[i] - position[i] for i in range(3)]
    norm = math.sqrt(sum(value * value for value in forward))
    forward = [value / norm for value in forward]
    right = [-forward[1], forward[0], 0.0]
    norm = math.sqrt(sum(value * value for value in right))
    assert norm > 1e-6, 'Camera must have a defined horizontal heading'
    right = [value / norm for value in right]
    up = [forward[1] * right[2] - forward[2] * right[1],
          forward[2] * right[0] - forward[0] * right[2],
          forward[0] * right[1] - forward[1] * right[0]]
    ratio = 0.0
    for bounds in framing_boxes:
        for corner in box_corners(bounds):
            relative = [corner[i] - position[i] for i in range(3)]
            depth = sum(relative[i] * forward[i] for i in range(3))
            assert depth > 0, 'Framing subject is behind capture camera'
            horizontal = abs(sum(relative[i] * right[i] for i in range(3))) / depth
            vertical = abs(sum(relative[i] * up[i] for i in range(3))) / depth
            ratio = max(ratio, horizontal, vertical * RESOLUTION[0] / RESOLUTION[1])
    fov = max(minimum, math.degrees(2 * math.atan(ratio * 1.14)))
    assert fov < 90, 'Capture framing requires an excessively wide lens'
    return fov


def add_view(name, position_cm, target_cm, framing_boxes, minimum_fov):
    fov = fit_fov(position_cm, target_cm, framing_boxes, minimum_fov)
    position = unreal.Vector(*position_cm)
    rotation = unreal.MathLibrary.find_look_at_rotation(position, unreal.Vector(*target_cm))
    camera = actors.spawn_actor_from_class(unreal.CameraActor, position, rotation)
    assert camera, 'Could not create temporary stacker capture camera'
    temporary_cameras.append(camera)
    camera.set_actor_label('TEMP_NORMAL_STACKER_CAPTURE_' + name)
    component = camera.get_component_by_class(unreal.CameraComponent)
    component.set_field_of_view(fov)
    component.set_aspect_ratio(RESOLUTION[0] / RESOLUTION[1])
    component.set_editor_property('constrain_aspect_ratio', True)
    views.append(dict(view=name, camera=camera, target_cm=list(target_cm),
        framing_boxes_cm=framing_boxes,
        path=ROOT / 'Saved' / ('GHS_NormalStackers_' + name + '.png')))


try:
    original_keep_python_script_alive = unreal.EditorPythonScripting.get_keep_python_script_alive()
    unreal.EditorPythonScripting.set_keep_python_script_alive(True)
    assert unreal.EditorPythonScripting.get_keep_python_script_alive(), 'Could not keep asynchronous capture alive'
    report['python_executor_kept_alive'] = True
    plan = json.loads(PLAN_PATH.read_text(encoding='utf-8'))
    assert plan['success'] and plan['map'] == MAPS['Normal'] and plan['asset'].split('.')[0] == MESH_PATH
    rows = plan['placements']
    assert len(rows) == 12 and len({row['label'] for row in rows}) == 12
    main_row = rows[4]
    ACTOR_LABEL = main_row['label']
    report.update(style='Normal', map=MAPS['Normal'], actor=ACTOR_LABEL,
                  plan_path=str(PLAN_PATH), plan_sha256=sha(PLAN_PATH), primary_placement_index=5)
    for map_path in MAPS.values():
        protect_package(map_path)
    world = editor.get_editor_world()
    current = world.get_path_name().split('.')[0] if world else None
    del world
    if current != MAPS['Normal']:
        assert levels.load_level(MAPS['Normal']), 'Could not load Normal warehouse'
    original_viewport = editor.get_level_viewport_camera_info()
    original_selection = list(actors.get_selected_level_actors())
    existing = list(actors.get_all_level_actors())
    for actor in existing:
        if actor.get_component_by_class(unreal.CameraComponent):
            saved_cameras.append((actor, camera_state(actor)))
    by_label = {}
    for actor in existing:
        by_label.setdefault(actor.get_actor_label(), []).append(actor)
    material_paths = set()
    for row in rows:
        matches = by_label.get(row['label'], [])
        assert len(matches) == 1, 'Missing or duplicate stacker: ' + row['label']
        actor = matches[0]
        component = actor.get_component_by_class(unreal.StaticMeshComponent)
        assert component, 'Stacker has no StaticMeshComponent'
        mesh = component.get_editor_property('static_mesh')
        assert mesh and mesh.get_path_name().split('.')[0] == MESH_PATH, 'Unexpected stacker mesh'
        assert max(abs(a - b) for a, b in zip(vector_values(actor.get_actor_location()), row['position_cm'])) < 0.1
        assert max(abs(value - 1.0) for value in vector_values(actor.get_actor_scale3d())) < 1e-6
        assert abs((float(actor.get_actor_rotation().yaw) - row['yaw_deg'] + 180) % 360 - 180) < 0.001
        for material_index in range(component.get_num_materials()):
            material = component.get_material(material_index)
            assert material, 'Missing stacker material'
            material_paths.add(material.get_path_name())
    protect_package(MESH_PATH)
    for material_path in material_paths:
        protect_package(material_path)
    robot = by_label[ACTOR_LABEL][0]
    transform = robot.get_actor_transform()
    settings = unreal.get_default_object(unreal.load_class(None, '/Script/UnrealEd.EditorPerformanceSettings'))
    original_throttle = settings.get_editor_property('bThrottleCPUWhenNotForeground')
    settings.set_editor_property('bThrottleCPUWhenNotForeground', False)

    def local_cm(offset_m):
        return vector_values(unreal.MathLibrary.transform_location(
            transform, unreal.Vector(*(value * 100 for value in offset_m))))

    subject_boxes = [main_row['bounds_cm'], main_row['target']['bounds_cm']]
    combined = [min(bounds[i] for bounds in subject_boxes) for i in range(3)] + [
        max(bounds[i + 3] for bounds in subject_boxes) for i in range(3)]
    close_target = [(combined[i] + combined[i + 3]) / 2 for i in range(3)]
    # Local -Y is the fork direction. Cameras stand behind and to the side,
    # above the cross aisle, so the cargo row cannot obstruct the approach view.
    add_view('Close', local_cm((3.7, 2.3, 3.5)), close_target, subject_boxes, 50.0)
    add_view('Medium', local_cm((10.0, 7.0, 10.0)), local_cm((0.0, -3.0, 0.9)), subject_boxes, 60.0)
    all_boxes = [bounds for row in rows for bounds in (row['bounds_cm'], row['target']['bounds_cm'])]
    all_bounds = [min(bounds[i] for bounds in all_boxes) for i in range(3)] + [
        max(bounds[i + 3] for bounds in all_boxes) for i in range(3)]
    overview_target = [(all_bounds[i] + all_bounds[i + 3]) / 2 for i in range(3)]
    overview_position = [overview_target[0], overview_target[1] + 16000.0, overview_target[2] + 20000.0]
    add_view('Overview', overview_position, overview_target, all_boxes, 54.0)
    actors.set_selected_level_actors([])
    report.update(status='waiting_for_shaders', mesh=MESH_PATH, materials=sorted(material_paths),
                  actor_position_cm=vector_values(robot.get_actor_location()),
                  target_cargo=main_row['target'], stacker_count=len(rows),
                  warmup_seconds=WARMUP_SECONDS, capture_delay_seconds=CAPTURE_DELAY_SECONDS,
                  camera_count=len(views), saved_camera_count=len(saved_cameras),
                  initial_saved_package_sha256=dict(protected_files),
                  view_plan=[dict(view=view['view'], camera=camera_state(view['camera']),
                      target_cm=view['target_cm'], framing_boxes_cm=view['framing_boxes_cm']) for view in views])
    write_report()
    started = time.monotonic()
    callback = unreal.register_slate_post_tick_callback(tick)
    unreal.log('GHS_NORMAL_STACKERS_CAPTURE_QUEUED: three 1920x1080 captures; primary=' + ACTOR_LABEL)
except Exception:
    finish(traceback.format_exc())
    raise
