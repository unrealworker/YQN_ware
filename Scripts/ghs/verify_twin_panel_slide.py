"""Verify full-width panel sliding and overview selection reset in owned UE game.

Start at 1920x1080 with -game -RenderOffscreen. This script also verifies an
in-process resize to 600x900. It never starts an editor or saves project assets.
Home's non-reflected InputKey route is checked from source; its shared overview
command and both native toolbar routes are exercised in the running game.
"""
import json
import math
import re
import struct
import time
import traceback
from pathlib import Path

import unreal

ROOT = Path(r'D:\UEPro\Test')
CLI = unreal.SystemLibrary.get_command_line()
assert re.search(r'(?:^|\s)-game(?:\s|$)', CLI, re.I) and '-RenderOffscreen' in CLI
REPORT = ROOT / 'Saved/PanelSlide_Acceptance.json'
START = time.monotonic()
world = pc = pawn = widget = None
handle = None
step = 0
next_at = 0
current_size = (1920, 1080)
motion = None
pending_capture = None
cargo_points = []
result = dict(success=False, checks=[], motion_segments=[], captures=[], assets_saved=False,
              input_scope='Native widget routes and shared command; no simulated OS keyboard input')


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
    unreal.log('PANEL_SLIDE_CHECK ' + name)


def snapshot():
    return json.loads(widget.get_snapshot())


def browser():
    text = widget.get_editor_property('last_browser_report')
    return json.loads(text) if text else {}


def command(action, **values):
    widget.command(json.dumps(dict(action=action, **values)))


def pose():
    camera = pawn.get_editor_property('warehouse_camera')
    arm = pawn.get_editor_property('spring_arm_component')
    rotation = camera.get_world_rotation()
    return dict(pivot=xyz(pawn.get_actor_location()), camera=xyz(camera.get_world_location()),
                rotation=[rotation.pitch, rotation.yaw, rotation.roll],
                zoom=float(arm.get_editor_property('target_arm_length')),
                offset=xyz(arm.get_editor_property('socket_offset')),
                flight=bool(pawn.is_pose_transition_active()))


def same_pose(before, after):
    for key in ['pivot', 'camera', 'offset']:
        assert distance(before[key], after[key]) < .1, (key, before, after)
    assert abs(before['zoom']-after['zoom']) < .1, (before, after)
    assert max(abs((a-b+180) % 360-180) for a, b in zip(before['rotation'], after['rotation'])) < .001, (before, after)
    assert not after['flight'], ('Panel action started a camera flight', after)


def panel_sample():
    position=widget.get_panel_visual_position(); size=widget.get_panel_visual_size()
    right=current_size[0]; open_x=right-size.x
    if position.x<right-2:
        assert not widget.is_scene_point(unreal.Vector2D((position.x+right)*.5,position.y+size.y*.5)), 'Visible moving panel leaked scene input'
    if position.x>open_x+2:
        assert widget.is_scene_point(unreal.Vector2D((open_x+min(position.x,right))*.5,position.y+size.y*.5)), 'Exposed scene remains blocked by old panel bounds'
    return dict(at=time.monotonic()-START, game_seconds=unreal.GameplayStatics.get_time_seconds(world),
                position=xy(widget.get_panel_visual_position()), size=xy(widget.get_panel_visual_size()),
                opacity=float(widget.get_panel_opacity()),
                progress=float(widget.get_panel_transition_progress()), pose=pose())


def browser_identity(report):
    # These fields identify the displayed business view and its actual scene data.
    keys = ['page', 'detail', 'equipmentCount', 'facilityCount']
    return {key: report.get(key) for key in keys}


def discover():
    global world, pc, pawn, widget
    for candidate in unreal.ObjectIterator(unreal.World):
        controller = unreal.GameplayStatics.get_player_controller(candidate, 0)
        if controller and hasattr(controller, 'twin_hud_widget') and controller.get_editor_property('twin_hud_widget'):
            world, pc = candidate, controller
            pawn = pc.get_controlled_pawn()
            widget = pc.get_editor_property('twin_hud_widget')
            break
    if not widget or not widget.get_editor_property('browser_ready') or not browser():
        return False
    assert 'ZcoolSmartFactory' in world.get_name()
    for name in ['get_panel_visual_position', 'get_panel_visual_size', 'get_panel_opacity']:
        assert hasattr(widget, name), ('Missing runtime diagnostic', name)
    data = snapshot()
    assert len(data['equipment']) == 106 and len(data['facilities']) == 56
    record('owned_game_scene_and_browser_ready', map=world.get_path_name(), browser=browser())


