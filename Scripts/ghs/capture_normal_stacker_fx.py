"""Four fixed-camera frames of saved Normal stacker FX; never save UE packages.

Requires a dedicated full editor: -RenderOffscreen -NormalStackerFXCapture.
Keep the asynchronous Python executor alive until capture, cleanup, and quit.
Run analyze_normal_stacker_fx.py with ordinary Python after this editor exits.
"""
import hashlib
import itertools
import json
import math
import re
import struct
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import unreal


COMMAND_LINE = unreal.SystemLibrary.get_command_line()
OFFSCREEN_OWNED = bool(re.search(r'(?:^|\s)-RenderOffscreen(?=\s|$)', COMMAND_LINE, re.I))
CAPTURE_REQUESTED = bool(re.search(r'(?:^|\s)-NormalStackerFXCapture(?=\s|$)', COMMAND_LINE, re.I))
if not (OFFSCREEN_OWNED and CAPTURE_REQUESTED):
    raise RuntimeError('Requires -RenderOffscreen -NormalStackerFXCapture; no mutation or quit performed.')

ROOT = Path(r'D:\UEPro\Test')
MAP = '/Game/Maps/GHS_CAD_NormalWarehouse'
BLUE_MAP = '/Game/Maps/GHS_CAD_DigitalTwin'
MESH = '/Game/VideoDigitalTwin/Meshes/SM_VR_BlueStacker'
SOURCE = ROOT / 'Saved/GHS_NormalStackers.json'
REPORT = ROOT / 'Saved/GHS_NormalStackerFX_CaptureReport.json'
RESOLUTION = (1280, 960)
FRAME_INTERVAL = .43
WARMUP = 20.
TIMEOUT = 240.
LABEL = 'GHN_FloorStacker_05'
TEMP_PREFIX = 'TEMP_NORMAL_STACKER_FX_CAPTURE_'
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
started = time.monotonic()
done = busy = False
callback = task = pending = camera = None
original_viewport = original_selection = settings = original_throttle = original_keepalive = None
baseline = None
frame_index = 0
next_request_at = 0.
task_finished_at = None
protected = {}
report = dict(success=False, status='initializing', map=MAP, actor=LABEL,
              resolution=list(RESOLUTION), screenshots=[], requested_interval_seconds=FRAME_INTERVAL,
              timing_note='Request and completion timestamps bound capture. PNG mtime is a write timestamp, not an exact GPU exposure timestamp.',
              offscreen_required=True, no_package_save=True)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def vec(v):
    return [float(v.x), float(v.y), float(v.z)]


def rot(r):
    return [float(r.pitch), float(r.yaw), float(r.roll)]


def protect(path):
    package = path.split('.')[0]
    if package.startswith('/Game/'):
        suffix = '.umap' if package in (MAP, BLUE_MAP) else '.uasset'
        filename = ROOT / 'Content' / (package[6:] + suffix)
        assert filename.is_file(), 'Missing saved package: ' + str(filename)
        protected[str(filename)] = sha(filename)


def protect_material(material):
    seen = set()
    while material and material.get_path_name() not in seen:
        seen.add(material.get_path_name())
        protect(material.get_path_name())
        if isinstance(material, unreal.MaterialInstanceConstant):
            material = material.get_editor_property('parent')
        else:
            break


def camera_state(actor):
    c = actor.get_component_by_class(unreal.CameraComponent)
    return dict(position_cm=vec(actor.get_actor_location()), rotation_deg=rot(actor.get_actor_rotation()),
                fov=float(c.get_editor_property('field_of_view')), aspect=float(c.get_editor_property('aspect_ratio')),
                constrain_aspect_ratio=bool(c.get_editor_property('constrain_aspect_ratio')))


def actor_snapshot():
    result = {}
    for actor in actors.get_all_level_actors():
        if actor.get_actor_label().startswith(TEMP_PREFIX):
            continue
        parent = actor.get_attach_parent_actor()
        row = dict(label=actor.get_actor_label(), actor_class=actor.get_class().get_path_name(),
                   position=vec(actor.get_actor_location()), rotation=rot(actor.get_actor_rotation()),
                   scale=vec(actor.get_actor_scale3d()), parent=parent.get_path_name() if parent else None)
        c = actor.get_component_by_class(unreal.CameraComponent)
        if c:
            row['camera'] = camera_state(actor)
        c = actor.get_component_by_class(unreal.StaticMeshComponent)
        if c:
            mesh = c.get_editor_property('static_mesh')
            row['mesh'] = mesh.get_path_name() if mesh else None
            row['materials'] = [c.get_material(k).get_path_name() if c.get_material(k) else None for k in range(c.get_num_materials())]
        c = actor.get_component_by_class(unreal.DecalComponent)
        if c:
            material = c.get_decal_material()
            row['decal'] = dict(material=material.get_path_name() if material else None,
                                size=vec(c.get_editor_property('decal_size')))
        result[actor.get_path_name()] = row
    return result


