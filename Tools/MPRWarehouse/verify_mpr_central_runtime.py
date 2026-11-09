"""Native acceptance for the shared MPR distributor and six CAD feed operators.

Run in an owned -game -RenderOffscreen -TwinDiagnostics -EnablePython process,
with -ForceRes -ResX=1920 -ResY=1080. Never saves the map or assets. The imported
validator supplies only lifecycle, camera, capture and CSV infrastructure;
its obsolete per-machine manual-feeding assertions are not invoked.
-MPRCentralCaptureSequence adds two 16-second, 8-fps fixed-camera segments,
one for each three-person feed group (256 consecutively numbered PNG frames).
"""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import sys
import time

sys.path.insert(0, str(Path(__file__).parent))
import verify_mpr_full_sorter_runtime as v

CAD_FILE = v.ROOT / 'SourceAssets/MPR/sorter_simulation/central_distribution/cad_layout.json'
CAD = json.loads(CAD_FILE.read_text(encoding='utf-8-sig'))
FEET = [x['position_ue_cm'] for x in CAD['central64']['workers']]
TOTALS = v.TOTAL_FIELDS
current_view = ''
cart_instances = {}
central_phases = set()


def verify_state(value):
    assert value['ready'] and value['schema_version'] == 2, value.get('error')
    assert value['machine_count'] == len(value['machines']) == 22
    assert value['cart_count'] == 96 and value['worker_slots'] == 28
    assert value['manual_feed_workers'] == 6
    assert value['suppressed_obsolete_spine_instances'] == 24
    assert value['legacy_worker_instances'] == 0
    assert value['conserved'] and value['unique_parcel_ownership']
    assert value['central_conserved'] and value['global_unique_ownership']
    assert value['shared_aisle_mutex_valid']
    assert value['spawned'] == value['completed'] + value['active'] + value['queued']
    assert value['completed'] == value['collected'] + value['occupancy']
    assert value['central_generated'] == value['central_delivered'] + value['central_in_transit']
    assert value['central_delivered'] == value['spawned']
    assert value['central_generated'] == value['completed'] + value['active'] + value['queued'] + value['central_in_transit']
    assert value['tower_instances'] == value['tray_instances'] == value['parcel_instances'] == 88
    assert value['infeed_instances'] == 66 and value['bin_parcel_instances'] == 4896

    owners, cart_ids, active_carts = [], [], []
    assert [m['id'] for m in value['machines']] == [m['id'] for m in v.LAYOUT['machines']]
    waiting = 0
    for mi, machine in enumerate(value['machines']):
        assert machine['transfer_mode'] == 'central_distribution_powered_connection'
        assert len(machine['carriers']) == 4 and len(machine['infeed']) == machine['queued'] <= 3
        assert machine['spawned'] == machine['completed'] + machine['active'] + machine['queued']
        assert machine['completed'] == machine['collected'] + machine['occupancy']
        carrier_ids = [c['parcel_id'] for c in machine['carriers'] if c['parcel_id']]
        queue_ids = [p['parcel_id'] for p in machine['infeed']]
        cell_ids = [p for b in machine['cells'] for p in b['parcel_ids']]
        assert len(carrier_ids) == machine['active'] and len(cell_ids) == machine['occupancy']
        owners.extend(carrier_ids + queue_ids + cell_ids)
        assert sum(c['occupancy'] for c in machine['carts']) == machine['occupancy']
        for cell in machine['cells']:
            assert len(cell['parcel_ids']) == cell['occupancy']
            assert 0 <= cell['occupancy'] <= 3 and 0 <= cell['reserved'] <= 3
            assert cell['occupancy'] + cell['reserved'] <= 3
        for ci, cart in enumerate(machine['carts']):
            assert cart['index'] == ci and cart['generation'] >= 1
            assert cart['state_code'] in range(7)
            assert cart['visible'] == (cart['state_code'] != 6)
            assert cart['capacity'] == cart['column_count'] * 12
            assert len(cart['parcel_ids']) == cart['occupancy'] <= cart['capacity']
            assert 0 <= cart['progress01'] <= 1
            cart_ids.append(cart['physical_cart_id'])
            members = [b for b in machine['cells'] if b['cart_index'] == ci]
            assert sorted(cart['parcel_ids']) == sorted(p for b in members for p in b['parcel_ids'])
            assert cart['reserved'] == sum(b['reserved'] for b in members)
            if cart['state_code'] in (1, 2, 3, 6):
                assert cart['occupancy'] == cart['capacity'] and cart['reserved'] == 0
            if cart['state_code'] in (4, 5):
                assert cart['occupancy'] == cart['reserved'] == 0
            if cart['state_code'] == 1:
                waiting += 1
            if cart['state_code'] >= 2:
                active_carts.append((mi, ci))
                assert machine['active'] == 0, ('Exchanging before carrier drain', mi, ci)
        for carrier in machine['carriers']:
            assert 0 <= carrier['distance01'] < 1
            if carrier['parcel_id']:
                target = machine['carts'][carrier['target_cart']]
                assert target['state_code'] == 0
                assert target['generation'] == carrier['target_cart_generation']
    assert len(cart_ids) == len(set(cart_ids)) == 96
    assert len(active_carts) == value['active_exchange_count'] <= 1
    assert waiting == value['waiting_exchange_count']
    if active_carts:
        assert value['exchange_owner_machine'] == active_carts[0][0]
    for key in TOTALS:
        assert value[key] == sum(m[key] for m in value['machines']), ('Fleet total', key)

    banks = value['distribution_banks']
    assert len(banks) == 2 and [len(b['carriers']) for b in banks] == [48, 12]
    assert [len(b['connections']) for b in banks] == [18, 4]
    assert sorted(c['machine'] for b in banks for c in b['connections']) == sorted(m['id'] for m in value['machines'])
    assert value['central_generated'] == sum(b['generated'] for b in banks)
    assert value['central_delivered'] == sum(b['delivered'] for b in banks)
    assert value['central_in_transit'] == sum(b['active'] for b in banks)
    manual = [s for b in banks for s in b['stations'] if s['manual']]
    assert [s['worker_index'] for s in manual] == list(range(22, 28))
    assert len([s for s in banks[1]['stations'] if s['manual']]) == 0
    for si, station in enumerate(manual):
        assert math.dist(station['feet_cm'], FEET[si]) < .02, ('CAD station mismatch', si)
    for bank in banks:
        ids = [c['parcel_id'] for c in bank['carriers'] if c['parcel_id']]
        assert len(ids) == bank['active']
        assert bank['generated'] == bank['delivered'] + bank['active']
        owners.extend(ids)
        for c in bank['carriers']:
            assert 0 <= c['distance01'] < 1 and 0 <= c['progress'] <= 1
            assert c['state'] in range(6)
            central_phases.add(c['state'])
            assert all(math.isfinite(x) for x in c['tray_cm'])
            if c['parcel_id']:
                assert c['target_machine'] in range(22)
                assert all(math.isfinite(x) for x in c['parcel_cm'])
    assert all(p > 0 and p == int(p) for p in owners)
    assert len(owners) == len(set(owners)), 'Duplicate global parcel ownership'
    assert len(owners) == value['central_in_transit'] + value['active'] + value['queued'] + value['occupancy']

    workers = value['skeletal_workers']
    assert len(workers) == 28 and sum(w['visible'] for w in workers) in (6, 7)
    for w in workers:
        assert w['ready'] and w['bone_count'] == 89
        assert w['mesh'].endswith('SKM_Manny_Simple.SKM_Manny_Simple')
        if w['visible']:
            assert max(w['left_error_cm'], w['right_error_cm']) < .25, ('Hand IK', w['index'])
            assert w['limb_length_error_cm'] < .03
            assert -.1 < min(w['left_sole'][2], w['right_sole'][2]) < 1.0
        if w['index'] >= 22:
            assert w['visible']
            assert math.dist(w['transform']['translation_cm'], FEET[w['index'] - 22]) < .02
    return value


