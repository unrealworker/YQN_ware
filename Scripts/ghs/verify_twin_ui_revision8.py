"""Revision 8 acceptance in an owned -game -RenderOffscreen process.

Run through UE Python's -ExecutePythonScript as with verify_twin_ui_runtime.py.
Full starts at 1920x1080 and also resizes to 1366x768 and 600x900 in-process.
-TwinSmall / -TwinPortrait validate their initial resolution without resizing.
This script never loads, saves, or edits assets and never starts another process.
"""
import itertools
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
VARIANT = 'Portrait' if '-TwinPortrait' in CLI else 'Small' if '-TwinSmall' in CLI else 'Full'
INITIAL_SIZE = {'Full': (1920, 1080), 'Small': (1366, 768), 'Portrait': (600, 900)}[VARIANT]
REPORT = ROOT / f'Saved/Revision8_{VARIANT}.json'
START = time.monotonic()
world = pc = pawn = widget = None
step = 0
next_at = 0
pending_capture = None
handle = None
current_size = INITIAL_SIZE
pose_watch = None
phase_watch = None
last_report_text = ''
region_bounds = {}
rack_candidate = None
result = dict(success=False, variant=VARIANT, checks=[], captures=[], camera_flights=[],
              page_transitions=[], assets_saved=False, initial_resolution=list(INITIAL_SIZE))


def xyz(value):
    return [float(value.x), float(value.y), float(value.z)]


def distance(a, b):
    return math.sqrt(sum((x-y)**2 for x, y in zip(a, b)))


def write():
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


def record(name, **values):
    result['checks'].append(dict(name=name, passed=True, **values))
    write()
    unreal.log('REVISION8_CHECK ' + name)


def snapshot():
    return json.loads(widget.get_snapshot())


def browser_report():
    raw = widget.get_editor_property('last_browser_report')
    return json.loads(raw) if raw else {}


def command(action, **values):
    widget.command(json.dumps(dict(action=action, **values)))


def pose():
    camera = pawn.get_editor_property('warehouse_camera')
    arm = pawn.get_editor_property('spring_arm_component')
    rotation = camera.get_world_rotation()
    return dict(elapsed=time.monotonic()-START, world_seconds=unreal.GameplayStatics.get_time_seconds(world),
                pivot=xyz(pawn.get_actor_location()), camera=xyz(camera.get_world_location()),
                rotation=[rotation.pitch, rotation.yaw, rotation.roll],
                distance=float(arm.get_editor_property('target_arm_length')),
                socket_offset=xyz(arm.get_editor_property('socket_offset')),
                active=bool(pawn.is_pose_transition_active()))


def same_pose(before, after, tolerance=.1):
    assert distance(before['pivot'], after['pivot']) < tolerance, ('Pivot moved', before, after)
    assert distance(before['camera'], after['camera']) < tolerance, ('Camera moved', before, after)
    assert abs(before['distance']-after['distance']) < tolerance, ('Zoom changed', before, after)
    angles = [abs((a-b+180) % 360-180) for a, b in zip(before['rotation'], after['rotation'])]
    assert max(angles) < .001, ('Rotation changed', before, after)
    assert distance(before['socket_offset'], after['socket_offset']) < tolerance, ('Framing changed', before, after)


def scene_center():
    panel = widget.get_panel_position()
    size = widget.get_panel_size()
    width, height = current_size
    header = 52 if width < 700 else 64
    if size.x < 1:
        return unreal.Vector2D(width*.5, (height+header)*.5)
    if width < 900:
        return unreal.Vector2D(width*.5, (panel.y+header)*.5)
    return unreal.Vector2D(panel.x*.5, (height+header)*.5)


def screen_projection(point):
    projected = pc.project_world_location_to_screen(unreal.Vector(*point), False)
    assert projected is not None, ('Projection failed', point)
    return [float(projected.x), float(projected.y)]


def assert_center(point, label):
    center = scene_center()
    screen = screen_projection(point)
    error = distance(screen, [center.x, center.y])
    assert error < 1., (label, 'Center projection must be within 1 pixel', error, screen, center)
    assert widget.is_scene_point(unreal.Vector2D(*screen)), (label, screen)
    return dict(point=point, projected=screen, expected=[center.x, center.y], error_pixels=error)


