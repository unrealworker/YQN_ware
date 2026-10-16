"""Opt-in live-editor GPU CSV capture; importing this module performs no actions.

Call start('Before') / start('After') from the same stationary editor viewport.
Keep the window non-minimized and its viewport dimensions unchanged. Do not run
screenshots, asset compilation, or a second capture while sampling. All temporary
console/settings values are restored; no level, asset, or config is saved.
"""
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import re
import statistics
import time
import traceback

ROOT = Path(r'D:\UEPro\Test')
_active = globals().get('_active')
STATUS_PATH = ROOT/'Saved/GHS_LightingProfileStatus.json'


def _stats(values):
    ordered = sorted(values)
    assert ordered, 'No usable samples'
    return dict(count=len(ordered), mean_ms=statistics.fmean(ordered),
                median_ms=statistics.median(ordered),
                p95_ms=ordered[max(0, math.ceil(len(ordered) * .95) - 1)],
                min_ms=ordered[0], max_ms=ordered[-1])


def summarize_csv(path, trim_frames=10, expected_frames=360):
    """Read UE's final header (column set may grow during capture), not its first."""
    path = Path(path)
    contents = path.read_text(encoding='utf-8-sig')
    assert '[HasHeaderRowAtEnd],1' in contents, 'CSV has not finished writing'
    rows = list(csv.reader(io.StringIO(contents)))
    headers = [i for i, row in enumerate(rows) if row and row[0] == 'EVENTS']
    assert headers, 'CSV lacks final EVENTS header'
    end = headers[-1]
    names = rows[end]
    start = headers[0] + 1 if len(headers) > 1 else 0
    samples = [row for row in rows[start:end]
               if row and not row[0].startswith('[') and row[0] != 'EVENTS']
    assert len(samples) >= expected_frames - 2, ('Incomplete frame capture', len(samples))
    samples = samples[trim_frames:len(samples) - trim_frames]
    assert 'GPUTime' in names and 'GPU/Total' in names, 'Actual GPU timing columns missing'
    result = {}
    for index, name in enumerate(names):
        if name not in ('GPUTime', 'FrameTime', 'GameThreadTime', 'RenderThreadTime') and not name.startswith('GPU/'):
            continue
        values = []
        for row in samples:
            try:
                value = float(row[index]) if index < len(row) else 0.0
            except ValueError:
                continue
            if math.isfinite(value):
                values.append(value)
        if name in ('GPUTime', 'GPU/Total'):
            assert sum(v > 0 for v in values) >= len(samples) * .95, (name, 'GPU timing unavailable')
        if values:
            result[name] = _stats(values)
    return dict(csv=str(path), csv_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                captured_frame_count=len(samples) + trim_frames * 2,
                analyzed_frame_count=len(samples), trim_each_end_frames=trim_frames,
                primary_metric='GPUTime', units='milliseconds', metrics=result)


def try_completed_csv(path, expected_frames=360):
    """UE's Windows writer denies readers until close; a locked file is pending."""
    path = Path(path)
    try:
        size = path.stat().st_size
        with path.open('rb') as stream:
            stream.seek(max(0, size - 32768))
            if b'[HasHeaderRowAtEnd],1' not in stream.read():
                return None
        return summarize_csv(path, expected_frames=expected_frames)
    except (OSError, UnicodeError):
        # Includes file-not-created, sharing violations, and incomplete writes.
        # The capture deadline remains responsible for a persistent I/O failure.
        return None


def _view(unreal):
    position, rotation = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_level_viewport_camera_info()
    level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    return dict(position_cm=[position.x, position.y, position.z],
                rotation_deg=[rotation.pitch, rotation.yaw, rotation.roll],
                viewport_config_key=str(level.get_active_viewport_config_key()),
                game_view=level.editor_get_game_view())


def _same_view(a, b):
    return all(abs(x-y) < 1e-4 for key in ('position_cm', 'rotation_deg')
               for x, y in zip(a[key], b[key])) and all(
                   a[key] == b[key] for key in ('viewport_config_key', 'game_view'))