def write_report():
    REPORT.write_text(json.dumps(report, indent=2), encoding='utf8')


def time_sample():
    world = editor.get_editor_world()
    return dict(monotonic_seconds=time.monotonic(), utc=datetime.now(timezone.utc).isoformat(),
                engine_frame=int(unreal.SystemLibrary.get_frame_count()),
                world_game_seconds=float(unreal.GameplayStatics.get_time_seconds(world)),
                world_real_seconds=float(unreal.GameplayStatics.get_real_time_seconds(world)))


def png_resolution(path):
    with path.open('rb') as f:
        header = f.read(24)
    assert header[:8] == b'\x89PNG\r\n\x1a\n' and len(header) == 24, 'Invalid screenshot PNG'
    return struct.unpack('>II', header[16:24])


def finish(error=None):
    global done
    if done:
        return
    done = True
    errors = []

    def cleanup(fn):
        try:
            fn()
        except Exception:
            errors.append(traceback.format_exc())

    def remove_camera():
        assert actors.destroy_actor(camera), 'Temporary camera removal failed'

    def check_state():
        assert not any(a.get_actor_label().startswith(TEMP_PREFIX) for a in actors.get_all_level_actors())
        if baseline is not None:
            assert actor_snapshot() == baseline, 'An original actor/camera/attachment/material changed in memory'
            report['original_actor_snapshot_unchanged'] = True
        report['temporary_cameras_removed'] = True

    def check_files():
        for path, expected in protected.items():
            assert sha(Path(path)) == expected, 'Saved package changed: ' + path
        report['saved_package_sha256'] = protected
        report['saved_packages_unchanged'] = True

    if callback is not None:
        cleanup(lambda: unreal.unregister_slate_post_tick_callback(callback))
    if camera is not None:
        cleanup(remove_camera)
    cleanup(check_state)
    if original_viewport is not None:
        cleanup(lambda: editor.set_level_viewport_camera_info(*original_viewport))
    if original_selection is not None:
        cleanup(lambda: actors.set_selected_level_actors(original_selection))
    if settings is not None and original_throttle is not None:
        cleanup(lambda: settings.set_editor_property('bThrottleCPUWhenNotForeground', original_throttle))
    cleanup(check_files)
    if errors:
        error = (error + '\n' if error else '') + '\nCleanup errors:\n' + '\n'.join(errors)
    complete = error is None and len(report['screenshots']) == 4
    report.update(success=complete, status='complete' if complete else 'failed', elapsed_seconds=round(time.monotonic() - started, 3))
    times = [r['requested']['monotonic_seconds'] for r in report['screenshots']]
    report['request_intervals_seconds'] = [round(b - a, 6) for a, b in zip(times, times[1:])]
    report['visual_animation_proven'] = False
    report['visual_analysis_note'] = 'Four fresh PNGs alone do not prove animation. Run analyze_normal_stacker_fx.py and inspect the green FX changes.'
    if error:
        report['error'] = error
        unreal.log_error('GHS_NORMAL_STACKER_FX_CAPTURE_FAILED ' + error)
    else:
        unreal.log('GHS_NORMAL_STACKER_FX_CAPTURE_COMPLETE: four fixed-camera 1280x960 frames')
    try:
        write_report()
    finally:
        # The two startup flags guarantee this is our dedicated capture editor.
        # No save_current_level/save_asset/save_config/save_dirty_packages calls.
        try:
            if original_keepalive is not None:
                unreal.EditorPythonScripting.set_keep_python_script_alive(original_keepalive)
        finally:
            unreal.SystemLibrary.quit_editor()


