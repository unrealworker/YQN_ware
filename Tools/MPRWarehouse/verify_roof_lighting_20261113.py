"""Four fixed-view captures for the shared MPR/GHS roof lighting lifecycle.

Run an owned -game -RenderOffscreen -TwinDiagnostics -EnablePython process.
-MPRRoofBaseline records the unfixed result; -RoofLightingGHS selects GHS.
Only four PNGs and one small report per map/run mode are written. No assets save.
"""
from pathlib import Path
import hashlib
import json
import re
import struct
import time
import traceback
import unreal as u

ROOT = Path(__file__).resolve().parents[2]
CLI = u.SystemLibrary.get_command_line()
flag = lambda name: bool(re.search(r'(?:^|\s)-'+name+r'(?=\s|$)', CLI, re.I))
assert all(flag(name) for name in ('own', 'game', 'RenderOffscreen', 'TwinDiagnostics'))
assert not flag('MPRProfile')
BASELINE = flag('MPRRoofBaseline')
GHS = flag('RoofLightingGHS')
MAP = '/Game/Maps/'+('GHS_CAD_NormalWarehouse_ZcoolSmartFactory' if GHS else 'MPR_CAD_Warehouse_B50B57')
MAP_FILE = ROOT/'Content'/(MAP.removeprefix('/Game/')+'.umap')
OUT = ROOT/'Saved/MPR/roof_lighting_20261113'/('before' if BASELINE else 'after')/('ghs' if GHS else 'mpr')
OUT.mkdir(parents=True, exist_ok=True)
PROPERTIES = ('cast_shadow', 'cast_hidden_shadow', 'affect_distance_field_lighting',
              'affect_dynamic_indirect_lighting', 'affect_indirect_lighting_while_hidden',
              'visible_in_ray_tracing', 'shadow_cache_invalidation_behavior')
report = dict(success=False, baseline=BASELINE, map=MAP, checks=[], states=[], assets_saved=False)
report['map_sha256'] = hashlib.sha256(MAP_FILE.read_bytes()).hexdigest()
world = pc = pawn = roof = handle = None
parts = []
done = busy = False
START = time.monotonic()


