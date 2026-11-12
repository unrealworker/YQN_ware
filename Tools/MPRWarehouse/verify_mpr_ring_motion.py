"""Measure individual MPR sorter ring motion in real native frames.

Run the existing map in an owned -game -RenderOffscreen -TwinDiagnostics
-EnablePython -ForceRes -ResX=1920 -ResY=1080 process. No assets are saved.
-MPRRingBaseline records the old 20 Hz defect without asserting smoothness.
Real station stops are excluded by state/chain flags and a documented 75 ms
event margin; all excluded frames and ordinary moving-frame counts are reported.
"""
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import sys
import time

sys.path.insert(0, str(Path(__file__).parent))
import verify_mpr_continuous_runtime as continuous
v = continuous.v
BASELINE = False
ORIGINAL_CVARS = {}
ORIGINAL_FINISH = v.finish
RESULTS = []
LIGHTWEIGHT = False


def flag(name):
    return bool(re.search(r'(?:^|\s)-' + re.escape(name) + r'(?=\s|$)',
                          v.u.SystemLibrary.get_command_line(), re.I))


def invariants():
    value = v.state()
    assert value['ready'] and not value['error']
    for key in ('conserved', 'unique_parcel_ownership', 'central_conserved',
                'global_unique_ownership', 'shared_aisle_mutex_valid'):
        assert value[key], key
    assert value['central_delivered'] == value['spawned']
    assert value['central_generated'] == value['central_delivered'] + value['central_in_transit']
    return value


def result(name, passed, **data):
    row = dict(name=name, passed=bool(passed), **data)
    RESULTS.append(row)
    v.report['checks'].append(row)
    v.write()


def snapshot():
    start = time.monotonic()
    value = json.loads(v.sim.get_ring_motion_diagnostics()) if LIGHTWEIGHT else v.state()
    machines = value['machines']
    assert len(machines) == 22
    columns, trays = v.components['MovingColumns'], v.components['LiftTrays']
    poses = []
    for index in range(88):
        tower, tray = v.instance(columns, index), v.instance(trays, index)
        q = tower.rotation
        poses.append(dict(column=v.xyz(tower.translation), tray=v.xyz(tray.translation),
                          rotation=[q.x, q.y, q.z, q.w]))
    rows = []
    for mi, machine in enumerate(machines):
        assert len(machine['carriers']) == 4
        rows.append(dict(stopped=machine['chain_stopped'],
            states=[c['state_code'] for c in machine['carriers']],
            distance=[c.get('visual_distance01', c['distance01']) for c in machine['carriers']],
            sim_time=machine.get('sim_time', value.get('sim_time', 0.)),
            speed=machine.get('speed_cm_s', 40.),
            poses=poses[mi*4:mi*4+4]))
    return dict(world_time=float(v.u.GameplayStatics.get_time_seconds(v.world)),
                read_seconds=time.monotonic()-start, machines=rows)


def rotation_delta(a, b):
    # q and -q encode the same orientation. Normalize to avoid float drift.
    dot = abs(sum(x*y for x, y in zip(a, b)))
    scale = math.sqrt(sum(x*x for x in a) * sum(x*x for x in b))
    return 2*math.acos(min(1., dot/scale))