def check_layout():
    position, size = widget.get_panel_position(), widget.get_panel_size()
    assert abs(position.x+size.x-current_size[0]) < 1 and abs(position.y+size.y-current_size[1]) < 1, (position, size, current_size)
    assert size.x >= 360 and size.y >= 200
    assert widget.get_panel_transition_progress() >= .999
    assert not browser().get('overflow'), browser()
    record('open_panel_layout', resolution=list(current_size), sample=panel_sample())


def toggle():
    assert widget.handle_chrome_click(unreal.Vector2D(current_size[0]-30, 25))


def begin_motion(name, opening):
    global motion
    assert motion is None
    baseline = panel_sample()
    assert not baseline['pose']['flight'], 'Settle the camera before testing panel movement'
    motion = dict(name=name, opening=opening, resolution=list(current_size),
                  before_browser=browser_identity(browser()), before_selection=widget.get_editor_property('selected_id'),
                  before_ids=[row['id'] for row in snapshot()['equipment']], samples=[baseline])
    toggle()
    immediate = panel_sample()
    assert distance(baseline['position'], immediate['position']) < .01, ('Toggle teleported panel before its animation tick', baseline, immediate)
    same_pose(baseline['pose'], immediate['pose'])


def finish_motion(expect_endpoint=True):
    global motion
    assert motion is not None
    motion['samples'].append(panel_sample())
    samples = motion['samples']
    width = samples[0]['size'][0]
    assert width > 0
    for sample in samples:
        assert abs(sample['opacity']-1.) < .001, ('Panel fades instead of translating at full opacity', sample)
        assert abs(sample['size'][0]-width) < .1, ('Panel width changed during slide', sample, width)
        assert abs(sample['position'][1]-samples[0]['position'][1]) < .1, ('Panel slides vertically', samples)
        same_pose(samples[0]['pose'], sample['pose'])
    delta = [b['position'][0]-a['position'][0] for a, b in zip(samples, samples[1:])]
    if motion['opening']:
        assert all(value <= .05 for value in delta), ('Opening must move right to left', samples)
    else:
        assert all(value >= -.05 for value in delta), ('Closing must move left to right', samples)
    assert any(0.01 < sample['progress'] < .99 for sample in samples), ('No intermediate slide frame', samples)
    if expect_endpoint:
        expected_progress = 1. if motion['opening'] else 0.
        assert abs(samples[-1]['progress']-expected_progress) < .001, samples[-1]
        expected_x = current_size[0]-width if motion['opening'] else current_size[0]
        assert abs(samples[-1]['position'][0]-expected_x) < .1, ('Panel did not travel completely off/on screen', samples[-1], expected_x)
        start_at_endpoint = samples[0]['progress'] < .001 or samples[0]['progress'] > .999
        if start_at_endpoint:
            assert abs(abs(samples[-1]['position'][0]-samples[0]['position'][0])-width) < .1, ('Full slide must cover one complete panel width', samples)
    motion['after_browser'] = browser_identity(browser())
    assert motion['after_browser'] == motion['before_browser'], ('Sliding rebuilt or navigated the business page', motion)
    assert widget.get_editor_property('selected_id') == motion['before_selection']
    assert [row['id'] for row in snapshot()['equipment']] == motion['before_ids']
    result['motion_segments'].append(motion)
    record('slide_'+motion['name'], resolution=list(current_size), samples=len(samples),
           start_x=samples[0]['position'][0], end_x=samples[-1]['position'][0], width=width)
    motion = None


def reverse_midflight():
    current = panel_sample()
    assert .02 < current['progress'] < .98, ('Reversal must happen during motion', current)
    finish_motion(False)
    begin_motion('rapid_reverse_to_open', True)
    assert distance(current['position'], panel_sample()['position']) < .01, 'Reversal changed the panel position immediately'


def source_routes():
    controller_path = ROOT / 'Source/Test/GHSWarehousePlayerController.cpp'
    hud_path = ROOT / 'Source/Test/GHSTwinHUDWidget.cpp'
    controller = controller_path.read_text(encoding='utf-8')
    hud = hud_path.read_text(encoding='utf-8')
    home = re.search(r'if\s*\(Key\s*==\s*EKeys::Home.*?\n\s*\}', controller, re.S)
    assert home and 'TwinHUDWidget->Command' in home.group() and 'overview' in home.group(), 'Home must use the same overview command as browser navigation'
    assert re.search(r'Action==TEXT\("overview"\)\)\s*Overview\(\)', hud), 'Browser overview command must call the shared Overview method'
    chrome = hud[hud.index('bool UGHSTwinHUDWidget::HandleChromeClick'):hud.index('bool UGHSTwinHUDWidget::HandleSceneClick')]
    assert chrome.count('Overview()') >= 2, 'Both native overview toolbar buttons must call the shared method'
    record('home_browser_and_native_toolbars_share_overview',
           evidence='Source route verification, followed by runtime tests of the shared command and toolbar methods',
           controller=str(controller_path), hud=str(hud_path))