def write():
    (OUT/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf8')


def check(name, passed):
    report['checks'].append(dict(name=name, passed=bool(passed)))


def console(command):
    u.SystemLibrary.execute_console_command(world, command, pc)


def wait(name, predicate, seconds=45):
    report['stage'] = name
    end = time.monotonic()+seconds
    while not predicate():
        assert time.monotonic() < end, 'Timed out: '+name
        yield


def pause(seconds):
    end = time.monotonic()+seconds
    while time.monotonic() < end:
        yield


def discover():
    global world, pc, pawn, roof
    for w in u.ObjectIterator(u.World):
        if not w.get_path_name().startswith(MAP+'.'):
            continue
        c = u.GameplayStatics.get_player_controller(w, 0)
        if not c or not hasattr(c, 'warehouse_roof'):
            continue
        candidate = c.warehouse_roof
        if candidate and candidate.has_roof():
            world, pc, pawn, roof = w, c, c.get_controlled_pawn(), candidate
            return bool(pawn)
    return False


def camera():
    manager = pc.player_camera_manager
    p, r = manager.get_camera_location(), manager.get_camera_rotation()
    return [p.x, p.y, p.z, r.pitch, r.yaw, r.roll]


def mesh_flags(mesh):
    values = {name: mesh.get_editor_property(name) for name in PROPERTIES}
    values['shadow_cache_invalidation_behavior'] = str(values['shadow_cache_invalidation_behavior'])
    return values


def state(name):
    rows = []
    for actor, mesh in parts:
        mids = []
        for i in range(mesh.get_num_materials()):
            material = mesh.get_material(i)
            if isinstance(material, u.MaterialInstanceDynamic):
                mids.append(material.get_scalar_parameter_value('RoofOpenProgress'))
        rows.append(dict(actor=actor.get_name(), mesh=mesh.get_name(),
                         hidden=actor.get_editor_property('hidden'), flags=mesh_flags(mesh),
                         material_progress=mids))
    return dict(name=name, camera=camera(), phase=roof.get_transition_phase(),
                progress=roof.get_open_progress(), parts=rows)


def png_ready(path):
    if not path.exists():
        return False
    raw = path.read_bytes()
    return len(raw)>24 and raw[-12:] == bytes.fromhex('0000000049454e44ae426082')


def capture(name):
    item = state(name)
    path = OUT/(name+'.png')
    # Remove only this script's previous capture so stale output cannot pass.
    if path.exists():
        path.unlink()
    console('Shot showui filename="'+path.as_posix()+'" -nosuffix')
    yield from wait('screenshot_'+name, lambda: png_ready(path), 20)
    raw = path.read_bytes()
    assert struct.unpack('>II', raw[16:24]) == (1920, 1080)
    item.update(path=str(path), sha256=hashlib.sha256(raw).hexdigest())
    report['states'].append(item)
    write()


def run():
    yield from wait('discover', discover, 90)
    yield from wait('camera_settled', lambda: not pawn.is_pose_transition_active())
    for command in ('DisableAllScreenMessages', 't.MaxFPS 60', 'r.VSync 0',
                    't.IdleWhenNotForeground 0', 'Slate.bAllowThrottling 0'):
        console(command)
    tag = 'GHS_WarehouseRoof' if GHS else 'MPR_Roof'
    for actor in u.GameplayStatics.get_all_actors_of_class(world, u.Actor):
        if tag in [str(t) for t in actor.tags]:
            for mesh in actor.get_components_by_class(u.StaticMeshComponent):
                if mesh.static_mesh:
                    parts.append((actor, mesh))
    assert parts, 'No tagged roof components'
    roof.restore_roof(False)
    yield from pause(8)
    original = [mesh_flags(mesh) for _, mesh in parts]
    fixed = camera()
    yield from capture('01_closed')
    u.GameplayStatics.set_global_time_dilation(world, .08)
    assert roof.open_roof(False)
    yield from wait('half_open', lambda: roof.get_open_progress() >= .49)
    roof.set_component_tick_enabled(False)
    u.GameplayStatics.set_global_time_dilation(world, 1)
    yield from pause(2)
    yield from capture('02_half_open')
    active = [mesh_flags(mesh) for _, mesh in parts]
    check('scan_shadows_invalidate_each_frame', all('ALWAYS' in f['shadow_cache_invalidation_behavior'].upper() for f in active))
    check('scan_releases_full_roof_indirect_occlusion', all(not f['affect_distance_field_lighting'] and
          not f['affect_dynamic_indirect_lighting'] and not f['visible_in_ray_tracing'] for f in active))
    check('scan_keeps_authored_direct_shadows', all(a['cast_shadow'] == b['cast_shadow'] for a,b in zip(active,original)))
    roof.set_component_tick_enabled(True)
    yield from wait('fully_open', lambda: roof.is_interior_available())
    yield from pause(3)
    yield from capture('03_open')
    opened = [mesh_flags(mesh) for _, mesh in parts]
    check('open_roof_cannot_cast_hidden_shadow', all(not f['cast_shadow'] and not f['cast_hidden_shadow'] for f in opened))
    check('open_roof_cannot_occlude_indirect_light', all(not f['affect_distance_field_lighting'] and
          not f['affect_dynamic_indirect_lighting'] and not f['affect_indirect_lighting_while_hidden'] and
          not f['visible_in_ray_tracing'] for f in opened))
    roof.restore_roof(True)
    yield from wait('restored', lambda: roof.is_roof_closed())
    yield from pause(3)
    yield from capture('04_restored')
    check('restore_preserves_all_authored_lighting_flags', original == [mesh_flags(mesh) for _,mesh in parts])
    check('all_views_share_fixed_camera', all(max(abs(a-b) for a,b in zip(fixed,s['camera'])) < .05 for s in report['states']))
    check('saved_map_unchanged', hashlib.sha256(MAP_FILE.read_bytes()).hexdigest() == report['map_sha256'])
    check('closed_idle_does_not_tick', not roof.is_component_tick_enabled())
    report['regression_passed'] = all(c['passed'] for c in report['checks'])
    report.update(success=BASELINE or report['regression_passed'], stage='complete')
    write()


def finish(error=None):
    global done
    done = True
    if error:
        report.update(success=False, error=error)
    if world:
        u.GameplayStatics.set_global_time_dilation(world, 1)
        if roof:
            roof.restore_roof(False)
    write()
    if handle is not None:
        u.unregister_slate_post_tick_callback(handle)
    if world:
        u.SystemLibrary.quit_game(world, pc, u.QuitPreference.QUIT, False)


steps = run()


def tick(delta):
    global busy
    if done or busy:
        return
    busy = True
    try:
        assert time.monotonic()-START < 150, 'Roof lighting verification deadline'
        next(steps)
    except StopIteration:
        finish()
    except Exception:
        finish(traceback.format_exc())
    finally:
        busy = False


handle = u.register_slate_post_tick_callback(tick)
