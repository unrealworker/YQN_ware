"""Native regression: continuous central circulation with fast manual feeding.

Run an owned existing-map -own -game -RenderOffscreen -TwinDiagnostics
-EnablePython -ForceRes -ResX=1920 -ResY=1080 process and
-ExecCmds="py D:/UEPro/Test/Tools/MPRWarehouse/verify_mpr_continuous_runtime.py".
Optional -MPRContinuousCaptureSequence writes two eight-second 16-fps segments.
Never saves assets. Timing is demonstration data, not vendor throughput.
"""
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import struct
import sys
import time

sys.path.insert(0, str(Path(__file__).parent))
import verify_mpr_central_runtime as central
v = central.v
CAD_WORKERS_FILE = v.ROOT / 'SourceAssets/MPR/sorter_simulation/cad_workers/cad_workers.json'
CAD_WORKERS = json.loads(CAD_WORKERS_FILE.read_text(encoding='utf-8-sig'))
CAD_BY_HANDLE = {w['source_handle']: w for w in CAD_WORKERS['workers']}
PHASES = {0: 'loading', 1: 'travel', 2: 'discharging', 3: 'empty_return',
          4: 'retracting', 5: 'recovering'}
WORKER_COMPONENTS = {}
REFERENCE_FACING = {}


def worker_components():
    if not WORKER_COMPONENTS:
        WORKER_COMPONENTS.update({int(c.get_name().removeprefix('MannyWorker_')): c
            for c in v.sim.get_components_by_class(v.u.MPRWorkerPoseComponent)})
        # Component transforms include MeshToBody (-reference-facing yaw).
        # CAD specifies the person's heading, so undo that mesh-axis rotation.
        REFERENCE_FACING.update({i: c.get_reference_facing_yaw_degrees()
                                for i, c in WORKER_COMPONENTS.items()})
    return WORKER_COMPONENTS


def verify_state(value):
    assert value['ready'] and not value['error']
    assert value['machine_count'] == len(value['machines']) == 22
    assert value['cart_count'] == 96 and value['manual_feed_workers'] == 6
    for key in ('conserved', 'unique_parcel_ownership', 'central_conserved',
                'global_unique_ownership', 'shared_aisle_mutex_valid'):
        assert value[key], key
    assert value['central_generated'] == value['central_delivered'] + value['central_in_transit']
    assert value['central_delivered'] == value['spawned']
    assert value['spawned'] == value['completed'] + value['active'] + value['queued']
    assert value['completed'] == value['collected'] + value['occupancy']
    banks = value['distribution_banks']
    assert len(banks) == 2
    owners = []
    for bank in banks:
        assert bank['speed_cm_s'] > 0 and bank['loop_length_cm'] > 0
        assert bank['generated'] == bank['delivered'] + bank['active']
        assert bank['active'] == sum(bool(c['parcel_id']) for c in bank['carriers'])
        counts = [s['fed_count'] for s in bank['stations']]
        assert sum(counts) == bank['generated']
        assert max(counts) - min(counts) <= 1, ('Feed operator starvation', bank['id'], counts)
        if value['playing']:
            assert not bank['stopped'], ('Playing bank stopped', bank['id'])
        for ci, c in enumerate(bank['carriers']):
            assert 0 <= c['distance01'] < 1 and 0 <= c['progress'] <= 1
            assert c['state'] in PHASES
            offset = (c['distance01'] - bank['carriers'][0]['distance01']) % 1
            expected = ci / len(bank['carriers'])
            assert abs((offset - expected + .5) % 1 - .5) < 1.e-6, 'Carrier spacing changed'
            if c['parcel_id']:
                owners.append(c['parcel_id'])
    for m in value['machines']:
        owners.extend(c['parcel_id'] for c in m['carriers'] if c['parcel_id'])
        owners.extend(p['parcel_id'] for p in m['infeed'])
        owners.extend(pid for cell in m['cells'] for pid in cell['parcel_ids'])
    assert len(owners) == len(set(owners)), 'Global duplicate parcel ID'
    assert len(owners) == value['central_in_transit'] + value['active'] + value['queued'] + value['occupancy']
    manual = [s for bank in banks for s in bank['stations'] if s['manual']]
    assert len(manual) == 6
    workers = {w['index']: w for w in value['skeletal_workers']}
    assert value['cad_worker_count'] == CAD_WORKERS['count'] == 256
    assert value['worker_slots'] == len(workers) == 22 + CAD_WORKERS['count']
    placements = value['cad_workers']
    worker_components()
    assert len(placements) == len(CAD_BY_HANDLE)
    assert {w['source_handle'] for w in placements} == set(CAD_BY_HANDLE)
    assert len({w['worker_index'] for w in placements}) == len(placements), 'Duplicate CAD person instance'
    for row in placements:
        source = CAD_BY_HANDLE[row['source_handle']]
        w = workers[row['worker_index']]
        assert row['central_feed'] == source['central_feed']
        assert math.dist(row['feet_cm'], source['feet_ue_cm']) < .02
        assert math.dist(w['transform']['translation_cm'], source['feet_ue_cm']) < .02
        assert w['visible'] and w['ready'] and w['bone_count'] == 89
        assert w['mesh'].endswith('SKM_Manny_Simple.SKM_Manny_Simple')
        qx, qy, qz, qw = w['transform']['rotation_xyzw']
        yaw = math.degrees(math.atan2(2 * (qw * qz + qx * qy), 1 - 2 * (qy * qy + qz * qz)))
        body_yaw = yaw + REFERENCE_FACING[row['worker_index']]
        yaw_error = abs((body_yaw - source['facing_ue_yaw_deg'] + 180) % 360 - 180)
        assert yaw_error < .02, ('CAD body heading', row['source_handle'], row['worker_index'],
                                body_yaw, source['facing_ue_yaw_deg'], yaw_error)
    assert {w['worker_index'] for w in placements if w['central_feed']} == {s['worker_index'] for s in manual}
    for s in manual:
        w = workers[s['worker_index']]
        assert w['ready'] and w['visible']
        assert math.dist(s['feet_cm'], w['transform']['translation_cm']) < .02
        assert max(w['left_error_cm'], w['right_error_cm']) < .25
    return value


