"""Runtime controls acceptance in an owned -game -RenderOffscreen process.

Launch at 1920x1080 with -TwinDiagnostics and execute using -ExecCmds="py ...".
Samples actual widget geometry on every Slate post-tick, resizes to 600x900,
and invokes native widget click routes. This does not synthesize OS middle
button input; InputKey middle-button coverage belongs to the native automation
tests named in the output. No scene or project assets are saved.
"""
import json
import importlib.util
import math
import re
import struct
import time
import traceback
from pathlib import Path

import unreal

ROOT = Path(r'D:/UEPro/Test')
CLI = unreal.SystemLibrary.get_command_line()
assert re.search(r'(?:^|\s)-game(?:\s|$)', CLI, re.I)
assert re.search(r'(?:^|\s)-RenderOffscreen(?:\s|$)', CLI, re.I)
assert re.search(r'(?:^|\s)-TwinDiagnostics(?:\s|$)', CLI, re.I)
OUT = ROOT / 'Saved/SceneRefinements'
OUT.mkdir(parents=True, exist_ok=True)
REPORT = OUT / 'controls_runtime.json'
START = time.monotonic()
world = pc = pawn = widget = handle = None
step = 0
current_size = (1920, 1080)
motion = pending_capture = None
reset_pending = False
result = dict(
    success=False, checks=[], motion_segments=[], captures=[], assets_saved=False,
    input_scope='Native widget click routes; no OS input simulation or OS middle-button claim',
    middle_input_automation_tests=[
        'GHS.WarehouseCamera.Input.MiddleClickResetsOverview',
        'GHS.WarehouseCamera.Input.MiddleClickClearsTwinSelection'],
    middle_input_automation_executed_by_this_script=False)


def xy(value):
    return [float(value.x), float(value.y)]


def xyz(value):
    return [float(value.x), float(value.y), float(value.z)]


def distance(a, b):
    return math.sqrt(sum((x-y)**2 for x, y in zip(a, b)))


def write():
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


def record(name, **values):
    result['checks'].append(dict(name=name, passed=True, **values))
    write()
    unreal.log('SCENE_CONTROLS_CHECK ' + name)


def browser():
    text = widget.get_editor_property('last_browser_report')
    return json.loads(text) if text else {}


def selected():
    return widget.get_editor_property('selected_id')


def sample():
    panel = widget.get_panel_visual_position()
    panel_size = widget.get_panel_visual_size()
    tool = widget.get_scene_controls_position()
    progress = float(widget.get_panel_transition_progress())
    assert all(math.isfinite(v) for v in xy(tool)+xy(panel)), (tool, panel)
    if current_size[0] >= 900:
        assert abs(tool.x+60-panel.x) < .1, ('Controls detached from sliding drawer edge', tool, panel, progress)
        assert abs(tool.y-(current_size[1]-132)) < .1, (tool, current_size)
    else:
        assert abs(tool.x-(current_size[0]-60)) < .1, (tool, current_size)
        assert abs(tool.y-(panel.y-132)) < .1, ('Narrow controls must stay above the bottom sheet', tool, panel)
    assert 0 <= tool.x and tool.x+40 <= current_size[0]+.1
    assert tool.y >= 52 and tool.y+112 <= current_size[1]+.1
    assert widget.is_scene_point(unreal.Vector2D(tool.x+20, tool.y+56)), 'Visible controls are inside blocked browser input bounds'
    return dict(at_seconds=time.monotonic()-START,
                game_seconds=unreal.GameplayStatics.get_time_seconds(world),
                progress=progress, panel=xy(panel), panel_size=xy(panel_size),
                controls=xy(tool), desired_zoom=float(pawn.get_editor_property('desired_zoom')),
                selected=selected())


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
    assert hasattr(widget, 'get_scene_controls_position'), 'Rebuild native controls changes before running acceptance'
    if pawn.is_pose_transition_active():
        return False
    assert tuple(pc.get_viewport_size()) == current_size, pc.get_viewport_size()
    asset_checks_path = ROOT / 'Scripts/ghs/check_scene_refinement_assets.py'
    spec = importlib.util.spec_from_file_location('ghs_scene_refinement_asset_checks', asset_checks_path)
    asset_checks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(asset_checks)
    result['scene_assets'] = asset_checks.check_assets(world, widget)
    record('owned_game_and_browser_ready', map=world.get_path_name(), resolution=list(current_size), sample=sample())


