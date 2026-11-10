"""Native regression for sub-tick central motion and CAD worker/table contact.

Run in the existing MPR map, owned -game -RenderOffscreen -TwinDiagnostics
-EnablePython -ForceRes -ResX=1920 -ResY=1080 process. This never saves assets.
-MPRMotionBaseline records the unfixed defects without requiring a green result.
-MPRMotionCaptureSequence optionally captures a 60 fps deterministic preview;
the independent native Tick samples, not this preview, measure live motion.
"""
import hashlib
import math
from pathlib import Path
import re
import statistics
import sys

sys.path.insert(0, str(Path(__file__).parent))
import verify_mpr_continuous_runtime as check
import capture_mpr_cad_workers as tables
v = check.v

BASELINE = False
RESULTS = []


def result(name, passed, **data):
    item = dict(name=name, passed=bool(passed), **data)
    RESULTS.append(item)
    v.report['checks'].append(item)
    v.write()
    return item


def positions(indices=None):
    c = v.components['CentralMovingColumns']
    if indices is None:
        indices = range(c.get_instance_count())
    return [v.xyz(v.instance(c, i).translation) for i in indices]


def measure_step(before, after, dt, speeds):
    moves = [math.dist(a[:2], b[:2]) for a, b in zip(before, after)]
    expected = [dt * speed for speed in speeds]
    # At these time steps even the smallest 44 cm turn has chord/arc error
    # under .02 cm. This tolerance detects repeated poses and 4.5 cm jumps.
    errors = [abs(a-b) for a, b in zip(moves, expected)]
    return dict(dt=dt, stopped=sum(d < .0001 for d in moves),
                max_error_cm=max(errors), min_distance_cm=min(moves),
                max_distance_cm=max(moves))


def state_invariants():
    value = v.state()
    assert value['ready'] and not value['error']
    for key in ('conserved', 'unique_parcel_ownership', 'central_conserved',
                'global_unique_ownership', 'shared_aisle_mutex_valid'):
        assert value[key], key
    assert value['central_generated'] == value['central_delivered'] + value['central_in_transit']
    assert value['central_delivered'] == value['spawned']
    return value


def controlled_motion():
    v.sim.set_automatic_advance_for_diagnostics(False)
    for label, cadence in [('60_hz', [1/60]), ('120_hz', [1/120]),
                           ('irregular', [.007, .021, .011, .039, .013, .027])]:
        v.sim.reset_simulation()
        v.sim.set_central_feeding_enabled(False)
        v.sim.set_simulation_playing(True)
        assert v.sim.advance_simulation_for_diagnostics(.1)
        value = state_invariants()
        speeds = [bank['speed_cm_s'] for bank in value['distribution_banks']
                  for _ in bank['carriers']]
        before, rows = positions(), []
        for i in range(240):
            dt = cadence[i % len(cadence)]
            assert v.sim.advance_simulation_for_diagnostics(dt)
            after = positions()
            rows.append(measure_step(before, after, dt, speeds))
            before = after
            if i % 8 == 7:
                yield
        state_invariants()
        failed = [r for r in rows if r['stopped'] or r['max_error_cm'] > .04]
        result('native_columns_subtick_' + label, not failed, frames=len(rows),
               carriers=len(before), frozen_carrier_frames=sum(r['stopped'] for r in rows),
               max_distance_error_cm=max(r['max_error_cm'] for r in rows),
               failed_frames=len(failed), samples=rows,
               scope='Native instance transforms after production diagnostic advance; all carriers include straight, bend and loop-wrap locations.')
    # Pause with a fractional remainder, then resume without a pose snap.
    assert v.sim.advance_simulation_for_diagnostics(.007)
    before = positions()
    v.sim.set_simulation_playing(False)
    paused = positions()
    assert v.sim.advance_simulation_for_diagnostics(.31)
    still = positions()
    freeze_error = max(math.dist(a, b) for a, b in zip(before, paused))
    freeze_error = max(freeze_error, max(math.dist(a, b) for a, b in zip(paused, still)))
    result('manual_pause_preserves_fractional_render_pose', freeze_error < .01,
           max_motion_cm=freeze_error)
    v.sim.set_simulation_playing(True)
    resumed = positions()
    restart_error = max(math.dist(a, b) for a, b in zip(still, resumed))
    assert v.sim.advance_simulation_for_diagnostics(.009)
    after = positions()
    resume = measure_step(resumed, after, .009, speeds)
    result('resume_has_no_backwards_or_delayed_jump', restart_error < .01 and
           resume['stopped'] == 0 and resume['max_error_cm'] < .04,
           restart_error_cm=restart_error, first_step=resume)