def readback(value):
    error, offset = 0., 0
    poses = []
    for bank in value['distribution_banks']:
        for c in bank['carriers']:
            tray = v.instance(v.components['CentralLiftTrays'], offset)
            column = v.instance(v.components['CentralMovingColumns'], offset)
            parcel = v.instance(v.components['CentralParcels'], offset)
            xyz = v.xyz(tray.translation)
            assert v.visible(tray) and v.visible(column)
            error = max(error, math.dist(xyz, c['tray_cm']),
                        math.dist(v.xyz(column.translation)[:2], c['tray_cm'][:2]))
            assert v.visible(parcel) == bool(c['parcel_id'])
            if c['parcel_id']:
                error = max(error, math.dist(v.xyz(parcel.translation), c['parcel_cm']))
            poses.append(xyz)
            offset += 1
    assert error < .04, ('Native ISM/report disagreement', error)
    return dict(carriers=offset, max_error_cm=error, tray_positions=poses)


def cad_native_readback(value):
    components = worker_components()
    assert len(components) == value['worker_slots']
    max_position_error, max_yaw_error = 0., 0.
    for row in value['cad_workers']:
        source = CAD_BY_HANDLE[row['source_handle']]
        component = components[row['worker_index']]
        position_error = math.dist(v.xyz(component.get_world_location()), source['feet_ue_cm'])
        body_yaw = component.get_world_rotation().yaw + component.get_reference_facing_yaw_degrees()
        yaw_error = abs((body_yaw - source['facing_ue_yaw_deg'] + 180) % 360 - 180)
        assert component.is_visible()
        assert position_error < .02 and yaw_error < .02, ('Native CAD body pose', row['source_handle'],
            row['worker_index'], position_error, body_yaw, source['facing_ue_yaw_deg'], yaw_error)
        max_position_error = max(max_position_error, position_error)
        max_yaw_error = max(max_yaw_error, yaw_error)
    result = dict(people=len(value['cad_workers']), central_feed_subset=6,
                  skeletal_slots=len(components), max_position_error_cm=max_position_error,
                  max_yaw_error_deg=max_yaw_error,
                  source_sha256=hashlib.sha256(CAD_WORKERS_FILE.read_bytes()).hexdigest())
    v.record('all_cad_people_native_positions_orientations_and_visibility', **result)
    return result