def bind(value):
    counts = Counter()
    by_mesh = {v.canonical_mesh(c.get_editor_property('static_mesh').get_path_name()): c
               for name, c in v.components.items() if name.startswith('RuntimeCart_')}
    for mi, m in enumerate(value['machines']):
        for c in m['carts']:
            mesh = v.canonical_mesh(c['mesh'])
            assert mesh in by_mesh
            cart_instances[(mi, c['index'])] = (by_mesh[mesh], counts[mesh])
            counts[mesh] += 1
    assert sum(counts.values()) == 96
    for key in ('CentralMovingColumns', 'CentralLiftTrays', 'CentralParcels'):
        assert v.components[key].get_instance_count() == 60
    assert sum(v.components[n].get_instance_count() for n in
               ('CentralFrameMetal', 'CentralFrameWhite', 'CentralFrameBlue', 'CentralBelts')) < 3000
    v.report['instance_pool'] = {n: c.get_instance_count() for n, c in v.components.items()}


def readback(value):
    count, error, offset = 0, 0.0, 0
    for bank in value['distribution_banks']:
        for carrier in bank['carriers']:
            tray = v.instance(v.components['CentralLiftTrays'], offset)
            error = max(error, math.dist(v.xyz(tray.translation), carrier['tray_cm']))
            assert v.visible(tray)
            col = v.instance(v.components['CentralMovingColumns'], offset)
            assert math.dist(v.xyz(col.translation)[:2], carrier['tray_cm'][:2]) < .03
            parcel = v.instance(v.components['CentralParcels'], offset)
            assert v.visible(parcel) == bool(carrier['parcel_id'])
            if carrier['parcel_id']:
                error = max(error, math.dist(v.xyz(parcel.translation), carrier['parcel_cm']))
                count += 1
            offset += 1
    for mi, machine in enumerate(value['machines']):
        for ci, carrier in enumerate(machine['carriers']):
            tray = v.instance(v.components['LiftTrays'], mi * 4 + ci)
            error = max(error, math.dist(v.xyz(tray.translation), carrier['tray_world_cm']))
            parcel = v.instance(v.components['MovingParcels'], mi * 4 + ci)
            assert v.visible(parcel) == bool(carrier['parcel_id'])
            if carrier['parcel_id']:
                error = max(error, math.dist(v.xyz(parcel.translation), carrier['parcel_world_cm']))
        for cart in machine['carts']:
            component, slot = cart_instances[(mi, cart['index'])]
            rendered = v.instance(component, slot)
            assert v.visible(rendered) == cart['visible']
            error = max(error, math.dist(v.xyz(rendered.translation), cart['world_transform']['translation_cm']))
    assert error < .04, ('Render/report mismatch cm', error)
    return dict(central_trays=60, central_visible_packages=count, machine_carriers=88, carts=96, max_position_error_cm=error)