def assess(label, snapshots, deltas, scope):
    elapsed = [0.]
    for dt in deltas:
        elapsed.append(elapsed[-1]+dt)
    event_times = [[] for _ in range(22)]
    for i in range(1, len(snapshots)):
        for mi in range(22):
            a, b = snapshots[i-1]['machines'][mi], snapshots[i]['machines'][mi]
            if a['stopped'] != b['stopped'] or a['states'] != b['states']:
                event_times[mi].append(elapsed[i])
    counts = dict(eligible_carrier_frames=0, frozen_carrier_frames=0,
                  jump_carrier_frames=0, bend_carrier_frames=0,
                  intentional_stop_machine_frames=0, station_boundary_machine_frames=0,
                  long_frame_machine_frames=0, vertical_moving_carrier_frames=0)
    max_error = max_turn_error = max_readback_error = 0.
    machine_counts = [0]*22
    failures = []
    frames = []
    for i, dt in enumerate(deltas, 1):
        frame = dict(dt=dt, eligible=0, frozen=0, jumps=0, max_error_cm=0.)
        for mi in range(22):
            a, b = snapshots[i-1]['machines'][mi], snapshots[i]['machines'][mi]
            # Real arrivals can be displayed at the station before the next
            # authoritative 50 ms event. Exclude a bounded window on both sides
            # of those actual state transitions, including the next sample.
            near_event = any(abs(elapsed[i]-t) < .075 or abs(elapsed[i-1]-t) < .075
                             for t in event_times[mi])
            profile = v.LAYOUT['profiles'][v.LAYOUT['machines'][mi]['profile']]
            radius = float(profile['track_radius_cm'])
            for pa, pb in zip(a['poses'], b['poses']):
                # Towers and trays must stay on the same horizontal carriage.
                error = math.dist(pb['column'][:2], pb['tray'][:2])
                max_readback_error = max(max_readback_error, error)
                counts['vertical_moving_carrier_frames'] += abs(pb['tray'][2]-pa['tray'][2]) > .0001
            if a['stopped'] or b['stopped']:
                counts['intentional_stop_machine_frames'] += 1
                continue
            if near_event:
                counts['station_boundary_machine_frames'] += 1
                continue
            if not .0001 < dt < .045:
                counts['long_frame_machine_frames'] += 1
                continue
            expected = b['speed']*dt
            for ci, (pa, pb) in enumerate(zip(a['poses'], b['poses'])):
                move = math.dist(pa['column'][:2], pb['column'][:2])
                turn = rotation_delta(pa['rotation'], pb['rotation'])
                error = abs(move-expected)
                turn_error = max(0., turn-b['speed']*dt/radius)
                frozen, jump = move < .0001, error > .09 or turn_error > .004
                counts['eligible_carrier_frames'] += 1
                counts['frozen_carrier_frames'] += frozen
                counts['jump_carrier_frames'] += jump
                counts['bend_carrier_frames'] += turn > .0001
                machine_counts[mi] += 1
                frame['eligible'] += 1
                frame['frozen'] += frozen
                frame['jumps'] += jump
                frame['max_error_cm'] = max(frame['max_error_cm'], error)
                max_error, max_turn_error = max(max_error, error), max(max_turn_error, turn_error)
                if (frozen or jump) and len(failures) < 25:
                    failures.append(dict(frame=i, machine=mi, carrier=ci, dt=dt,
                        expected_cm=expected, actual_cm=move, turn_radians=turn,
                        before_states=a['states'], after_states=b['states']))
        frames.append(frame)
    enough = counts['eligible_carrier_frames'] >= 300 and counts['bend_carrier_frames'] >= 4
    passed = enough and not counts['frozen_carrier_frames'] and not counts['jump_carrier_frames']
    passed = passed and max_readback_error < .03
    result(label, passed, **counts, machine_moving_sample_counts=machine_counts,
        all_machines_read=22, all_carriers_read=88, frames=len(deltas),
        nominal_sample_seconds=sum(deltas), observed_sample_fps=len(deltas)/sum(deltas),
        max_chord_vs_arc_error_cm=max_error, max_turn_excess_radians=max_turn_error,
        max_tower_tray_horizontal_error_cm=max_readback_error,
        mean_snapshot_read_ms=1000*sum(s['read_seconds'] for s in snapshots)/len(snapshots),
        station_event_exclusion_seconds=.075, example_failures=failures,
        per_frame=frames, scope=scope)


def prepare():
    v.sim.set_automatic_advance_for_diagnostics(False)
    v.sim.reset_simulation()
    v.sim.set_central_feeding_enabled(True)
    v.sim.set_simulation_playing(True)
    assert v.sim.advance_simulation_for_diagnostics(140)
    invariants()


def controlled():
    for name, cadence in [('60_hz', [1/60]), ('120_hz', [1/120]),
                           ('irregular', [.007, .021, .011, .039, .013, .027])]:
        prepare()
        samples, deltas = [snapshot()], []
        for frame in range(240):
            dt = cadence[frame % len(cadence)]
            assert v.sim.advance_simulation_for_diagnostics(dt)
            samples.append(snapshot())
            deltas.append(dt)
            if frame % 8 == 7:
                yield
        invariants()
        assess('production_diagnostic_' + name, samples, deltas,
               'Production diagnostic advances at explicit cadences; all 22 native ring components, not performance.')
    before = snapshot()
    v.sim.set_simulation_playing(False)
    assert v.sim.advance_simulation_for_diagnostics(.31)
    yield from v.pause(.2)
    after = snapshot()
    error = max(math.dist(a[k], b[k]) for ma, mb in zip(before['machines'], after['machines'])
                for a, b in zip(ma['poses'], mb['poses']) for k in ('column', 'tray'))
    result('pause_freezes_current_ring_and_lift_pose', error < .01, max_pose_change_cm=error)
    v.sim.set_simulation_playing(True)
    resumed = snapshot()
    error = max(math.dist(a[k], b[k]) for ma, mb in zip(after['machines'], resumed['machines'])
                for a, b in zip(ma['poses'], mb['poses']) for k in ('column', 'tray'))
    result('resume_has_no_pose_snap', error < .01, max_pose_change_cm=error)


