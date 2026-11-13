"""Read-only native transfer regression; two stills, no frame sequence.

Use the existing MPR map in an owned -game -RenderOffscreen -TwinDiagnostics
-EnablePython -ForceRes -ResX=1920 -ResY=1080 process. -MPRTransferBaseline
records the previous collision without requiring a passing clearance result.
"""
import math
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).parent))
import verify_mpr_full_sorter_runtime as v


def check(name, passed, **details):
    v.report['checks'].append(dict(name=name, passed=bool(passed), **details))
    v.write()


def invariant(value):
    assert value['ready'] and not value['error']
    for key in ('conserved', 'unique_parcel_ownership', 'central_conserved',
                'global_unique_ownership', 'shared_aisle_mutex_valid'):
        assert value[key], key
    assert value['machine_count'] == 22 and value['cart_count'] == 96


def feed_clearances(value):
    # Read production ISM cube transforms, not the source endpoint formula.
    decks = []
    component = v.components['CentralBelts']
    for index in range(component.get_instance_count()):
        t = v.instance(component, index)
        size = [abs(x)*100 for x in v.xyz(t.scale3d)]
        # Powered source belt is 42 cm wide; the rubber surface is 38 cm.
        if abs(size[1]-38) < .01 and abs(size[2]-1) < .01:
            decks.append((index, v.xyz(t.translation), size))
    mesh = v.components['CentralLiftTrays'].get_editor_property('static_mesh')
    bounds = mesh.get_bounding_box()
    outward_half = -float(bounds.min.y)*1.6
    rows = []
    for bank_index, bank in enumerate(value['distribution_banks']):
        center = (-10433.998536, 54) if bank_index == 0 else (-11155.743336, 44)
        for station_index, station in enumerate(bank['stations']):
            drop = station['drop_cm']
            side = 1 if drop[0] > center[0] else -1
            rail_x = center[0]+side*center[1]
            candidates = [(i, p, size) for i, p, size in decks
                          if abs(p[1]-drop[1]) < .02
                          and (p[0]-rail_x)*side >= -.02
                          and abs(p[0]-rail_x) < abs(drop[0]-rail_x)]
            assert len(candidates) == 1, (bank_index, station_index, candidates)
            index, point, size = candidates[0]
            tip_distance = (point[0]-rail_x)*side-size[0]*.5
            rows.append(dict(bank=bank['id'], station=station_index, deck_instance=index,
                             tray_outward_half_cm=outward_half, tip_distance_cm=tip_distance,
                             clearance_cm=tip_distance-outward_half))
    check('all_seven_feed_belts_clear_real_scaled_tray_mesh',
          len(rows) == 7 and min(x['clearance_cm'] for x in rows) >= 1.9, ports=rows)


def still(name, pivot):
    v.pawn.focus_on_target(v.u.Vector(*pivot), 570,
        v.u.Rotator(pitch=-33, yaw=35), v.u.Vector2D(1920,1080), v.u.Vector2D(960,540), 0)
    yield from v.pause(.4)
    v.pawn.freeze_current_pose()
    path = v.OUT/(name+'.png')
    v.console('HighResShot 1920x1080 filename="'+str(path).replace('\\','/')+'"')
    yield from v.wait('still_'+name, lambda: path.exists() and path.stat().st_size > 1000, 15)
    v.report['captures'].append(dict(name=name, path=str(path), camera=v.camera()))
    v.write()


def run():
    baseline = bool(re.search(r'(?:^|\s)-MPRTransferBaseline(?=\s|$)', v.u.SystemLibrary.get_command_line(), re.I))
    v.report.update(scope='Actual source-belt / tray clearance, continuous circulation and full-cart replacement.', baseline=baseline)
    yield from v.wait('discover', v.discover, 40)
    yield from v.wait('viewport', lambda: list(v.pc.get_viewport_size()) == [1920,1080], 10)
    v.sim.set_panel_visible(False)
    v.sim.set_automatic_advance_for_diagnostics(False)
    v.sim.reset_simulation()
    v.sim.set_simulation_playing(True)
    v.sim.focus_machine(0)
    yield from v.wait('roof', lambda: v.roof.is_interior_available() and not v.pawn.is_pose_transition_active(), 25)
    value = v.state()
    invariant(value)
    feed_clearances(value)
    # Capture the exact phase where the lower source tray passes the fixed tip.
    found = False
    for iteration in range(360):
        assert v.sim.advance_simulation_for_diagnostics(1/60)
        value = v.state()
        first = value['distribution_banks'][0]
        if any(c['source_station'] == 1 and c['state'] == 0 and .69 <= c['progress'] <= .79
               for c in first['carriers']):
            found = True
            break
        if iteration % 20 == 19:
            yield
    check('source_loading_contact_phase_observed', found)
    yield from still('source_loading', [-10520,-142,110])
    # Existing production full-cart workflow continues; no capacity/timing override.
    exchanged = False
    for iteration in range(180):
        assert v.sim.advance_simulation_for_diagnostics(10)
        value = v.state()
        invariant(value)
        if value['exchanged_carts'] > 0:
            exchanged = True
            break
        yield
    check('full_cart_replacement_and_unique_parcel_ownership', exchanged,
          exchanged_carts=value['exchanged_carts'], generated=value['central_generated'],
          delivered=value['central_delivered'])
    v.sim.set_central_feeding_enabled(False)
    before = [v.xyz(v.instance(v.components['CentralMovingColumns'], i).translation)
              for i in range(v.components['CentralMovingColumns'].get_instance_count())]
    assert v.sim.advance_simulation_for_diagnostics(1/60)
    after = [v.xyz(v.instance(v.components['CentralMovingColumns'], i).translation)
             for i in range(len(before))]
    distances = [math.dist(a[:2], b[:2]) for a, b in zip(before, after)]
    check('all_120_columns_continue_through_straights_and_turns', len(before) == 120 and
          min(distances) > 1.49 and max(distances) < 1.51,
          min_motion_cm=min(distances), max_motion_cm=max(distances))
    yield from still('after_full_cart_exchange', [-10520,-142,110])
    failed = [r['name'] for r in v.report['checks'] if not r['passed']]
    v.report.update(success=not failed, stage='baseline_complete' if baseline else 'complete',
                    regression_failures=failed, expected_baseline_defects_observed=bool(baseline and failed))
    v.write()


v.BASE = v.ROOT/'Saved/MPR/transfer_clearance_20261113/runtime'
v.DEADLINE_SECONDS = 480
v.run = run
if __name__ == '__main__':
    v.main()
