"""Exercise continuous rotation in an explicitly owned offscreen globe game."""
from pathlib import Path
import hashlib, json, re, time, traceback
import unreal as u

CLI = u.SystemLibrary.get_command_line()
assert all(re.search(r'(?:^|\s)-' + flag + r'(?=\s|$)', CLI, re.I)
           for flag in ('game', 'RenderOffscreen', 'GlobeContinuousRotationCheck'))
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'Saved/GlobeContinuousRotation/result.json'
OUT.parent.mkdir(parents=True, exist_ok=True)
MAPS = [ROOT / 'Content/Maps' / name for name in
        ('GHS_GlobalWarehouse.umap', 'MPR_CAD_Warehouse_B50B57.umap')]
def hashes(): return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in MAPS}
before = hashes()
started = time.monotonic()
world = pc = handle = None
busy = done = False
report = dict(success=False, checks=[], samples=[], stage='discover')
def write(): OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
def state(): return json.loads(pc.get_state())
def now(): return u.GameplayStatics.get_time_seconds(world)
def command(action, **args): pc.command(json.dumps(dict(action=action, **args)))
def yaw(): return state()['camera']['globeYaw']
def delta(a, b): return (b - a + 180) % 360 - 180
def check(name, passed, details=None):
    report['checks'].append(dict(name=name, passed=bool(passed), details=details)); write()
    assert passed, (name, details)
def pause(seconds):
    end = now() + seconds
    while now() < end: yield
def wait(name, predicate, seconds=60):
    report['stage'] = name; write(); end = time.monotonic() + seconds
    while not predicate():
        assert time.monotonic() < end, ('Timeout', name)
        if pc: assert state()['phase'] != 'error', state()
        yield
def discover():
    global world, pc
    for w in u.ObjectIterator(u.World):
        if not w.get_path_name().startswith('/Game/Maps/GHS_GlobalWarehouse.'): continue
        c = u.GameplayStatics.get_player_controller(w, 0)
        if c and c.get_class().get_name() == 'GHSGlobePlayerController':
            world, pc = w, c
            return state()['phase'] == 'idle'
    return False
def sample(name, action=None, rotating=True):
    report['stage'] = name; write()
    start = previous_time = now(); previous = yaw(); travel = 0; advances = []
    while now() - start < 1.0:
        command('interaction', active=True)
        if action: action()
        yield
        current_time = now(); current = yaw(); step = delta(previous, current)
        if current_time > previous_time + 1.e-5: advances.append(step)
        travel += step; previous, previous_time = current, current_time
        report['samples'].append(dict(test=name, time=current_time, yaw=current, phase=state()['phase']))
    expected = pc.get_editor_property('idle_rotation_degrees_per_second') * (now() - start)
    details = dict(travel=travel, expected=expected, frames=len(advances), stalled=sum(abs(s) < 1.e-5 for s in advances))
    moving = bool(advances) and details['stalled'] <= 1 and all(s >= -1.e-4 for s in advances)
    check(name, moving and abs(travel - expected) < max(.15, abs(expected) * .2)
          if rotating else abs(travel) < .001, details)
def run():
    yield from wait('discover', discover, 30); yield from pause(3)
    u.SystemLibrary.execute_console_command(world, 't.MaxFPS 60', pc)
    command('reducedMotion', enabled=False)
    yield from sample('interaction remains active')
    yield from sample('continuous drag', lambda: command('orbit', dx=.3, dy=0))
    zoom_sign = [1]
    def zoom():
        command('zoom', steps=zoom_sign[0] * .02); zoom_sign[0] *= -1
    yield from sample('continuous zoom', zoom)
    for warehouse in ('ghs-ca', 'mpr-nj'):
        command('select', id=warehouse, inputSource='pointer')
        yield from sample('selected ' + warehouse)
        yield from sample('repeated selection ' + warehouse,
                          lambda: command('select', id=warehouse, inputSource='pointer'))
    command('clear'); yield from sample('clear selection resumes without cooldown')
    command('home'); yield from pause(.9)
    yield from sample('home completes without cooldown')
    command('reducedMotion', enabled=True)
    yield from sample('explicit reduced motion stops rotation', rotating=False)
    command('reducedMotion', enabled=False)
    if re.search(r'(?:^|\s)-GlobeRotationTransitions(?=\s|$)', CLI, re.I):
        command('enter', id='mpr-nj', inputSource='pointer')
        yield from wait('flight', lambda: state()['phase'] == 'flying')
        flight_yaw = yaw()
        while state()['phase'] == 'flying':
            assert abs(delta(flight_yaw, yaw())) < .001, 'Flight target moved with globe'
            yield
        check('flight keeps its geographic destination fixed', True)
        yield from wait('warehouse arrival', lambda: state()['phase'] == 'warehouse')
        command('back', inputSource='pointer')
        yield from wait('return', lambda: state()['phase'] == 'selected')
        yield from sample('return resumes immediately with selected warehouse')
    check('probe does not save scene files', hashes() == before)
    report['stage'] = 'complete'
def finish(error=None):
    global done
    done = True; report.update(success=error is None, error=error, elapsed=time.monotonic()-started); write()
    if handle is not None: u.unregister_slate_post_tick_callback(handle)
    if world: u.SystemLibrary.quit_game(world, pc, u.QuitPreference.QUIT, False)
steps = run()
def tick(dt):
    global busy
    if busy or done: return
    busy = True
    try:
        assert time.monotonic()-started < 150, 'Overall timeout'
        next(steps)
    except StopIteration: finish()
    except Exception: finish(traceback.format_exc())
    finally: busy = False
handle = u.register_slate_post_tick_callback(tick)