def bounds_for(mesh, transform):
    bounds = mesh.get_bounds()
    points = [xyz(unreal.MathLibrary.transform_location(transform, unreal.Vector(
        bounds.origin.x+sx*bounds.box_extent.x,
        bounds.origin.y+sy*bounds.box_extent.y,
        bounds.origin.z+sz*bounds.box_extent.z))) for sx, sy, sz in itertools.product((-1, 1), repeat=3)]
    return ([min(point[i] for point in points) for i in range(3)],
            [max(point[i] for point in points) for i in range(3)])


def discover():
    global world, pc, pawn, widget
    for candidate in unreal.ObjectIterator(unreal.World):
        controller = unreal.GameplayStatics.get_player_controller(candidate, 0)
        if controller and hasattr(controller, 'twin_hud_widget') and controller.get_editor_property('twin_hud_widget'):
            world, pc = candidate, controller
            pawn = pc.get_controlled_pawn()
            widget = pc.get_editor_property('twin_hud_widget')
            break
    if not widget or not widget.get_editor_property('browser_ready') or not browser_report():
        return False
    assert 'ZcoolSmartFactory' in world.get_name(), world.get_name()
    data = snapshot()
    assert len(data['equipment']) == 106 and len(data['facilities']) == 56
    assert not pc.get_editor_property('truck_hud_widget')
    result['map'] = world.get_path_name()
    record('scene_and_native_browser_connected', equipment=106, facilities=56)


def layout():
    panel, size = widget.get_panel_position(), widget.get_panel_size()
    width, height = current_size
    assert abs(panel.x+size.x-width) < 1 and abs(panel.y+size.y-height) < 1, (panel, size, current_size)
    assert size.x >= 360 and size.y >= 200, (panel, size)
    assert panel.x == 0 if width < 900 else panel.x > 0
    assert not widget.is_scene_point(unreal.Vector2D(panel.x+size.x*.5, panel.y+size.y*.5))
    record('responsive_layout', resolution=list(current_size), panel=[panel.x, panel.y, size.x, size.y])


def assert_page(page):
    report = browser_report()
    assert report.get('page') == page, (page, report)
    assert report.get('transition', {}).get('phase') == 'idle', report
    assert not report.get('overflow'), report
    assert not report.get('imageFailures'), report
    assert report.get('detailActionsVisible') is not False, report
    assert report.get('equipmentCount') == 106 and report.get('facilityCount') == 56, report
    record('page_' + page, resolution=list(current_size), browser=report)


def capture(label):
    global pending_capture
    path = ROOT / f'Saved/Revision8_{VARIANT}_{current_size[0]}x{current_size[1]}_{label}.png'
    pending_capture = (path, time.time(), time.monotonic())
    unreal.SystemLibrary.execute_console_command(world, f'Shot showui filename="{path.as_posix()}" -nosuffix', pc)


def capture_ready():
    global pending_capture
    path, requested, started = pending_capture
    if not path.exists() or path.stat().st_mtime < requested or path.stat().st_size < 10000:
        assert time.monotonic()-started < 30, ('Screenshot timed out', str(path))
        return False
    data = path.read_bytes()
    assert data[:8] == b'\x89PNG\r\n\x1a\n'
    dimensions = struct.unpack('>II', data[16:24])
    assert tuple(current_size) == dimensions, (current_size, dimensions)
    result['captures'].append(dict(path=str(path), size=list(dimensions)))
    pending_capture = None
    write()
    return True


def start_focus():
    global pose_watch
    before = pose()
    assert widget.select_object('AGV-07', True)
    same_pose(before, pose())
    assert pawn.is_pose_transition_active(), 'Device focus should start a timed flight'
    pose_watch = dict(name='AGV-07 focus', started=unreal.GameplayStatics.get_time_seconds(world), samples=[before])