def live_motion():
    for cap in (60, 120):
        v.console('t.MaxFPS ' + str(cap))
        v.sim.set_automatic_advance_for_diagnostics(False)
        v.sim.reset_simulation()
        v.sim.set_central_feeding_enabled(True)
        v.sim.set_simulation_playing(True)
        assert v.sim.advance_simulation_for_diagnostics(140)
        current = state_invariants()
        counts = [len(bank['carriers']) for bank in current['distribution_banks']]
        # Six columns per bank include both straights and returns. One read per
        # actual frame; no full-state JSON or screenshots inside this sample.
        indices, speeds, offset = [], [], 0
        for bank, count in zip(current['distribution_banks'], counts):
            selected = sorted(set([0, 1, count//4, count//2, 3*count//4, count-1]))
            indices.extend(offset+i for i in selected)
            speeds.extend([bank['speed_cm_s']] * len(selected))
            offset += count
        v.sim.set_automatic_advance_for_diagnostics(True)
        yield from v.pause(.5)
        before = positions(indices)
        last_time = v.u.GameplayStatics.get_time_seconds(v.world)
        reads, rows = v.report_reads, []
        for _ in range(240):
            yield
            now = v.u.GameplayStatics.get_time_seconds(v.world)
            after = positions(indices)
            dt = now-last_time
            assert dt > 0, ('World clock did not advance', now, last_time)
            rows.append(measure_step(before, after, dt, speeds))
            before, last_time = after, now
        assert v.report_reads == reads
        v.sim.set_automatic_advance_for_diagnostics(False)
        state_invariants()
        # Long stalls are reported separately; they cannot falsely establish
        # smooth rendering. Sub-.1s frames must still track elapsed game time.
        ordinary = [r for r in rows if r['dt'] < .1]
        failed = [r for r in ordinary if r['stopped'] or r['max_error_cm'] > .08]
        result('actual_tick_per_frame_' + str(cap), not failed and len(ordinary) >= 220,
               frames=len(rows), sampled_carriers=len(indices), cap_fps=cap,
               mean_observed_fps=len(rows)/sum(r['dt'] for r in rows),
               p95_frame_ms=sorted(r['dt']*1000 for r in rows)[int(.95*(len(rows)-1))],
               frozen_carrier_frames=sum(r['stopped'] for r in rows), failed_frames=len(failed),
               long_frame_count=len(rows)-len(ordinary),
               max_distance_error_cm=max(r['max_error_cm'] for r in ordinary),
               full_state_reads_during_sample=0, samples=rows,
               scope='Actual native actor Tick plus lightweight ISM readback; this is instrumented motion acceptance, not a pure performance benchmark.')
    v.console('t.MaxFPS 0')


def table_contacts(value):
    actual = []
    for actor in v.u.GameplayStatics.get_all_actors_of_class(v.world, v.u.Actor):
        for component in actor.get_components_by_class(v.u.InstancedStaticMeshComponent):
            mesh = component.get_editor_property('static_mesh')
            if not mesh or mesh.get_name() != 'SM_MPR_WorkTable':
                continue
            for index in range(component.get_instance_count()):
                transform = v.instance(component, index)
                if not v.visible(transform):
                    continue
                # The mesh's tabletop is z=93; the complete mesh bounds also
                # include its monitor and must not stand in for the desktop.
                half_y, top_z = 60., 93.
                corners = []
                height_sum = 0.
                for x, y in [(-50., -half_y), (50., -half_y), (50., half_y), (-50., half_y)]:
                    point = tables.native_point(transform, [x, y, top_z])
                    assert len(point) == 3
                    height_sum += float(point[2])
                    corners.append([float(point[0]), float(point[1])])
                actual.append(dict(component=component.get_path_name(), instance=index,
                    corners=corners, height_cm=height_sum/4.))
    roots = {row['source_handle']: row for row in value['cad_workers']}
    components = check.worker_components()
    clearances = []
    for source in check.CAD_WORKERS['workers']:
        row = roots[source['source_handle']]
        body = v.xyz(components[row['worker_index']].get_world_location())
        assert math.dist(body, source['feet_ue_cm']) < .02
        # Keep scalar arithmetic separate from the comparison. This also emits
        # useful native-data diagnostics if a bridge value is not numeric.
        relevant = []
        for table in actual:
            assert isinstance(table['height_cm'], (int, float)), ('Invalid desktop height', table)
            assert isinstance(body[2], (int, float)), ('Invalid body height', body)
            relative_height = float(table['height_cm']) - float(body[2])
            if relative_height > 40. and relative_height < 150.:
                relevant.append(table)
        assert relevant, ('No desktop surfaces at body height', source['source_handle'], body)
        distance, nearest = math.inf, -1
        for i, table in enumerate(relevant):
            candidate = tables.outside_distance(body, table['corners'])
            if candidate < distance:
                distance, nearest = candidate, i
        clearances.append(dict(source_handle=source['source_handle'], worker_index=row['worker_index'],
            body_cm=body, clearance_cm=distance, nearest_table=relevant[nearest]))
    failures = [row for row in clearances if row['clearance_cm'] < 15]
    result('all_cad_people_clear_visible_worktable_footprints', not failures,
           people=len(clearances), visible_tabletops=len(actual), body_radius_cm=15,
           minimum_root_to_table_edge_cm=min(row['clearance_cm'] for row in clearances),
           conflicts=failures, all_clearances=clearances)
    station = check.CAD_WORKERS['operator_stations'][0]['console']
    expected = tables.rectangle(station['center_ue_cm'],station['size_cm'],station['yaw_deg'])
    matches = []
    for table in actual:
        error = max(min(math.dist(point, corner) for corner in table['corners']) for point in expected)
        if error < .02:
            matches.append(dict(max_corner_error_cm=error, **table))
    result('source_console_restored_once', len(matches) == 1 and value.get('refitted_cad_operator_stations') == 1,
           source_handle='2CCF60', exact_matches=matches)
    return clearances


def contact_captures():
    v.sim.set_automatic_advance_for_diagnostics(False)
    v.sim.set_simulation_playing(False)
    value = state_invariants()
    rows = table_contacts(value)
    target = next(row for row in rows if row['source_handle'] == '2CCF61')
    pivot = [target['body_cm'][0]-45, target['body_cm'][1]-30, 85]
    for name, yaw, pitch in [('worker_contact_oblique', -135, -24),
                             ('worker_contact_opposite', 45, -28)]:
        yield from check.central.focus_view(name, pivot, 520, pitch, yaw, fov=38)
        path = v.OUT / (name+'.png')
        yield from check.capture_frame(path)
        v.report['captures'].append(dict(name=name, path=str(path),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(), camera=v.fixed_camera[:],
            resolution=[1920,1080], source_handle='2CCF61', native_contact=target))
        v.write()


def optional_clip():
    if not re.search(r'(?:^|\s)-MPRMotionCaptureSequence(?=\s|$)', v.u.SystemLibrary.get_command_line(), re.I):
        return
    v.sim.reset_simulation()
    v.sim.set_central_feeding_enabled(True)
    v.sim.set_simulation_playing(True)
    assert v.sim.advance_simulation_for_diagnostics(140)
    yield from check.central.focus_view('motion_60fps', [-10530, -150, 130], 1350, -28, 30, fov=25)
    folder = v.OUT/'sequence_60fps'
    folder.mkdir(parents=True)
    for frame in range(240):
        assert v.sim.advance_simulation_for_diagnostics(1/60)
        path = folder/f'{frame:04d}.png'
        yield from check.capture_frame(path)
        v.report['sequence'].append(dict(frame=frame, simulation_fps=60, path=str(path),
                                        camera=v.fixed_camera[:]))
        if frame % 60 == 59:
            v.write()


def run():
    global BASELINE
    BASELINE = bool(re.search(r'(?:^|\s)-MPRMotionBaseline(?=\s|$)', v.u.SystemLibrary.get_command_line(), re.I))
    v.report.update(scope='Subtick native central motion and complete CAD-person worktable contact audit.', baseline=BASELINE)
    yield from v.wait('discover', v.discover, 40)
    yield from v.wait('viewport', lambda: list(v.pc.get_viewport_size()) == [1920,1080], 10)
    for command in ('DisableAllScreenMessages','t.MaxFPS 0','r.VSync 0','t.IdleWhenNotForeground 0','Slate.bAllowThrottling 0'):
        v.console(command)
    v.sim.set_panel_visible(False)
    v.sim.set_automatic_advance_for_diagnostics(False)
    yield from controlled_motion()
    yield from live_motion()
    yield from contact_captures()
    if not BASELINE:
        yield from optional_clip()
    failures = [row['name'] for row in RESULTS if not row['passed']]
    v.report['regression_failures'] = failures
    v.report.update(success=not failures, stage='baseline_complete' if BASELINE else 'complete',
                    expected_baseline_defects_observed=bool(BASELINE and failures))
    v.write()


v.BASE = v.ROOT/'Saved/MPR/motion_contacts_20261110/runtime'
v.DEADLINE_SECONDS = 600
v.run = run
if __name__ == '__main__':
    v.main()