def check_layout():
    if tuple(pc.get_viewport_size()) != current_size or pawn.is_pose_transition_active():
        return False
    position, size = widget.get_panel_visual_position(), widget.get_panel_visual_size()
    if abs(position.x+size.x-current_size[0]) > 1 or abs(position.y+size.y-current_size[1]) > 1:
        return False
    assert widget.get_panel_transition_progress() == 1
    assert not browser().get('overflow'), browser()
    record('expanded_controls_layout', resolution=list(current_size), sample=sample())


def select_fixture():
    assert widget.select_object('AGV-07', True), 'AGV-07 fixture absent'


def wait_fixture():
    if pawn.is_pose_transition_active() or (browser().get('detail') or {}).get('id') != 'AGV-07':
        return False
    assert selected() == 'AGV-07'
    record('selected_device_fixture_ready', resolution=list(current_size), sample=sample())


def toggle():
    assert widget.handle_chrome_click(unreal.Vector2D(current_size[0]-30, 25))


def begin_motion(name, opening, zoom=None):
    global motion
    assert motion is None
    before = sample()
    motion = dict(name=name, opening=opening, resolution=list(current_size),
                  samples=[before], zoom=zoom, zoom_checked=False)
    toggle()
    immediate = sample()
    assert distance(before['panel'], immediate['panel']) < .01, 'Toggle immediately teleported the panel'
    assert distance(before['controls'], immediate['controls']) < .01, 'Toggle immediately teleported controls'


def sample_motion():
    if motion is None:
        return
    current = sample()
    motion['samples'].append(current)
    if motion['zoom'] is not None and not motion['zoom_checked'] and .15 < current['progress'] < .85:
        tool = current['controls']
        original = motion['samples'][0]['controls']
        before = current['desired_zoom']
        button_y = 18 if motion['zoom'] > 0 else 56
        # Once the moving control has left its old location, the old hit area
        # must not keep consuming clicks. Narrow controls intentionally stay put.
        if current_size[0] >= 900 and abs(tool[0]-original[0]) > 45:
            assert not widget.handle_chrome_click(unreal.Vector2D(original[0]+20, original[1]+button_y)), 'Old toolbar hit area remains active'
        assert widget.handle_chrome_click(unreal.Vector2D(tool[0]+20, tool[1]+button_y)), 'Moving toolbar hit area is not clickable'
        after = float(pawn.get_editor_property('desired_zoom'))
        assert after < before if motion['zoom'] > 0 else after > before, (before, after, motion['zoom'])
        assert selected() == 'AGV-07', 'Zoom unexpectedly cleared device selection'
        motion['zoom_checked'] = True
        record('moving_toolbar_zoom_hit_area', segment=motion['name'], progress=current['progress'],
               before_zoom=before, after_zoom=after, point=[tool[0]+20, tool[1]+button_y])
        capture(motion['name']+'_midpoint')