def verify_focus():
    global pose_watch
    data = snapshot()['selection']
    assert data['id'] == 'AGV-07'
    actor = next(a for a in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor) if a.get_name() == data['actor'])
    component = next(c for c in actor.get_components_by_class(unreal.StaticMeshComponent) if c.get_name() == data['component'])
    low, high = bounds_for(component.get_editor_property('static_mesh'), component.get_world_transform())
    actual_center = [(a+b)*.5 for a, b in zip(low, high)]
    assert distance(data['worldPosition'], actual_center) < .1, ('Registry must match actual mesh bounds', data, actual_center)
    assert distance(xyz(pawn.get_actor_location()), actual_center) < .1, ('Orbit pivot differs from actual model center', pose(), actual_center)
    assert distance(xyz(pawn.get_focus_target()), actual_center) < .1
    assert pawn.uses_object_pivot() and not pawn.is_pose_transition_active()
    projected = assert_center(actual_center, 'AGV-07')
    if pose_watch:
        samples = pose_watch['samples']
        start, end = samples[0]['pivot'], actual_center
        total = distance(start, end)
        progress = [distance(sample['pivot'], start)/max(total, 1.) for sample in samples if sample['active']]
        assert total > 100, ('Focus fixture needs a meaningful travel distance', total)
        assert any(.02 < value < .98 for value in progress), ('No intermediate flight pose captured', samples)
        assert all(b >= a-.0001 for a, b in zip(progress, progress[1:])), ('Flight must not reverse progress', progress)
        for sample in samples:
            assert all(math.isfinite(v) for v in sample['pivot']+sample['camera']+sample['rotation'])
            assert abs(sample['rotation'][2]) < .01, ('Camera horizon rolled during flight', sample)
        pose_watch['final'] = pose()
        result['camera_flights'].append(pose_watch)
        pose_watch = None
    report = browser_report()
    assert (report.get('detail') or {}).get('id') == 'AGV-07', report
    assert not report.get('overflow') and not report.get('imageFailures'), report
    assert report.get('detailActionsVisible') is not False, report
    record('actual_model_center_is_orbit_pivot_and_scene_center', resolution=list(current_size), projection=projected, pose=pose())


def poi_check():
    report = json.loads(widget.get_poi_report())
    labels = report['labels']
    selected = [item for item in labels if item['id'] == 'AGV-07']
    assert len(selected) == 1 and selected[0]['selected'], report
    assert selected[0]['icon'] == 'agv' and selected[0]['fill'] == '356BFA', selected
    assert labels and all(item.get('icon') and item['height'] == 42 for item in labels), report
    assert report['selectionStroke'] == 4, report
    assert not any(item['id'].startswith('RACK:') for item in labels), report
    record('poi_icons_42px_blue_selection_and_4px_outline', report=report)


def collapse():
    result['collapse_pose'] = pose()
    assert not pawn.is_pose_transition_active()
    assert widget.handle_chrome_click(unreal.Vector2D(current_size[0]-30, 25))


def collapsed():
    assert widget.get_panel_size().x == 0
    same_pose(result['collapse_pose'], pose())
    assert not pawn.is_pose_transition_active()
    record('panel_collapse_never_reframes_camera', before=result['collapse_pose'], after=pose())


def expand():
    assert widget.handle_chrome_click(unreal.Vector2D(current_size[0]-30, 25))


def expanded():
    layout()
    same_pose(result['collapse_pose'], pose())
    assert not pawn.is_pose_transition_active()
    record('panel_expand_never_reframes_camera', after=pose())


def storage_geometry():
    global rack_candidate
    metadata = json.loads((ROOT / 'Content/GHSTwinUI/data/rack-slots.json').read_text(encoding='utf-8'))
    models = {entry['name']: entry for entry in metadata['meshes']}
    counts = dict(racks=0, floor=0)
    for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor):
        for component in actor.get_components_by_class(unreal.InstancedStaticMeshComponent):
            mesh = component.get_editor_property('static_mesh')
            if not mesh:
                continue
            name = mesh.get_name()
            kind = 'racks' if name.startswith('SM_GHS_V2Rack_') else 'floor' if name.startswith('SM_GHS_Presentation_Cargo') else None
            if kind is None:
                continue
            for index in range(component.get_instance_count()):
                transform = component.get_instance_transform(index, world_space=True)
                low, high = bounds_for(mesh, transform)
                if kind not in region_bounds:
                    region_bounds[kind] = [low[:], high[:]]
                else:
                    current = region_bounds[kind]
                    current[0] = [min(a, b) for a, b in zip(current[0], low)]
                    current[1] = [max(a, b) for a, b in zip(current[1], high)]
                counts[kind] += 1
                if rack_candidate is None and kind == 'racks' and name in models and models[name]['cargo_stacks']:
                    rack_candidate = dict(actor=actor.get_name(), component=component.get_path_name(), index=index,
                                          key=f'RACK:{actor.get_name()}:{component.get_name()}:{index}', model=models[name])
    assert rack_candidate and all(counts.values()), counts
    result['storage_geometry'] = dict(bounds=region_bounds, counts=counts)
    record('storage_region_expectations_come_from_actual_geometry', counts=counts)