def motion_delta(before, after):
    """Absolute constant speed, independent of the C++ event/stopping state."""
    max_error, states = 0., Counter()
    for a, b in zip(before['distribution_banks'], after['distribution_banks']):
        dt = b['sim_time'] - a['sim_time']
        assert dt > 0 and not b['stopped']
        expected = dt * b['speed_cm_s'] / b['loop_length_cm']
        for old, new in zip(a['carriers'], b['carriers']):
            actual = (new['distance01'] - old['distance01']) % 1
            error = abs((actual - expected + .5) % 1 - .5)
            assert error < 1.e-7, ('Loop stopped or changed speed', a['id'], old['state'], new['state'], dt, actual, expected)
            max_error = max(max_error, error)
            states[PHASES[old['state']]] += 1
            # Tiny forward steps must move the real tray, including empty trays.
            if 0 < expected < .02:
                assert math.dist(old['tray_cm'][:2], new['tray_cm'][:2]) > .01
    return max_error, states


def reset(feeding=True):
    v.sim.reset_simulation()
    v.sim.set_central_feeding_enabled(feeding)
    v.sim.set_automatic_collection(True)
    v.sim.set_simulation_playing(True)
    result = verify_state(v.state())
    assert all(b['feeding_enabled'] == feeding for b in result['distribution_banks'])
    return result


def empty_and_pause():
    current = reset(False)
    native_before = readback(current)
    for _ in range(20):
        after = v.step(.2)
        motion_delta(current, after)
        assert after['central_generated'] == 0
        current = after
        yield
    assert native_before['tray_positions'] != readback(current)['tray_positions']
    v.record('empty_before_work_keeps_circulating', seconds=4)
    v.sim.set_simulation_playing(False)
    paused = v.state()
    transforms = v.all_render_transforms()
    assert v.equivalent(paused, v.step(10))
    v.sim.set_automatic_advance_for_diagnostics(True)
    yield from v.pause(.3)
    v.sim.set_automatic_advance_for_diagnostics(False)
    assert v.equivalent(paused, v.state())
    assert v.equivalent(transforms, v.all_render_transforms())
    v.record('manual_pause_freezes_logic_and_native_render_poses')


def active_and_cadence():
    current = reset()
    # One complete first lap reaches both ends before measuring steady cadence.
    warm = max(b['loop_length_cm'] / b['speed_cm_s'] for b in current['distribution_banks'])
    for _ in range(math.ceil(warm / 5)):
        after = v.step(5)
        motion_delta(current, after)
        current = after
        yield
    seen = set()
    events = defaultdict(list)
    states = Counter()
    max_error = 0.
    for i in range(450):
        after = v.step(.2)
        error, observed = motion_delta(current, after)
        max_error = max(max_error, error)
        states.update(observed)
        for bi, bank in enumerate(after['distribution_banks']):
            for c in bank['carriers']:
                pid = c['parcel_id']
                if c['state'] == 0 and pid and pid not in seen:
                    seen.add(pid)
                    events[(bi, c['source_station'])].append(bank['sim_time'])
        current = after
        if i % 5 == 0:
            readback(current)
            yield
    assert {'loading', 'travel', 'discharging', 'empty_return', 'recovering'} <= states.keys(), states
    rows = []
    for bi, bank in enumerate(current['distribution_banks']):
        for si, station in enumerate(bank['stations']):
            if not station['manual']:
                continue
            stamps = events[(bi, si)]
            gaps = [b - a for a, b in zip(stamps, stamps[1:])]
            assert len(gaps) >= 5, ('Feed operator did not repeat', bi, si, stamps)
            typical = statistics.median(gaps)
            pitch_seconds = bank['loop_length_cm'] / bank['speed_cm_s'] / len(bank['carriers'])
            # Hand action speed and wait-for-tray time are different quantities.
            # Six stations share one loop; do not invent an unsustainable per-
            # person throughput by treating each station as an independent line.
            assert 0 < bank['loading_seconds'] <= 1.5, ('Slow manual action', bi, si)
            rows.append(dict(bank=bank['id'], station=si, worker_index=station['worker_index'],
                admissions=len(stamps), median_seconds=typical, max_seconds=max(gaps),
                total_fed=station['fed_count'],
                pitch_seconds=pitch_seconds, loading_seconds=bank['loading_seconds'],
                observed_simulation_seconds=90))
    v.report['feeding_cadence'] = rows
    v.record('active_phases_move_at_constant_speed', samples=450, seconds=90,
             max_normalized_error=max_error, phase_observations=dict(states),
             native_readback=readback(current))
    v.record('six_operators_repeat_fast_feed_cycles', stations=rows)
    # Stop new arrivals, not the motor; finish work then verify unloaded motion.
    v.sim.set_central_feeding_enabled(False)
    generated = current['central_generated']
    for _ in range(240):
        after = v.step(5)
        motion_delta(current, after)
        assert after['central_generated'] == generated
        current = after
        yield
        if current['central_in_transit'] == 0 and current['active'] == 0 and current['queued'] == 0:
            break
    assert current['central_in_transit'] == current['active'] == current['queued'] == 0, 'Work did not drain'
    start = current
    for _ in range(30):
        after = v.step(.2)
        motion_delta(current, after)
        assert after['central_generated'] == generated and after['central_in_transit'] == 0
        current = after
        yield
    # Read actual final ISMs and compare their world positions to the prior
    # logical state, rather than reading the same live instances twice.
    final_native = readback(current)
    assert any(math.dist(a['tray_cm'][:2], b[:2]) > 1 for a, b in zip(
        [c for bank in start['distribution_banks'] for c in bank['carriers']], final_native['tray_positions']))
    v.record('finished_work_empty_carriers_keep_circulating', seconds=6,
             generated=generated, completed=current['completed'], native_readback=final_native)


