"""Owned native MPR sorter verification; never saves a map or an asset.

Required: -own -game -RenderOffscreen -TwinDiagnostics -EnablePython
          -ForceRes -ResX=1920 -ResY=1080
ExecCmds: py D:/UEPro/Test/Tools/MPRWarehouse/verify_mpr_sorter_runtime.py
Optional -MPRSorterCaptureSequence adds 96 fixed-camera PNGs at 6 simulation fps.
Optional -MPRSorterVisualOnly takes eight targeted views plus the sequence,
skipping control tests and the FPS sample. Default run checks native controls,
takes three baseline plus eight targeted images and profiles 15 seconds of real
automatic Tick. It does not claim OS input testing.
"""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import math
import re
import sys
import time
import traceback
import unreal as u

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
import profile_mpr_runtime as timing

CLI = u.SystemLibrary.get_command_line()
assert all(re.search(r'(?:^|\s)-' + flag + r'(?=\s|$)', CLI, re.I)
           for flag in ('own', 'game', 'RenderOffscreen', 'TwinDiagnostics'))
assert not re.search(r'(?:^|\s)-(?:MPRProfile|UseFixedTimeStep)(?=\s|$)', CLI, re.I)
VISUAL_ONLY = bool(re.search(r'(?:^|\s)-MPRSorterVisualOnly(?=\s|$)', CLI, re.I))
SEQUENCE = VISUAL_ONLY or bool(re.search(r'(?:^|\s)-MPRSorterCaptureSequence(?=\s|$)', CLI, re.I))
LAYOUT_FILE = ROOT / 'SourceAssets/MPR/sorter_simulation/layout.json'
LAYOUT = json.loads(LAYOUT_FILE.read_text(encoding='utf8'))
MAP = '/Game/Maps/MPR_CAD_Warehouse_B50B57'
MAP_FILE = ROOT / 'Content/Maps/MPR_CAD_Warehouse_B50B57.umap'
STAMP = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
BASE = ROOT / 'Saved/MPR/sorter_sim_20261107/runtime'
OUT = BASE / STAMP
OUT.mkdir(parents=True, exist_ok=True)
ASSETS = [MAP_FILE, *sorted((ROOT / 'Content/MPRWarehouse/SorterSimulation').rglob('*.uasset'))]
HASHES = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in ASSETS}
START = time.monotonic()
world = pc = hud = pawn = roof = sim = callback = None
components = {}
done = busy = False
fixed_camera = None
baseline_camera = None
report = dict(success=False, run_id=STAMP, resolution=[1920, 1080], checks=[],
              captures=[], targeted_captures=[], sequence=[], performance={}, assets_saved=False,
              map_sha256=HASHES[str(MAP_FILE)], capture_sequence=SEQUENCE,
              visual_only=VISUAL_ONLY, layout_sha256=hashlib.sha256(LAYOUT_FILE.read_bytes()).hexdigest(),
              scope='Native API controls and rendered readback in an owned game; no OS pointer-input claim.',
              data_mode='demonstration')


def write():
    text = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    (OUT / 'report.json').write_text(text, encoding='utf8')
    (BASE / 'report.json').write_text(text, encoding='utf8')


def record(name, **data):
    report['checks'].append(dict(name=name, passed=True, **data))
    write()


def console(value):
    u.SystemLibrary.execute_console_command(world, value, pc)


def camera():
    manager = pc.player_camera_manager
    p, r = manager.get_camera_location(), manager.get_camera_rotation()
    return [p.x, p.y, p.z, r.pitch, r.yaw, r.roll]


def same_pose(a, b):
    return len(a) == len(b) and max(abs(x-y) for x, y in zip(a, b)) < .05


def wait(name, predicate, seconds=40):
    report['stage'] = name
    write()
    end = time.monotonic() + seconds
    while not predicate():
        assert time.monotonic() < end, 'Timed out: ' + name
        yield


def pause(seconds, check_camera=False):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if check_camera:
            assert same_pose(fixed_camera, camera()), 'Fixed camera moved'
        yield