def select_agv():
    assert widget.select_object('AGV-07', True)


def verify_agv():
    assert widget.get_editor_property('selected_id') == 'AGV-07'
    assert (browser().get('detail') or {}).get('id') == 'AGV-07', browser()
    assert any(item['id'] == 'AGV-07' and item['selected'] for item in json.loads(widget.get_poi_report())['labels'])
    assert not pawn.is_pose_transition_active()


def overview_via(source):
    result['pending_overview_source'] = source
    if source == 'shared_home_browser_command':
        command('overview')
    elif source == 'top_left_toolbar':
        header = 52 if current_size[0] < 700 else 64
        assert widget.handle_chrome_click(unreal.Vector2D(60, header+30))
    elif source == 'scene_zoom_toolbar':
        panel = widget.get_panel_position()
        width, height = current_size
        scene_right = width if width < 900 else panel.x
        scene_bottom = panel.y if width < 900 else height
        assert widget.handle_chrome_click(unreal.Vector2D(scene_right-40, scene_bottom-35))
    else:
        raise AssertionError(source)


def overview_cleared():
    data, report = snapshot(), browser()
    assert not widget.get_editor_property('selected_id'), data
    assert data.get('selection') is None, data.get('selection')
    assert report.get('detail') is None, report
    assert report.get('transition', {}).get('phase') == 'idle', report
    selected = [item for item in json.loads(widget.get_poi_report())['labels'] if item['selected']]
    assert not selected, ('Overview retained selected object/region POI', selected)
    assert not pawn.is_pose_transition_active()
    assert not pawn.uses_object_pivot()
    assert distance(xyz(pawn.get_actor_location()), xyz(pawn.get_editor_property('overview_center'))) < .1
    record('overview_clears_all_selection', route=result.pop('pending_overview_source'), resolution=list(current_size), browser=report)


def select_region():
    command('preset', value='racks')


def verify_region():
    labels = json.loads(widget.get_poi_report())['labels']
    assert any(item['id'] == 'REGION:racks' and item['selected'] for item in labels), labels
    assert pawn.uses_object_pivot()
    record('region_selection_fixture_ready', poi=labels)


def prepare_cargo():
    global cargo_points
    models = {entry['name']: entry for entry in json.loads((ROOT/'Content/GHSTwinUI/data/rack-slots.json').read_text(encoding='utf-8'))['meshes']}
    command('layers', equipment=True, racks=True, pois=False)
    for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor):
        for component in actor.get_components_by_class(unreal.InstancedStaticMeshComponent):
            mesh = component.get_editor_property('static_mesh')
            if not mesh or mesh.get_name() not in models or component.get_instance_count() == 0:
                continue
            slots = sorted(models[mesh.get_name()]['cargo_stacks'], key=lambda slot: slot['stack_top_z_m'], reverse=True)
            if not slots:
                continue
            transform = component.get_instance_transform(0, world_space=True)
            cargo_points = [unreal.MathLibrary.transform_location(transform, unreal.Vector(
                slot['pallet_center_x_m']*100, 0, (slot['base_z_m']+slot['stack_top_z_m'])*50)) for slot in slots]
            panel = widget.get_panel_position()
            header = 52 if current_size[0] < 700 else 64
            center = unreal.Vector2D(current_size[0]*.5, (header+panel.y)*.5) if current_size[0] < 900 else unreal.Vector2D(panel.x*.5, (header+current_size[1])*.5)
            pawn.focus_on_target(cargo_points[0], 2800., unreal.Rotator(pitch=-65, yaw=-90, roll=0), unreal.Vector2D(*current_size), center, .85)
            return
    raise AssertionError('No actual rack cargo fixture found')


def click_cargo():
    for point in cargo_points:
        screen = pc.project_world_location_to_screen(point, False)
        if screen is None or not widget.is_scene_point(screen):
            continue
        widget.handle_scene_click(screen)
        selected = snapshot().get('selection') or {}
        if selected.get('kind') == 'material' and selected.get('id', '').startswith('MATERIAL:'):
            result['cargo_selection'] = selected
            return
    raise AssertionError('Actual cargo click did not select a material')


def verify_cargo():
    assert widget.get_editor_property('selected_id').startswith('MATERIAL:')
    assert (browser().get('detail') or {}).get('kind') == 'material', browser()
    command('layers', equipment=True, racks=True, pois=True)
    record('cargo_selection_fixture_ready', selection=result['cargo_selection'])