def start(label, frames=360, warmup_frames=120, warmup_seconds=3.0, timeout_seconds=180,
          planned_movement=None, report_path=None, status_path=None, csv_prefix=None,
          restore_camera=None):
    """Schedule capture on Slate ticks; never block the render loop with sleep."""
    import unreal
    global _active
    assert _active is None, 'A lighting profile is already running'
    assert re.fullmatch(r'[A-Za-z0-9_-]+', label), 'Use a short safe capture label'
    assert frames >= 120 and warmup_frames >= 30 and warmup_seconds >= 1
    # Stationary verification remains the default. Only this explicit option
    # permits the camera positions generated by our own planned motion.
    if planned_movement is not None:
        planned_movement = dict(planned_movement)
        duration = float(planned_movement['duration_seconds'])
        distance = float(planned_movement['distance_cm'])
        assert math.isfinite(duration) and 1 <= duration <= 60
        assert math.isfinite(distance) and 0 < distance <= 10000
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    assert world and world.get_name() == 'GHS_CAD_DigitalTwin', 'Load the GHS map first'
    settings = unreal.get_default_object(unreal.load_class(None, '/Script/UnrealEd.EditorPerformanceSettings'))
    throttle_property = 'bThrottleCPUWhenNotForeground'
    temporary = {
        'r.GPUStatsEnabled': 1, 'r.GPUCsvStatsEnabled': 1, 'csv.CompressionMode': 0,
        'Slate.bAllowThrottling': 0, 't.IdleWhenNotForeground': 0,
        't.MaxFPS': 0, 'r.VSync': 0, 'r.VSyncEditor': 0,
        'r.DynamicRes.OperationMode': 0,
    }
    observe = ['r.ScreenPercentage', 'r.Editor.Viewport.ScreenPercentage',
               'r.Editor.Viewport.ScreenPercentageMode.RealTime', 'sg.ResolutionQuality',
               'r.AntiAliasingMethod', 'r.DynamicGlobalIlluminationMethod',
               'r.ReflectionMethod', 'r.Lumen.DiffuseIndirect.Allow', 'r.SSR.Quality']
    old = {name:unreal.SystemLibrary.get_console_variable_string_value(name) for name in temporary}
    assert all(value != '' for value in old.values()), ('Missing console variable', old)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = (csv_prefix or 'GHS_Lighting_') + label + '_' + timestamp + '.csv'
    csv_path = ROOT / 'Saved/Profiling/CSV' / filename
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    report_path = Path(report_path) if report_path else ROOT / 'Saved' / ('GHS_LightingProfile_' + label + '.json')
    status_path = Path(status_path) if status_path else STATUS_PATH
    assert not csv_path.exists(), 'Capture filename already exists'
    original_view = _view(unreal)
    restore_camera = restore_camera or original_view
    original_throttle = settings.get_editor_property(throttle_property)
    state = dict(success=False, phase='warmup', label=label,
                 created_utc=datetime.now(timezone.utc).isoformat(),
                 camera=original_view, requested_frames=frames,
                 warmup_frames=warmup_frames, warmup_seconds=warmup_seconds,
                 original_console_values=old, temporary_console_values=temporary,
                 observed_console_values={name:unreal.SystemLibrary.get_console_variable_string_value(name)
                                          for name in observe},
                 original_background_throttle=original_throttle, csv=str(csv_path),
                 note='Editor viewport GPU workload; fixed viewport dimensions required; no asset/config save')
    clock = dict(start=time.monotonic(), warmup_ticks=0, handle=None, capturing=False, ticks=0, finished=False,
                 expected_view=original_view)
    if planned_movement is not None:
        yaw = math.radians(original_view['rotation_deg'][1])
        right = [-math.sin(yaw), math.cos(yaw), 0.0]
        state['planned_movement'] = dict(
            duration_seconds=duration, distance_cm=distance,
            direction_world=right, speed_cm_per_second=distance / duration,
            start_camera=original_view, restored_camera_target=restore_camera,
            path='Constant-height camera-right translation with fixed rotation',
            captured_ticks=0, maximum_tick_interval_seconds=0.0,
            comparison_note='Moving workload; not a stationary Before/After comparison')
        state['requested_frames'] = None
        state['minimum_capture_frames'] = 120

    def command(value):
        unreal.SystemLibrary.execute_console_command(world, value)

    def write():
        report_path.write_text(json.dumps(state, indent=2), encoding='utf-8')
        status_path.write_text(json.dumps(dict(
            status=state['phase'], phase=label, success=state['success'],
            report=str(report_path), csv=str(csv_path),
            error=state.get('error'), settings_restored=state.get('settings_restored', False),
            gpu_time=state.get('metrics', {}).get('GPUTime'),
            updated_utc=datetime.now(timezone.utc).isoformat()), indent=2), encoding='utf-8')

    def set_view(view):
        position, rotation = view['position_cm'], view['rotation_deg']
        unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).set_level_viewport_camera_info(
            unreal.Vector(*position),
            unreal.Rotator(pitch=rotation[0], yaw=rotation[1], roll=rotation[2]))

    def restore():
        global _active
        # If unregister itself fails, a dormant callback must never repeat
        # cleanup or overwrite the user's subsequent camera/settings edits.
        clock['finished'] = True
        errors = []
        for name, value in old.items():
            try:
                command(name + ' ' + value)
                actual = unreal.SystemLibrary.get_console_variable_string_value(name)
                assert actual == value or float(actual) == float(value), (name, value, actual)
            except Exception:
                errors.append(traceback.format_exc())
        try:
            settings.set_editor_property(throttle_property, original_throttle)
            assert settings.get_editor_property(throttle_property) == original_throttle
        except Exception:
            errors.append(traceback.format_exc())
        if clock['handle'] is not None:
            try:
                unreal.unregister_slate_post_tick_callback(clock['handle'])
                clock['handle'] = None
            except Exception:
                errors.append(traceback.format_exc())
        if planned_movement is not None:
            try:
                current_view = _view(unreal)
                assert current_view['viewport_config_key'] == restore_camera['viewport_config_key'], 'Active viewport changed; camera restore skipped to protect the other viewport'
                assert unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world() == world, 'Editor world changed; camera restore skipped'
                set_view(restore_camera)
                state['restored_camera'] = _view(unreal)
                # Vector camera setters round coordinates to float32 in UE5.4.
                assert all(abs(a-b) < .01 for key in ('position_cm', 'rotation_deg')
                           for a, b in zip(restore_camera[key], state['restored_camera'][key]))
                state['camera_restored'] = True
            except Exception:
                state['camera_restored'] = False
                errors.append(traceback.format_exc())
        state['settings_restored'] = not errors
        if errors:
            state['restore_errors'] = errors
            state['success'] = False
            state['phase'] = 'failed'
        _active = None

    def tick(delta):
        if clock['finished']:
            return
        try:
            clock['ticks'] += 1
            now = time.monotonic()
            assert now - clock['start'] < timeout_seconds, 'GPU capture timed out'
            if planned_movement is not None or clock['ticks'] % 15 == 0:
                assert _same_view(clock['expected_view'], _view(unreal)), 'Unplanned viewport change during capture'
            if state['phase'] == 'warmup':
                clock['warmup_ticks'] += 1
                if clock['warmup_ticks'] < warmup_frames or time.monotonic() - clock['start'] < warmup_seconds:
                    return
                command('CsvProfile STARTFILE=' + filename)
                command('CsvProfile START' if planned_movement is not None else 'CsvProfile FRAMES=' + str(frames))
                clock['capturing'] = True
                clock['motion_start'] = now
                clock['motion_last_tick'] = now
                state['phase'] = 'capturing'
                state['capture_started_utc'] = datetime.now(timezone.utc).isoformat()
                write()
                return
            if planned_movement is not None and state['phase'] == 'capturing':
                elapsed = now - clock['motion_start']
                progress = min(1.0, elapsed / duration)
                target_view = dict(original_view, position_cm=[
                    start + axis * distance * progress
                    for start, axis in zip(original_view['position_cm'], right)])
                set_view(target_view)
                clock['expected_view'] = _view(unreal)
                motion = state['planned_movement']
                motion['captured_ticks'] += 1
                motion['maximum_tick_interval_seconds'] = max(
                    motion['maximum_tick_interval_seconds'], now - clock['motion_last_tick'])
                clock['motion_last_tick'] = now
                if progress < 1.0:
                    return
                motion['actual_duration_seconds'] = elapsed
                motion['end_camera'] = clock['expected_view']
                motion['actual_distance_cm'] = math.dist(
                    original_view['position_cm'], clock['expected_view']['position_cm'])
                assert abs(motion['actual_distance_cm'] - distance) < .01
                state['phase'] = 'draining_gpu_queries'
                clock['drain_ticks'] = 0
                write()
                return
            if planned_movement is not None and state['phase'] == 'draining_gpu_queries':
                # The timestamp profiler resolves GPU queries several frames
                # later. Hold the endpoint for the tail trimmed by the parser.
                clock['drain_ticks'] += 1
                if clock['drain_ticks'] < 10:
                    return
                command('CsvProfile STOP')
                clock['capturing'] = False
                state['phase'] = 'writing_csv'
                write()
                return
            if clock['ticks'] % 15:
                return
            result = try_completed_csv(csv_path, expected_frames=120 if planned_movement is not None else frames)
            if result is None:
                return
            clock['capturing'] = False
            state.update(result)
            state['final_camera'] = _view(unreal)
            assert _same_view(clock['expected_view'], state['final_camera'])
            state.update(success=True, phase='complete', completed_utc=datetime.now(timezone.utc).isoformat())
            restore()
            write()
            unreal.log('GHS_LIGHTING_PROFILE ' + label + ': GPUTime mean_ms=' + str(state['metrics']['GPUTime']['mean_ms']))
        except Exception:
            state.update(success=False, phase='failed', error=traceback.format_exc())
            if clock['capturing']:
                try:
                    command('CsvProfile STOP')
                except Exception:
                    state['stop_error'] = traceback.format_exc()
            restore()
            write()
            unreal.log_error(state['error'])

    try:
        _active = state
        settings.set_editor_property(throttle_property, False)
        for name, value in temporary.items():
            command(name + ' ' + str(value))
        # GPU category is enabled by default in UE5.4; avoid altering its prior state.
        write()
        clock['handle'] = unreal.register_slate_post_tick_callback(tick)
    except Exception:
        state.update(phase='failed', error=traceback.format_exc())
        restore()
        write()
        raise
    return str(report_path)


