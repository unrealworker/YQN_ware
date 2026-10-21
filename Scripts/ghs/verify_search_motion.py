"""Verify actual UMG search geometry in an owned offscreen game process.

Launch with -game -RenderOffscreen -TwinDiagnostics -ResX=1920 -ResY=1080.
No editor asset mutation, simulated OS input, or legacy occupancy assertions.
The native scene-click routes are exercised at the moving search bounds.
"""
import json
import math
import re
import struct
import time
import traceback
from pathlib import Path

import unreal

ROOT = Path(r'D:/UEPro/Test')
CLI = unreal.SystemLibrary.get_command_line()
for flag in ('game', 'RenderOffscreen', 'TwinDiagnostics'):
    assert re.search(r'(?:^|\s)-' + flag + r'(?:\s|$)', CLI, re.I), flag
OUT = ROOT / 'Saved/DockNumbers'
OUT.mkdir(parents=True, exist_ok=True)
REPORT = OUT / 'search_runtime.json'
START = time.monotonic()
world = pc = pawn = widget = handle = None
step = 0
current_size = (1920, 1080)
motion = pending_capture = None
result = dict(success=False, checks=[], motion_segments=[], captures=[], assets_saved=False,
              input_scope='Actual UMG geometry and native scene-click routes; no OS input simulation')


def xy(value):
    return [float(value.x), float(value.y)]


def distance(a, b):
    return math.sqrt(sum((x-y)**2 for x, y in zip(a, b)))


def write():
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


def record(name, **values):
    result['checks'].append(dict(name=name, passed=True, **values))
    write()
    unreal.log('SEARCH_MOTION_CHECK ' + name)


def browser():
    text = widget.get_editor_property('last_browser_report')
    return json.loads(text) if text else {}


def selected():
    return str(widget.get_editor_property('selected_id'))


def sample():
    panel = widget.get_panel_visual_position()
    panel_size = widget.get_panel_visual_size()
    tool = widget.get_scene_controls_position()
    search = widget.get_scene_search_position()
    search_size = widget.get_scene_search_size()
    visible = bool(widget.is_scene_search_visible())
    progress = float(widget.get_panel_transition_progress())
    assert all(math.isfinite(v) for v in xy(panel)+xy(tool)+xy(search)+xy(search_size))
    expanded_scene_width = current_size[0] if current_size[0] < 900 else current_size[0]-panel_size.x
    assert visible == (expanded_scene_width >= 600), ('Search visibility changed during slide', current_size, visible, progress)
    assert abs(search_size.x-max(0, min(360, expanded_scene_width-160))) < .1
    assert abs(search_size.y-36) < .1
    assert abs(search.y-((52 if current_size[0] < 700 else 64)+16)) < .1
    if current_size[0] >= 900:
        assert abs(tool.x+60-panel.x) < .1, ('Toolbar detached from drawer', tool, panel, progress)
        assert abs(tool.y-(current_size[1]-132)) < .1
        if visible:
            assert abs(search.x+search_size.x+24-panel.x) < .1, ('Search detached from drawer', search, panel, progress)
            assert abs(search.x+324-tool.x) < .1, ('Search and toolbar disagree', search, tool)
    else:
        assert abs(tool.x-(current_size[0]-60)) < .1
        assert abs(tool.y-(panel.y-132)) < .1
        assert abs(search.x-(current_size[0]-384)) < .1
    if visible:
        assert search.x >= 140 and search.x+search_size.x <= current_size[0]-24+.1
        assert search.y+search_size.y <= panel.y if current_size[0] < 900 else True
        center = unreal.Vector2D(search.x+search_size.x*.5, search.y+search_size.y*.5)
        assert not widget.is_scene_point(center), 'Visible search passes input through to the scene'
        assert not widget.handle_chrome_click(center), 'Visible search overlaps a native chrome action'
    return dict(at_seconds=time.monotonic()-START,
                game_seconds=unreal.GameplayStatics.get_time_seconds(world), progress=progress,
                panel=xy(panel), panel_size=xy(panel_size), controls=xy(tool), search=xy(search),
                search_size=xy(search_size), search_visible=visible, selected=selected())


