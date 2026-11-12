"""Optimization acceptance in an owned native game; never edits scene assets.

Retains the prior 16 continuous/feed/full-cart checks, replacing only the old
all-CAD-people fixture with the explicit sorter-only worker policy. Adds native
cart cache readback/counter checks. Run with the same flags as the preserved
sorter validator; output is isolated under Saved/MPR/optimization_20261112.
"""
from collections import Counter
from pathlib import Path
import hashlib
import json
import math
import re
import sys

sys.path.insert(0, str(Path(__file__).parent))
import verify_mpr_interior_preserved_sorter_20261112 as preserved
continuous = preserved.continuous
central = preserved.central
v = preserved.v
worker_components = continuous.worker_components
REFERENCE_FACING = continuous.REFERENCE_FACING
POLICY_FILE = v.ROOT / 'SourceAssets/MPR/sorter_simulation/worker_presentation_policy.json'
POLICY = json.loads(POLICY_FILE.read_text(encoding='utf-8-sig'))
CAD_SOURCE = continuous.CAD_WORKERS
EXPECTED = POLICY['expected_counts']
RETAINED = {row['source_handle']: row for row in POLICY['retained_workers']}
assert POLICY['schema_version'] == 1
assert POLICY['source_cad_sha256'] == CAD_SOURCE['source_sha256']
assert len(RETAINED) == EXPECTED['retained_cad_workers'] == 7
assert {h for h, row in RETAINED.items() if row['role'] == 'central_feed'} == {
    '2CCF63', '2CCF64', '2CCF65', '2CCF69', '2CCF67', '2CCF68'}
assert {h for h, row in RETAINED.items() if row['role'] == 'sorter_console'} == {'2CCF61'}
CAD_BY_HANDLE = {h: continuous.CAD_BY_HANDLE[h] for h in RETAINED}
PHASES = continuous.PHASES
ORIGINAL_STEP = v.step
ORIGINAL_STATE = v.state
ORIGINAL_EQUIVALENT = v.equivalent
CART_LAST = None
CART_AUDIT = dict(manual_steps=0, unchanged_steps=0, changed_steps=0,
    changed_cart_instances=0, transform_submissions=0, component_dirty_submissions=0,
    native_cart_reads=0, maximum_native_transform_error=0., visibility_transitions=[])
CART_PHASES = {'cad64': set(), 'cad120': set()}
PRESERVED_CHECKS = (
    'all_cad_people_native_positions_orientations_and_visibility',
    'empty_before_work_keeps_circulating',
    'manual_pause_freezes_logic_and_native_render_poses',
    'active_phases_move_at_constant_speed',
    'six_operators_repeat_fast_feed_cycles',
    'finished_work_empty_carriers_keep_circulating',
    'full_destination_backpressure_does_not_stop_common_chain',
    'native_tick_15_seconds_without_json_or_capture_polling',
    'conserved_ids_and_bounded_native_instance_pools',
    'current_cart_and_central_instance_binding',
    'cad64_whole_cart_full_waits_and_external_infeed_backpressures',
    'cad64_full_outbound_handoff_empty_arrival_docking_and_receiving_recovery',
    'cad120_whole_cart_full_waits_and_external_infeed_backpressures',
    'cad120_full_outbound_handoff_empty_arrival_docking_and_receiving_recovery',
    'automatic_whole_cart_replacement_preserved_with_continuous_chain',
    'both_cart_profiles_complete_without_actor_or_instance_pool_growth',
)