def reject_rack_structure():
    before = widget.get_editor_property('selected_id')
    assert not widget.select_object(rack_candidate['key'], True), 'Rack structure must not open a material detail'
    assert widget.get_editor_property('selected_id') == before
    record('rack_structure_id_is_not_selectable', rejected=rack_candidate['key'])


def aim_at_cargo():
    command('layers', equipment=True, racks=True, pois=False)
    component = unreal.find_object(None, rack_candidate['component'])
    transform = component.get_instance_transform(rack_candidate['index'], world_space=True)
    slots = sorted(rack_candidate['model']['cargo_stacks'], key=lambda value: value['stack_top_z_m'], reverse=True)
    points = [unreal.MathLibrary.transform_location(transform, unreal.Vector(
        slot['pallet_center_x_m']*100, 0, (slot['base_z_m']+slot['stack_top_z_m'])*50)) for slot in slots]
    rack_candidate['points'] = [xyz(point) for point in points]
    pawn.focus_on_target(points[0], 2800., unreal.Rotator(pitch=-65., yaw=-90., roll=0.),
                         unreal.Vector2D(*current_size), scene_center(), .85)


def click_cargo():
    for point in rack_candidate['points']:
        projected = screen_projection(point)
        position = unreal.Vector2D(*projected)
        if not widget.is_scene_point(position):
            continue
        widget.handle_scene_click(position)
        selected = snapshot().get('selection') or {}
        if selected.get('kind') == 'material' and selected.get('id', '').startswith('MATERIAL:'):
            assert selected.get('cadId') and selected.get('level', 0) > 0 and selected.get('column', 0) > 0, selected
            assert not selected.get('businessBound'), selected
            assert selected['id'] != rack_candidate['key']
            result['cargo_selection'] = selected
            record('actual_rack_cargo_still_opens_material_detail', selection=selected, click=projected)
            return
    raise AssertionError('No projected real rack cargo selected an actual MATERIAL slot')


def cargo_detail():
    report = browser_report()
    assert (report.get('detail') or {}).get('kind') == 'material', report
    assert not report.get('overflow') and not report.get('imageFailures'), report
    record('cargo_detail_browser_binding', browser=report)
    command('layers', equipment=True, racks=True, pois=True)


def region_preset(region):
    command('preset', value=region)


def assert_region(region):
    low, high = region_bounds[region]
    expected = [(a+b)*.5 for a, b in zip(low, high)]
    assert distance(xyz(pawn.get_focus_target()), expected) < .5, ('Preset used the wrong geometry region', region, expected, xyz(pawn.get_focus_target()))
    assert distance(xyz(pawn.get_actor_location()), expected) < .5, (region, pose(), expected)
    assert not pawn.is_pose_transition_active()
    assert not widget.get_editor_property('selected_id'), 'Area view must not impersonate an individual rack'
    assert not browser_report().get('detail'), 'Area view must clear stale device/material details'
    projected = assert_center(expected, 'region_' + region)
    record('preset_' + region + '_uses_actual_region_center', projection=projected, pose=pose(), poi=json.loads(widget.get_poi_report()))


def start_page_transition():
    global phase_watch
    phase_watch = dict(name='overview_to_inventory', reports=[])
    widget.navigate('inventory')


def verify_page_transition():
    global phase_watch
    report = browser_report()
    phases = [item.get('transition', {}).get('phase') for item in phase_watch['reports']]
    recent = report.get('transition', {}).get('recentPhases', [])
    history = [item.get('phase') if isinstance(item, dict) else item for item in recent]
    observed = phases if all(item in phases for item in ('out', 'in', 'idle')) else history
    assert 'out' in observed and 'in' in observed and 'idle' in observed, ('Missing real browser transition phases', phases, recent, report)
    assert observed.index('out') < observed.index('in'), observed
    assert report['transition']['phase'] == 'idle'
    assert report['transition']['durationMs'] >= 250, report
    assert_page('inventory')
    phase_watch['final'] = report
    result['page_transitions'].append(phase_watch)
    phase_watch = None
    record('browser_pages_have_exit_enter_and_idle_phases', observed=observed)


def rapid_pages():
    for page in ['inventory', 'devices', 'settings', 'alerts', 'overview', 'orders']:
        widget.navigate(page)