def state():
    return json.loads(sim.get_simulation_report_json())


def verify_state(value):
    assert value['ready'] and value['data_mode'] == 'demonstration', value.get('error')
    assert value['machine_count'] == len(value['machines']) == 22
    assert value['tower_instances'] == value['tray_instances'] == value['parcel_instances'] == 88
    assert value['bin_parcel_instances'] == 1632 * 3 and value['components'] == 6
    assert value['conserved']
    assert value['spawned'] == value['completed'] + value['active']
    assert value['completed'] == value['collected'] + value['occupancy']
    assert len({m['id'] for m in value['machines']}) == 22
    for machine in value['machines']:
        carriers = machine['carriers']
        assert len(carriers) == 4
        ids = [c['parcel_id'] for c in carriers if c['parcel_id']]
        assert len(ids) == len(set(ids)) == machine['active']
        assert machine['spawned'] == machine['completed'] + machine['active']
        assert machine['completed'] == machine['collected'] + machine['occupancy']
        assert sum(c['occupancy'] for c in machine['cells']) == machine['occupancy']
        assert len({(c['side'], c['column'], c['level']) for c in machine['cells']}) == len(machine['cells'])
        for cell in machine['cells']:
            assert 0 <= cell['occupancy'] <= 3 and 0 <= cell['reserved'] <= 1
            assert cell['occupancy'] + cell['reserved'] <= 3
        for index, carrier in enumerate(carriers):
            assert all(math.isfinite(carrier[key]) for key in ('distance01', 'lift_cm', 'unload_progress'))
            assert 0 <= carrier['distance01'] < 1 and 0 <= carrier['unload_progress'] <= 1
            assert all(math.isfinite(x) for x in carrier['tray_world_cm'])
            offset = (carrier['distance01'] - carriers[0]['distance01']) % 1
            assert abs(offset-index*.25) < 1e-7
    return value


def step(seconds):
    assert sim.advance_simulation_for_diagnostics(seconds), ('Rejected step', seconds)
    return verify_state(state())