def discover():
    global world, pc, pawn, widget
    for candidate in unreal.ObjectIterator(unreal.World):
        controller = unreal.GameplayStatics.get_player_controller(candidate, 0)
        if controller and hasattr(controller, 'twin_hud_widget'):
            hud = controller.get_editor_property('twin_hud_widget')
            if hud:
                world, pc, widget = candidate, controller, hud
                pawn = pc.get_controlled_pawn()
                break
    if not widget or not widget.get_editor_property('browser_ready') or not browser():
        return False
    assert 'GHS_CAD_NormalWarehouse' in world.get_name() and 'ZcoolSmartFactory' in world.get_name()
    for method in ('get_scene_search_position', 'get_scene_search_size', 'is_scene_search_visible'):
        assert hasattr(widget, method), 'Rebuild native search changes before running acceptance: '+method
    if pawn.is_pose_transition_active():
        return False
    assert tuple(pc.get_viewport_size()) == current_size, pc.get_viewport_size()
    unreal.SystemLibrary.execute_console_command(world, 't.MaxFPS 60', pc)
    record('owned_game_browser_and_search_ready', map=world.get_path_name(), sample=sample())


def check_layout():
    if tuple(pc.get_viewport_size()) != current_size or pawn.is_pose_transition_active():
        return False
    panel, size = widget.get_panel_visual_position(), widget.get_panel_visual_size()
    if abs(panel.x+size.x-current_size[0]) > .1 or abs(panel.y+size.y-current_size[1]) > .1:
        return False
    if widget.get_panel_transition_progress() != 1 or browser().get('overflow'):
        return False
    record('expanded_search_layout', resolution=list(current_size), sample=sample())


def select_fixture():
    assert widget.select_object('AGV-07', False), 'AGV-07 fixture absent'


def wait_fixture():
    report = browser()
    if (report.get('detail') or {}).get('id') != 'AGV-07' or report.get('transition', {}).get('phase') != 'idle':
        return False
    assert selected() == 'AGV-07'


def toggle():
    assert widget.handle_chrome_click(unreal.Vector2D(current_size[0]-30, 25))


def begin_motion(name, opening):
    global motion
    assert motion is None
    before = sample()
    motion = dict(name=name, opening=opening, resolution=list(current_size),
                  samples=[before], search_click_protected=False)
    toggle()
    after = sample()
    for field in ('panel', 'controls', 'search'):
        assert distance(before[field], after[field]) < .01, ('Toggle teleported '+field, before, after)


def sample_motion():
    if motion is None:
        return
    row = sample()
    motion['samples'].append(row)
    if row['search_visible'] and not motion['search_click_protected'] and .15 < row['progress'] < .85:
        center = unreal.Vector2D(row['search'][0]+row['search_size'][0]*.5,
                                 row['search'][1]+row['search_size'][1]*.5)
        before = selected()
        assert not widget.handle_scene_click(center), 'Moving search click fell through to scene selection'
        assert selected() == before, 'Moving search click changed selection'
        motion['search_click_protected'] = True
        record('moving_search_click_is_protected', segment=motion['name'], progress=row['progress'],
               position=xy(center), selection=before)
        # One midpoint screenshot is enough; frame-by-frame validation continues
        # while the renderer writes it, so capture latency cannot conceal a snap.
        if current_size == (1920, 1080) and motion['name'] == 'desktop_close' and pending_capture is None:
            capture('desktop_close_midpoint')


def finish_motion(endpoint=True):
    global motion
    assert motion is not None
    samples = motion['samples']
    if endpoint and samples[-1]['progress'] != (1. if motion['opening'] else 0.):
        return False
    assert any(.01 < row['progress'] < .99 for row in samples), ('Missing intermediate frames', motion['name'])
    for previous, current in zip(samples, samples[1:]):
        panel_delta = current['panel'][0]-previous['panel'][0]
        assert panel_delta <= .05 if motion['opening'] else panel_delta >= -.05
        if current_size[0] >= 900:
            assert abs((current['controls'][0]-previous['controls'][0])-panel_delta) < .1, 'Toolbar skipped an animation frame'
            if current['search_visible']:
                assert abs((current['search'][0]-previous['search'][0])-panel_delta) < .1, 'Search skipped an animation frame or snapped at the end'
        else:
            for field in ('search', 'controls'):
                assert distance(current[field], previous[field]) < .1, 'Narrow '+field+' jumped during horizontal bottom-sheet slide'
        assert current['search_visible'] == samples[0]['search_visible'], 'Search appeared/disappeared during slide'
        assert current['search_size'] == samples[0]['search_size'], 'Search resized during slide'
        assert current['selected'] == samples[0]['selected'], 'Panel movement changed selection'
    if samples[0]['search_visible']:
        assert motion['search_click_protected'], ('Moving search click was not exercised', motion['name'])
    result['motion_segments'].append(motion)
    record('search_slide_'+motion['name'], resolution=list(current_size), frames=len(samples),
           first=samples[0], last=samples[-1])
    motion = None


