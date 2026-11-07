"""Schema-2 native MPR acceptance; readback only, never saves the map/assets.

Run an owned process with -own -game -RenderOffscreen -TwinDiagnostics
-EnablePython -ForceRes -ResX=1920 -ResY=1080 and
-ExecCmds="py D:/UEPro/Test/Tools/MPRWarehouse/verify_mpr_full_sorter_runtime.py".
-MPRFullWorkflowCaptureSequence adds two separate 6-fps sequences: the first
32 seconds after reset (192 frames), and 22 seconds from full-cart withdrawal
(132 frames). The gap between these segments is fast-forwarded, not recorded.
The full/wait states are separate fixed-camera images. The second profile is
viewed from the opposite side.

This checks production APIs and actual ISM readback, not OS input delivery,
vendor PLC timing, real orders, or operator-route engineering approval.
"""
from collections import Counter
from datetime import datetime, timezone
import faulthandler
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
LAYOUT_FILE = ROOT / 'SourceAssets/MPR/sorter_simulation/layout.json'
LAYOUT = json.loads(LAYOUT_FILE.read_text(encoding='utf8'))
MAP = '/Game/Maps/MPR_CAD_Warehouse_B50B57'
MAP_FILE = ROOT / 'Content/Maps/MPR_CAD_Warehouse_B50B57.umap'
BASE = ROOT / 'Saved/MPR/full_workflow_20261107/runtime'
PACKAGE_CM = (22., 16., 5.)  # Actor package contract; three fit below the bin rim.
DEADLINE_SECONDS = 360
TOTAL_FIELDS = ('spawned', 'completed', 'collected', 'active', 'queued', 'occupancy', 'exchanged_carts')
u = timing = world = pc = pawn = roof = sim = callback = None
components = {}
cart_instances = {}
bin_offsets = []
report = {}
fixed_camera = None
done = busy = False
report_reads = 0
report_bytes = 0
START = 0.
OUT = None
ASSETS = []
HASHES = {}
SEQUENCE = False
steps = None
FAULT_LOG = None  # Keep the file alive while faulthandler's native handler owns its fd.


def fault_note(event, detail=''):
    if FAULT_LOG is not None:
        FAULT_LOG.write(f'{time.monotonic()-START:.6f} {event} {detail}\n')
        FAULT_LOG.flush()


def encode_report(value):
    # indent=None selects CPython's C encoder. Pretty printing selects nested
    # Python _iterencode generators; the native crash stack entered FOR_ITER
    # with a closure cell instead of an iterator. Keep semantics/cycle checks,
    # and instrument this boundary instead of attributing it to stack depth.
    assert json.encoder.c_make_encoder is not None, 'Native C JSON encoder is unavailable'
    return json.dumps(value, ensure_ascii=False, indent=None, separators=(',', ':'),
                      check_circular=True, allow_nan=False)+'\n'