def compare(before_label='Before', after_label='After'):
    """Reject mismatched viewpoints/settings; expose GPU improvement without a target claim."""
    reports = [json.loads((ROOT/'Saved'/('GHS_LightingProfile_'+label+'.json')).read_text())
               for label in (before_label, after_label)]
    before, after = reports
    assert all(r['success'] and r['settings_restored'] for r in reports)
    assert _same_view(before['camera'], after['camera']), 'Before/after viewpoints differ'
    assert before['temporary_console_values'] == after['temporary_console_values']
    assert before['analyzed_frame_count'] == after['analyzed_frame_count']
    for name in ['r.ScreenPercentage', 'r.Editor.Viewport.ScreenPercentage',
                 'r.Editor.Viewport.ScreenPercentageMode.RealTime', 'sg.ResolutionQuality', 'r.AntiAliasingMethod']:
        assert before['observed_console_values'][name] == after['observed_console_values'][name], name
    a, b = (report['metrics']['GPUTime']['mean_ms'] for report in reports)
    comparison = dict(success=True, before=before, after=after,
                      gpu_mean_ms_before=a, gpu_mean_ms_after=b,
                      gpu_mean_reduction_ms=a-b, gpu_mean_reduction_percent=100*(a-b)/a,
                      viewport_dimensions_must_be_confirmed_unchanged=True)
    path = ROOT/'Saved/GHS_LightingPerformance.json'
    path.write_text(json.dumps(comparison, indent=2), encoding='utf-8')
    return comparison


def run():
    """The live dispatcher invokes this entry using the explicitly queued phase."""
    import unreal
    label = (ROOT/'Saved/GHS_LightingProfilePhase.txt').read_text().strip()
    assert label in ('Before', 'After'), 'Phase must be Before or After'
    reference = json.loads((ROOT/'Saved/GHS_LightingBefore.json').read_text())
    view = reference.get('viewport', reference.get('camera', reference))
    position = view['position_cm']
    rotation = view.get('rotation_deg', view.get('rotation'))
    assert len(position) == 3 and len(rotation) == 3
    if isinstance(rotation, dict):
        rotation = [rotation[name] for name in ('pitch', 'yaw', 'roll')]
    editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    editor.set_level_viewport_camera_info(
        unreal.Vector(*position), unreal.Rotator(pitch=rotation[0], yaw=rotation[1], roll=rotation[2]))
    return start(label)


if __name__ == '__main__':
    try:
        run()
    except Exception:
        STATUS_PATH.write_text(json.dumps(dict(status='failed', success=False,
            error=traceback.format_exc()), indent=2), encoding='utf-8')
        raise
