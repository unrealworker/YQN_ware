"""Capture fixed MPR views and native frame/GPU timing in an owned game process.

Launch UnrealEditor.exe with the B50B57 map and
    -own -game -RenderOffscreen -MPRProfile -ForceRes -ResX=1920 -ResY=1080
    -ExecCmds="py D:/UEPro/Test/Tools/MPRWarehouse/capture_mpr_site_completion.py"

Reads Saved/MPR/site_completion_20261105/run_config.json. Only runtime objects
are changed; this script never imports or saves a map, asset, or project setting.
"""
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time
import traceback

import unreal as u

# UE's Python file executor may clear __file__ before deferred Slate callbacks.
SCRIPT_PATH = Path(__file__).resolve()
sys.path.insert(0, str(SCRIPT_PATH.parent))
import profile_mpr_runtime as base


ROOT = Path(u.Paths.convert_relative_path_to_full(u.Paths.project_dir())).resolve()
OUTPUT_ROOT = ROOT / 'Saved/MPR/site_completion_20261105'
CONFIG_FILE = OUTPUT_ROOT / 'run_config.json'
MAP = '/Game/Maps/MPR_CAD_Warehouse_B50B57'
MAP_FILE = ROOT / 'Content/Maps/MPR_CAD_Warehouse_B50B57.umap'
WARMUP_SECONDS = 12.
SAMPLE_SECONDS = 15.
DEADLINE_SECONDS = 180.
START = time.monotonic()
RUN_ID = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')

base.MAP = MAP
base.MAP_FILE = MAP_FILE
base.result['map'] = MAP