def resize(size):
    global current_size
    current_size = size
    unreal.SystemLibrary.execute_console_command(world, f'r.SetRes {size[0]}x{size[1]}w', pc)


def collect_samples():
    global last_report_text
    if pawn and pose_watch:
        pose_watch['samples'].append(pose())
    if widget and phase_watch:
        raw = widget.get_editor_property('last_browser_report')
        if raw and raw != last_report_text:
            phase_watch['reports'].append(json.loads(raw))
            last_report_text = raw


steps = [('discover', discover, 1.2), ('initial_layout', layout, .1),
         ('overview_check', lambda: assert_page('overview'), .1),
         ('overview_capture', lambda: capture('Overview'), .1),
         ('select_agv', start_focus, 1.3), ('verify_focus', verify_focus, .1),
         ('poi_check', poi_check, .1), ('device_capture', lambda: capture('Device'), .1),
         ('collapse', collapse, .5), ('collapsed', collapsed, .1),
         ('expand', expand, .5), ('expanded', expanded, .1),
         ('storage_geometry', storage_geometry, .1), ('rack_rejected', reject_rack_structure, .1),
         ('cargo_aim', aim_at_cargo, 1.2), ('cargo_click', click_cargo, 1.2),
         ('cargo_detail', cargo_detail, .1), ('cargo_capture', lambda: capture('Material'), .1),
         ('preset_racks', lambda: region_preset('racks'), 1.3),
         ('preset_racks_check', lambda: assert_region('racks'), .1),
         ('preset_racks_capture', lambda: capture('RacksPreset'), .1),
         ('preset_floor', lambda: region_preset('floor'), 1.3),
         ('preset_floor_check', lambda: assert_region('floor'), .1),
         ('preset_floor_capture', lambda: capture('FloorPreset'), .1),
         ('transition_from', lambda: widget.navigate('overview'), .6),
         ('transition_start', start_page_transition, .6),
         ('transition_check', verify_page_transition, .1),
         ('rapid_pages', rapid_pages, .6), ('rapid_final_page', lambda: assert_page('orders'), .1)]

for page_name in ['overview', 'inventory', 'orders', 'devices', 'alerts', 'trace', 'settings']:
    steps += [(page_name+'_navigate', lambda name=page_name: widget.navigate(name), .6),
              (page_name+'_layout_check', lambda name=page_name: assert_page(name), .1)]

if VARIANT == 'Full':
    for new_size in [(1366, 768), (600, 900)]:
        tag = f'{new_size[0]}x{new_size[1]}'
        steps += [(tag+'_resize', lambda size=new_size: resize(size), 2.),
                  (tag+'_layout', layout, .1),
                  (tag+'_select', lambda: widget.select_object('AGV-07', True), 1.3),
                  (tag+'_focus', verify_focus, .1),
                  (tag+'_capture', lambda: capture('DeviceResize'), .1)]
        for page_name in ['overview', 'inventory', 'orders', 'devices', 'alerts', 'trace', 'settings']:
            steps += [(tag+'_'+page_name+'_navigate', lambda name=page_name: widget.navigate(name), .6),
                      (tag+'_'+page_name+'_check', lambda name=page_name: assert_page(name), .1)]


def finish(error=None):
    result.update(success=error is None, error=error,
                  failed_step=steps[step][0] if error and step < len(steps) else None,
                  elapsed=time.monotonic()-START)
    if pose_watch:
        result['unfinished_camera_flight'] = pose_watch
    if phase_watch:
        result['unfinished_page_transition'] = phase_watch
    write()
    if handle:
        unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log_error if error else unreal.log)('REVISION8_' + ('FAILED '+str(error) if error else 'SUCCESS'))
    if world:
        unreal.SystemLibrary.execute_console_command(world, 'quit', pc)


def tick(delta_seconds):
    global step, next_at
    try:
        now = time.monotonic()
        assert now-START < 300, 'Revision 8 acceptance timeout'
        collect_samples()
        if pending_capture and not capture_ready():
            return
        if now < next_at:
            return
        if step >= len(steps):
            finish()
            return
        name, action, delay = steps[step]
        if action() is False:
            return
        step += 1
        next_at = time.monotonic()+delay
    except Exception:
        finish(traceback.format_exc())


write()
handle = unreal.register_slate_post_tick_callback(tick)