def blocked_outputs():
    current = reset()
    v.sim.set_automatic_collection(False)
    for _ in range(100):
        after = v.step(30)
        motion_delta(current, after)
        current = after
        yield
        if current['waiting_exchange_count'] and sum(b['blocked_passes'] for b in current['distribution_banks']):
            break
    assert current['waiting_exchange_count'], 'No full cart backpressure observed'
    before_blocked = sum(b['blocked_passes'] for b in current['distribution_banks'])
    lap = max(b['loop_length_cm'] / b['speed_cm_s'] for b in current['distribution_banks'])
    for _ in range(math.ceil(lap / .5)):
        after = v.step(.5)
        motion_delta(current, after)
        current = after
        yield
    assert sum(b['blocked_passes'] for b in current['distribution_banks']) > before_blocked
    v.record('full_destination_backpressure_does_not_stop_common_chain',
             waiting_carts=current['waiting_exchange_count'],
             blocked_passes=sum(b['blocked_passes'] for b in current['distribution_banks']),
             native_readback=readback(current))


def capture_frame(path):
    yield
    yield
    v.console('Shot showui filename="' + path.as_posix() + '" -nosuffix')
    yield from v.wait('capture_' + path.stem, lambda: v.timing.png_ready(path), 12, log=False)
    data = path.read_bytes()
    assert struct.unpack('>II', data[16:24]) == (1920, 1080)
    assert v.same_pose(v.fixed_camera, v.camera())


def capture_sequence():
    folder = v.OUT / 'sequence'
    folder.mkdir(parents=True, exist_ok=True)
    for group, pivot, yaw in [('end_a', [-10530, -150, 120], 30),
                              ('end_b', [-10330, 2770, 120], -150)]:
        yield from central.focus_view(group, pivot, 1100, -30, yaw, fov=25)
        reset()
        v.step(140)
        start = len(v.report['sequence'])
        for i in range(128):
            current = v.step(1 / 16)
            path = folder / f'{start + i:04d}.png'
            yield from capture_frame(path)
            v.report['sequence'].append(dict(frame=start + i, group=group,
                simulation_fps=16, path=str(path), camera=v.fixed_camera[:],
                generated=current['central_generated'],
                central_carriers=[{k: c[k] for k in ('distance01', 'state', 'parcel_id', 'tray_cm')}
                                  for c in current['distribution_banks'][0]['carriers']]))
        v.write()
    v.record('two_fixed_view_eight_second_segments', frames=256, simulation_fps=16)