def verify_worker_roles(value, workers):
    assert value['worker_presentation_policy'] == POLICY['policy'] == 'sorter_workers_only'
    roles = Counter(w['role'] for w in workers.values())
    assert roles == dict(cart_exchange=22, central_feed=6, sorter_console=1), roles
    assert value['legacy_worker_instances'] == 0
    assert len(worker_components()) == 29
    assert 7 <= sum(w['visible'] for w in workers.values()) <= 8
    retained = {w['source_handle']: w for w in workers.values() if w['role'] != 'cart_exchange'}
    assert set(retained) == set(RETAINED), ('Wrong retained CAD handles', set(retained))
    for handle, worker in retained.items():
        assert worker['role'] == RETAINED[handle]['role'] and worker['visible']
    exchanges = [w for w in workers.values() if w['role'] == 'cart_exchange']
    assert {w['machine_id'] for w in exchanges} == {m['id'] for m in value['machines']}
    assert all(not w['source_handle'] for w in exchanges)
    for worker in workers.values():
        assert worker['ready'] and worker['bone_count'] == 89
        assert worker['mesh'].endswith('SKM_Manny_Simple.SKM_Manny_Simple')
        assert worker['forced_lod'] == 0
    for placement in value['cad_workers']:
        assert placement['role'] == RETAINED[placement['source_handle']]['role']
        assert workers[placement['worker_index']]['source_handle'] == placement['source_handle']


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
    assert value['cad_source_worker_count'] == CAD_SOURCE['count'] == POLICY['source_worker_count'] == 256
    assert value['cad_worker_count'] == EXPECTED['retained_cad_workers'] == 7
    assert value['omitted_cad_worker_count'] == EXPECTED['omitted_cad_workers'] == 249
    assert value['worker_slots'] == len(workers) == EXPECTED['runtime_worker_slots'] == 29
    verify_worker_roles(value, workers)
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