config = None
output = None
handle = None
finished = False
busy = False
capturing = False
owned_launch = False
phase = 'initializing'
original_cvars = {}
original_roof_hidden = []
original_camera_properties = {}
original_camera_transform = None
original_view_target = None
original_business_state = None
original_pawn_tick = None
original_controller_tick = None
camera_component = None
report = {
    'success': False,
    'run_id': RUN_ID,
    'map': MAP,
    'assets_saved': False,
    'scope': 'Owned UnrealEditor -game offscreen viewport; not PIE, packaged-game, '
             'Pixel Streaming, or concurrent-user performance acceptance.',
    'resolution': [1920, 1080],
    'warmup_seconds_per_view': WARMUP_SECONDS,
    'sample_seconds': SAMPLE_SECONDS,
    'deadline_seconds': DEADLINE_SECONDS,
    'timing_source': 'Native CSV FrameTime, GameThreadTime, RenderThreadTime and '
                     'GPUTime; Python/Slate intervals are never frame timing.',
    'captures': [],
    'performance': None,
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_report():
    report.update(phase=phase, elapsed_seconds=time.monotonic() - START)
    if output is None:
        return
    output.mkdir(parents=True, exist_ok=True)
    temporary = output / 'report.json.tmp'
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(output / 'report.json')


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def read_config():
    raw = CONFIG_FILE.read_bytes()
    require(len(raw) <= 65536, 'Capture configuration is unexpectedly large')
    data = json.loads(raw.decode('utf-8-sig'))
    require(isinstance(data, dict), 'Capture configuration must be an object')
    require(set(data) == {'stage', 'views', 'fov', 'profile'},
            'Capture configuration requires only stage, views, fov and profile')
    require(data['stage'] in ('baseline', 'round1', 'round2'), 'Unknown capture stage')
    require(type(data['profile']) is bool, 'profile must be a JSON boolean')
    require(number(data['fov']) and 5 <= data['fov'] <= 120, 'Invalid horizontal FOV')
    require(isinstance(data['views'], list) and 1 <= len(data['views']) <= 8,
            'Provide one to eight views within the 180-second driver budget')
    names = set()
    for index, view in enumerate(data['views']):
        require(isinstance(view, list) and len(view) == 6, 'Invalid view at index %d' % index)
        name, target, distance, pitch, yaw, hidden = view
        require(isinstance(name, str) and 0 < len(name) <= 128 and name not in names,
                'View names must be nonempty and unique')
        names.add(name)
        require(isinstance(target, list) and len(target) == 3 and all(number(v) for v in target),
                'View target must contain three finite CAD coordinates in metres')
        require(number(distance) and distance > 0, 'View distance must be positive centimetres')
        require(number(pitch) and -89.9 <= pitch <= 89.9 and number(yaw), 'Invalid view rotation')
        require(type(hidden) is bool, 'View roof visibility must be a JSON boolean')
    report['config_sha256'] = hashlib.sha256(raw).hexdigest()
    report['config'] = data
    return data


def console(command):
    base.console(command)


def actual_camera():
    value = base.view()
    value['horizontal_fov_deg'] = float(base.pc.player_camera_manager.get_fov_angle())
    return value


def matches(expected):
    return (base.camera_matches(expected)
            and abs(actual_camera()['horizontal_fov_deg'] - config['fov']) < .03)


def verify_runtime():
    state = base.business_state()
    require(state == original_business_state, 'Controller, pawn or business state changed')
    require(base.pawn.is_actor_tick_enabled() == original_pawn_tick, 'Pawn tick changed')
    require(base.pc.is_actor_tick_enabled() == original_controller_tick, 'Controller tick changed')
    return state


def wait(name, predicate, seconds=20., stable=1):
    global phase
    phase = name
    until = time.monotonic() + seconds
    count = 0
    write_report()
    while True:
        require(time.monotonic() < until, 'Timed out: ' + name)
        count = count + 1 if predicate() else 0
        if count >= stable:
            return
        yield


def pause(seconds, expected):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        require(matches(expected), 'Actual camera, FOV or viewport changed during warmup/sample')
        yield


def configure_camera():
    global camera_component, original_camera_transform, original_view_target
    camera_component = base.camera.get_component_by_class(u.CameraComponent)
    require(camera_component is not None, 'Review camera lacks a CameraComponent')
    original_camera_transform = base.camera.get_actor_transform()
    original_view_target = base.pc.get_view_target()
    changes = {
        'field_of_view': float(config['fov']),
        'constrain_aspect_ratio': False,
        'override_aspect_ratio_axis_constraint': True,
        'aspect_ratio_axis_constraint': u.AspectRatioAxisConstraint.ASPECT_RATIO_MAINTAIN_XFOV,
    }
    for key, value in changes.items():
        original_camera_properties[key] = camera_component.get_editor_property(key)
        camera_component.set_editor_property(key, value)
    original_roof_hidden.extend((actor, bool(actor.get_editor_property('hidden'))) for actor in base.roofs)
    base.pawn.cancel_pose_transition()
    base.pawn.freeze_current_pose()
    verify_runtime()


def set_view(view):
    name, target_m, distance, pitch, yaw, hidden = view
    verify_runtime()
    for actor in base.roofs:
        actor.set_actor_hidden_in_game(hidden)
    require(all(bool(actor.get_editor_property('hidden')) == hidden for actor in base.roofs),
            'Roof visibility did not match the configured view')
    rotation = u.Rotator(pitch=pitch, yaw=yaw)
    target = u.Vector(target_m[0] * 100., -target_m[1] * 100., target_m[2] * 100.)
    eye = target - u.MathLibrary.get_forward_vector(rotation) * distance
    base.camera.set_actor_location_and_rotation(eye, rotation, False, True)
    base.pc.set_view_target_with_blend(base.camera, 0.)
    return {'position_cm': base.xyz(eye), 'rotation_deg': [pitch, yaw, 0.]}


def measure_overview(name, expected, hidden):
    global phase, capturing
    state_before = verify_runtime()
    filename = 'MPR_SITE_%s_%s.csv' % (config['stage'], RUN_ID)
    path = ROOT / 'Saved/Profiling/CSV' / filename
    require(not path.exists(), 'Performance output already exists')
    console('CsvProfile STARTFILE=' + filename)
    console('CsvProfile START')
    capturing = True
    phase = 'overview_native_csv'
    write_report()
    sample_start = time.monotonic()
    yield from pause(SAMPLE_SECONDS, expected)
    wall_seconds = time.monotonic() - sample_start
    console('CsvProfile STOP')
    capturing = False
    yield from wait('overview_csv_flush', lambda: base.csv_complete(path), seconds=20.)
    require(matches(expected), 'Camera changed while flushing native CSV')
    native = base.parse_csv(path)
    state_after = verify_runtime()
    require(state_before == state_after, 'Runtime state changed during native timing capture')
    report['performance'] = {
        'view': name,
        'camera': actual_camera(),
        'roof_hidden': hidden,
        'sample_wall_seconds': wall_seconds,
        'warmup_seconds': WARMUP_SECONDS,
        'native_csv': native,
        'average_fps': 1000. / native['metrics']['FrameTime']['mean_ms'],
        'fps_formula': 'native frame count / sum of native FrameTime seconds',
        'runtime_state_before': state_before,
        'runtime_state_after': state_after,
        'pawn_tick_suppressed': False,
        'controller_tick_suppressed': False,
    }
    write_report()
    yield from pause(.5, expected)


def capture_view(index, view):
    global phase
    name, target, distance, pitch, yaw, hidden = view
    expected = set_view(view)
    yield from wait('view_%02d_fixed_camera' % index, lambda: matches(expected), stable=5)
    phase = 'view_%02d_temporal_warmup' % index
    write_report()
    yield from pause(WARMUP_SECONDS, expected)
    if index == 0 and config['profile']:
        yield from measure_overview(name, expected, hidden)
    verify_runtime()
    require(not capturing, 'Screenshots must not overlap the performance sample')
    safe_name = re.sub(r'[^A-Za-z0-9_-]+', '_', name).strip('_')[:64] or 'view'
    png = output / ('%02d_%s_%s.png' % (index, safe_name, RUN_ID))
    require(not png.exists(), 'Screenshot output already exists')
    console('Shot filename="' + png.as_posix() + '" -nosuffix')
    yield from wait('view_%02d_screenshot_flush' % index, lambda: base.png_ready(png), seconds=15.)
    require(matches(expected), 'Actual camera changed for the screenshot')
    verify_runtime()
    report['captures'].append({
        'name': name,
        'path': str(png),
        'sha256': sha(png),
        'resolution': [1920, 1080],
        'camera': actual_camera(),
        'configured_view': view,
        'roof_hidden': hidden,
        'temporal_warmup_seconds': WARMUP_SECONDS,
        'outside_performance_window': True,
    })
    write_report()


def run():
    global config, output, original_business_state, original_pawn_tick, original_controller_tick, owned_launch
    cli = u.SystemLibrary.get_command_line()
    required = ('own', 'game', 'RenderOffscreen', 'MPRProfile')
    require(all(re.search(r'(?:^|\s)-' + flag + r'(?=\s|$)', cli, re.I) for flag in required),
            'Only an owned -own -game -RenderOffscreen -MPRProfile process is allowed')
    owned_launch = True
    require(not re.search(r'(?:^|\s)-(?:TwinPerf=|UseFixedTimeStep\b|benchmark\b)', cli, re.I),
            'Do not combine profiling drivers or fixed-step/benchmark simulation')
    config = read_config()
    output = OUTPUT_ROOT / config['stage']
    report.update(stage=config['stage'], engine_version=u.SystemLibrary.get_engine_version(),
                  map_sha256_before=sha(MAP_FILE), script_sha256=sha(SCRIPT_PATH),
                  coordinate_convention='View targets are CAD metres; UE target=(x,-y,z)*100 cm',
                  launch_flags=list(required))
    require(re.match(r'5\.8\.', report['engine_version']), 'Native GPU checks require UE 5.8')
    write_report()
    yield from wait('discover_owned_game_world', base.discover, seconds=30.)
    yield from wait('viewport_1920x1080', lambda: list(base.pc.get_viewport_size()) == [1920, 1080],
                    seconds=10., stable=4)
    original_business_state = base.business_state()
    original_pawn_tick = base.pawn.is_actor_tick_enabled()
    original_controller_tick = base.pc.is_actor_tick_enabled()
    report['runtime_fixture'] = base.result['runtime_fixture']
    report['runtime_state_before'] = original_business_state
    configure_camera()
    cvars = {
        'r.GPUCsvStatsEnabled': 1, 'csv.CompressionMode': 0,
        't.MaxFPS': 0, 'r.VSync': 0, 't.IdleWhenNotForeground': 0,
        'Slate.bAllowThrottling': 0, 'r.DynamicRes.OperationMode': 0, 'r.ScreenPercentage': 100,
    }
    for key, value in cvars.items():
        previous = u.SystemLibrary.get_console_variable_string_value(key)
        require(previous != '', 'Missing required CVar: ' + key)
        original_cvars[key] = previous
        console(key + ' ' + str(value))
        effective = u.SystemLibrary.get_console_variable_string_value(key)
        require(float(effective) == float(value), 'CVar did not accept requested value: ' + key)
    report['capture_cvars'] = cvars
    report['original_cvars'] = dict(original_cvars)
    report['render_quality'] = {
        key: u.SystemLibrary.get_console_variable_string_value(key) for key in (
            'r.Nanite.MaxPixelsPerEdge', 'r.Nanite.AllowVoxels', 'r.Shadow.Virtual.Enable',
            'r.RayTracing', 'r.Lumen.HardwareRayTracing', 'r.LumenScene.GlobalSDF.ClipmapExtent',
        )
    }
    write_report()
    for index, view in enumerate(config['views']):
        yield from capture_view(index, view)
    require(len(report['captures']) == len(config['views']), 'Not all configured views were captured')
    require((report['performance'] is not None) == config['profile'], 'Performance capture is incomplete')
    report['runtime_state_after'] = verify_runtime()
    require(sha(CONFIG_FILE) == report['config_sha256'], 'Configuration changed while capture was running')


def finish(error=None):
    global finished, capturing, handle, phase
    if finished:
        return
    finished = True
    if error is not None:
        report['failed_phase'] = phase
    restore_errors = []

    def restore(action):
        try:
            action()
        except Exception:
            restore_errors.append(traceback.format_exc())

    if capturing:
        restore(lambda: console('CsvProfile STOP'))
        capturing = False
    for actor, hidden in original_roof_hidden:
        restore(lambda actor=actor, hidden=hidden: actor.set_actor_hidden_in_game(hidden))
    if camera_component is not None:
        for key, value in original_camera_properties.items():
            restore(lambda key=key, value=value: camera_component.set_editor_property(key, value))
    if original_camera_transform is not None:
        restore(lambda: base.camera.set_actor_transform(original_camera_transform, False, True))
    if original_view_target is not None:
        restore(lambda: base.pc.set_view_target_with_blend(original_view_target, 0.))
    for key, value in original_cvars.items():
        restore(lambda key=key, value=value: console(key + ' ' + value))
    if original_business_state is not None:
        restore(verify_runtime)
    if 'map_sha256_before' in report:
        try:
            report['map_sha256_after'] = sha(MAP_FILE)
            report['map_unchanged'] = report['map_sha256_before'] == report['map_sha256_after']
            require(report['map_unchanged'], 'Map file changed during the capture')
        except Exception:
            restore_errors.append(traceback.format_exc())
    report.update(error=error, restore_errors=restore_errors,
                  success=error is None and not restore_errors)
    phase = 'complete' if report['success'] else 'failed'
    try:
        write_report()
        (u.log if report['success'] else u.log_error)('MPR_SITE_COMPLETION ' + json.dumps({
            'success': report['success'],
            'report': str(output / 'report.json') if output else None,
            'error': error,
            'restore_errors': restore_errors,
        }, ensure_ascii=False))
    finally:
        if handle is not None:
            u.unregister_slate_post_tick_callback(handle)
            handle = None
        # An accidental invocation in the user's editor must not close it.
        if owned_launch:
            if base.world is not None and base.pc is not None:
                u.SystemLibrary.quit_game(base.world, base.pc, u.QuitPreference.QUIT, False)
            else:
                u.SystemLibrary.execute_console_command(None, 'quit')


steps = run()


def tick(delta):
    global busy
    if finished or busy:
        return
    busy = True
    try:
        require(time.monotonic() - START < DEADLINE_SECONDS, 'MPR capture deadline exceeded (180 s)')
        next(steps)
    except StopIteration:
        finish()
    except Exception:
        finish(traceback.format_exc())
    finally:
        busy = False


if __name__ == '__main__':
    handle = u.register_slate_post_tick_callback(tick)
    u.log('MPR_SITE_COMPLETION_STARTED ' + str(CONFIG_FILE))