def summary(value):
    return dict(totals={k: value[k] for k in TOTALS},
                central={k: value[k] for k in ('central_generated', 'central_delivered', 'central_in_transit')},
                sim_time=value['machines'][0]['sim_time'],
                central_phases=dict(Counter(str(c['state']) for b in value['distribution_banks'] for c in b['carriers'])))


def save_stage(name, value):
    path = v.OUT / 'states' / (name + '.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(v.encode_report(value), encoding='utf8')
    return str(path)


def focus_view(name, pivot, distance, pitch, yaw, fov=60, machine_index=0):
    global current_view
    assert isinstance(v.pawn, v.u.GHSWarehouseCameraPawn)
    assert isinstance(v.pc, v.u.GHSWarehousePlayerController)
    v.sim.focus_machine(machine_index)
    yield from v.wait('open_roof_shared_ghs_camera', lambda: v.roof.is_interior_available()
                      and not v.pawn.is_pose_transition_active(), 25)
    cameras = v.pawn.get_components_by_class(v.u.CameraComponent)
    assert len(cameras) == 1, 'Shared warehouse pawn must have one camera component'
    cameras[0].set_field_of_view(fov)
    v.pawn.focus_on_target(v.u.Vector(*pivot), distance, v.u.Rotator(pitch=pitch, yaw=yaw),
                          v.u.Vector2D(1920, 1080), v.u.Vector2D(1115, 565), 0)
    yield from v.pause(.4)
    v.pawn.freeze_current_pose()
    v.fixed_camera = v.camera()
    current_view = name
    v.report['fixed_views'].append(dict(name=name, pivot=pivot, distance=distance,
                                       pitch=pitch, yaw=yaw, fov_deg=fov, camera=v.fixed_camera[:]))
    v.write()


def capture(name, value):
    checked = readback(verify_state(value))
    assert v.same_pose(v.fixed_camera, v.camera())
    yield
    yield
    path = v.OUT / 'images' / (name + '.png')
    path.parent.mkdir(parents=True, exist_ok=True)
    v.console('Shot showui filename="' + path.as_posix() + '" -nosuffix')
    yield from v.wait('capture_' + name, lambda: v.timing.png_ready(path), 12, log=False)
    assert v.same_pose(v.fixed_camera, v.camera())
    # Read PNG IHDR rather than treating existence alone as resolution proof.
    assert struct.unpack('>II', path.read_bytes()[16:24]) == (1920, 1080)
    v.report['captures'].append(dict(name=name, view=current_view, path=str(path),
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(), camera=v.fixed_camera[:],
        readback=checked, state_file=save_stage(name, value), **summary(value)))
    v.write()


def controls():
    v.sim.reset_simulation()
    initial = verify_state(v.state())
    assert not initial['playing'] and initial['rate'] == 1
    assert initial['central_generated'] == 0 and all(initial[k] == 0 for k in TOTALS)
    v.sim.set_simulation_playing(True)
    moving = v.step(32)
    assert moving['central_generated'] > 0
    v.sim.set_simulation_playing(False)
    paused = v.state()
    transforms = v.all_render_transforms()
    assert v.equivalent(paused, v.step(80)), 'Paused logical state advanced'
    v.sim.set_automatic_advance_for_diagnostics(True)
    yield from v.pause(.3)
    v.sim.set_automatic_advance_for_diagnostics(False)
    assert v.equivalent(paused, v.state())
    assert v.equivalent(transforms, v.all_render_transforms()), 'Paused poses changed'
    v.record('pause_freezes_central_and_machine_states_and_actual_render_poses')
    for rate in (1, 2, 4):
        v.sim.reset_simulation()
        v.sim.set_simulation_playing(True)
        v.sim.set_simulation_rate(rate)
        current = v.step(32 / rate)
        assert v.equivalent(moving['machines'], current['machines'])
        assert v.equivalent(moving['distribution_banks'], current['distribution_banks'])
        yield
    before = v.state()
    assert not v.sim.advance_simulation_for_diagnostics(-1)
    assert v.equivalent(before, v.state())
    v.sim.reset_simulation()
    assert v.equivalent(initial['machines'], v.state()['machines'])
    assert v.equivalent(initial['distribution_banks'], v.state()['distribution_banks'])
    v.record('rates_1_2_4_match_and_reset_clears_shared_global_id_space')


def feed_sequence(group, pivot, yaw):
    """One explicit 16-second, 8-fps simulation segment; no wall-clock speedup."""
    yield from focus_view('feed_sequence_' + group, pivot, 1100, -30, yaw, fov=25)
    v.sim.set_automatic_advance_for_diagnostics(False)
    v.sim.reset_simulation()
    v.sim.set_simulation_playing(True)
    value = verify_state(v.state())
    assert value['rate'] == 1
    start_frame = len(v.report['infeed_sequence'])
    folder = v.OUT / 'infeed_sequence'
    folder.mkdir(parents=True, exist_ok=True)
    v.report['sequence_segments'].append(dict(name=group, kind='central_feed',
        first_frame=start_frame, frame_count=128, simulation_fps=8,
        duration_seconds=16, starts_after_reset=True, view=current_view,
        camera=v.fixed_camera[:], fov_deg=25,
        sampling='Diagnostic delta 0.125 seconds at rate 1; engine fixed-step accumulator is 0.05 seconds.'))
    for local_frame in range(128):
        if local_frame:
            value = v.step(1 / 8)
        checked = readback(value)
        assert v.same_pose(v.fixed_camera, v.camera())
        yield
        yield
        frame = start_frame + local_frame
        path = folder / f'{frame:04d}.png'
        v.console('Shot showui filename="' + path.as_posix() + '" -nosuffix')
        yield from v.wait('central_sequence_' + str(frame), lambda: v.timing.png_ready(path), 12, log=False)
        data = path.read_bytes()
        assert struct.unpack('>II', data[16:24]) == (1920, 1080)
        assert v.same_pose(v.fixed_camera, v.camera())
        v.report['infeed_sequence'].append(dict(frame=frame, segment=group,
            local_frame=local_frame, simulation_fps=8, presentation_seconds=local_frame / 8,
            view=current_view, camera=v.fixed_camera[:], path=str(path),
            sha256=hashlib.sha256(data).hexdigest(), readback=checked,
            operators=[{k: w[k] for k in ('index', 'visible', 'left_palm', 'right_palm')}
                       for w in value['skeletal_workers'] if w['index'] >= 22],
            central_carriers=[{k: c[k] for k in ('state', 'parcel_id', 'distance01', 'progress', 'tray_cm')}
                              for c in value['distribution_banks'][0]['carriers']],
            **summary(value)))
        if local_frame % 8 == 0:
            v.write()
    # Complete the final interval so each segment advances exactly 16 seconds.
    value = v.step(1 / 8)
    assert abs(value['machines'][0]['sim_time'] - 16) < 1.e-5
    v.record('fixed_camera_feed_sequence_' + group, frames=128, simulation_fps=8,
             duration_seconds=16, first_frame=start_frame,
             state_file=save_stage('feed_sequence_' + group + '_end', value))


def exchange_cycle(profile):
    assert profile in ('cad64', 'cad120')
    v.sim.reset_simulation()
    v.sim.set_automatic_collection(False)
    v.sim.set_simulation_playing(True)
    current = verify_state(v.state())
    # Large steps only while automatic exchange is disabled: no full-cart
    # handoff/arrival/docking event can be silently skipped in this search.
    waiting = []
    for attempt in range(400):
        current = v.step(50)
        yield
        waiting = [(mi, ci) for mi, m in enumerate(current['machines']) if m['profile'] == profile
                   for ci, c in enumerate(m['carts']) if c['state_code'] == 1]
        if waiting:
            break
    assert waiting, profile + ': no whole cart reached FullWaiting within 20000 simulation seconds'
    assert current['exchanged_carts'] == 0
    mi, ci = waiting[0]
    stopped = current['machines'][mi]['spawned']
    current = v.step(10)
    assert current['machines'][mi]['spawned'] == stopped, 'Full target accepted external parcel'
    assert current['machines'][mi]['carts'][ci]['state_code'] == 1
    t = v.LAYOUT['machines'][mi]['world_transform']['translation_cm']
    yield from focus_view('cart_exchange_' + profile, [t[0], t[1], 110], 1700, -36, -65,
                          fov=30, machine_index=mi)
    current = verify_state(v.state())
    yield from capture(profile + '_cart_full_waiting', current)
    v.record(profile + '_whole_cart_full_waits_and_external_infeed_backpressures',
             profile=profile, machine=mi, cart=ci,
             state_file=save_stage(profile + '_full_waiting', current))
    # Request only this selected machine through the production control. Other
    # profiles remain in FullWaiting, so they cannot steal this acceptance run.
    # The entire withdrawal/handoff/empty arrival/docking sequence is automatic
    # after this request; no occupancy or physical pose is injected by the test.
    v.sim.clear_full_bins()
    active = []
    for attempt in range(240):
        current = v.step(.5)
        yield
        active = [(a, b) for a, m in enumerate(current['machines']) if a == mi and m['profile'] == profile
                  for b, c in enumerate(m['carts']) if c['state_code'] >= 2]
        if active:
            break
    assert active, profile + ': requested full cart failed to enter exchange'
    mi, ci = active[0]
    first = current['machines'][mi]['carts'][ci]
    original_ids = sorted(first['parcel_ids'])
    generation, original_cart = first['generation'], first['physical_cart_id']
    seen, transitions = set(), []
    previous_code = None
    completion_before = current['machines'][mi]['exchanged_carts']
    for attempt in range(500):
        cart = current['machines'][mi]['carts'][ci]
        code = cart['state_code']
        if code != previous_code:
            transitions.append(dict(state_code=code, sim_time=current['machines'][mi]['sim_time'],
                generation=cart['generation'], occupancy=cart['occupancy'], collected=cart['collected'],
                physical_cart_id=cart['physical_cart_id']))
            seen.add(code)
            yield from capture(profile + '_cart_phase_' + str(code), current)
            previous_code = code
        if code in (2, 3, 6):
            assert cart['generation'] == generation and cart['physical_cart_id'] == original_cart
            assert sorted(cart['parcel_ids']) == original_ids
        if code in (4, 5):
            assert cart['generation'] == generation + 1 and cart['physical_cart_id'] != original_cart
            assert cart['occupancy'] == 0 and sorted(cart['last_outbound_parcel_ids']) == original_ids
        if code == 6:
            assert not cart['visible']
        if code == 0 and current['machines'][mi]['exchanged_carts'] > completion_before:
            break
        current = v.step(.5)
        yield
    assert {0, 2, 3, 4, 5, 6}.issubset(seen), ('Missing whole-cart exchange phase', seen)
    done = current['machines'][mi]
    for attempt in range(120):
        current = v.step(10)
        yield
        later = current['machines'][mi]
        if later['spawned'] > done['spawned'] and later['completed'] > done['completed']:
            break
    assert later['spawned'] > done['spawned'] and later['completed'] > done['completed'], 'No receiving recovery after empty-cart docking'
    assert all(m['exchanged_carts'] == 0 for index, m in enumerate(current['machines']) if index != mi)
    v.record(profile + '_full_outbound_handoff_empty_arrival_docking_and_receiving_recovery',
        profile=profile, machine=mi, cart=ci, exchange_trigger='selected_machine_request_then_automatic_cycle',
        source_full_parcel_ids=original_ids, transitions=transitions,
        state_file=save_stage(profile + '_receiving_resumed', current))


def performance():
    v.sim.set_automatic_advance_for_diagnostics(False)
    v.sim.reset_simulation()
    v.sim.set_automatic_collection(True)
    v.sim.set_simulation_playing(True)
    for attempt in range(30):
        precondition = v.step(30)
        yield
        if precondition['completed'] > 5 and precondition['central_delivered'] > 10:
            break
    assert precondition['completed'] > 5
    v.sim.set_automatic_advance_for_diagnostics(True)
    yield from v.pause(3, True)
    before = verify_state(v.state())
    filename = 'MPR_CENTRAL_' + v.report['run_id'] + '.csv'
    path = v.ROOT / 'Saved/Profiling/CSV' / filename
    v.console('CsvProfile STARTFILE=' + filename)
    v.console('CsvProfile START')
    reads = v.report_reads
    start = time.monotonic()
    # No JSON polls, captures, ISM enumeration or diagnostic steps during sample.
    yield from v.pause(15, True)
    sample_wall = time.monotonic() - start
    v.console('CsvProfile STOP')
    assert reads == v.report_reads
    v.sim.set_automatic_advance_for_diagnostics(False)
    after = verify_state(v.state())
    yield from v.wait('native_csv_flush', lambda: v.timing.csv_complete(path), 15)
    native = v.timing.parse_csv(path)
    native['fps'] = native['frame_count'] / native['native_frame_time_seconds']
    assert after['machines'][0]['sim_time'] - before['machines'][0]['sim_time'] > 10
    v.report['performance'] = dict(native_csv=native, sampled_wall_seconds=sample_wall,
        camera=v.fixed_camera[:], actor_auto_tick=True, manual_steps=0, report_reads_during_sample=0,
        resolution=[1920, 1080], hud_visible=True, before=summary(before), after=summary(after),
        scope='One local native offscreen game: 22 machines, 96 carts, 60 central carriers, 28 worker slots (six feeding, up to one exchanging), HUD. Not Pixel Streaming or measured vendor throughput.')
    v.record('native_tick_15_second_csv_without_json_polling', fps=native['fps'])


def run():
    capture_sequence = bool(re.search(r'(?:^|\s)-MPRCentralCaptureSequence(?=\s|$)',
                                      v.u.SystemLibrary.get_command_line(), re.I))
    v.report.update(scope='Central automatic distribution and CAD six-person feeding; native production API and render-instance readback.',
        capture_sequence=capture_sequence,
        cad_sha256=hashlib.sha256(CAD_FILE.read_bytes()).hexdigest(),
        limitations=['Mechanical timing is configurable demonstration data, not vendor PLC measurements.',
                     'Screenshots still require visual review; no OS mouse delivery or Pixel Streaming claim.'])
    yield from v.wait('discover_mpr_central_distribution', v.discover, 40)
    yield from v.wait('viewport_1920x1080', lambda: list(v.pc.get_viewport_size()) == [1920, 1080], 10)
    for command in ('DisableAllScreenMessages', 't.MaxFPS 0', 'r.VSync 0', 't.IdleWhenNotForeground 0',
                    'Slate.bAllowThrottling 0', 'csv.CompressionMode 0', 'r.GPUCsvStatsEnabled 1'):
        v.console(command)
    v.sim.set_automatic_advance_for_diagnostics(False)
    v.sim.set_panel_visible(True)
    value = verify_state(v.state())
    bind(value)
    v.report['actor_count_before'] = len(v.u.GameplayStatics.get_all_actors_of_class(v.world, v.u.Actor))
    v.report['engine_version'] = v.u.SystemLibrary.get_engine_version()
    v.report['camera_class'] = v.pawn.get_class().get_path_name()
    v.record('two_banks_six_cad_operators_60_carriers_22_connected_machines', readback=readback(value))
    yield from controls()
    yield from focus_view('central_overview', [-10434, 1300, 120], 4800, -62, -105)
    v.sim.reset_simulation()
    v.sim.set_simulation_playing(True)
    for seconds in (0, 30, 90):
        value = v.step(seconds)
        yield from capture('overview_t' + str(round(value['machines'][0]['sim_time'])), value)
    yield from focus_view('six_person_feed_close', [-10490, -160, 135], 1100, -30, -135, fov=25)
    v.sim.reset_simulation()
    v.sim.set_simulation_playing(True)
    for seconds in (4, 12, 20):
        value = v.step(seconds)
        yield from capture('feed_t' + str(round(value['machines'][0]['sim_time'])), value)
    if capture_sequence:
        yield from feed_sequence('end_a_three_operators', [-10490, -160, 135], -135)
        yield from feed_sequence('end_b_three_operators', [-10375, 2760, 135], 45)
    yield from exchange_cycle('cad64')
    yield from exchange_cycle('cad120')
    yield from focus_view('performance_overview', [-10434, 1300, 120], 4800, -62, -105)
    yield from performance()
    assert len(v.u.GameplayStatics.get_all_actors_of_class(v.world, v.u.Actor)) == v.report['actor_count_before']
    assert v.report['instance_pool'] == {n: c.get_instance_count() for n, c in v.components.items()}
    for view in v.report['fixed_views']:
        rows = [r for r in v.report['captures'] + v.report['infeed_sequence'] if r['view'] == view['name']]
        assert all(v.same_pose(view['camera'], r['camera']) for r in rows)
    assert len(v.report['infeed_sequence']) == (256 if capture_sequence else 0)
    assert {0, 1, 2, 3, 5}.issubset(central_phases), ('Unobserved normal central phase', central_phases)
    v.record('global_id_conservation_bounded_instance_pools_fixed_views', central_phases=sorted(central_phases))
    v.report.update(success=True, stage='complete')


v.BASE = v.ROOT / 'Saved/MPR/central_distribution_20261109/runtime'
v.DEADLINE_SECONDS = 900
v.verify_state = verify_state
v.run = run

if __name__ == '__main__':
    v.main()
