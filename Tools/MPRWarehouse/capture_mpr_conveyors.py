"""Capture MPR conveyor before/after with identical native runtime cameras.

Owned offscreen game only. Never saves assets or the level. Run a second time
with -MPRConveyorAfter after the scoped conveyor repair has been saved.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, re, sys, time, traceback
import unreal as u

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
import profile_mpr_runtime as timing

CLI = u.SystemLibrary.get_command_line()
assert all(re.search(r'(?:^|\s)-' + f + r'(?=\s|$)', CLI, re.I)
           for f in ('own', 'game', 'RenderOffscreen'))
AFTER = bool(re.search(r'(?:^|\s)-MPRConveyorAfter(?=\s|$)', CLI, re.I))
OUT = ROOT / 'Saved/MPR/conveyor_repair_20261106' / ('after' if AFTER else 'before')
OUT.mkdir(parents=True, exist_ok=True)
MAP = '/Game/Maps/MPR_CAD_Warehouse_B50B57'
MAP_FILE = ROOT / 'Content/Maps/MPR_CAD_Warehouse_B50B57.umap'
STAMP = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
VIEWS = [
    dict(name='workflow_overview', pivot=[-11200, 1000, 180], distance=14000, pitch=-50, yaw=-80),
    dict(name='east_branches', pivot=[-8930, 1150, 95], distance=1700, pitch=-52, yaw=-100),
    dict(name='west_mirrored_stations', pivot=[-15670, -6100, 95], distance=1200, pitch=-45, yaw=-80),
    dict(name='east_plan', pivot=[-8930, 1150, 95], distance=1800, pitch=-89, yaw=-90),
    dict(name='mirrored_curve_pair', pivot=[10535, -5934, 100], distance=2600, pitch=-65, yaw=-90),
    dict(name='v_roller_merge', pivot=[-9513, -3389, 100], distance=800, pitch=-65, yaw=-90),
]
# These are AFTER-only inspection views for recovered source linework. They
# never replace the original six comparison cameras or mutate the baseline.
SUPPLEMENTAL_VIEWS = [
    dict(name='north_feed_lines_complete', pivot=[10550, -5985, 125], distance=6800, pitch=-70, yaw=-90),
    dict(name='third_feed_line_complete', pivot=[5940, -5750, 125], distance=3400, pitch=-70, yaw=-90),
]
report = dict(success=False, run_id=STAMP, phase='after' if AFTER else 'before',
              resolution=[1920, 1080], views=VIEWS, captures=[], assets_saved=False,
              supplemental_views=SUPPLEMENTAL_VIEWS if AFTER else [],
              matched_before_view_count=0,
              map_before=hashlib.sha256(MAP_FILE.read_bytes()).hexdigest())
world = pc = pawn = roof = post = handle = None
done = busy = False
started = time.monotonic()


def write():
    (OUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


def console(value):
    u.SystemLibrary.execute_console_command(world, value, pc)


def pose():
    camera = pc.player_camera_manager
    p, r = camera.get_camera_location(), camera.get_camera_rotation()
    return [p.x, p.y, p.z, r.pitch, r.yaw, r.roll]


def pause(seconds):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        yield


def wait(name, predicate, seconds=45):
    report['stage'] = name
    write()
    end = time.monotonic() + seconds
    while not predicate():
        assert time.monotonic() < end, name
        yield


def discover():
    global world, pc, pawn, roof, post
    for candidate in u.ObjectIterator(u.World):
        if not candidate.get_path_name().startswith(MAP + '.'):
            continue
        controller = u.GameplayStatics.get_player_controller(candidate, 0)
        if not controller or not controller.get_editor_property('twin_hud_widget'):
            continue
        world, pc = candidate, controller
        pawn, roof = controller.get_controlled_pawn(), controller.warehouse_roof
        volumes = [a for a in u.GameplayStatics.get_all_actors_of_class(world, u.PostProcessVolume)
                   if a.get_actor_label() == 'MPR4_ReferenceStyle']
        assert len(volumes) == 1
        post = volumes[0]
        return roof.has_roof()
    return False


def set_view(view):
    pawn.focus_on_target(u.Vector(*view['pivot']), view['distance'],
                         u.Rotator(pitch=view['pitch'], yaw=view['yaw']),
                         u.Vector2D(1920, 1080), u.Vector2D(960, 540), 0)


def capture(view, supplemental=False):
    path = OUT / (view['name'] + '_' + STAMP + '.png')
    console('Shot showui filename="' + path.as_posix() + '" -nosuffix')
    yield from wait(view['name'], lambda: timing.png_ready(path))
    report['captures'].append(dict(name=view['name'], camera=pose(), path=str(path),
                                   comparison_group='after_only' if supplemental else 'matched',
                                   sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    write()


def run():
    yield from wait('discover', discover)
    for command in ('DisableAllScreenMessages', 't.MaxFPS 0', 'r.VSync 0',
                    't.IdleWhenNotForeground 0', 'Slate.bAllowThrottling 0',
                    'csv.CompressionMode 0', 'r.GPUCsvStatsEnabled 1'):
        console(command)
    settings = post.get_editor_property('settings')
    report['exposure'] = {key: str(settings.get_editor_property(key)) for key in (
        'auto_exposure_method', 'auto_exposure_min_brightness',
        'auto_exposure_max_brightness', 'auto_exposure_bias', 'bloom_intensity')}
    assert abs(settings.get_editor_property('auto_exposure_min_brightness') - .6) < 1e-5
    assert abs(settings.get_editor_property('auto_exposure_max_brightness') - .6) < 1e-5
    yield from pause(8)
    assert roof.open_roof()
    yield from wait('open_roof', roof.is_interior_available)
    for view in VIEWS:
        set_view(view)
        yield from pause(4)
        yield from capture(view)
    if AFTER:
        before = json.loads((OUT.parent / 'before/report.json').read_text(encoding='utf8'))
        assert before['success'] and before['views'] == VIEWS
        assert len(before['captures']) == len(VIEWS) == 6
        assert len(report['captures']) == len(VIEWS)
        assert before['exposure'] == report['exposure']
        for previous, current in zip(before['captures'], report['captures']):
            assert previous['name'] == current['name']
            assert max(abs(a-b) for a, b in zip(previous['camera'], current['camera'])) < 1e-4
        report['matching_before_cameras'] = True
        report['matched_before_view_count'] = len(VIEWS)
        for view in SUPPLEMENTAL_VIEWS:
            set_view(view)
            yield from pause(4)
            yield from capture(view, supplemental=True)
        set_view(VIEWS[0])
        yield from pause(8)
        filename = 'MPR_CONVEYOR_' + STAMP + '.csv'
        path = ROOT / 'Saved/Profiling/CSV' / filename
        console('CsvProfile STARTFILE=' + filename)
        console('CsvProfile START')
        yield from pause(15)
        console('CsvProfile STOP')
        yield from wait('native_csv', lambda: timing.csv_complete(path))
        report['performance'] = timing.parse_csv(path)
        report['performance']['fps'] = (report['performance']['frame_count'] /
                                         report['performance']['native_frame_time_seconds'])
    report.update(success=True, stage='complete')


def finish(error=None):
    global done
    done = True
    if error:
        report.update(success=False, error=error)
    if roof:
        roof.restore_roof(False)
    report['map_unchanged'] = hashlib.sha256(MAP_FILE.read_bytes()).hexdigest() == report['map_before']
    report['success'] = report['success'] and report['map_unchanged']
    write()
    if handle is not None:
        u.unregister_slate_post_tick_callback(handle)
    if world:
        console('CsvProfile STOP')
        u.SystemLibrary.quit_game(world, pc, u.QuitPreference.QUIT, False)


steps = run()


def tick(delta):
    global busy
    if done or busy:
        return
    busy = True
    try:
        assert time.monotonic() - started < 180, 'capture timeout'
        next(steps)
    except StopIteration:
        finish()
    except Exception:
        finish(traceback.format_exc())
    finally:
        busy = False


handle = u.register_slate_post_tick_callback(tick)