def equivalent(a, b, tolerance=1e-5):
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(equivalent(a[k], b[k], tolerance) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(equivalent(x, y, tolerance) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and not isinstance(a, bool):
        return abs(a-b) < tolerance
    return a == b


def counts(value):
    return {key: value[key] for key in ('spawned', 'completed', 'collected', 'active', 'occupancy')}


def discover():
    global world, pc, hud, pawn, roof, sim, components
    for candidate in u.ObjectIterator(u.World):
        if not candidate.get_path_name().startswith(MAP + '.'):
            continue
        controller = u.GameplayStatics.get_player_controller(candidate, 0)
        if not controller or not controller.get_editor_property('twin_hud_widget'):
            continue
        actors = list(u.GameplayStatics.get_all_actors_of_class(candidate, u.MPRSorterSimulationActor))
        if len(actors) != 1:
            continue
        world, pc, sim = candidate, controller, actors[0]
        hud, pawn, roof = pc.twin_hud_widget, pc.get_controlled_pawn(), pc.warehouse_roof
        components = {c.get_name(): c for c in sim.get_components_by_class(u.InstancedStaticMeshComponent)}
        current = state()
        return bool(current['ready'] and current['panel_attached'] and pawn and roof and roof.has_roof())
    return False


def verify_rendered_carriers(value):
    assert components['ActiveCells'].get_instance_count() == components['FullCells'].get_instance_count() == 1632
    for machine_index, machine in enumerate(value['machines']):
        for carrier_index, carrier in enumerate(machine['carriers']):
            index = machine_index*4 + carrier_index
            transform = components['LiftTrays'].get_instance_transform(index, world_space=True)
            point = transform.translation
            assert math.dist([point.x, point.y, point.z], carrier['tray_world_cm']) < .01
            package = components['MovingParcels'].get_instance_transform(index, world_space=True)
            scale = package.scale3d
            visible = max(abs(scale.x), abs(scale.y), abs(scale.z)) > 1e-6
            assert visible == bool(carrier['parcel_id']), ('Parcel visibility mismatch', index)


def capture(name, sequence_index=None, machine_index=0, target=None):
    folder = 'targeted' if target is not None else ('sequence' if sequence_index is not None else 'images')
    path = OUT / folder / (name + '.png')
    path.parent.mkdir(parents=True, exist_ok=True)
    value = verify_state(state())
    verify_rendered_carriers(value)
    assert same_pose(fixed_camera, camera())
    console('Shot showui filename="' + path.as_posix() + '" -nosuffix')
    yield from wait('capture_' + name, lambda: timing.png_ready(path))
    assert same_pose(fixed_camera, camera())
    row = dict(name=name, path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
               camera=camera(), machine_index=machine_index, machine=value['machines'][machine_index], totals=counts(value))
    if target is not None:
        assert equivalent(value, state()), 'Simulation changed while capturing a fixed diagnostic state'
        pose_path = path.with_suffix('.state.json')
        pose_path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
        row.update(target=target, state_path=str(pose_path),
                   state_sha256=hashlib.sha256(pose_path.read_bytes()).hexdigest())
        report['targeted_captures'].append(row)
    elif sequence_index is None:
        report['captures'].append(row)
    else:
        row.update(frame=sequence_index, simulation_fps=6)
        report['sequence'].append(row)
    write()


def test_controls():
    sim.set_automatic_advance_for_diagnostics(False)
    sim.reset_simulation()
    initial = verify_state(state())
    assert not initial['playing'] and initial['rate'] == 1 and initial['automatic_collection']
    assert all(initial[k] == 0 for k in ('spawned', 'completed', 'collected', 'active', 'occupancy'))
    sim.set_simulation_playing(True)
    moving = step(20)
    assert moving['spawned'] > 0 and moving['completed'] > 0
    sim.set_simulation_playing(False)
    before_pause = state()
    assert equivalent(before_pause, step(80)), 'Paused state changed'
    yield from pause(.3)
    assert equivalent(before_pause, state()), 'Automatic advance was not disabled'
    record('pause_freezes_every_machine_and_render_state', **counts(moving))
    sim.reset_simulation()
    sim.set_simulation_playing(True)
    at_one = step(40)
    for rate in (2, 4):
        sim.reset_simulation()
        sim.set_simulation_playing(True)
        sim.set_simulation_rate(rate)
        at_rate = step(40/rate)
        assert at_rate['rate'] == rate and equivalent(at_one['machines'], at_rate['machines'])
    record('one_two_four_times_speed_have_identical_simulation_result', simulation_seconds=40)
    before_invalid = state()
    assert not sim.advance_simulation_for_diagnostics(-1)
    assert equivalent(before_invalid, state())
    sim.reset_simulation()
    assert equivalent(initial['machines'], state()['machines'])
    record('reset_restores_empty_paused_repeatable_wave_and_invalid_step_is_rejected')

    sim.set_automatic_collection(False)
    sim.set_simulation_playing(True)
    full = step(6000)
    assert all(m['block_reason'] == '满格等待取箱' and m['full_bins'] > 0 for m in full['machines'])
    phases = [m['phase'] for m in full['machines']]
    later = step(120)
    assert equivalent(phases, [m['phase'] for m in later['machines']])
    assert full['completed'] == later['completed'] and full['occupancy'] == later['occupancy']
    (OUT / 'full_bin_state.json').write_text(json.dumps(later, ensure_ascii=False, indent=2), encoding='utf8')
    record('every_machine_stops_its_shared_chain_at_full_bins', **counts(later))
    sim.clear_full_bins()
    recovered = step(10)
    assert recovered['completed'] > full['completed'] and recovered['collected'] > 0
    sim.set_automatic_collection(True)
    collected_before = recovered['collected']
    recovered = step(120)
    assert recovered['collected'] > collected_before
    assert recovered['completed'] > full['completed']
    record('operator_clear_and_automatic_collection_resume_without_loss', **counts(recovered))


def test_roof_and_camera():
    assert isinstance(pawn, u.GHSWarehouseCameraPawn)
    assert isinstance(pc, u.GHSWarehousePlayerController)
    report['camera_class'] = pawn.get_class().get_path_name()
    report['controller_class'] = pc.get_class().get_path_name()
    assert pc.campus_traffic is None and not pc.order_replay.is_replaying()
    roof.restore_roof(False)
    hud.command('{"action":"overview"}')
    yield from wait('closed_roof_and_original_overview', lambda: roof.is_roof_closed() and not pawn.is_pose_transition_active())
    yield from pause(1)
    original = camera()
    assert hud.open_warehouse()
    yield from wait('original_roof_opens', roof.is_interior_available)
    assert same_pose(original, camera()), 'Roof opening moved the shared camera'
    hud.command('{"action":"overview"}')
    yield from wait('original_roof_restores', lambda: roof.is_roof_closed() and not pawn.is_pose_transition_active())
    assert same_pose(original, camera())
    record('existing_ghs_camera_roof_open_and_overview_restore', overview_camera=original)
    sim.focus_machine(0)
    yield from wait('sorter_focus_waits_for_roof', lambda: roof.is_interior_available() and not pawn.is_pose_transition_active())
    yield from pause(2)
    assert state()['selected_machine'] == 0 and not same_pose(original, camera())
    initial_focus = camera()
    pawn.orbit_pixels(u.Vector2D(35, -10))
    yield from pause(.8)
    assert not same_pose(initial_focus, camera())
    zoom_before = pawn.get_editor_property('spring_arm_component').target_arm_length
    pawn.zoom_steps(1)
    yield from pause(.8)
    assert pawn.get_editor_property('spring_arm_component').target_arm_length < zoom_before
    yield from focus_baseline_camera()
    record('sorter_focus_reuses_shared_orbit_zoom_camera', machine=0, fixed_camera=fixed_camera)


def focus_baseline_camera():
    global fixed_camera, baseline_camera
    sim.focus_machine(0)
    yield from wait('fixed_machine_zero_camera', lambda: roof.is_interior_available() and not pawn.is_pose_transition_active())
    yield from pause(2)
    pawn.freeze_current_pose()
    fixed_camera = camera()
    if baseline_camera is None:
        baseline_camera = fixed_camera[:]
    else:
        assert same_pose(baseline_camera, fixed_camera), 'Machine zero baseline camera changed'
    report['baseline_camera'] = baseline_camera


def capture_states():
    sim.reset_simulation()
    sim.set_simulation_playing(True)
    loading = step(.2)
    assert loading['machines'][0]['carriers'][0]['state'] == '上包识别'
    yield from pause(1, True)
    yield from capture('01_loading')
    travelling = step(.75)
    carrier = travelling['machines'][0]['carriers'][0]
    assert carrier['state'] == '行走 / 升降' and carrier['distance01'] > .005
    assert abs(carrier['lift_cm']-loading['machines'][0]['carriers'][0]['lift_cm']) > 2
    yield from pause(.5, True)
    yield from capture('02_travel_and_lift')
    found = False
    for iteration in range(1600):
        current = step(.05)
        carrier = current['machines'][0]['carriers'][0]
        if carrier['state'] == '侧向投料' and .4 <= carrier['unload_progress'] <= .65:
            found = True
            break
        if iteration % 20 == 0:
            yield
    assert found, 'Did not reach first carrier unloading'
    yield from pause(.5, True)
    yield from capture('03_lateral_unload')
    assert all(same_pose(fixed_camera, c['camera']) for c in report['captures'])
    record('three_fixed_camera_phase_captures_and_rendered_instance_readback', capture_count=3)


def targeted_camera_spec(machine_index, side):
    source = LAYOUT['machines'][machine_index]
    profile = LAYOUT['profiles'][source['profile']]
    transform = source['world_transform']
    # The measured machine transforms are planar; verify this before applying
    # profile-local pivots so a future tilted fixture fails explicitly.
    qx, qy, qz, qw = transform['rotation_xyzw']
    assert abs(qx) < 1e-6 and abs(qy) < 1e-6
    assert max(abs(scale-1) for scale in transform['scale']) < 1e-6
    yaw = math.degrees(math.atan2(2*qw*qz, 1-2*qz*qz))
    pivot = list(transform['translation_cm'])
    pivot[2] += 105
    return dict(pivot=pivot,
                distance=(profile['track_half_straight_cm']+profile['track_radius_cm'])*3.7,
                pitch=-22, yaw=yaw+(-65 if side == 0 else 65),
                viewport=[1920, 1080], screen_position=[1920*.61, 1080*.53])


def capture_targeted_views():
    global fixed_camera
    current = verify_state(state())
    assert [m['id'] for m in current['machines']] == [m['id'] for m in LAYOUT['machines']]
    selected = [(profile, next(i for i, m in enumerate(current['machines']) if m['profile'] == profile))
                for profile in ('cad64', 'cad120')]
    assert sum(m['profile'] == 'cad120' for m in current['machines']) == 4
    for profile, machine_index in selected:
        for side in (0, 1):
            view = targeted_camera_spec(machine_index, side)
            sim.focus_machine(machine_index)
            yield from wait('targeted_machine_focus', lambda: roof.is_interior_available() and not pawn.is_pose_transition_active())
            pawn.focus_on_target(u.Vector(*view['pivot']), view['distance'],
                                 u.Rotator(pitch=view['pitch'], yaw=view['yaw']),
                                 u.Vector2D(*view['viewport']), u.Vector2D(*view['screen_position']), 0)
            yield from pause(1)
            pawn.freeze_current_pose()
            fixed_camera = camera()
            side_camera = fixed_camera[:]
            for level in (0, 3):
                sim.reset_simulation()
                sim.set_simulation_playing(True)
                match = None
                # Manual stepping preserves a genuine unloading state while the
                # native renderer settles. Yield every simulated second so the
                # diagnostics loop never blocks the game for the whole search.
                for iteration in range(4000):
                    value = step(.1)
                    for carrier_index, carrier in enumerate(value['machines'][machine_index]['carriers']):
                        if (carrier['side'] == side and carrier['level'] == level
                                and carrier['state'] == '侧向投料' and .4 <= carrier['unload_progress'] <= .65):
                            match = dict(machine_index=machine_index, machine_id=value['machines'][machine_index]['id'],
                                         profile=profile, carrier_index=carrier_index, parcel_id=carrier['parcel_id'],
                                         side=side, side_label='A' if side == 0 else 'B', level=level,
                                         column=carrier['column'], unload_progress=carrier['unload_progress'],
                                         simulation_seconds=value['machines'][machine_index]['sim_time'],
                                         camera_spec=view, carrier_pose=carrier)
                            break
                    if match is not None:
                        break
                    if iteration % 10 == 9:
                        yield
                assert match is not None, ('No targeted unload within 400 simulation seconds', profile, side, level)
                yield from pause(.5, True)
                name = f'{profile}_machine_{machine_index:02d}_{match["side_label"]}_level_{level}_unload'
                yield from capture(name, machine_index=machine_index, target=match)
                assert same_pose(side_camera, fixed_camera), 'Low/high comparison camera changed'
    assert len(report['targeted_captures']) == 8
    record('two_profiles_both_sides_low_and_high_unload_with_native_poses',
           capture_count=8, machine_indices=[index for _, index in selected],
           levels_zero_based=[0, 3], sides_zero_based=[0, 1])


def capture_sequence():
    if SEQUENCE:
        sim.reset_simulation()
        sim.set_simulation_playing(True)
        step(55)
        for index in range(96):
            yield from capture(f'frame_{index:04d}', index)
            step(1/6)
        record('optional_fixed_camera_sequence', frames=96, simulation_fps=6, duration_seconds=16,
               warmup_simulation_seconds=55, machine_index=0, camera=fixed_camera)


def sample_runtime():
    sim.reset_simulation()
    sim.set_simulation_playing(True)
    sim.set_automatic_advance_for_diagnostics(True)
    yield from pause(8, True)
    before = verify_state(state())
    filename = 'MPR_SORTER_' + STAMP + '.csv'
    path = ROOT / 'Saved/Profiling/CSV' / filename
    console('CsvProfile STARTFILE=' + filename)
    console('CsvProfile START')
    # No manual advancement, screenshots, JSON snapshots or scans in this window.
    yield from pause(15, True)
    console('CsvProfile STOP')
    after = verify_state(state())
    sim.set_automatic_advance_for_diagnostics(False)
    yield from wait('native_runtime_csv_flush', lambda: timing.csv_complete(path))
    native = timing.parse_csv(path)
    native['fps'] = native['frame_count']/native['native_frame_time_seconds']
    assert after['machines'][0]['sim_time'] > before['machines'][0]['sim_time'] + 10
    assert after['completed'] > before['completed']
    report['performance'] = dict(native_csv=native, camera=fixed_camera,
        actor_auto_tick=True, manual_simulation_steps_during_sample=0, hud_visible=True,
        before=counts(before), after=counts(after),
        scope='One owned 1920x1080 local native game; 22 working machines and HUD. Not an isolated-hardware or streaming benchmark.')
    record('real_automatic_tick_advances_during_native_15_second_profile', fps=native['fps'])


def run():
    yield from wait('discover_mpr_sorter', discover, 65)
    yield from wait('viewport_1920x1080', lambda: list(pc.get_viewport_size()) == [1920, 1080])
    for command in ('DisableAllScreenMessages', 't.MaxFPS 0', 'r.VSync 0',
                    't.IdleWhenNotForeground 0', 'Slate.bAllowThrottling 0',
                    'csv.CompressionMode 0', 'r.GPUCsvStatsEnabled 1'):
        console(command)
    report['engine_version'] = u.SystemLibrary.get_engine_version()
    report['actor_count_before'] = len(u.GameplayStatics.get_all_actors_of_class(world, u.Actor))
    sim.set_automatic_advance_for_diagnostics(False)
    sim.set_panel_visible(True)
    initial = verify_state(state())
    verify_rendered_carriers(initial)
    record('native_fixture_22_machines_88_carriers_1632_cells',
           counts={name: component.get_instance_count() for name, component in components.items()},
           panel_attached=initial['panel_attached'])
    if VISUAL_ONLY:
        yield from focus_baseline_camera()
    else:
        yield from test_controls()
        yield from test_roof_and_camera()
        yield from capture_states()
    yield from capture_targeted_views()
    yield from focus_baseline_camera()
    yield from capture_sequence()
    if VISUAL_ONLY:
        report['performance'] = dict(skipped=True, reason='MPRSorterVisualOnly')
        record('visual_only_skips_control_suite_and_performance_sample')
    else:
        yield from sample_runtime()
    assert len(u.GameplayStatics.get_all_actors_of_class(world, u.Actor)) == report['actor_count_before']
    record('actor_and_component_pools_remain_bounded')
    report.update(success=True, stage='complete')


def finish(error=None):
    global done
    done = True
    if error:
        report.update(success=False, error=error)
    if world:
        console('CsvProfile STOP')
        if sim:
            sim.set_automatic_advance_for_diagnostics(False)
            sim.set_simulation_playing(False)
        if roof:
            roof.restore_roof(False)
    report['assets_unchanged'] = all(p.exists() and hashlib.sha256(p.read_bytes()).hexdigest() == HASHES[str(p)] for p in ASSETS)
    report['success'] = report['success'] and report['assets_unchanged']
    report['elapsed_wall_seconds'] = time.monotonic()-START
    write()
    if callback is not None:
        u.unregister_slate_post_tick_callback(callback)
    if world:
        u.SystemLibrary.quit_game(world, pc, u.QuitPreference.QUIT, False)


steps = run()


def tick(delta):
    global busy
    if done or busy:
        return
    busy = True
    try:
        assert time.monotonic()-START < (600 if SEQUENCE else 360), 'Sorter runtime verification timeout'
        next(steps)
    except StopIteration:
        finish()
    except Exception:
        finish(traceback.format_exc())
    finally:
        busy = False


write()
callback = u.register_slate_post_tick_callback(tick)
