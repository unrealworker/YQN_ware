"""Validate the header in an owned offscreen game without saving scene assets."""
import datetime
import hashlib
import json
from pathlib import Path
import re
import time
import traceback
import unreal

ROOT = Path('D:/UEPro/Test')
OUT = ROOT / 'Saved/AddressClock'
CLI = unreal.SystemLibrary.get_command_line()
assert all(re.search(r'(?:^|\s)-' + flag + r'(?=\s|$)', CLI, re.I) for flag in ('game', 'RenderOffscreen', 'TwinDiagnostics'))
OUT.mkdir(parents=True, exist_ok=True)
MAP = ROOT / 'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'
map_hash = hashlib.sha256(MAP.read_bytes()).hexdigest()
result = dict(success=False, checks=[], captures=[])
world = pc = hud = pawn = None
started = time.monotonic()
handle = None
stage = 'discover'

def write():
    (OUT / 'runtime.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')

def state():
    return json.loads(hud.get_poi_report())

def clock():
    return state()['warehouseClock']

def record(name, **values):
    result['checks'].append(dict(name=name, **values))
    write()

def wait(name, condition, timeout=30):
    global stage
    stage = name
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, 'Timed out: ' + name
        yield

def pause(seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        yield

def discover():
    global world, pc, hud, pawn
    for candidate in unreal.ObjectIterator(unreal.World):
        if not candidate.get_path_name().startswith('/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.'):
            continue
        controller = unreal.GameplayStatics.get_player_controller(candidate, 0)
        widget = getattr(controller, 'twin_hud_widget', None) if controller else None
        if widget and widget.browser_ready:
            world, pc, hud, pawn = candidate, controller, widget, controller.get_controlled_pawn()
            return bool(clock()['time'])
    return False

def capture(name):
    path = OUT / (name + '.png')
    old = path.stat().st_mtime_ns if path.exists() else 0
    unreal.SystemLibrary.execute_console_command(world, 'Shot showui filename="' + path.as_posix() + '" -nosuffix', pc)
    yield from wait(name, lambda: path.exists() and path.stat().st_mtime_ns != old)
    result['captures'].append(str(path))
    write()

def verify_time():
    current = clock()
    assert current['zone'] == 'America/Los_Angeles'
    match = re.fullmatch(r'(\d{4}\.\d{2}\.\d{2}) · (PDT|PST) \(UTC−(07|08):00\)', current['date'])
    assert match, current
    assert (match[2], match[3]) in (('PDT', '07'), ('PST', '08'))
    shown = datetime.datetime.strptime(match[1] + ' ' + current['time'], '%Y.%m.%d %H:%M:%S')
    utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    assert abs((shown + datetime.timedelta(hours=int(match[3])) - utc).total_seconds()) < 2, current
    return current

def run():
    yield from wait('discover', discover, 90)
    unreal.SystemLibrary.execute_console_command(world, 'DisableAllScreenMessages', pc)
    yield from wait('initial_camera', lambda: not pawn.is_pose_transition_active())
    yield from pause(2)
    before = verify_time()
    yield from wait('clock_ticks', lambda: clock()['time'] != before['time'], 4)
    record('real_wall_time_ticks', before=before, after=verify_time())
    assert pc.warehouse_roof.is_roof_closed()
    assert [p['id'] for p in state()['labels']] == ['WAREHOUSE:GHS']
    yield from capture('01_2560x1600')

    # The runtime clock follows wall time even when the 3D simulation pauses.
    assert unreal.GameplayStatics.set_game_paused(world, True)
    paused_time = clock()['time']
    yield from wait('paused_wall_clock', lambda: clock()['time'] != paused_time, 4)
    assert unreal.GameplayStatics.set_game_paused(world, False)
    record('clock_continues_while_scene_paused', after=verify_time())

    for width, height in ((1024, 768), (800, 900), (390, 844)):
        unreal.SystemLibrary.execute_console_command(world, f'r.SetRes {width}x{height}w', pc)
        yield from wait('resize_' + str(width), lambda: pc.get_viewport_size() == (width, height))
        yield from pause(1)
        info = verify_time()
        assert int(info['width']) == width, info
        expected = 64 if width >= 1000 else 112 if width >= 640 else 168
        assert info['headerHeight'] == expected, info
        for x, y in ((info['addressX']+100, info['addressY']+24), (info['clockX']+180, info['clockY']+24)):
            point = unreal.Vector2D(x, y)
            assert not hud.is_scene_point(point)
            assert not hud.handle_chrome_click(point), 'Informational header opened the panel'
        toggle = unreal.Vector2D(width-64, 26 if width<1000 else 32)
        initial = hud.get_panel_transition_progress()
        assert hud.handle_chrome_click(toggle)
        yield from pause(.5)
        assert abs(hud.get_panel_transition_progress()-initial)>.8
        assert hud.handle_chrome_click(toggle)
        yield from pause(.5)
        record('responsive_header_'+str(width), clock=info)
        yield from capture('width_'+str(width))

    assert hashlib.sha256(MAP.read_bytes()).hexdigest() == map_hash
    record('map_unchanged', sha256=map_hash)

def finish(error=None):
    result['success'] = error is None
    result['elapsed_seconds'] = time.monotonic()-started
    if error:
        result.update(error=error, stage=stage)
    write()
    unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log_error if error else unreal.log)('GHS_ADDRESS_CLOCK_RUNTIME ' + json.dumps(result, ensure_ascii=False))
    if world:
        unreal.GameplayStatics.set_game_paused(world, False)
        unreal.SystemLibrary.quit_game(world, pc, unreal.QuitPreference.QUIT, False)

steps = run()
def tick(delta):
    try:
        assert time.monotonic()-started < 180, 'Runtime acceptance timeout'
        next(steps)
    except StopIteration:
        finish()
    except Exception:
        finish(traceback.format_exc())
handle = unreal.register_slate_post_tick_callback(tick)