def equivalent(a, b, tolerance=1.e-5):
    # Renderer feedback changes during pause. Paused central-feed updates also
    # resubmit identical poses; only their revision counter may increase. The
    # original pause regression still compares every native bone transform.
    if isinstance(a, dict):
        if not isinstance(b, dict) or a.keys() != b.keys():
            return False
        ignored = {'predicted_lod', 'display_lod_changes'} if 'bone_count' in a and 'pose_revision' in a else set()
        if ignored and a.get('role') == b.get('role') == 'central_feed':
            ignored.add('pose_revision')
        return all(equivalent(a[key], b[key], tolerance) for key in a if key not in ignored)
    if isinstance(a, (list, tuple)):
        return isinstance(b, (list, tuple)) and len(a) == len(b) and all(
            equivalent(x, y, tolerance) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and not isinstance(a, bool):
        return isinstance(b, (int, float)) and math.isfinite(a) and math.isfinite(b) and abs(a-b) <= tolerance
    return a == b


def state_with_cart_projection():
    """Reuse the existing read once; retain only 96 small primitive tuples."""
    global CART_LAST
    value = ORIGINAL_STATE()
    if not value.get('ready'):
        return value
    rows = []
    for mi in range(len(value['machines'])):
        machine = value['machines'][mi]
        for cart in machine['carts']:
            transform = cart['render_world_transform']
            values = tuple(transform['translation_cm'] + transform['rotation_xyzw'] + transform['scale'])
            rows.append((mi, cart['index'], machine['profile'], v.canonical_mesh(cart['mesh']),
                         cart['visible'], cart['state_code'], values))
    CART_LAST = (tuple(rows), value['cart_transform_submissions'], value['cart_component_dirty_submissions'])
    return value


def step_with_cart_audit(seconds):
    # Separate process only. Unlike the former observer, this adds no JSON
    # readback and never holds a second entire simulation report across a step.
    before = CART_LAST
    assert before is not None
    sample_index = CART_AUDIT['manual_steps']
    if sample_index % 32 == 0:
        v.fault_note('cart_step_begin', str(sample_index))
    after = ORIGINAL_STEP(seconds)
    current = CART_LAST
    assert len(before[0]) == len(current[0]) == 96
    changed = 0
    dirty_meshes = set()
    for row_index in range(96):
        old, row = before[0][row_index], current[0][row_index]
        assert old[:4] == row[:4]
        mi, ci, profile, mesh, visible, state_code, pose = row
        key = (mi, ci)
        CART_PHASES[profile].add(state_code)
        pose_changed = False
        for axis in range(10):
            if abs(old[6][axis] - pose[axis]) > 1.e-9:
                pose_changed = True
                break
        if pose_changed:
            changed += 1
            dirty_meshes.add(mesh)
            if key in central.cart_instances:
                component, index = central.cart_instances[key]
                actual = v.transform_values(v.instance(component, index))
                error = 0.
                for axis in range(10):
                    error = max(error, abs(actual[axis] - pose[axis]))
                assert error < .04, ('Changed cart native pose', key, error)
                CART_AUDIT['native_cart_reads'] += 1
                CART_AUDIT['maximum_native_transform_error'] = max(CART_AUDIT['maximum_native_transform_error'], error)
        if old[4] != visible:
            CART_AUDIT['visibility_transitions'].append(dict(profile=profile,
                machine=mi, cart=ci, visible_before=old[4], visible_after=visible, state_code=state_code))
    submitted = current[1] - before[1]
    dirty = current[2] - before[2]
    assert submitted == changed, ('Cart submissions differ from changed poses', seconds, submitted, changed)
    assert dirty == len(dirty_meshes), ('Cart components dirtied redundantly', seconds, dirty, dirty_meshes)
    CART_AUDIT['manual_steps'] += 1
    CART_AUDIT['changed_steps' if changed else 'unchanged_steps'] += 1
    CART_AUDIT['changed_cart_instances'] += changed
    CART_AUDIT['transform_submissions'] += submitted
    CART_AUDIT['component_dirty_submissions'] += dirty
    if sample_index % 32 == 0:
        v.fault_note('cart_step_end', str(sample_index))
    return after


def cache_reset_and_stationary():
    v.fault_note('cache_reset_begin')
    v.sim.set_automatic_advance_for_diagnostics(False)
    before = v.state()
    reset_baseline = (before['cart_transform_submissions'], before['cart_component_dirty_submissions'])
    del before
    v.sim.reset_simulation()
    reset = verify_state(v.state())
    components = [c for name, c in v.components.items() if name.startswith('RuntimeCart_')]
    assert reset['cart_transform_submissions'] - reset_baseline[0] == 96
    assert reset['cart_component_dirty_submissions'] - reset_baseline[1] == len(components)
    preserved.bind_current_carts(reset)
    v.fault_note('cache_reset_native_readback_begin')
    preserved.current_readback(reset)
    v.fault_note('cache_reset_native_readback_end')
    assert sum(w['visible'] for w in reset['skeletal_workers']) == EXPECTED['idle_visible_workers'] == 7
    del reset
    v.sim.set_central_feeding_enabled(False)
    v.sim.set_automatic_collection(False)
    v.sim.set_simulation_playing(True)
    initial = verify_state(v.state())
    v.fault_note('cache_stationary_begin')
    before_counts = (initial['cart_transform_submissions'], initial['cart_component_dirty_submissions'])
    del initial
    for i in range(120):
        current = v.step(1 / 60)
        assert current['active_exchange_count'] == 0
        yield
    assert before_counts == (current['cart_transform_submissions'], current['cart_component_dirty_submissions'])
    preserved.current_readback(current)
    v.fault_note('cache_stationary_native_readback_end')
    v.record('cart_cache_reset_republishes_96_once_and_120_stationary_updates_submit_nothing',
        reset_instances=96, reset_component_count=len(components), stationary_updates=120)


def record_worker_policy():
    v.report['worker_policy'] = dict(path=str(POLICY_FILE),
        sha256=hashlib.sha256(POLICY_FILE.read_bytes()).hexdigest(),
        source_worker_count=256, expected_counts=EXPECTED,
        retained_handles=sorted(RETAINED), removed_cad_workers=249,
        scope='The legacy all_cad_people check now covers every retained policy person against the unchanged original CAD source.')
    current = verify_state(v.state())
    v.record('only_sorter_workers_retained_with_exact_source_handles_and_roles',
        source_cad_workers=current['cad_source_worker_count'],
        retained_cad_workers=current['cad_worker_count'], omitted_cad_workers=current['omitted_cad_worker_count'],
        worker_slots=current['worker_slots'], roles=dict(Counter(w['role'] for w in current['skeletal_workers'])))


def run():
    # The original 16 checks run without any new per-step observer or JSON read.
    v.report['validation_mode'] = 'full_workflow'
    yield from preserved.run()
    v.report.update(success=False, stage='checking_worker_policy')
    checks = {row['name'] for row in v.report['checks'] if row['passed']}
    assert set(PRESERVED_CHECKS) <= checks, ('Missing prior acceptance checks', set(PRESERVED_CHECKS) - checks)
    v.report['preserved_check_names'] = list(PRESERVED_CHECKS)
    record_worker_policy()
    v.report.update(success=True, stage='complete',
        scope='All original 16 sorter workflow checks plus the exact sorter-only worker policy. Cart counter acceptance runs independently with -MPROptCartAuditOnly.')


def run_cart_audit():
    v.report.update(validation_mode='cart_cache', stage='discovering_cart_audit',
        scope='Separate native process: both complete cart exchange profiles, native cart poses, exact submit counters, reset and stationary updates; no performance comparison.')
    yield from v.wait('discover', v.discover, 40)
    yield from v.wait('viewport', lambda: list(v.pc.get_viewport_size()) == [1920, 1080], 10)
    for command in ('DisableAllScreenMessages', 't.MaxFPS 0', 'r.VSync 0',
                    't.IdleWhenNotForeground 0', 'Slate.bAllowThrottling 0'):
        v.console(command)
    v.sim.set_automatic_advance_for_diagnostics(False)
    v.sim.set_central_feeding_enabled(True)
    v.sim.set_panel_visible(True)
    initial = verify_state(v.state())
    preserved.bind_current_carts(initial)
    del initial
    v.report['initial_instance_pool'] = {name: component.get_instance_count() for name, component in v.components.items()}
    actors_before = len(v.u.GameplayStatics.get_all_actors_of_class(v.world, v.u.Actor))
    record_worker_policy()
    for profile in ('cad64', 'cad120'):
        v.report['stage'] = profile + '_cart_cache_full_replacement'
        v.fault_note('cart_profile_begin', profile)
        yield from central.exchange_cycle(profile)
        v.fault_note('cart_profile_end', profile)
    for profile, phases in CART_PHASES.items():
        assert set(range(7)) <= phases, ('Cache coverage missed cart phase', profile, phases)
        events = [x for x in CART_AUDIT['visibility_transitions'] if x['profile'] == profile]
        assert any(not e['visible_after'] for e in events) and any(e['visible_after'] for e in events), profile
    assert CART_AUDIT['unchanged_steps'] > 0 and CART_AUDIT['native_cart_reads'] > 0
    yield from cache_reset_and_stationary()
    v.report['cart_cache_audit'] = dict(CART_AUDIT, phases_by_profile={k: sorted(p) for k, p in CART_PHASES.items()})
    v.report['cart_cache_audit']['extra_json_reads_per_step'] = 0
    v.report['cart_cache_audit']['retained_projection_rows'] = 96
    v.record('cart_submissions_match_changed_poses_through_both_complete_exchange_profiles', **v.report['cart_cache_audit'])
    assert len(v.u.GameplayStatics.get_all_actors_of_class(v.world, v.u.Actor)) == actors_before
    assert v.report['initial_instance_pool'] == {name: component.get_instance_count() for name, component in v.components.items()}
    v.report.update(success=True, stage='complete')


continuous.CAD_BY_HANDLE = CAD_BY_HANDLE
continuous.verify_state = verify_state
central.verify_state = verify_state
v.verify_state = verify_state
v.equivalent = equivalent
v.BASE = v.ROOT / 'Saved/MPR/optimization_20261112/optimized_sorter_runtime'
v.DEADLINE_SECONDS = 1800
v.run = run

if __name__ == '__main__':
    import unreal
    if re.search(r'(?:^|\s)-MPROptCartAuditOnly(?=\s|$)', unreal.SystemLibrary.get_command_line(), re.I):
        v.BASE = v.ROOT / 'Saved/MPR/optimization_20261112/cart_cache_runtime'
        v.state = state_with_cart_projection
        v.step = step_with_cart_audit
        v.run = run_cart_audit
    v.main()