def live():
    for cap in (60, 120):
        v.console('t.MaxFPS ' + str(cap))
        prepare()
        v.sim.set_automatic_advance_for_diagnostics(True)
        yield from v.pause(.5, True)
        samples, deltas = [snapshot()], []
        for _ in range(240):
            yield
            sample = snapshot()
            dt = sample['world_time']-samples[-1]['world_time']
            assert dt > 0, 'Native world did not advance between snapshots'
            samples.append(sample)
            deltas.append(dt)
        v.sim.set_automatic_advance_for_diagnostics(False)
        invariants()
        assess('actual_tick_' + str(cap), samples, deltas,
               'Actual automatic Tick, all 88 carriage/tray instances; diagnostic JSON and pose readback are instrumented overhead.')


def captures():
    for profile in ('cad64', 'cad120'):
        mi = next(i for i, m in enumerate(v.LAYOUT['machines']) if m['profile'] == profile)
        prepare()
        position = v.LAYOUT['machines'][mi]['world_transform']['translation_cm']
        pivot = [position[0], position[1], position[2]+110]
        yield from continuous.central.focus_view('ring_' + profile, pivot, 1400, -42, -55, fov=38, machine_index=mi)
        v.sim.set_automatic_advance_for_diagnostics(True)
        yield from v.pause(1., True)
        path = v.OUT / ('ring_' + profile + '.png')
        yield
        v.console('Shot showui filename="' + path.as_posix() + '" -nosuffix')
        yield from v.wait('capture_' + profile, lambda: v.timing.png_ready(path), 15)
        assert v.same_pose(v.fixed_camera, v.camera())
        data = path.read_bytes()
        assert struct.unpack('>II', data[16:24]) == (1920, 1080)
        v.report['captures'].append(dict(profile=profile, machine_index=mi, path=str(path),
            camera=v.fixed_camera[:], resolution=[1920,1080], automatic_tick=True,
            sha256=hashlib.sha256(data).hexdigest()))
        v.sim.set_automatic_advance_for_diagnostics(False)


def performance():
    v.console('t.MaxFPS 60')
    v.console('csv.CompressionMode 0')
    v.console('r.GPUCsvStatsEnabled 1')
    v.sim.set_automatic_advance_for_diagnostics(True)
    yield from v.pause(2, True)
    filename = 'MPR_RING_' + v.report['run_id'] + '.csv'
    path = v.ROOT / 'Saved/Profiling/CSV' / filename
    v.console('CsvProfile STARTFILE=' + filename)
    v.console('CsvProfile START')
    yield from v.pause(15, True)
    v.console('CsvProfile STOP')
    yield from v.wait('native_csv_flush', lambda: v.timing.csv_complete(path), 10)
    sample = v.timing.parse_csv(path)
    sample['fps'] = sample['frame_count']/sample['native_frame_time_seconds']
    v.report['performance'] = dict(native_csv=sample, resolution=[1920,1080],
        fps_cap=60, automatic_tick=True, screenshot_and_pose_reads_during_sample=0,
        aa_method=v.u.SystemLibrary.get_console_variable_int_value('r.AntiAliasingMethod'))


def finish(error=None):
    if v.world:
        for name, value in ORIGINAL_CVARS.items():
            v.console(name + ' ' + str(value))
    ORIGINAL_FINISH(error)


def run():
    global BASELINE, LIGHTWEIGHT
    BASELINE = flag('MPRRingBaseline')
    yield from v.wait('discover', v.discover, 40)
    yield from v.wait('viewport', lambda: list(v.pc.get_viewport_size()) == [1920,1080], 10)
    LIGHTWEIGHT = hasattr(v.sim, 'get_ring_motion_diagnostics')
    v.report.update(baseline=BASELINE, lightweight_diagnostics=LIGHTWEIGHT,
        scope='Individual sorter ring continuity, preserving intentional process stops; native Tick and ISM readback.')
    for name in ('r.VSync', 't.IdleWhenNotForeground', 'Slate.bAllowThrottling',
                 'csv.CompressionMode', 'r.GPUCsvStatsEnabled'):
        ORIGINAL_CVARS[name] = v.u.SystemLibrary.get_console_variable_int_value(name)
    ORIGINAL_CVARS['t.MaxFPS'] = v.u.SystemLibrary.get_console_variable_float_value('t.MaxFPS')
    for command in ('DisableAllScreenMessages', 'r.VSync 0', 't.IdleWhenNotForeground 0',
                    'Slate.bAllowThrottling 0', 't.MaxFPS 60'):
        v.console(command)
    v.sim.set_panel_visible(False)
    yield from captures()
    yield from controlled()
    yield from live()
    yield from performance()
    invariants()
    failed = [row['name'] for row in RESULTS if not row['passed']]
    v.report['failed_motion_checks'] = failed
    if not BASELINE:
        assert not failed, ('Ring motion checks failed', failed)
    v.report.update(success=True, stage='complete', baseline_defect_observed=bool(failed))


v.BASE = v.ROOT / 'Saved/MPR/ring_motion_20261112/runtime'
v.DEADLINE_SECONDS = 420
v.run = run
v.finish = finish
if __name__ == '__main__':
    v.main()