def finish_motion(endpoint=True):
    global motion
    assert motion is not None
    samples = motion['samples']
    if endpoint:
        target = 1. if motion['opening'] else 0.
        if samples[-1]['progress'] != target:
            return False
    assert any(.01 < row['progress'] < .99 for row in samples), ('Missing intermediate animation frames', motion)
    for previous, current in zip(samples, samples[1:]):
        panel_delta = current['panel'][0]-previous['panel'][0]
        assert panel_delta <= .05 if motion['opening'] else panel_delta >= -.05, motion
        if current_size[0] >= 900:
            tool_delta = current['controls'][0]-previous['controls'][0]
            assert abs(tool_delta-panel_delta) < .1, 'Controls skipped an animation frame or jumped at the end'
        else:
            assert distance(current['controls'], previous['controls']) < .1, 'Narrow controls jumped during horizontal bottom-sheet slide'
        assert current['selected'] == samples[0]['selected'], 'Panel movement changed selection'
    if motion['zoom'] is not None:
        assert motion['zoom_checked'], ('No moving-toolbar zoom check was executed', motion['name'])
    result['motion_segments'].append(motion)
    record('controls_slide_'+motion['name'], resolution=list(current_size), frames=len(samples),
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
    assert distance(before['controls'], sample()['controls']) < .01, 'Mid-flight reversal teleported controls'


def reset_button():
    global reset_pending
    assert selected() == 'AGV-07'
    assert widget.get_panel_transition_progress() == 1
    tool = widget.get_scene_controls_position()
    assert widget.handle_chrome_click(unreal.Vector2D(tool.x+20, tool.y+92)), 'Reset button is not clickable at its visible location'
    assert not selected(), 'Reset must clear selected device immediately'
    reset_pending = True


def wait_reset():
    global reset_pending
    assert reset_pending
    report = browser()
    if pawn.is_pose_transition_active() or report.get('detail') is not None or report.get('transition', {}).get('phase') != 'idle':
        return False
    assert not selected()
    assert json.loads(widget.get_snapshot()).get('selection') is None
    labels = json.loads(widget.get_poi_report())['labels']
    assert not any(row['selected'] for row in labels), 'Reset retained a selected POI'
    assert not pawn.uses_object_pivot()
    assert distance(xyz(pawn.get_actor_location()), xyz(pawn.get_editor_property('overview_center'))) < .1
    reset_pending = False
    record('visible_reset_button_restores_overview_and_clears_selection', resolution=list(current_size), sample=sample())


def capture(label):
    global pending_capture
    assert pending_capture is None
    path = OUT / f'controls_{current_size[0]}x{current_size[1]}_{label}.png'
    pending_capture = (path, time.time(), time.monotonic(), current_size)
    unreal.SystemLibrary.execute_console_command(world, f'Shot showui filename="{path.as_posix()}" -nosuffix', pc)


def capture_ready():
    global pending_capture
    path, requested, started, expected_size = pending_capture
    if not path.exists() or path.stat().st_mtime < requested or path.stat().st_size < 10000:
        assert time.monotonic()-started < 30, ('Screenshot timeout', str(path))
        return False
    data = path.read_bytes()
    assert data[:8] == b'\x89PNG\r\n\x1a\n'
    dimensions = struct.unpack('>II', data[16:24])
    assert dimensions == expected_size, (dimensions, expected_size)
    result['captures'].append(dict(path=str(path), size=list(dimensions)))
    pending_capture = None
    write()
    return True


def resize_narrow():
    global current_size
    current_size = (600, 900)
    unreal.SystemLibrary.execute_console_command(world, 'r.SetRes 600x900w', pc)


steps = [('discover', discover), ('desktop_layout', check_layout)]


def add_resolution_steps(prefix):
    steps.extend([
        (prefix+'_select', select_fixture), (prefix+'_selected_ready', wait_fixture),
        (prefix+'_close_start', lambda: begin_motion(prefix+'_close', False, 1)),
        (prefix+'_closed', finish_motion), (prefix+'_closed_capture', lambda: capture(prefix+'_closed')),
        (prefix+'_open_start', lambda: begin_motion(prefix+'_open', True, -1)),
        (prefix+'_opened', finish_motion),
        (prefix+'_partial_start', lambda: begin_motion(prefix+'_partial_close', False)),
        (prefix+'_reverse', reverse_midflight), (prefix+'_reversed', finish_motion),
        (prefix+'_opened_capture', lambda: capture(prefix+'_opened')),
        (prefix+'_reset', reset_button), (prefix+'_reset_check', wait_reset),
        (prefix+'_overview_capture', lambda: capture(prefix+'_overview'))])


add_resolution_steps('desktop')
steps += [('resize_narrow', resize_narrow), ('narrow_layout', check_layout)]
add_resolution_steps('narrow')


def finish(error=None):
    result.update(success=error is None, error=error,
                  failed_step=steps[step][0] if error and step < len(steps) else None,
                  elapsed_seconds=time.monotonic()-START)
    if motion:
        result['unfinished_motion'] = motion
    write()
    if handle:
        unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log_error if error else unreal.log)('SCENE_CONTROLS_' + ('FAILED '+str(error) if error else 'SUCCESS'))
    if world:
        unreal.SystemLibrary.execute_console_command(world, 'quit', pc)


def tick(delta_seconds):
    global step
    try:
        assert time.monotonic()-START < 180, 'Scene controls acceptance timeout'
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