def capture(label):
    global pending_capture
    path = ROOT/f'Saved/PanelSlide_{current_size[0]}x{current_size[1]}_{label}.png'
    pending_capture = (path, time.time(), time.monotonic())
    unreal.SystemLibrary.execute_console_command(world, f'Shot showui filename="{path.as_posix()}" -nosuffix', pc)


def capture_ready():
    global pending_capture
    path, requested, started = pending_capture
    if not path.exists() or path.stat().st_mtime < requested or path.stat().st_size < 10000:
        assert time.monotonic()-started < 30, ('Screenshot timeout', path)
        return False
    data = path.read_bytes()
    assert data[:8] == b'\x89PNG\r\n\x1a\n'
    dimensions = struct.unpack('>II', data[16:24])
    assert dimensions == current_size, (dimensions, current_size)
    result['captures'].append(dict(path=str(path), size=list(dimensions)))
    pending_capture = None
    write()
    return True


def resize_narrow():
    global current_size
    current_size = (600, 900)
    unreal.SystemLibrary.execute_console_command(world, 'r.SetRes 600x900w', pc)


steps = [('discover', discover, 1.3), ('layout', check_layout, .1), ('source_routes', source_routes, .1),
         ('select_agv', select_agv, 1.3), ('agv_detail', verify_agv, .1)]


def add_slide_steps(prefix):
    steps.extend([(prefix+'_collapse', lambda: begin_motion(prefix+'_close', False), .2),
                  (prefix+'_capture_closing', lambda: capture(prefix+'_Closing'), .45),
                  (prefix+'_collapsed', finish_motion, .1),
                  (prefix+'_capture_closed', lambda: capture(prefix+'_Closed'), .1),
                  (prefix+'_expand', lambda: begin_motion(prefix+'_open', True), .2),
                  (prefix+'_capture_opening', lambda: capture(prefix+'_Opening'), .45),
                  (prefix+'_expanded', finish_motion, .1),
                  (prefix+'_reverse_start', lambda: begin_motion(prefix+'_reverse_partial_close', False), .1),
                  (prefix+'_reverse', reverse_midflight, .65),
                  (prefix+'_reverse_finished', finish_motion, .1),
                  (prefix+'_capture_open', lambda: capture(prefix+'_Opened'), .1)])


add_slide_steps('desktop_device')
steps += [('orders_page', lambda: widget.navigate('orders'), .6)]
add_slide_steps('desktop_orders')
steps += [('select_for_home', select_agv, 1.3),
          ('home_shared_command', lambda: overview_via('shared_home_browser_command'), 1.3),
          ('home_clear_check', overview_cleared, .1),
          ('prepare_cargo', prepare_cargo, 1.3), ('click_cargo', click_cargo, 1.3),
          ('verify_cargo', verify_cargo, .3),
          ('cargo_overview_toolbar', lambda: overview_via('top_left_toolbar'), 1.3),
          ('cargo_clear_check', overview_cleared, .1),
          ('select_region', select_region, 1.3), ('verify_region', verify_region, .1),
          ('region_overview_zoom_toolbar', lambda: overview_via('scene_zoom_toolbar'), 1.3),
          ('region_clear_check', overview_cleared, .1),
          ('resize_narrow', resize_narrow, 2.), ('narrow_layout', check_layout, .1),
          ('narrow_select', select_agv, 1.3), ('narrow_detail', verify_agv, .1)]
add_slide_steps('narrow_device')
steps += [('narrow_overview', lambda: overview_via('shared_home_browser_command'), 1.3),
          ('narrow_clear', overview_cleared, .1)]


def finish(error=None):
    result.update(success=error is None, error=error,
                  failed_step=steps[step][0] if error and step < len(steps) else None,
                  elapsed=time.monotonic()-START)
    if motion:
        result['unfinished_motion'] = motion
    write()
    if handle:
        unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log_error if error else unreal.log)('PANEL_SLIDE_' + ('FAILED '+str(error) if error else 'SUCCESS'))
    if world:
        unreal.SystemLibrary.execute_console_command(world, 'quit', pc)


def tick(delta_seconds):
    global step, next_at
    try:
        now = time.monotonic()
        assert now-START < 240, 'Panel slide acceptance timeout'
        if motion:
            motion['samples'].append(panel_sample())
        if pending_capture and not capture_ready():
            return
        if now < next_at:
            return
        if step >= len(steps):
            finish()
            return
        _, action, delay = steps[step]
        if action() is False:
            return
        step += 1
        next_at = time.monotonic()+delay
    except Exception:
        finish(traceback.format_exc())


write()
handle = unreal.register_slate_post_tick_callback(tick)