def equivalent(a, b, tolerance=1.e-5):
    if isinstance(a, dict):
        return isinstance(b, dict) and a.keys() == b.keys() and all(equivalent(a[k], b[k], tolerance) for k in a)
    if isinstance(a, (list, tuple)):
        return isinstance(b, (list, tuple)) and len(a) == len(b) and all(equivalent(x, y, tolerance) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and not isinstance(a, bool):
        return isinstance(b, (int, float)) and math.isfinite(a) and math.isfinite(b) and abs(a-b) <= tolerance
    return a == b


def xyz(value):
    return [float(value.x), float(value.y), float(value.z)]


def canonical_mesh(path):
    return path.split('.', 1)[0]


def world_point(machine_index, local):
    """Independent quaternion transformation of CAD/profile coordinates."""
    t = LAYOUT['machines'][machine_index]['world_transform']
    qx, qy, qz, qw = t['rotation_xyzw']
    x, y, z = [local[i]*t['scale'][i] for i in range(3)]
    tx, ty, tz = 2*(qy*z-qz*y), 2*(qz*x-qx*z), 2*(qx*y-qy*x)
    rotated = (x+qw*tx+qy*tz-qz*ty, y+qw*ty+qz*tx-qx*tz, z+qw*tz+qx*ty-qy*tx)
    return [rotated[i]+t['translation_cm'][i] for i in range(3)]


def verify_state(value):
    assert value['ready'] and value['schema_version'] == 2 and value['data_mode'] == 'demonstration', value.get('error')
    assert value['machine_count'] == len(value['machines']) == 22
    assert value['cart_count'] == 96
    assert value['tower_instances'] == value['tray_instances'] == value['parcel_instances'] == 88
    assert value['infeed_instances'] == 66 and value['worker_slots'] == 44
    assert value['bin_parcel_instances'] == 1632*3
    assert value['conserved'] and value['unique_parcel_ownership'] and value['shared_aisle_mutex_valid']
    assert value['spawned'] == value['completed']+value['active']+value['queued']
    assert value['completed'] == value['collected']+value['occupancy']
    assert [m['id'] for m in value['machines']] == [m['id'] for m in LAYOUT['machines']]
    active_carts = []
    physical_cart_ids = []
    waiting = 0
    for mi, machine in enumerate(value['machines']):
        p = LAYOUT['profiles'][machine['profile']]
        assert len(machine['carriers']) == 4 and len(machine['carts']) == len(p['carts'])
        assert len(machine['infeed']) == machine['queued'] <= 3
        carrier_ids = [c['parcel_id'] for c in machine['carriers'] if c['parcel_id']]
        queue_ids = [c['parcel_id'] for c in machine['infeed']]
        cell_ids = [pid for cell in machine['cells'] for pid in cell['parcel_ids']]
        owned = carrier_ids+queue_ids+cell_ids
        assert all(pid > 0 and pid == int(pid) for pid in owned)
        assert len(owned) == len(set(owned)), ('Duplicate parcel ownership', mi)
        assert len(carrier_ids) == machine['active'] and len(cell_ids) == machine['occupancy']
        assert machine['spawned'] == machine['completed']+machine['active']+machine['queued']
        assert machine['completed'] == machine['collected']+machine['occupancy']
        assert sum(c['occupancy'] for c in machine['carts']) == machine['occupancy']
        assert len({(c['side'], c['column'], c['level']) for c in machine['cells']}) == len(machine['cells'])
        for cell in machine['cells']:
            assert len(cell['parcel_ids']) == cell['occupancy']
            # Multiple carriers may reserve this same destination before its
            # first delivery. The invariant is total reserved + occupied <= 3.
            assert 0 <= cell['occupancy'] <= 3 and 0 <= cell['reserved'] <= 3
            assert cell['occupancy']+cell['reserved'] <= 3
        for ci, cart in enumerate(machine['carts']):
            assert cart['index'] == ci and cart['generation'] >= 1
            assert cart['state_code'] in (0, 1, 2, 3, 4, 5, 6)
            assert bool(cart['visible']) == (cart['state_code'] != 6)
            assert isinstance(cart['physical_cart_id'], str) and cart['physical_cart_id']
            physical_cart_ids.append(cart['physical_cart_id'])
            assert cart['capacity'] == cart['column_count']*4*3
            children = [c for c in machine['cells'] if c['cart_index'] == ci]
            assert sorted(cart['parcel_ids']) == sorted(pid for c in children for pid in c['parcel_ids'])
            assert cart['occupancy'] == len(cart['parcel_ids']) <= cart['capacity']
            assert cart['reserved'] == sum(c['reserved'] for c in children)
            assert 0 <= cart['progress01'] <= 1
            if cart['state_code'] == 1:
                waiting += 1
            if cart['state_code'] in (1, 2, 3, 6):
                assert cart['occupancy'] == cart['capacity'] and cart['reserved'] == 0
            if cart['state_code'] in (4, 5):
                assert cart['occupancy'] == cart['reserved'] == 0
            if cart['state_code'] >= 2:
                active_carts.append((mi, ci))
                assert machine['active'] == 0, ('Moving cart before carrier drain', mi, ci)
        for ci, carrier in enumerate(machine['carriers']):
            for key in ('distance01', 'lift_cm', 'scan_progress', 'induct_progress', 'unload_progress'):
                assert math.isfinite(carrier[key]), (mi, ci, key)
            assert 0 <= carrier['distance01'] < 1
            for key in ('scan_progress', 'induct_progress', 'unload_progress'):
                assert 0 <= carrier[key] <= 1
            offset = (carrier['distance01']-machine['carriers'][0]['distance01']) % 1
            assert abs(offset-ci*.25) < 1.e-6
            if carrier['parcel_id']:
                cart = machine['carts'][carrier['target_cart']]
                assert cart['state_code'] == 0 and cart['generation'] == carrier['target_cart_generation']
    assert len(active_carts) == value['active_exchange_count'] <= 1
    assert len(physical_cart_ids) == len(set(physical_cart_ids)) == 96
    assert waiting == value['waiting_exchange_count']
    if active_carts:
        assert value['exchange_owner_machine'] == active_carts[0][0]
    for key in TOTAL_FIELDS:
        assert value[key] == sum(m[key] for m in value['machines']), ('Fleet total mismatch', key)
    return value


def compact(value, machine_index):
    """Store only the selected machine; no full-fleet per-frame report files."""
    m = value['machines'][machine_index]
    return dict(machine_id=m['id'], machine_index=machine_index, profile=m['profile'], sim_time=m['sim_time'],
                phase=m['phase'], block_reason=m['block_reason'], chain_stopped=m['chain_stopped'],
                totals={k: value[k] for k in TOTAL_FIELDS}, machine_totals={k: m[k] for k in TOTAL_FIELDS},
                infeed=m['infeed'], carriers=m['carriers'], carts=m['carts'],
                active_exchange_count=value['active_exchange_count'], exchange_owner_machine=value['exchange_owner_machine'])


def write():
    report.update(elapsed_wall_seconds=time.monotonic()-START, report_reads=report_reads, report_bytes=report_bytes)
    fault_note('report_encode_begin', f'captures={len(report["captures"])} infeed={len(report["infeed_sequence"])} exchange={len(report["sequence"])}')
    payload = encode_report(report)
    fault_note('report_encode_end', f'characters={len(payload)}')
    (OUT / 'report.json').write_text(payload, encoding='utf8')
    (BASE / 'report.json').write_text(payload, encoding='utf8')
    fault_note('report_write_end')


def record(name, **data):
    report['checks'].append(dict(name=name, passed=True, **data))
    write()


def deadline():
    assert time.monotonic()-START < DEADLINE_SECONDS, f'Native acceptance exceeded {DEADLINE_SECONDS}-second wall budget'


def state():
    global report_reads, report_bytes
    raw = sim.get_simulation_report_json()
    report_reads += 1
    report_bytes += len(raw)
    return json.loads(raw)


def step(seconds):
    deadline()
    assert sim.advance_simulation_for_diagnostics(seconds), ('Diagnostic step rejected', seconds)
    return verify_state(state())


def console(command):
    u.SystemLibrary.execute_console_command(world, command, pc)


def camera():
    manager = pc.player_camera_manager
    rotation = manager.get_camera_rotation()
    return xyz(manager.get_camera_location())+[rotation.pitch, rotation.yaw, rotation.roll]


def same_pose(a, b):
    return a is not None and b is not None and equivalent(a, b, .05)


def pause(seconds, hold_camera=False):
    end = time.monotonic()+seconds
    while time.monotonic() < end:
        deadline()
        if hold_camera:
            assert same_pose(fixed_camera, camera()), 'Fixed camera moved'
        yield


def wait(name, predicate, seconds=15, log=True):
    if log:
        report['stage'] = name
        write()
    end = time.monotonic()+seconds
    while not predicate():
        deadline()
        assert time.monotonic() < end, 'Timed out: '+name
        yield


def discover():
    global world, pc, pawn, roof, sim, components
    for candidate in u.ObjectIterator(u.World):
        if not candidate.get_path_name().startswith(MAP+'.'):
            continue
        controller = u.GameplayStatics.get_player_controller(candidate, 0)
        if not controller or not controller.get_editor_property('twin_hud_widget'):
            continue
        actors = list(u.GameplayStatics.get_all_actors_of_class(candidate, u.MPRSorterSimulationActor))
        if len(actors) != 1:
            continue
        world, pc, sim = candidate, controller, actors[0]
        pawn, roof = pc.get_controlled_pawn(), pc.warehouse_roof
        components = {c.get_name(): c for c in sim.get_components_by_class(u.InstancedStaticMeshComponent)}
        value = state()
        if value['error']:
            raise AssertionError(value['error'])
        return bool(value['ready'] and value['panel_attached'] and pawn and roof and roof.has_roof())
    return False


def bind_instances(value):
    counts = Counter()
    by_mesh = {}
    for name, component in components.items():
        if name.startswith('RuntimeCart_'):
            mesh = canonical_mesh(component.get_editor_property('static_mesh').get_path_name())
            assert mesh not in by_mesh, ('Duplicate runtime cart component', mesh)
            by_mesh[mesh] = component
    offset = 0
    for mi, machine in enumerate(value['machines']):
        bin_offsets.append(offset)
        offset += LAYOUT['profiles'][machine['profile']]['modeled_capacity']
        for cart in machine['carts']:
            mesh = canonical_mesh(cart['mesh'])
            assert mesh in by_mesh, ('Missing cooked cart mesh component', mesh)
            cart_instances[(mi, cart['index'])] = (by_mesh[mesh], counts[mesh])
            counts[mesh] += 1
    assert sum(counts.values()) == 96 and len(by_mesh) == 10
    assert value['components'] == len(components) == 11+len(by_mesh)
    assert all(by_mesh[mesh].get_instance_count() == count for mesh, count in counts.items())
    assert components['ActiveCells'].get_instance_count() == components['FullCells'].get_instance_count() == 1632
    report['instance_pool'] = {name: c.get_instance_count() for name, c in components.items()}


def transform_values(transform):
    q = transform.rotation
    return xyz(transform.translation)+[q.x, q.y, q.z, q.w]+xyz(transform.scale3d)


def all_render_transforms():
    return {name: [transform_values(c.get_instance_transform(i, world_space=True))
                   for i in range(c.get_instance_count())] for name, c in components.items()}


def instance(component, index):
    transform = component.get_instance_transform(index, world_space=True)
    assert transform is not None, ('Missing instance', component.get_name(), index)
    return transform


def visible(transform):
    return max(abs(x) for x in xyz(transform.scale3d)) > 1.e-6


def verify_rendered(value, machine_indices):
    cart_checked = box_checked = carrier_checked = hands_checked = queue_checked = 0
    hidden_loaded_boxes = hidden_carts = hidden_exchange_worker_slots = 0
    max_error = 0.
    for mi in machine_indices:
        machine = value['machines'][mi]
        profile = LAYOUT['profiles'][machine['profile']]
        for ci, carrier in enumerate(machine['carriers']):
            slot = mi*4+ci
            tray = instance(components['LiftTrays'], slot)
            assert math.dist(xyz(tray.translation), carrier['tray_world_cm']) < .03
            package = instance(components['MovingParcels'], slot)
            assert visible(package) == bool(carrier['parcel_id'])
            if carrier['parcel_id']:
                assert math.dist(xyz(package.translation), carrier['parcel_world_cm']) < .03
                if carrier['state_code'] == 5:
                    hands = [xyz(instance(components['OperatorSkin'], mi*6+j).translation) for j in (1, 2)]
                    midpoint = [(hands[0][a]+hands[1][a])/2 for a in range(3)]
                    parcel = carrier['parcel_world_cm']
                    assert abs(math.dist(hands[0], hands[1])-PACKAGE_CM[0]*1.1) < .05
                    assert math.dist(midpoint, [parcel[0], parcel[1], parcel[2]-2]) < .05
                    hands_checked += 1
            carrier_checked += 1
        for qi in range(3):
            package = instance(components['InfeedParcels'], mi*3+qi)
            assert visible(package) == (qi < len(machine['infeed']))
            if qi < len(machine['infeed']):
                assert math.dist(xyz(package.translation), machine['infeed'][qi]['world_cm']) < .03
            queue_checked += 1
        for cart in machine['carts']:
            component, slot = cart_instances[(mi, cart['index'])]
            actual = instance(component, slot)
            expected = cart['render_world_transform']
            error = math.dist(xyz(actual.translation), expected['translation_cm'])
            max_error = max(max_error, error)
            assert visible(actual) == cart['visible'] and error < .03, ('Cart transform/visibility mismatch', mi, cart['index'], error)
            q = actual.rotation
            qvalues = [q.x, q.y, q.z, q.w]
            assert min(math.dist(qvalues, expected['rotation_xyzw']), math.dist(qvalues, [-x for x in expected['rotation_xyzw']])) < 1.e-5
            assert equivalent(xyz(actual.scale3d), expected['scale'])
            if cart['state_code'] == 6:
                hidden_carts += 1
                assert not visible(actual) and equivalent(expected['scale'], [0, 0, 0])
                assert math.dist(expected['translation_cm'], cart['world_transform']['translation_cm']) < .03
                # The second operator belongs to cart exchange. The first
                # infeed operator must remain present during the handoff dwell.
                worker = mi*2+1
                for name, slots in (('OperatorClothing', 10), ('OperatorSkin', 3),
                                    ('OperatorBoots', 2), ('OperatorHelmets', 1)):
                    for wi in range(slots):
                        assert not visible(instance(components[name], worker*slots+wi)), ('Exchange worker visible during handoff', mi, name, wi)
                        hidden_exchange_worker_slots += 1
                assert visible(instance(components['OperatorHelmets'], mi*2)), 'Infeed operator hidden during cart handoff'
            cart_checked += 1
        cells = {(c['side'], c['column'], c['level']): c for c in machine['cells']}
        for source in profile['bins']:
            key = (source['side'], source['column'], source['level'])
            count = cells.get(key, {}).get('occupancy', 0)
            local_index = (source['side']*profile['modeled_columns']+source['column'])*4+source['level']
            offset = machine['carts'][source['cart_index']]['local_offset_cm']
            handing_off = machine['carts'][source['cart_index']]['state_code'] == 6
            for pi in range(3):
                package = instance(components['CollectedParcels'], (bin_offsets[mi]+local_index)*3+pi)
                assert visible(package) == (pi < count and not handing_off), ('Collected parcel visibility', mi, key, pi)
                if pi < count and handing_off:
                    hidden_loaded_boxes += 1
                elif pi < count:
                    local = [source['bin_drop_cm'][a]+offset[a] for a in range(3)]
                    local[2] += PACKAGE_CM[2]*(pi+.5)+.3
                    expected = world_point(mi, local)
                    error = math.dist(xyz(package.translation), expected)
                    max_error = max(max_error, error)
                    assert error < .03, ('Box did not follow cart', mi, key, pi, error)
                    box_checked += 1
    return dict(carts=cart_checked, visible_boxes=box_checked, carriers=carrier_checked,
                queue_slots=queue_checked, handoffs=hands_checked, hidden_handoff_carts=hidden_carts,
                hidden_handoff_loaded_boxes=hidden_loaded_boxes, hidden_exchange_worker_slots=hidden_exchange_worker_slots,
                max_position_error_cm=max_error)


def trace_parcel(trace, value, mi):
    machine = value['machines'][mi]
    pid = trace['parcel_id']
    item = None
    for p in machine['infeed']:
        if p['parcel_id'] == pid:
            item = dict(stage='queue', state_code=None, world_cm=p['world_cm'])
    for ci, c in enumerate(machine['carriers']):
        if c['parcel_id'] == pid:
            item = dict(stage='carrier', carrier=ci, state_code=c['state_code'], target_cart=c['target_cart'], world_cm=c['parcel_world_cm'])
    for c in machine['cells']:
        if pid in c['parcel_ids']:
            cart = machine['carts'][c['cart_index']]
            item = dict(stage='bin', cart=c['cart_index'], state_code=cart['state_code'], side=c['side'], column=c['column'], level=c['level'])
    for c in machine['carts']:
        if pid in c['last_outbound_parcel_ids']:
            item = dict(stage='cartout', cart=c['index'], state_code=c['state_code'], generation=c['generation'])
    if item is not None:
        signature = (item['stage'], item['state_code'])
        previous = trace['events'][-1] if trace['events'] else None
        if previous is None or (previous['stage'], previous['state_code']) != signature:
            trace['events'].append(dict(sim_time=machine['sim_time'], **item))


def verify_trace(trace):
    stages = [item['stage'] for item in trace['events']]
    for first, second in zip(('queue', 'carrier', 'bin'), ('carrier', 'bin', 'cartout')):
        assert first in stages and second in stages and stages.index(first) < stages.index(second), trace
    carrier_states = {e['state_code'] for e in trace['events'] if e['stage'] == 'carrier'}
    assert {1, 5, 4}.issubset(carrier_states), ('Trace missed recognition, manual induction or unload', trace)


def capture(name, mi, value=None, frame=None, evidence=None, sequence_kind='exchange'):
    value = verify_state(value if value is not None else state())
    fault_note('capture_readback_begin', sequence_kind+'/'+name)
    readback = verify_rendered(value, [mi])
    fault_note('capture_readback_end', sequence_kind+'/'+name)
    assert same_pose(fixed_camera, camera())
    folder = ('infeed_sequence' if sequence_kind == 'infeed' else 'sequence') if frame is not None else 'images'
    path = OUT / folder / (name+'.png')
    path.parent.mkdir(parents=True, exist_ok=True)
    # Two native frames after ISM updates allow render-thread data to settle.
    yield
    yield
    console('Shot showui filename="'+path.as_posix()+'" -nosuffix')
    fault_note('capture_shot_requested', sequence_kind+'/'+name)
    yield from wait('capture_'+name, lambda: timing.png_ready(path), seconds=8, log=False)
    fault_note('capture_png_complete', sequence_kind+'/'+name)
    assert same_pose(fixed_camera, camera()), 'Capture camera changed'
    row = dict(name=name, path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
               camera=fixed_camera[:], readback=readback, **compact(value, mi))
    if evidence is not None:
        row['evidence'] = evidence
    if frame is None:
        report['captures'].append(row)
        write()
    else:
        row.update(frame=frame, simulation_fps=6, segment=sequence_kind)
        report[folder].append(row)
        if frame % 12 == 0:
            write()


def focus(mi, side):
    global fixed_camera
    assert isinstance(pawn, u.GHSWarehouseCameraPawn) and isinstance(pc, u.GHSWarehousePlayerController)
    sim.focus_machine(mi)
    yield from wait('shared_ghs_focus_'+str(mi), lambda: roof.is_interior_available() and not pawn.is_pose_transition_active(), 20)
    profile = LAYOUT['profiles'][LAYOUT['machines'][mi]['profile']]
    t = LAYOUT['machines'][mi]['world_transform']
    qx, qy, qz, qw = t['rotation_xyzw']
    assert abs(qx) < 1.e-6 and abs(qy) < 1.e-6 and equivalent(t['scale'], [1, 1, 1])
    yaw = math.degrees(math.atan2(2*qw*qz, 1-2*qz*qz))+(-65 if side == 0 else 65)
    pivot = world_point(mi, [0, 0, 100])
    spec = dict(pivot=pivot, distance=(profile['track_half_straight_cm']+profile['track_radius_cm'])*4.6,
                pitch=-29, yaw=yaw, viewport=[1920, 1080], screen_position=[1171.2, 572.4])
    pawn.focus_on_target(u.Vector(*pivot), spec['distance'], u.Rotator(pitch=spec['pitch'], yaw=yaw),
                         u.Vector2D(*spec['viewport']), u.Vector2D(*spec['screen_position']), 0)
    yield from pause(.35)
    pawn.freeze_current_pose()
    fixed_camera = camera()
    assert state()['selected_machine'] == mi
    report['fixed_views'].append(dict(machine_index=mi, side=side, spec=spec, camera=fixed_camera[:]))
    write()


def control_tests():
    sim.reset_simulation()
    initial = verify_state(state())
    assert not initial['playing'] and initial['rate'] == 1 and initial['automatic_collection']
    assert all(initial[k] == 0 for k in TOTAL_FIELDS)
    sim.set_simulation_playing(True)
    moving = step(24)
    assert moving['spawned'] > 0 and moving['completed'] > 0
    sim.set_simulation_playing(False)
    paused = state()
    transforms = all_render_transforms()
    assert equivalent(paused, step(80)), 'Paused logical state advanced'
    sim.set_automatic_advance_for_diagnostics(True)
    yield from pause(.3)
    sim.set_automatic_advance_for_diagnostics(False)
    assert equivalent(paused, state()), 'Paused native Tick advanced'
    assert equivalent(transforms, all_render_transforms()), 'Paused ISM render state moved'
    record('pause_freezes_all_machine_queue_cart_worker_and_box_states', rendered_instances=sum(len(v) for v in transforms.values()))
    sim.reset_simulation()
    sim.set_simulation_playing(True)
    one = step(32)
    for rate in (2, 4):
        sim.reset_simulation()
        sim.set_simulation_playing(True)
        sim.set_simulation_rate(rate)
        at_rate = step(32/rate)
        assert at_rate['rate'] == rate and equivalent(one['machines'], at_rate['machines']), ('Rate mismatch', rate)
    record('rates_1_2_4_have_equivalent_32_second_state')
    invalid_before = state()
    assert not sim.advance_simulation_for_diagnostics(-1)
    assert equivalent(invalid_before, state())
    sim.reset_simulation()
    assert equivalent(initial['machines'], state()['machines'])
    verify_rendered(state(), range(22))
    record('reset_restores_paused_empty_generation_one_and_rejects_negative_delta')


def check_exchange_transition(previous, current, mi, cart_index):
    a, b = previous['machines'][mi], current['machines'][mi]
    ca, cb = a['carts'][cart_index], b['carts'][cart_index]
    if ca['state_code'] in (2, 3, 4, 5, 6):
        assert a['active'] == b['active'] == 0 or (ca['state_code'] == 5 and cb['state_code'] == 0)
        assert b['completed'] == a['completed'], 'Deposited while cart missing'
        if cb['state_code'] != 0:
            assert b['spawned'] == a['spawned'] and equivalent(a['infeed'], b['infeed']), 'Feed moved while cart missing'
    if cb['generation'] != ca['generation']:
        assert ca['state_code'] == 6 and cb['state_code'] == 4
        assert cb['generation'] == ca['generation']+1
        assert cb['physical_cart_id'] != ca['physical_cart_id']
    else:
        assert cb['physical_cart_id'] == ca['physical_cart_id']
    if cb['collected'] != ca['collected']:
        assert ca['state_code'] == 6 and cb['state_code'] == 4, 'Cart cargo cleared before handoff completion'
        assert cb['collected']-ca['collected'] == ca['capacity']
        assert sorted(cb['last_outbound_parcel_ids']) == sorted(ca['parcel_ids'])
    if ca['state_code'] == 6 and cb['state_code'] == 6:
        assert cb['occupancy'] == ca['occupancy'] == ca['capacity']
        assert cb['parcel_ids'] == ca['parcel_ids'] and cb['collected'] == ca['collected']
        assert not cb['visible'] and not ca['visible']
    if b['exchanged_carts'] != a['exchanged_carts']:
        assert ca['state_code'] == 5 and cb['state_code'] == 0
        assert b['exchanged_carts'] == a['exchanged_carts']+1
    for other_index, other in enumerate(current['machines']):
        if other_index != mi:
            assert other['exchanged_carts'] == 0
            assert all(c['state_code'] in (0, 1) and c['generation'] == 1 for c in other['carts']), 'Manual exchange affected another machine'


def resumed_receiving(before, after):
    """A label/playing flag is insufficient: new arrivals AND real deposits."""
    return after['completed'] > before['completed'] and after['spawned'] > before['spawned']


def recovery_sample(machine):
    return dict(sim_time=machine['sim_time'], totals={k: machine[k] for k in TOTAL_FIELDS},
                phase=machine['phase'], chain_stopped=machine['chain_stopped'], block_reason=machine['block_reason'],
                queue=[dict(parcel_id=p['parcel_id'], progress01=p['progress01']) for p in machine['infeed']],
                carriers=[{k: c[k] for k in ('parcel_id', 'state_code', 'distance01', 'target_cart',
                                             'target_cart_generation', 'side', 'column', 'level')}
                          for c in machine['carriers']])


def workflow(mi, side, sequence=False):
    sim.reset_simulation()
    sim.set_automatic_collection(False)
    yield from focus(mi, side)
    sim.set_simulation_playing(True)
    profile = LAYOUT['machines'][mi]['profile']
    prefix = f'{profile}_{mi:02d}'
    trace = dict(machine_index=mi, machine_id=LAYOUT['machines'][mi]['id'], parcel_id=1, reset_epoch=prefix, events=[])
    current = step(.1)
    trace_parcel(trace, current, mi)
    assert current['machines'][mi]['infeed'][0]['parcel_id'] == 1
    yield from capture(prefix+'_01_receiving_queue', mi, current)
    if sequence:
        # Record a genuine reset-to-first-delivery passage in the same fixed
        # view. Later fast-forward to full-cart exchange is a separate segment.
        sim.reset_simulation()
        sim.set_automatic_collection(False)
        sim.set_simulation_playing(True)
        current = verify_state(state())
        trace['events'].clear()
        observed_carrier_states = set()
        for frame in range(192):
            machine = current['machines'][mi]
            observed_carrier_states.update(c['state_code'] for c in machine['carriers'] if c['parcel_id'])
            trace_parcel(trace, current, mi)
            yield from capture(f'frame_{frame:04d}', mi, current, frame=frame, sequence_kind='infeed')
            current = step(1/6)
        assert current['machines'][mi]['completed'] > 0, 'No real first deposit in 32-second infeed recording'
        assert {1, 5, 4}.issubset(observed_carrier_states), 'Infeed recording missed recognition, manual handoff, or unload'
        report['sequence_segments'].append(dict(name='infeed_sequence', machine_index=mi, simulation_fps=6,
            frame_count=192, duration_seconds=32, start_sim_time=0, end_sim_time=current['machines'][mi]['sim_time'],
            reset_before=True, continuous_with_next_segment=False,
            note='The interval before the later full-cart sequence is fast-forwarded; these are separate clips.'))
        record(prefix+'_recorded_reset_queue_manual_handoff_and_first_deposit', frames=192, simulation_fps=6,
               completed=current['machines'][mi]['completed'], observed_carrier_states=sorted(observed_carrier_states))
    captured = set()
    # The opposite camera still records the actual first filled side; it does not
    # alter CAD destinations to make a picture. Every phase is a real core state.
    for iteration in range(1500):
        current = step(.2)
        trace_parcel(trace, current, mi)
        machine = current['machines'][mi]
        for ci, carrier in enumerate(machine['carriers']):
            tag = None
            if carrier['state_code'] == 5 and .25 <= carrier['induct_progress'] <= .75 and 'induct' not in captured:
                tag = 'induct'
            if carrier['state_code'] == 4 and .32 <= carrier['unload_progress'] <= .72 and carrier['level'] in (0, 3):
                candidate = 'unload_low' if carrier['level'] == 0 else 'unload_high'
                if candidate not in captured:
                    tag = candidate
            if tag:
                yield from capture(prefix+'_02_'+tag, mi, current, evidence=dict(carrier_index=ci, carrier=carrier))
                captured.add(tag)
        if captured == {'induct', 'unload_low', 'unload_high'}:
            break
        if iteration % 10 == 9:
            yield
    assert captured == {'induct', 'unload_low', 'unload_high'}, ('Missing real working stage', prefix, captured)
    # Reporting every five simulated seconds keeps large fleet JSON off the
    # per-frame path. Native steps still resolve every core boundary internally.
    for iteration in range(300):
        machine = current['machines'][mi]
        full = [c for c in machine['carts'] if c['state_code'] == 1]
        if full:
            break
        current = step(5)
        trace_parcel(trace, current, mi)
        if iteration % 5 == 4:
            yield
    else:
        raise AssertionError(('No full cart within 1500 additional simulation seconds', prefix))
    cart_index = full[0]['index']
    assert 1 in full[0]['parcel_ids'], 'Traced first parcel is not in the first full cart'
    assert current['exchanged_carts'] == current['collected'] == current['active_exchange_count'] == 0
    current = step(3)
    assert current['machines'][mi]['carts'][cart_index]['state_code'] == 1
    assert current['exchanged_carts'] == current['collected'] == 0
    yield from capture(prefix+'_03_whole_cart_full_auto_off', mi, current)
    before_request = current
    sim.clear_full_bins()  # Compatibility API requests a whole-cart exchange.
    requested = verify_state(state())
    assert requested['selected_machine'] == mi
    assert requested['occupancy'] == before_request['occupancy'] and requested['collected'] == before_request['collected']
    assert equivalent(requested['machines'][mi]['carts'], before_request['machines'][mi]['carts']), 'Manual request instantly emptied or moved a cart'
    record(prefix+'_auto_off_waits_and_manual_request_does_not_clear_boxes', cart_index=cart_index,
           full_capacity=full[0]['capacity'], simulated_seconds=current['machines'][mi]['sim_time'])
    # Drain existing carrier cargo, close feed, then retain the actual 12-second
    # full-cart dwell. Capture sequence starts only when withdrawal really starts.
    first_generation = full[0]['generation']
    current = requested
    for iteration in range(360):
        previous = current
        current = step(.2)
        check_exchange_transition(previous, current, mi, cart_index)
        trace_parcel(trace, current, mi)
        if current['machines'][mi]['carts'][cart_index]['state_code'] == 2:
            break
        if iteration % 10 == 9:
            yield
    else:
        raise AssertionError(('Manual exchange did not withdraw after drain/dwell', prefix))
    stages = set()
    labels = {2: 'withdrawing_loaded', 3: 'outbound_loaded', 6: 'handoff_waiting_hidden_loaded',
              4: 'empty_arriving_generation_2', 5: 'docking_empty', 0: 'docked_generation_2'}
    frames = 132 if sequence else 110
    delta = 1/6 if sequence else .2
    missing_samples = 0
    handoff_times = []
    sequence_start = current['machines'][mi]['sim_time']
    for frame in range(frames):
        cart = current['machines'][mi]['carts'][cart_index]
        code = cart['state_code']
        if code >= 2:
            missing_samples += 1
        if code == 6:
            handoff_times.append(current['machines'][mi]['sim_time'])
        if code in labels and code not in stages:
            if code == 6:
                sim.set_simulation_playing(False)
                paused_handoff = verify_state(state())
                assert equivalent(paused_handoff, step(4)), 'Paused handoff consumed its dwell or transferred cargo'
                yield from pause(.1, True)
                assert equivalent(paused_handoff, state())
                handoff_readback = verify_rendered(paused_handoff, [mi])
                assert handoff_readback['hidden_handoff_carts'] == 1
                assert handoff_readback['hidden_handoff_loaded_boxes'] == cart['capacity']
                sim.set_simulation_playing(True)
                current = verify_state(state())
                record(prefix+'_handoff_pause_retains_hidden_full_cart_manifest', readback=handoff_readback)
            yield from capture(prefix+'_04_'+labels[code], mi, current)
            stages.add(code)
        if sequence:
            yield from capture(f'frame_{frame:04d}', mi, current, frame=frame)
        previous = current
        current = step(delta)
        check_exchange_transition(previous, current, mi, cart_index)
        trace_parcel(trace, current, mi)
        if not sequence and frame % 5 == 4:
            yield
    assert stages == {0, 2, 3, 4, 5, 6}, ('Incomplete cart cycle', prefix, stages)
    assert missing_samples > 0
    assert len(handoff_times) >= 8 and handoff_times[-1]-handoff_times[0] >= 1.5, 'Handoff dwell was skipped or shortened'
    final_cart = current['machines'][mi]['carts'][cart_index]
    assert final_cart['generation'] == first_generation+1 and final_cart['state_code'] == 0
    assert current['machines'][mi]['exchanged_carts'] == 1
    if sequence:
        report['sequence_segments'].append(dict(name='sequence', machine_index=mi, simulation_fps=6,
            frame_count=frames, duration_seconds=frames/6, start_sim_time=sequence_start,
            end_sim_time=current['machines'][mi]['sim_time'], reset_before=False,
            continuous_with_previous_segment=False,
            note='Starts at genuine full-cart withdrawal after fast-forwarding the intervening loading and waiting period.'))
    # Recovery requires an actual new deposit. A -X CAD120 entry can need ~7 s
    # for an empty carrier to return, ~30 s to reach column 5, plus recognition,
    # induction and shared-chain stops. A fixed 18-second wait is insufficient.
    before_resume = current['machines'][mi]
    recovery = dict(machine_index=mi, machine_id=before_resume['id'], passed=False,
                    timeout_simulation_seconds=90, step_simulation_seconds=2,
                    samples=[recovery_sample(before_resume)])
    report.setdefault('resumption_checks', []).append(recovery)
    report['stage'] = prefix+'_waiting_for_real_post_exchange_delivery'
    write()
    resumed = current
    for recovery_step in range(45):
        resumed = step(2)
        after_resume = resumed['machines'][mi]
        recovery['samples'].append(recovery_sample(after_resume))
        assert after_resume['carts'][cart_index]['generation'] == first_generation+1
        assert after_resume['carts'][cart_index]['state_code'] == 0
        assert after_resume['exchanged_carts'] == 1
        trace_parcel(trace, resumed, mi)
        if resumed_receiving(before_resume, after_resume):
            recovery.update(passed=True, observed_wait_simulation_seconds=after_resume['sim_time']-before_resume['sim_time'],
                            completed_increase=after_resume['completed']-before_resume['completed'],
                            spawned_increase=after_resume['spawned']-before_resume['spawned'])
            write()
            break
        if recovery_step % 3 == 2:
            write()
            yield
    else:
        recovery['last_machine_state'] = resumed['machines'][mi]
        write()
        raise AssertionError(('No real post-exchange arrival and deposit within 90 simulation seconds',
                              prefix, recovery['samples'][-1]))
    trace_parcel(trace, resumed, mi)
    verify_trace(trace)
    report['parcel_traces'].append(trace)
    yield from capture(prefix+'_05_resumed_work', mi, resumed)
    record(prefix+'_selected_whole_cart_cycle_and_parcel_conservation', cart_index=cart_index,
           generation_before=first_generation, generation_after=final_cart['generation'], absent_cart_samples=missing_samples,
           handoff_observed_seconds=handoff_times[-1]-handoff_times[0],
           recovery_wait_simulation_seconds=recovery['observed_wait_simulation_seconds'],
           captured_states=sorted(stages), traced_parcel=1,
           sequence_frames=frames if sequence else 0, sequence_start_sim_time=sequence_start)


def automatic_exchange_test():
    # Both earlier profiles already hold other full carts. Enabling automatic
    # mode must schedule the waiting fleet through the single shared aisle.
    before = verify_state(state())
    sim.set_automatic_collection(True)
    seen = set()
    for i in range(160):
        value = step(.5)
        if value['active_exchange_count']:
            seen.add(value['exchange_owner_machine'])
        if i % 8 == 7:
            yield
    assert value['exchanged_carts'] > before['exchanged_carts']
    assert len(seen) >= 2, ('Automatic scheduler did not serve multiple machines', seen)
    verify_rendered(value, range(22))
    record('automatic_exchange_resumes_fleet_with_single_shared_aisle_owner', observed_machine_owners=sorted(seen),
           exchanged_before=before['exchanged_carts'], exchanged_after=value['exchanged_carts'])


def performance_sample():
    sim.set_automatic_advance_for_diagnostics(False)
    sim.reset_simulation()
    sim.set_simulation_playing(True)
    precondition = step(80)
    assert precondition['completed'] > 0, 'Performance precondition did not reach steady receiving'
    sim.set_automatic_advance_for_diagnostics(True)
    yield from pause(3, True)
    before = verify_state(state())
    filename = 'MPR_FULL_WORKFLOW_'+report['run_id']+'.csv'
    path = ROOT / 'Saved/Profiling/CSV' / filename
    console('CsvProfile STARTFILE='+filename)
    console('CsvProfile START')
    reads_before = report_reads
    sample_start = time.monotonic()
    # No screenshot, diagnostic advance, instance scan, or JSON snapshot here.
    yield from pause(15, True)
    sample_wall = time.monotonic()-sample_start
    console('CsvProfile STOP')
    assert report_reads == reads_before
    sim.set_automatic_advance_for_diagnostics(False)
    after = verify_state(state())
    yield from wait('native_csv_flush', lambda: timing.csv_complete(path), 10)
    native = timing.parse_csv(path)
    native['fps'] = native['frame_count']/native['native_frame_time_seconds']
    assert after['machines'][0]['sim_time']-before['machines'][0]['sim_time'] > 10
    assert after['completed'] > before['completed']
    report['performance'] = dict(native_csv=native, sampled_wall_seconds=sample_wall, camera=fixed_camera[:],
                                actor_auto_tick=True, manual_steps=0, report_reads_during_sample=0,
                                precondition_advance_simulation_seconds=80,
                                resolution=[1920, 1080], hud_visible=True,
                                before={k: before[k] for k in TOTAL_FIELDS}, after={k: after[k] for k in TOTAL_FIELDS},
                                scope='One local owned native game, 22 machines, 96 carts, 44 operator slots and HUD; not a streaming or isolated hardware benchmark.')
    record('real_native_tick_15_second_csv_profile', fps=native['fps'])


def run():
    yield from wait('discover_schema2_mpr', discover, 35)
    yield from wait('viewport_1920x1080', lambda: list(pc.get_viewport_size()) == [1920, 1080], 10)
    for command in ('DisableAllScreenMessages', 't.MaxFPS 0', 'r.VSync 0', 't.IdleWhenNotForeground 0',
                    'Slate.bAllowThrottling 0', 'csv.CompressionMode 0', 'r.GPUCsvStatsEnabled 1'):
        console(command)
    sim.set_automatic_advance_for_diagnostics(False)
    sim.set_panel_visible(True)
    value = verify_state(state())
    bind_instances(value)
    report['actor_count_before'] = len(u.GameplayStatics.get_all_actors_of_class(world, u.Actor))
    report['engine_version'] = u.SystemLibrary.get_engine_version()
    report['camera_class'] = pawn.get_class().get_path_name()
    record('schema2_fixture_22_machines_96_carts_88_carriers_66_queue_slots', readback=verify_rendered(value, range(22)))
    yield from control_tests()
    first64 = next(i for i, m in enumerate(LAYOUT['machines']) if m['profile'] == 'cad64')
    first120 = next(i for i, m in enumerate(LAYOUT['machines']) if m['profile'] == 'cad120')
    yield from workflow(first64, side=0, sequence=SEQUENCE)
    yield from workflow(first120, side=1)
    yield from automatic_exchange_test()
    yield from performance_sample()
    assert len(u.GameplayStatics.get_all_actors_of_class(world, u.Actor)) == report['actor_count_before']
    assert report['instance_pool'] == {name: c.get_instance_count() for name, c in components.items()}
    for view in report['fixed_views']:
        rows = [r for r in report['captures']+report['sequence']+report['infeed_sequence'] if r['machine_index'] == view['machine_index']]
        assert rows and all(same_pose(view['camera'], r['camera']) for r in rows)
    assert len(report['sequence']) == (132 if SEQUENCE else 0)
    assert len(report['infeed_sequence']) == (192 if SEQUENCE else 0)
    record('bounded_actor_component_instance_pools_and_fixed_1920x1080_views')
    report.update(success=True, stage='complete')


def finish(error=None):
    global done
    done = True
    if error:
        report.update(success=False, error=error)
    fault_note('finish_begin', 'error' if error else 'normal')
    if world:
        console('CsvProfile STOP')
        if sim:
            sim.set_automatic_advance_for_diagnostics(False)
            sim.set_simulation_playing(False)
    report['assets_unchanged'] = all(p.exists() and hashlib.sha256(p.read_bytes()).hexdigest() == HASHES[str(p)] for p in ASSETS)
    report['success'] = report['success'] and report['assets_unchanged']
    write()
    if callback is not None:
        u.unregister_slate_post_tick_callback(callback)
    if world:
        u.SystemLibrary.quit_game(world, pc, u.QuitPreference.QUIT, False)


def tick(delta):
    global busy
    if done or busy:
        return
    busy = True
    try:
        deadline()
        next(steps)
    except StopIteration:
        finish()
    except Exception:
        finish(traceback.format_exc())
    finally:
        busy = False


def main():
    global u, timing, START, OUT, ASSETS, HASHES, SEQUENCE, report, callback, steps, FAULT_LOG
    import unreal as unreal_module
    u = unreal_module
    sys.path.insert(0, str(Path(__file__).parent))
    import profile_mpr_runtime as timing_module
    timing = timing_module
    cli = u.SystemLibrary.get_command_line()
    assert all(re.search(r'(?:^|\s)-'+flag+r'(?=\s|$)', cli, re.I)
               for flag in ('own', 'game', 'RenderOffscreen', 'TwinDiagnostics'))
    assert not re.search(r'(?:^|\s)-(?:MPRProfile|UseFixedTimeStep)(?=\s|$)', cli, re.I)
    assert LAYOUT['schema_version'] == 2
    SEQUENCE = bool(re.search(r'(?:^|\s)-MPRFullWorkflowCaptureSequence(?=\s|$)', cli, re.I))
    START = time.monotonic()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    OUT = BASE / stamp
    OUT.mkdir(parents=True, exist_ok=True)
    FAULT_LOG = (OUT / 'python_fault.log').open('w', encoding='utf8', buffering=1)
    faulthandler.enable(file=FAULT_LOG, all_threads=True)
    fault_note('native_python_diagnostics_started', sys.version.replace('\n', ' '))
    ASSETS = [MAP_FILE, LAYOUT_FILE, *sorted((ROOT / 'Content/MPRWarehouse/SorterSimulation').rglob('*.uasset'))]
    HASHES = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in ASSETS}
    report = dict(success=False, run_id=stamp, schema_version=2, stage='initializing', resolution=[1920, 1080],
                  deadline_seconds=DEADLINE_SECONDS, checks=[], captures=[], sequence=[], infeed_sequence=[],
                  sequence_segments=[], fixed_views=[], parcel_traces=[],
                  performance={}, assets_saved=False, map_sha256=HASHES[str(MAP_FILE)],
                  layout_sha256=HASHES[str(LAYOUT_FILE)], capture_sequence=SEQUENCE, data_mode='demonstration',
                  scope='Native production API controls, actual ISM readback, genuine deterministic states and images; no OS input or vendor PLC acceptance claim.',
                  diagnostics=dict(python_fault_log=str(OUT / 'python_fault.log'),
                                   json_encoder='CPython C encoder; compact JSON with circular reference checks and finite-number enforcement'),
                  limitations=['Presentation timing and manual transfer path are demonstration assumptions, not surveyed operating instructions.',
                               'Screenshots require human visual review; this script validates file completion, resolution, camera and instance poses.'])
    write()
    steps = run()
    callback = u.register_slate_post_tick_callback(tick)


if __name__ == '__main__':
    main()
