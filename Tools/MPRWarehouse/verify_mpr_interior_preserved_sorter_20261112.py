"""Existing-map acceptance after CAD interior edits; never saves scene assets.

Run in an owned -game -RenderOffscreen -TwinDiagnostics -EnablePython process
at -ForceRes -ResX=1920 -ResY=1080, using this script as the ExecCmds Python
entry point. Reuses the complete current continuous-motion regression, then
checks both cart profiles through full outbound/empty inbound replacement.
Only diagnostics/production controls in that isolated game are exercised.
"""
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
import verify_mpr_continuous_runtime as continuous

central = continuous.central
v = continuous.v
original_readback = central.readback


def bind_current_carts(value):
    """Bind real cart instances without the old 60-carrier/28-worker fixture."""
    by_mesh = {}
    for name, component in v.components.items():
        if not name.startswith('RuntimeCart_'):
            continue
        mesh = v.canonical_mesh(component.get_editor_property('static_mesh').get_path_name())
        assert mesh not in by_mesh, ('Duplicate runtime cart component', mesh)
        by_mesh[mesh] = component
    counts = Counter()
    central.cart_instances.clear()
    for mi, machine in enumerate(value['machines']):
        for cart in machine['carts']:
            mesh = v.canonical_mesh(cart['mesh'])
            assert mesh in by_mesh, ('Missing runtime cart component', mesh)
            central.cart_instances[(mi, cart['index'])] = (by_mesh[mesh], counts[mesh])
            counts[mesh] += 1
    assert sum(counts.values()) == value['cart_count'] == 96
    assert len(central.cart_instances) == value['cart_count']
    assert set(counts) == set(by_mesh)
    assert all(by_mesh[mesh].get_instance_count() == count for mesh, count in counts.items())
    carriers = sum(len(bank['carriers']) for bank in value['distribution_banks'])
    assert carriers == 120
    for name in ('CentralMovingColumns', 'CentralLiftTrays', 'CentralParcels'):
        assert v.components[name].get_instance_count() == carriers
    v.record('current_cart_and_central_instance_binding', carts=sum(counts.values()),
             cart_mesh_variants=len(by_mesh), central_carriers=carriers)


def current_readback(value):
    # The old readback already iterates every real central carrier, ring tray
    # and cart. Only its returned central_trays metadata was hard-coded to 60.
    # Keep its position/visibility checks; the continuous-only readback does
    # not inspect withdrawing/arriving cart instances.
    result = original_readback(value)
    result['central_trays'] = sum(len(bank['carriers']) for bank in value['distribution_banks'])
    result['machine_carriers'] = sum(len(machine['carriers']) for machine in value['machines'])
    result['carts'] = sum(len(machine['carts']) for machine in value['machines'])
    return result


def automatic_exchange():
    """Also retain automatic scheduling through the one shared cart aisle."""
    previous = before = continuous.verify_state(v.state())
    assert before['waiting_exchange_count'] > 0
    v.sim.set_automatic_collection(True)
    owners = set()
    max_motion_error = 0.
    for i in range(160):
        current = v.step(.5)
        error, _ = continuous.motion_delta(previous, current)
        max_motion_error = max(max_motion_error, error)
        if current['active_exchange_count']:
            owners.add(current['exchange_owner_machine'])
        assert current['active_exchange_count'] <= 1 and current['shared_aisle_mutex_valid']
        if i % 8 == 7:
            current_readback(current)
            yield
        previous = current
    assert current['exchanged_carts'] > before['exchanged_carts']
    assert len(owners) >= 2, ('Automatic scheduler did not serve multiple machines', owners)
    v.record('automatic_whole_cart_replacement_preserved_with_continuous_chain',
             exchanged_before=before['exchanged_carts'], exchanged_after=current['exchanged_carts'],
             observed_machine_owners=sorted(owners), max_normalized_motion_error=max_motion_error,
             native_readback=current_readback(current))


def run():
    # This includes empty/loaded/blocked/drained continuous motion, CAD workers,
    # fast feeding, actual native ISM readback and the original 15-second CSV.
    yield from continuous.run()
    v.report.update(success=False, stage='checking_preserved_whole_cart_replacement',
        scope='Existing MPR sorter preserved after CAD interior edits: complete continuous regression plus cad64/cad120 full-cart replacement and automatic shared-aisle scheduling.')
    v.sim.set_automatic_advance_for_diagnostics(False)
    v.sim.set_central_feeding_enabled(True)
    v.sim.set_panel_visible(True)
    value = continuous.verify_state(v.state())
    bind_current_carts(value)
    actors_before = len(v.u.GameplayStatics.get_all_actors_of_class(v.world, v.u.Actor))
    for profile in ('cad64', 'cad120'):
        v.report['stage'] = profile + '_whole_cart_replacement'
        yield from central.exchange_cycle(profile)
    yield from automatic_exchange()
    assert len(v.u.GameplayStatics.get_all_actors_of_class(v.world, v.u.Actor)) == actors_before
    assert v.report['initial_instance_pool'] == {n: c.get_instance_count() for n, c in v.components.items()}
    v.record('both_cart_profiles_complete_without_actor_or_instance_pool_growth',
             profiles=['cad64', 'cad120'], actor_count=actors_before)
    v.report.update(success=True, stage='complete')


central.verify_state = continuous.verify_state
central.readback = current_readback
v.verify_state = continuous.verify_state
v.BASE = v.ROOT / 'Saved/MPR/interior_cad_20261112/preserved_sorter_runtime'
v.DEADLINE_SECONDS = 1800
v.run = run

if __name__ == '__main__':
    v.main()