def reverse_midflight():
    if not .2 < motion['samples'][-1]['progress'] < .8:
        assert motion['samples'][-1]['progress'] > 0, 'Missed reversal before collapse completed'
        return False
    before = sample()
    prefix = motion['name'].replace('_partial_close', '')
    finish_motion(False)
    begin_motion(prefix+'_reversed_open', True)
    after = sample()
    for field in ('search', 'controls', 'panel'):
        assert distance(before[field], after[field]) < .01, 'Mid-flight reversal teleported '+field


def capture(label):
    global pending_capture
    assert pending_capture is None
    path = OUT / f'search_{current_size[0]}x{current_size[1]}_{label}.png'
    pending_capture = (path, time.time(), time.monotonic(), current_size)
    unreal.SystemLibrary.execute_console_command(world, f'Shot showui filename="{path.as_posix()}" -nosuffix', pc)


def capture_ready():
    global pending_capture
    path, requested, started, expected = pending_capture
    if not path.exists() or path.stat().st_mtime < requested or path.stat().st_size < 10000:
        assert time.monotonic()-started < 30, ('Screenshot timeout', str(path))
        return False
    data = path.read_bytes()
    assert data[:8] == b'\x89PNG\r\n\x1a\n'
    dimensions = struct.unpack('>II', data[16:24])
    assert dimensions == expected, (dimensions, expected)
    result['captures'].append(dict(path=str(path), size=list(dimensions)))
    pending_capture = None
    write()
    return True


def resize(width, height):
    global current_size
    assert motion is None and pending_capture is None
    current_size = (width, height)
    unreal.SystemLibrary.execute_console_command(world, f'r.SetRes {width}x{height}w', pc)


steps = [('discover', discover), ('desktop_layout', check_layout),
         ('desktop_default_capture', lambda: capture('default')),
         ('select_fixture', select_fixture), ('selected_ready', wait_fixture)]


def add_resolution_steps(prefix):
    steps.extend([
        (prefix+'_close_start', lambda: begin_motion(prefix+'_close', False)),
        (prefix+'_closed', finish_motion),
        (prefix+'_open_start', lambda: begin_motion(prefix+'_open', True)),
        (prefix+'_opened', finish_motion),
        (prefix+'_partial_start', lambda: begin_motion(prefix+'_partial_close', False)),
        (prefix+'_reverse', reverse_midflight), (prefix+'_reversed', finish_motion)])


add_resolution_steps('desktop')
steps += [('desktop_final_capture', lambda: capture('expanded'))]
for prefix, width, height in (('narrow', 600, 900), ('desktop_900', 900, 700), ('desktop_960', 960, 768)):
    steps += [(prefix+'_resize', lambda w=width, h=height: resize(w, h)), (prefix+'_layout', check_layout)]
    add_resolution_steps(prefix)
steps += [('restore_desktop', lambda: resize(1920, 1080)), ('restored_desktop_layout', check_layout)]


def finish(error=None):
    result.update(success=error is None, error=error,
                  failed_step=steps[step][0] if error and step < len(steps) else None,
                  elapsed_seconds=time.monotonic()-START)
    if motion:
        result['unfinished_motion'] = motion
    write()
    if handle:
        unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log_error if error else unreal.log)('SEARCH_MOTION_' + ('FAILED '+str(error) if error else 'SUCCESS'))
    if world:
        unreal.SystemLibrary.execute_console_command(world, 'quit', pc)


def tick(delta_seconds):
    global step
    try:
        assert time.monotonic()-START < 210, 'Search motion acceptance timeout'
        sample_motion()
        if pending_capture and not capture_ready():
            return
        if step >= len(steps):
            finish()
            return
        _, action = steps[step]
        if action() is not False:
            step += 1
    except Exception:
        finish(traceback.format_exc())


write()
handle = unreal.register_slate_post_tick_callback(tick)