def tick(delta):
    global busy, task, pending, frame_index, next_request_at, task_finished_at
    if busy or done:
        return
    busy = True
    try:
        now = time.monotonic()
        assert now - started < TIMEOUT, 'Capture timed out'
        if now - started < WARMUP:
            return
        if task is not None:
            if not task.is_task_done():
                pending['last_incomplete'] = time_sample()
                return
            if task_finished_at is None:
                task_finished_at = now
                pending['first_done'] = time_sample()
            path = pending['path']
            refreshed = path.is_file() and path.stat().st_size > 0
            if refreshed and pending['previous_mtime_ns'] is not None:
                refreshed = path.stat().st_mtime_ns != pending['previous_mtime_ns']
            if not refreshed and now - task_finished_at < 10.:
                return
            assert refreshed, 'Screenshot not refreshed: ' + str(path)
            assert png_resolution(path) == RESOLUTION, 'Unexpected screenshot resolution'
            assert camera_state(camera) == report['camera'], 'Capture camera drifted'
            report['screenshots'].append(dict(frame=pending['frame'], path=str(path),
                requested=pending['requested'], api_returned=pending['api_returned'],
                last_incomplete=pending.get('last_incomplete'), first_done=pending['first_done'],
                completed=time_sample(), png_mtime_ns=path.stat().st_mtime_ns,
                png_mtime_utc=datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                bytes=path.stat().st_size, sha256=sha(path), resolution=list(RESOLUTION), camera=report['camera']))
            task = pending = task_finished_at = None
            write_report()
        if frame_index == 4:
            finish()
            return
        if now < next_request_at:
            return
        frame_index += 1
        path = ROOT / 'Saved' / ('GHS_NormalStackerFX_Frame%02d.png' % frame_index)
        pending = dict(frame=frame_index, path=path, requested=time_sample(),
                       previous_mtime_ns=path.stat().st_mtime_ns if path.exists() else None)
        next_request_at = pending['requested']['monotonic_seconds'] + FRAME_INTERVAL
        report['status'] = 'capturing_frame_%02d' % frame_index
        write_report()
        # Zero API delay avoids imposing the old four-second (=two animation
        # periods) delay. Slate schedules requests .43s apart, subject to render time.
        task = unreal.AutomationLibrary.take_high_res_screenshot(*RESOLUTION, str(path), camera=camera, delay=0.)
        pending['api_returned'] = time_sample()
        assert task is not None, 'UE did not create a screenshot task'
    except Exception:
        finish(traceback.format_exc())
    finally:
        busy = False