def performance():
    yield from central.focus_view('performance_overview', [-10434, 1300, 130], 4300, -48, 0, fov=60)
    reset()
    v.step(140)
    v.sim.set_panel_visible(True)
    v.sim.set_automatic_advance_for_diagnostics(True)
    yield from v.pause(3, True)
    before = verify_state(v.state())
    filename = 'MPR_CONTINUOUS_' + v.report['run_id'] + '.csv'
    path = v.ROOT / 'Saved/Profiling/CSV' / filename
    v.console('CsvProfile STARTFILE=' + filename)
    v.console('CsvProfile START')
    reads = v.report_reads
    start = time.monotonic()
    # Actual native Tick, no JSON/instance reads or screenshots in this window.
    yield from v.pause(15, True)
    elapsed = time.monotonic() - start
    v.console('CsvProfile STOP')
    assert reads == v.report_reads
    v.sim.set_automatic_advance_for_diagnostics(False)
    after = verify_state(v.state())
    yield from v.wait('native_csv_flush', lambda: v.timing.csv_complete(path), 15)
    native = v.timing.parse_csv(path)
    native['fps'] = native['frame_count'] / native['native_frame_time_seconds']
    assert after['distribution_banks'][0]['sim_time'] - before['distribution_banks'][0]['sim_time'] > 10
    motion_delta(before, after)
    v.report['performance'] = dict(native_csv=native, sampled_wall_seconds=elapsed,
        camera=v.fixed_camera[:], actor_auto_tick=True, manual_steps=0,
        report_reads_during_sample=0, resolution=[1920, 1080],
        worker_slots=after['worker_slots'], visible_workers=sum(w['visible'] for w in after['skeletal_workers']),
        scope='Local native renderer with all current CAD workers, full scene and HUD; not Pixel Streaming or vendor throughput.')
    v.record('native_tick_15_seconds_without_json_or_capture_polling', fps=native['fps'])


def run():
    v.report.update(scope='Continuous central motion while loading, transferring, blocked and fully drained; six-person fast feeding.',
        limitations=['Configured demonstration timing is not measured vendor throughput.',
                     'Capture fps is independent of real-time rendering performance.'])
    yield from v.wait('discover', v.discover, 40)
    yield from v.wait('viewport', lambda: list(v.pc.get_viewport_size()) == [1920, 1080], 10)
    for command in ('DisableAllScreenMessages', 't.MaxFPS 0', 'r.VSync 0', 't.IdleWhenNotForeground 0',
                    'Slate.bAllowThrottling 0', 'csv.CompressionMode 0', 'r.GPUCsvStatsEnabled 1'):
        v.console(command)
    v.sim.set_automatic_advance_for_diagnostics(False)
    current = verify_state(v.state())
    cad_native_readback(current)
    count = sum(len(b['carriers']) for b in current['distribution_banks'])
    for name in ('CentralMovingColumns', 'CentralLiftTrays', 'CentralParcels'):
        assert v.components[name].get_instance_count() == count
    v.report['initial_instance_pool'] = {n: c.get_instance_count() for n, c in v.components.items()}
    yield from empty_and_pause()
    yield from active_and_cadence()
    yield from blocked_outputs()
    yield from central.focus_view('continuous_overview', [-10434, 1300, 130], 4300, -48, 0, fov=60)
    reset()
    current = v.step(140)
    path = v.OUT / 'overview.png'
    yield from capture_frame(path)
    v.report['captures'].append(dict(path=str(path), camera=v.fixed_camera[:], sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    if re.search(r'(?:^|\s)-MPRContinuousCaptureSequence(?=\s|$)', v.u.SystemLibrary.get_command_line(), re.I):
        v.sim.set_panel_visible(False)
        yield from capture_sequence()
    yield from performance()
    assert v.report['initial_instance_pool'] == {n: c.get_instance_count() for n, c in v.components.items()}
    v.record('conserved_ids_and_bounded_native_instance_pools')
    v.report.update(success=True, stage='complete')


v.BASE = v.ROOT / 'Saved/MPR/continuous_distribution_20261109/runtime'
v.DEADLINE_SECONDS = 1200
v.verify_state = verify_state
v.run = run
if __name__ == '__main__':
    v.main()
