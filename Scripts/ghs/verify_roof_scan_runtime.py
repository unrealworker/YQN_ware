"""Roof scan acceptance in an owned offscreen game; never save assets.

Launch with -game -RenderOffscreen -TwinDiagnostics -ForceRes -ResX=1920
-ResY=1080 and this file as -ExecCmds="py ...". The process quits when done.
Saved/RoofScan/runtime.json contains normal-speed transition traces, separate
slow-motion PNG evidence, asset hashes, and two fixed-camera 10-second timing
windows. Screenshots are deliberately excluded from transition timing and CSV.
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
import struct
import time
import traceback

import unreal

ROOT = Path('D:/UEPro/Test')
OUT = ROOT/'Saved/RoofScan'
MAP = ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'
CLI = unreal.SystemLibrary.get_command_line()
assert all(re.search(r'(?:^|\s)-'+flag+r'(?=\s|$)', CLI, re.I)
           for flag in ('game', 'RenderOffscreen', 'TwinDiagnostics')), 'Owned diagnostic game only'
assert not re.search(r'(?:^|\s)-TwinPerf=', CLI, re.I), 'Do not combine profiling scripts'
OUT.mkdir(parents=True, exist_ok=True)
STAMP = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
START = time.monotonic()
world = pc = hud = pawn = roof = actor = mesh = handle = None
finished = capturing = False
active_sample = None
stage = 'discover'
original_cvars = {}
source_materials = []
asset_hashes = {str(MAP): hashlib.sha256(MAP.read_bytes()).hexdigest()}
result = dict(success=False, assets_saved=False, checks=[], transitions={}, captures=[], performance={},
              performance_benchmark=False, output=str(OUT), run_id=STAMP,
              performance_scope='Local offscreen editor-game, one 10s window per state; no performance SLA or Pixel Streaming claim',
              capture_scope='Slow-motion stills only; normal-speed timings are measured separately before captures',
              asset_sha256_before=asset_hashes)


def write():
    result['stage'] = stage
    (OUT/'runtime.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


def record(name, **data):
    result['checks'].append(dict(name=name, passed=True, **data))
    write()
    unreal.log('GHS_ROOF_SCAN_CHECK '+name)


def console(value):
    unreal.SystemLibrary.execute_console_command(world, value, pc)


def command(action, **values):
    hud.command(json.dumps(dict(action=action, **values)))


def poi():
    return json.loads(hud.get_poi_report())


def ids():
    return [item['id'] for item in poi()['labels']]


def game_time():
    return float(unreal.GameplayStatics.get_time_seconds(world))


def xyz(value):
    return [float(value.x), float(value.y), float(value.z)]


def roof_transform_values():
    transform = actor.get_actor_transform()
    return xyz(transform.translation) + xyz(transform.rotation) + [float(transform.rotation.w)] + xyz(transform.scale3d)


def camera_state():
    camera = pc.player_camera_manager
    rotation = camera.get_camera_rotation()
    return dict(position_cm=xyz(camera.get_camera_location()),
                rotation_deg=[rotation.pitch, rotation.yaw, rotation.roll], viewport=list(pc.get_viewport_size()))


def same_camera(a, b):
    return a['viewport'] == b['viewport'] and all(abs(x-y) < .02
        for key in ('position_cm', 'rotation_deg') for x, y in zip(a[key], b[key]))


def wait(name, condition, seconds=20, stable=1):
    global stage
    stage = name
    deadline = time.monotonic()+seconds
    consecutive = 0
    while True:
        assert time.monotonic() < deadline, 'Timed out: '+name
        consecutive = consecutive+1 if condition() else 0
        if consecutive >= stable:
            return
        yield


def pause(seconds):
    deadline = time.monotonic()+seconds
    while time.monotonic() < deadline:
        yield


def discover():
    global world, pc, hud, pawn, roof
    for candidate in unreal.ObjectIterator(unreal.World):
        if not candidate.get_path_name().startswith('/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.'):
            continue
        controller = unreal.GameplayStatics.get_player_controller(candidate, 0)
        widget = getattr(controller, 'twin_hud_widget', None) if controller else None
        if widget and widget.browser_ready:
            world, pc, hud = candidate, controller, widget
            pawn, roof = pc.get_controlled_pawn(), pc.warehouse_roof
            return bool(pawn and roof)
    return False


def material_paths():
    return [mesh.get_material(i).get_path_name() for i in range(mesh.get_num_materials())]


def remember_asset(object_path):
    package = object_path.split('.')[0]
    assert package.startswith('/Game/'), 'Unexpected source package '+package
    base = ROOT/'Content'/package[len('/Game/'):]
    assert base.with_suffix('.uasset').is_file(), 'Source asset missing '+str(base)
    for extension in ('.uasset', '.uexp', '.ubulk'):
        path = base.with_suffix(extension)
        if path.is_file():
            asset_hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot():
    report = poi()
    return dict(game_seconds=game_time(), phase=float(roof.get_transition_phase()),
                progress=float(roof.get_open_progress()), duration=float(roof.get_transition_duration()),
                opening=bool(roof.is_opening()), closing=bool(roof.is_closing()),
                closed=bool(roof.is_roof_closed()), interior=bool(roof.is_interior_available()),
                tick=bool(roof.is_component_tick_enabled()), selected_id=str(hud.selected_id),
                pending=report['pendingNavigation'], pending_id=report['pendingNavigationId'],
                warehouse_opacity=report['warehousePOIOpacity'], interior_opacity=report['interiorLabelOpacity'],
                labels=[dict(id=item['id'], opacity=item['opacity']) for item in report['labels']])


def assert_locked(check_click=False):
    report = poi()
    assert not roof.is_interior_available() and not report['interiorAvailable']
    assert report['roofOpening'] == roof.is_opening() and report['roofClosing'] == roof.is_closing()
    assert report['roofTransitioning'] == roof.is_transitioning()
    assert not hud.selected_id, 'Interior selection leaked through a transitioning roof'
    assert all(item['id'] == 'WAREHOUSE:GHS' for item in report['labels']), report
    assert report['interiorLabelOpacity'] == 0, report
    for item in report['labels']:
        assert not item['interactive'] and 0 <= item['opacity'] <= 1, item
    if check_click:
        # The roof anchor projects into the scene, outside the web panel/chrome.
        point = unreal.GameplayStatics.project_world_to_screen(pc, roof.get_poi_world_location(), False)
        assert point is not None and hud.is_scene_point(point)
        before = roof.get_open_progress()
        assert hud.handle_scene_click(point)
        assert not hud.selected_id and abs(roof.get_open_progress()-before) < 1e-6


def assert_idle(opened):
    assert not roof.is_transitioning() and not roof.is_component_tick_enabled()
    assert roof.is_interior_available() == opened and roof.is_roof_closed() != opened
    assert abs(roof.get_open_progress()-(1 if opened else 0)) < 1e-6
    assert bool(actor.get_editor_property('hidden')) == opened
    assert material_paths() == source_materials, 'Idle state did not restore every source material slot'


def transition(name, opening, expected_seconds=None, fixed_camera=None, click=False):
    """Keep all frames, including completion; permit only one observed-frame timing slack."""
    global stage
    stage = name
    start = game_time()
    deadline = time.monotonic()+15
    samples = []
    previous = None
    active_materials = material_paths()
    assert all(isinstance(mesh.get_material(i), unreal.MaterialInstanceDynamic)
               for i in range(mesh.get_num_materials())), 'A roof slot has no active scan material'
    while True:
        assert time.monotonic() < deadline, 'Timed out: '+name
        current = snapshot()
        current['elapsed_game_seconds'] = current['game_seconds']-start
        samples.append(current)
        p = current['phase']
        assert 0 <= p <= 1 and math.isfinite(p)
        assert abs(current['progress']-p*p*(3-2*p)) < 2e-5, 'Roof aperture must follow smoothstep'
        if previous:
            change = current['progress']-previous['progress']
            assert (change >= -1e-6 if opening else change <= 1e-6), 'Roof aperture changed direction unexpectedly'
            if opening:
                assert current['warehouse_opacity'] <= previous['warehouse_opacity']+1e-5, 'Main POI opacity increased while opening'
        done = roof.is_interior_available() if opening else roof.is_roof_closed()
        if done:
            break
        assert (roof.is_opening() if opening else roof.is_closing())
        assert roof.is_component_tick_enabled()
        assert_locked(click)
        if fixed_camera is not None:
            assert not pawn.is_pose_transition_active() and same_camera(fixed_camera, camera_state())
        previous = current
        yield
    elapsed = samples[-1]['elapsed_game_seconds']
    max_step = max((b['game_seconds']-a['game_seconds'] for a, b in zip(samples, samples[1:])), default=0)
    result['transitions'][name] = dict(expected_game_seconds=expected_seconds, elapsed_game_seconds=elapsed,
        max_observed_frame_seconds=max_step, time_dilation=1.0, active_materials=active_materials, samples=samples)
    if expected_seconds is not None:
        assert expected_seconds-.003 <= elapsed <= expected_seconds+max_step+.015, (name, elapsed, expected_seconds, max_step)
    assert_idle(opening)
    record(name, game_seconds=elapsed, sample_count=len(samples), max_observed_frame_seconds=max_step)


def restore(name='restore'):
    command('overview')
    assert not hud.selected_id and not poi()['pendingNavigation'] and not poi()['pendingNavigationId']
    assert all(item == 'WAREHOUSE:GHS' for item in ids())
    yield from wait(name+'_roof', roof.is_roof_closed)
    yield from wait(name+'_camera', lambda: not pawn.is_pose_transition_active(), stable=4)
    yield from wait(name+'_poi', lambda: ids() == ['WAREHOUSE:GHS'] and poi()['warehousePOIOpacity'] > .99)
    assert_idle(False)


def capture(name, **metadata):
    assert active_sample is None and not capturing, 'Screenshots must not contaminate profiling'
    path = OUT/(name+'.png')
    old = path.stat().st_mtime_ns if path.exists() else None
    before = snapshot()
    def ready():
        try:
            if path.stat().st_mtime_ns == old or path.stat().st_size < 32:
                return False
            with path.open('rb') as stream:
                stream.seek(-12, 2)
                return stream.read() == b'\x00\x00\x00\x00IEND\xaeB\x60\x82'
        except OSError:
            return False
    console('Shot showui filename="'+path.as_posix()+'" -nosuffix')
    yield from wait('capture_'+name, ready)
    raw = path.read_bytes()
    assert raw[:8] == b'\x89PNG\r\n\x1a\n' and struct.unpack('>II', raw[16:24]) == (1920, 1080)
    result['captures'].append(dict(name=name, path=str(path), sha256=hashlib.sha256(raw).hexdigest(),
        state_at_request=before, state_at_completion=snapshot(), camera=camera_state(), **metadata))
    write()


def frame_stats(values):
    ordered = sorted(values)
    assert ordered and all(math.isfinite(value) and value >= 0 for value in ordered)
    count = len(ordered)
    return dict(count=count, mean_ms=statistics.fmean(ordered), median_ms=statistics.median(ordered),
        p95_ms=ordered[math.ceil(count*.95)-1], p99_ms=ordered[math.ceil(count*.99)-1], max_ms=ordered[-1],
        over_50ms_count=sum(value > 50 for value in ordered), over_50ms_percent=100*sum(value > 50 for value in ordered)/count)


def completed_csv(path):
    try:
        with path.open('rb') as stream:
            stream.seek(max(0, path.stat().st_size-32768))
            return b'[HasHeaderRowAtEnd],1' in stream.read()
    except OSError:
        return False


def csv_metrics(path):
    raw = path.read_bytes()
    rows = list(csv.reader(io.StringIO(raw.decode('utf-8-sig'))))
    headers = [i for i, row in enumerate(rows) if row and row[0] == 'EVENTS']
    assert headers, 'CSV final header missing'
    names = rows[headers[-1]]
    first = headers[0]+1 if len(headers) > 1 else 0
    rows = [row for row in rows[first:headers[-1]] if row and not row[0].startswith('[')]
    required = ('FrameTime', 'GameThreadTime', 'RenderThreadTime')
    assert all(name in names for name in required) and len(rows) >= 50, (names, len(rows))
    values = {name: [float(row[names.index(name)]) for row in rows]
              for name in required+('GPUTime', 'GPU/Total') if name in names}
    gpu_verified = all(name in values and sum(value > 0 for value in values[name]) >= len(rows)*.95
                       for name in ('GPUTime', 'GPU/Total'))
    return dict(csv=str(path), csv_sha256=hashlib.sha256(raw).hexdigest(), gpu_verified=gpu_verified,
        metrics={name: frame_stats(data) for name, data in values.items()},
        native_frame_time_seconds=sum(values['FrameTime'])/1000,
        sample_window='All CSV frames between start/stop, including boundary frames; no spikes discarded')


def sample_performance(name, repeated=False):
    global active_sample, capturing, stage
    stage = 'performance_'+name
    assert not pawn.is_pose_transition_active() and roof.is_roof_closed()
    fixed = camera_state()
    filename = 'RoofScan_'+STAMP+'_'+name+'.csv'
    path = ROOT/'Saved/Profiling/CSV'/filename
    console('CsvProfile STARTFILE='+filename)
    console('CsvProfile START')
    capturing = True
    active_sample = dict(delta_ms=[], wall_ms=[], previous=None)
    start = time.monotonic()
    cycles = 0
    while time.monotonic()-start < 10:
        assert same_camera(fixed, camera_state()) and not pawn.is_pose_transition_active()
        if repeated:
            if roof.is_roof_closed():
                assert hud.open_warehouse()
            elif roof.is_interior_available():
                roof.restore_roof(True)
                cycles += 1
        yield
    elapsed = time.monotonic()-start
    console('CsvProfile STOP')
    capturing = False
    sample = active_sample
    active_sample = None
    yield from wait('csv_'+name, lambda: completed_csv(path), seconds=20)
    assert same_camera(fixed, camera_state())
    native = csv_metrics(path)
    result['performance'][name] = dict(camera=fixed, wall_seconds=elapsed, completed_openings=cycles,
        slate_delta=frame_stats(sample['delta_ms']), slate_wall_interval=frame_stats(sample['wall_ms']),
        native_csv=native, gpu_verified=native['gpu_verified'],
        slate_note='Slate callback intervals are not GameThreadTime, RenderThreadTime, or GPUTime',
        stimulus='Normal .8s manual open and .55s component close, HUD active, camera static' if repeated else 'Warm closed roof, HUD active, camera static')
    if repeated:
        assert cycles >= 2, 'Too few open/close cycles in the 10s sample'
    write()


def run():
    global actor, mesh, source_materials
    yield from wait('discover', discover, seconds=60)
    assert tuple(pc.get_viewport_size()) == (1920, 1080), 'Use -ForceRes -ResX=1920 -ResY=1080'
    assert abs(unreal.GameplayStatics.get_global_time_dilation(world)-1) < 1e-6
    console('DisableAllScreenMessages')
    yield from wait('initial_camera', lambda: not pawn.is_pose_transition_active(), stable=8)
    yield from pause(2)
    actor = next(a for a in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor)
                 if a.actor_has_tag('GHS_WarehouseRoof'))
    mesh = actor.get_component_by_class(unreal.StaticMeshComponent)
    source_materials = material_paths()
    for path in source_materials+[mesh.get_editor_property('static_mesh').get_path_name()]:
        remember_asset(path)
    initial_transform = roof_transform_values()
    initial_count = len(unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor))
    assert_idle(False)
    assert not hud.selected_id and not poi()['pendingNavigation'] and ids() == ['WAREHOUSE:GHS']
    assert poi()['warehousePOIOpacity'] > .99 and poi()['interiorLabelOpacity'] == 0
    record('initial_closed_no_entrance_animation', state=snapshot(), source_materials=source_materials,
           actor_count=initial_count, roof_transform=initial_transform)

    # Normal-time tests run before screenshot work. Main POI may fade while all
    # internal labels and selection remain locked throughout the opening.
    main = poi()['labels'][0]
    scale = hud.get_hud_scale()
    fixed = camera_state()
    point = unreal.Vector2D((main['x']+main['width']*.5)*scale, (main['y']+main['height']*.5)*scale)
    assert hud.handle_scene_click(point) and roof.is_opening()
    assert abs(roof.get_transition_duration()-.8) < 1e-6
    assert hud.open_warehouse() and abs(roof.get_open_progress()) < 1e-6
    yield from transition('manual_click_0_8_seconds', True, .8, fixed, click=True)
    yield from wait('interior_label_fade_complete', lambda: bool(ids()) and 'WAREHOUSE:GHS' not in ids()
                    and poi()['interiorLabelOpacity'] > .99)
    record('internal_labels_only_after_open_then_fade', state=snapshot())
    command('overview')
    yield from transition('normal_close_0_55_seconds', False, .55)
    yield from restore('after_normal_close')

    fixed = camera_state()
    assert hud.select_object('AGV-07', True)
    assert hud.select_object('FORK-07', True)
    assert poi()['pendingNavigation'] == 'select' and poi()['pendingNavigationId'] == 'FORK-07'
    assert hud.open_warehouse() and poi()['pendingNavigationId'] == 'FORK-07'
    assert abs(roof.get_transition_duration()-.5) < 1e-6
    yield from transition('fast_latest_target_0_5_seconds', True, .5, fixed)
    yield from wait('latest_selection_executed', lambda: hud.selected_id == 'FORK-07')
    assert not poi()['pendingNavigation'] and not poi()['pendingNavigationId']
    yield from wait('latest_selection_camera', lambda: not pawn.is_pose_transition_active(), stable=4)
    record('fast_request_latest_target_wins')
    yield from restore('after_fast')

    assert hud.open_warehouse()
    yield from wait('manual_before_fast_upgrade', lambda: roof.get_transition_phase() >= .2)
    before = roof.get_open_progress()
    phase = roof.get_transition_phase()
    fixed = camera_state()
    assert hud.select_object('AGV-07', True)
    assert abs(roof.get_open_progress()-before) < 1e-6
    assert abs(roof.get_transition_duration()-.5) < 1e-6
    yield from transition('manual_to_fast_no_jump', True, (1-phase)*.5, fixed)
    yield from wait('upgraded_selection', lambda: hud.selected_id == 'AGV-07')
    yield from restore('after_upgrade')

    assert hud.select_object('AGV-07', True)
    yield from wait('mid_open_before_reset', lambda: roof.get_transition_phase() >= .35)
    before = roof.get_open_progress()
    phase = roof.get_transition_phase()
    command('overview')
    assert roof.is_closing() and abs(roof.get_open_progress()-before) < 1e-6
    assert not poi()['pendingNavigation'] and not poi()['pendingNavigationId'] and not hud.selected_id
    yield from transition('reset_mid_open_continuous_close', False, phase*.55)
    yield from restore('after_cancel')
    yield from pause(.7)
    assert not hud.selected_id and not poi()['pendingNavigation']
    record('reset_cancels_queued_navigation_without_late_selection')

    assert hud.open_warehouse()
    yield from wait('opened_before_reverse', roof.is_interior_available)
    command('overview')
    yield from wait('mid_close_before_navigation', lambda: roof.get_transition_phase() <= .65)
    before = roof.get_open_progress()
    phase = roof.get_transition_phase()
    assert hud.select_object('AGV-07', True)
    assert roof.is_opening() and abs(roof.get_open_progress()-before) < 1e-6
    fixed = camera_state()
    assert hud.select_object('FORK-07', True)
    assert poi()['pendingNavigationId'] == 'FORK-07' and abs(roof.get_open_progress()-before) < 1e-6
    yield from transition('navigation_during_close_reverses_without_jump', True, (1-phase)*.5, fixed)
    yield from wait('reversed_latest_selection', lambda: hud.selected_id == 'FORK-07')
    yield from restore('after_reverse')

    command('layers', building=False)
    yield from wait('hidden_building_opened', roof.is_interior_available)
    assert not roof.is_building_visible()
    assert_idle(True)
    command('overview')
    yield from wait('hidden_building_restored_roof', roof.is_roof_closed)
    yield from restore('after_hidden_building')
    assert roof.is_building_visible()
    record('hidden_building_preference_and_overview_restore')

    # Warmed, identical overview camera; no PNGs, slow motion, or camera flights.
    for key, value in {'r.GPUStatsEnabled': 1, 'r.GPUCsvStatsEnabled': 1, 'csv.CompressionMode': 0,
                       't.MaxFPS': 0, 'r.VSync': 0, 'r.VSyncEditor': 0, 't.IdleWhenNotForeground': 0,
                       'Slate.bAllowThrottling': 0, 'r.DynamicRes.OperationMode': 0, 'r.ScreenPercentage': 100}.items():
        original = unreal.SystemLibrary.get_console_variable_string_value(key)
        assert original != '', 'Missing cvar '+key
        original_cvars[key] = original
        console(key+' '+str(value))
    yield from pause(3)
    yield from sample_performance('warm_closed_10s')
    yield from sample_performance('repeated_normal_open_close_10s', True)
    base, motion = (result['performance'][key] for key in ('warm_closed_10s', 'repeated_normal_open_close_10s'))
    assert same_camera(base['camera'], motion['camera'])
    result['performance_delta_ms'] = {metric: {key: data[key]-base['native_csv']['metrics'][metric][key]
        for key in ('mean_ms', 'median_ms', 'p95_ms', 'max_ms')}
        for metric, data in motion['native_csv']['metrics'].items() if metric in base['native_csv']['metrics']}
    result['performance_note'] = 'Opening changes visible scene load and traffic keeps moving. These two local windows cannot isolate scan shader cost or establish a performance guarantee.'
    yield from restore('before_visuals')

    yield from capture('01_closed_overview', time_dilation=1.0)
    unreal.GameplayStatics.set_global_time_dilation(world, .08)
    assert hud.open_warehouse()
    for name, target in (('02_activation', .015), ('03_open_025', .25), ('04_open_050', .5), ('05_open_080', .8)):
        yield from wait(name+'_progress', lambda: roof.get_open_progress() >= target)
        unreal.GameplayStatics.set_global_time_dilation(world, .0001)
        yield from capture(name, requested_progress=target, playback_time_dilation=.08, capture_time_dilation=.0001)
        unreal.GameplayStatics.set_global_time_dilation(world, .08)
    unreal.GameplayStatics.set_global_time_dilation(world, 1.)
    yield from wait('visual_open_complete', roof.is_interior_available)
    yield from wait('visual_labels_complete', lambda: poi()['interiorLabelOpacity'] > .99)
    yield from capture('06_fully_open', time_dilation=1.0)
    unreal.GameplayStatics.set_global_time_dilation(world, .08)
    roof.restore_roof(True)
    for name, target in (('07_close_080', .8), ('08_close_050', .5), ('09_close_025', .25)):
        yield from wait(name+'_progress', lambda: roof.get_open_progress() <= target)
        unreal.GameplayStatics.set_global_time_dilation(world, .0001)
        yield from capture(name, requested_progress=target, playback_time_dilation=.08, capture_time_dilation=.0001)
        unreal.GameplayStatics.set_global_time_dilation(world, .08)
    unreal.GameplayStatics.set_global_time_dilation(world, 1.)
    yield from restore('final_restore')
    yield from capture('10_closed_restored', time_dilation=1.0)
    final_transform = roof_transform_values()
    assert all(abs(a-b) < 1e-6 for a, b in zip(initial_transform, final_transform)), 'Roof transform changed'
    assert len(unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor)) == initial_count
    record('all_idle_ticks_stopped_materials_transform_actor_count_preserved', materials=material_paths(),
           initial_transform=initial_transform, final_transform=final_transform, actor_count=initial_count)


def finish(error=None):
    global finished, handle, active_sample
    if finished:
        return
    finished = True
    active_sample = None
    if error:
        result['error'] = error
        if hud and roof:
            try:
                result['failure_state'] = snapshot()
            except Exception:
                result['failure_state_error'] = traceback.format_exc()
    restore_errors = []
    if world:
        try:
            unreal.GameplayStatics.set_global_time_dilation(world, 1.)
        except Exception:
            restore_errors.append(traceback.format_exc())
        if capturing:
            try:
                console('CsvProfile STOP')
            except Exception:
                restore_errors.append(traceback.format_exc())
        if roof:
            try:
                roof.restore_roof(False)
            except Exception:
                restore_errors.append(traceback.format_exc())
        for key, value in original_cvars.items():
            try:
                console(key+' '+value)
            except Exception:
                restore_errors.append(traceback.format_exc())
    result.update(success=error is None and not restore_errors, elapsed_seconds=time.monotonic()-START,
                  restored_runtime_settings=not restore_errors)
    if restore_errors:
        result['restore_errors'] = restore_errors
    try:
        result['asset_sha256_after'] = {path: hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in asset_hashes}
        assert result['asset_sha256_after'] == asset_hashes, 'A saved map, mesh or source material changed'
        result['asset_hashes_unchanged'] = True
    except Exception:
        result.update(success=False, asset_hashes_unchanged=False, asset_verification_error=traceback.format_exc())
    write()
    if handle is not None:
        unreal.unregister_slate_post_tick_callback(handle)
        handle = None
    (unreal.log if result['success'] else unreal.log_error)('GHS_ROOF_SCAN_RUNTIME '+str(OUT/'runtime.json'))
    if world:
        unreal.SystemLibrary.quit_game(world, pc, unreal.QuitPreference.QUIT, False)


steps = run()


def tick(delta):
    if finished:
        return
    now = time.monotonic()
    if active_sample is not None:
        if math.isfinite(delta) and delta > 0:
            active_sample['delta_ms'].append(float(delta)*1000)
        if active_sample['previous'] is not None:
            active_sample['wall_ms'].append((now-active_sample['previous'])*1000)
        active_sample['previous'] = now
    try:
        assert now-START < 240, 'Acceptance timeout (240s including startup)'
        next(steps)
    except StopIteration:
        finish()
    except Exception:
        finish(traceback.format_exc())


write()
handle = unreal.register_slate_post_tick_callback(tick)