try:
    original_keepalive = unreal.EditorPythonScripting.get_keep_python_script_alive()
    unreal.EditorPythonScripting.set_keep_python_script_alive(True)
    assert unreal.EditorPythonScripting.get_keep_python_script_alive()
    report['python_executor_kept_alive'] = True
    source = json.loads(SOURCE.read_text(encoding='utf8'))
    assert source['success'] and source['map'] == MAP and source['added_count'] == 12
    placements = source['added']
    primary = next(row for row in placements if row['label'] == LABEL)
    report.update(source_report=str(SOURCE), source_report_sha256=sha(SOURCE), target_cargo=primary['target'])
    protect(MAP)
    protect(BLUE_MAP)
    assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages(), 'Refusing to load over unsaved maps'
    # Always load the saved package in this dedicated process, never reuse a live
    # editing session's world. Startup flags were checked before any mutation.
    assert levels.load_level(MAP), 'Failed to load saved Normal map'
    original_viewport = editor.get_level_viewport_camera_info()
    original_selection = list(actors.get_selected_level_actors())
    existing = list(actors.get_all_level_actors())
    by = {}
    for actor in existing:
        by.setdefault(actor.get_actor_label(), []).append(actor)
    assert len(existing) == source['actor_count'] + 24, ('Expected 24 saved FX actors', len(existing))
    fx_rows = []
    for row in placements:
        assert len(by.get(row['label'], [])) == 1
        robot = by[row['label']][0]
        component = robot.get_component_by_class(unreal.StaticMeshComponent)
        mesh = component.get_editor_property('static_mesh')
        assert mesh and mesh.get_path_name().split('.')[0] == MESH
        assert max(abs(a - b) for a, b in zip(vec(robot.get_actor_location()), row['position_cm'])) < .1
        assert max(abs(a - 1.) for a in vec(robot.get_actor_scale3d())) < 1e-6
        protect(mesh.get_path_name())
        for k in range(component.get_num_materials()):
            protect_material(component.get_material(k))
        for kind, radius in [('Diffusion', 155.), ('Radar', 300.)]:
            label = 'FX_' + row['label'] + '_' + kind
            assert len(by.get(label, [])) == 1, 'Missing/duplicate saved effect: ' + label
            effect = by[label][0]
            assert effect.get_attach_parent_actor() == robot, 'Effect is not attached to its stacker: ' + label
            decal = effect.get_component_by_class(unreal.DecalComponent)
            assert decal, 'Expected DecalComponent: ' + label
            size = vec(decal.get_editor_property('decal_size'))
            assert abs(size[1] - radius) < .01 and abs(size[2] - radius) < .01, ('Wrong FX radius', label, size)
            material = decal.get_decal_material()
            assert material and material.get_path_name().startswith('/Game/GHSNormalWarehouse/FX/')
            protect_material(material)
            fx_rows.append(dict(actor=label, parent=row['label'], material=material.get_path_name(), decal_size=size))
    baseline = actor_snapshot()
    robot = by[LABEL][0]
    transform = robot.get_actor_transform()

    def local(offset):
        return unreal.MathLibrary.transform_location(transform, unreal.Vector(*(v * 100 for v in offset)))

    position = local((3.7, 2.3, 6.2))
    target = local((0., -.9, .5))
    rotation = unreal.MathLibrary.find_look_at_rotation(position, target)
    camera = actors.spawn_actor_from_class(unreal.CameraActor, position, rotation)
    assert camera
    camera.set_actor_label(TEMP_PREFIX + 'Fixed')
    c = camera.get_component_by_class(unreal.CameraComponent)
    # Fit the actual diffusion circle and forward radar fan, plus the complete
    # vehicle and cargo. The shader draws a +/-40-degree fan along local -Y, not
    # a full 3 m disc. Preserve the requested close framing at a minimum 60 deg.
    p, t = vec(position), vec(target)
    forward = [t[i] - p[i] for i in range(3)]
    norm = math.sqrt(sum(v * v for v in forward))
    forward = [v / norm for v in forward]
    right = [-forward[1], forward[0], 0.]
    norm = math.sqrt(sum(v * v for v in right))
    right = [v / norm for v in right]
    up = [forward[1] * right[2] - forward[2] * right[1],
          forward[2] * right[0] - forward[0] * right[2],
          forward[0] * right[1] - forward[1] * right[0]]
    framing_points = [vec(local((1.55 * math.cos(math.radians(k)), 1.55 * math.sin(math.radians(k)), .0025)))
                      for k in range(360)]
    framing_points.extend(vec(local((3 * math.sin(math.radians(k)), -3 * math.cos(math.radians(k)), .0025)))
                          for k in range(-40, 41))
    for bounds in (primary['bounds_cm'], primary['target']['bounds_cm']):
        framing_points.extend([[bounds[i + 3 * side[i]] for i in range(3)]
                               for side in itertools.product((0, 1), repeat=3)])
    ratio = 0.
    for point in framing_points:
        relative = [point[i] - p[i] for i in range(3)]
        depth = sum(relative[i] * forward[i] for i in range(3))
        assert depth > 0., 'Framing subject behind temporary camera'
        ratio = max(ratio, abs(sum(relative[i] * right[i] for i in range(3))) / depth,
                    abs(sum(relative[i] * up[i] for i in range(3))) / depth * RESOLUTION[0] / RESOLUTION[1])
    fitted_fov = max(60., math.degrees(2 * math.atan(ratio * 1.08)))
    assert fitted_fov < 85.
    c.set_field_of_view(fitted_fov)
    c.set_aspect_ratio(RESOLUTION[0] / RESOLUTION[1])
    c.set_editor_property('constrain_aspect_ratio', True)
    settings = unreal.get_default_object(unreal.load_class(None, '/Script/UnrealEd.EditorPerformanceSettings'))
    original_throttle = settings.get_editor_property('bThrottleCPUWhenNotForeground')
    settings.set_editor_property('bThrottleCPUWhenNotForeground', False)
    # This API removes the subsystem's realtime=false override; UE has no paired
    # public getter for it. It does not by itself prove the base realtime flag.
    # The dedicated editor exits without saving preferences; sampled world time
    # and frame images provide the evidence that actual animation advanced.
    levels.editor_set_viewport_realtime(True)
    clock_cvars = {name: unreal.SystemLibrary.get_console_variable_string_value(name)
                   for name in ('r.RenderTimeFrozen', 'r.Test.OverrideTimeMaterialExpressions')}
    assert float(clock_cvars['r.RenderTimeFrozen']) == 0., 'Render time is frozen'
    assert float(clock_cvars['r.Test.OverrideTimeMaterialExpressions']) < 0., 'Material time is overridden'
    actors.set_selected_level_actors([])
    editor.set_level_viewport_camera_info(position, rotation)
    report.update(status='waiting_for_shaders', actor_count=len(existing), fx_count=len(fx_rows), fx=fx_rows,
                  camera=camera_state(camera), local_camera_m=[3.7, 2.3, 6.2], local_target_m=[0., -.9, .5],
                  target_world_cm=vec(target), actor_position_cm=vec(robot.get_actor_location()),
                  warmup_seconds=WARMUP, screenshot_api_delay_seconds=0.,
                  fitted_fov_degrees=fitted_fov, requested_minimum_fov_degrees=60.,
                  framing='155cm diffusion circle, forward +/-40deg 300cm radar fan, full stacker and target cargo with 8% angular margin',
                  time_console_variables=clock_cvars, viewport_subsystem_realtime_override_removed=True,
                  initial_saved_package_sha256=dict(protected))
    write_report()
    started = time.monotonic()
    callback = unreal.register_slate_post_tick_callback(tick)
    unreal.log('GHS_NORMAL_STACKER_FX_CAPTURE_QUEUED: 4 fixed frames, requested spacing 0.43s')
except Exception:
    finish(traceback.format_exc())
    raise
