"""Owned offscreen acceptance for the static warehouse title and rounded HUD.

Requires -game -RenderOffscreen -TwinDiagnostics at 1920x1080. Uses existing
native widget routes, camera state, browser diagnostics, and rendered captures.
Does not synthesize OS input, mutate assets, or claim pixel-level visual QA.
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

ROOT = Path(r'D:/UEPro/Test')
for flag in ('game', 'RenderOffscreen', 'TwinDiagnostics'):
    assert re.search(r'(?:^|\s)-' + flag + r'(?:\s|$)', unreal.SystemLibrary.get_command_line(), re.I), flag
OUT = ROOT / 'Saved/RoundedHUD'
OUT.mkdir(parents=True, exist_ok=True)
REPORT = OUT / 'runtime.json'
START = time.monotonic()
world = pc = pawn = widget = handle = None
step = 0
current_size = (1920, 1080)
pending_capture = title_watch = filter_watch = None
rack_geometry = None
initial_resize_requested = None
result = dict(success=False, checks=[], captures=[], assets_saved=False,
              input_scope='Native chrome and scene-click routes; no OS input simulation',
              visual_scope='Screenshots for human inspection; geometry and behavior asserted separately',
              poi_clearance=dict(frames=0, labels=0, selected_labels=0,
                                 widths_source='Native FLabel size contract: region 176, group 246, device 236'))


def xyz(value):
    return [float(value.x), float(value.y), float(value.z)]


def distance(a, b):
    return math.sqrt(sum((x-y)**2 for x, y in zip(a, b)))


def write():
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


def record(name, **values):
    result['checks'].append(dict(name=name, passed=True, **values))
    write()
    unreal.log('ROUNDED_HUD_CHECK ' + name)


def browser():
    text = widget.get_editor_property('last_browser_report')
    return json.loads(text) if text else {}


def poi():
    return json.loads(widget.get_poi_report())


def snapshot():
    return json.loads(widget.get_snapshot())


def selected():
    return str(widget.get_editor_property('selected_id'))


def command(action, **values):
    widget.command(json.dumps(dict(action=action, **values)))


def header():
    return 52 if current_size[0] < 700 else 64


def pose():
    camera = pawn.get_editor_property('warehouse_camera')
    arm = pawn.get_editor_property('spring_arm_component')
    rotation = camera.get_world_rotation()
    return dict(pivot=xyz(pawn.get_actor_location()), camera=xyz(camera.get_world_location()),
                rotation=[rotation.pitch, rotation.yaw, rotation.roll],
                distance=float(arm.get_editor_property('target_arm_length')),
                socket_offset=xyz(arm.get_editor_property('socket_offset')),
                active=bool(pawn.is_pose_transition_active()))


def same_pose(before, after):
    for key in ('pivot', 'camera', 'socket_offset'):
        assert distance(before[key], after[key]) < .1, ('Static title moved '+key, before, after)
    assert abs(before['distance']-after['distance']) < .1, ('Static title changed zoom', before, after)
    assert max(abs((a-b+180) % 360-180) for a, b in zip(before['rotation'], after['rotation'])) < .001
    assert not after['active'], 'Static title started a camera transition'


def discover():
    global world, pc, pawn, widget, initial_resize_requested
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
    actual_size = tuple(pc.get_viewport_size())
    if actual_size != current_size:
        if initial_resize_requested is None:
            initial_resize_requested = time.monotonic()
            result['initial_resize'] = dict(actual=list(actual_size), requested=list(current_size))
            write()
            unreal.SystemLibrary.execute_console_command(world, 'r.SetRes 1920x1080w', pc)
        assert time.monotonic()-initial_resize_requested < 20, ('Initial resolution did not settle', actual_size, current_size)
        return False
    if pawn.is_pose_transition_active():
        return False
    assert any(row['id'] == 'AGV-01' for row in snapshot()['equipment']), 'AGV-01 fixture absent'
    record('owned_scene_and_browser_ready', map=world.get_path_name(), resolution=list(current_size))


def layout_ready():
    if tuple(pc.get_viewport_size()) != current_size or pawn.is_pose_transition_active():
        return False
    panel, size = widget.get_panel_visual_position(), widget.get_panel_visual_size()
    if abs(panel.x+size.x-current_size[0]) > .1 or abs(panel.y+size.y-current_size[1]) > .1:
        return False
    report = browser()
    if widget.get_panel_transition_progress() != 1 or report.get('transition', {}).get('phase') != 'idle':
        return False
    assert not report.get('overflow'), report
    assert not report.get('imageFailures'), report
    assert not widget.is_scene_point(unreal.Vector2D(panel.x+size.x*.5, panel.y+size.y*.5))
    record('responsive_layout', resolution=list(current_size), panel=[panel.x, panel.y, size.x, size.y],
           expected_title_path=[32, header()+25], expected_title=[32, header()+50],
           expected_filter_row=[32, header()+147, 96, 40, 104])


def select_agv():
    assert widget.select_object('AGV-01', True)


def selected_ready():
    if pawn.is_pose_transition_active() or (browser().get('detail') or {}).get('id') != 'AGV-01':
        return False
    if browser().get('transition', {}).get('phase') != 'idle':
        return False
    assert selected() == 'AGV-01'
    assert snapshot()['selection']['id'] == 'AGV-01'
    record('agv_selected_before_title_input', selection=selected(), pose=pose())


def title_input():
    global title_watch
    assert selected() == 'AGV-01' and not pawn.is_pose_transition_active()
    before = pose()
    points = [(72, header()+34), (32, header()+25), (32, header()+50),
              (25, header()+17), (243, header()+95), (130, header()+90)]
    for x, y in points:
        point = unreal.Vector2D(x, y)
        assert not widget.handle_chrome_click(point), ('Static title still acts as overview button', x, y)
        assert not widget.is_scene_point(point), ('Static title permits scene input', x, y)
        assert not widget.handle_scene_click(point), ('Static title click fell through to scene selection', x, y)
        assert selected() == 'AGV-01', 'Static title cleared selection'
        same_pose(before, pose())
    title_watch = dict(start=time.monotonic(), pose=before, points=points, samples=0)


def title_settled():
    title_watch['samples'] += 1
    assert selected() == 'AGV-01'
    same_pose(title_watch['pose'], pose())
    if time.monotonic()-title_watch['start'] < .5:
        return False
    assert snapshot()['selection']['id'] == 'AGV-01'
    assert (browser().get('detail') or {}).get('id') == 'AGV-01'
    record('static_title_does_not_reset_focus_or_selection', samples=title_watch['samples'],
           protected_points=title_watch['points'], selection=selected())


def reset_button():
    assert selected() == 'AGV-01'
    tool = widget.get_scene_controls_position()
    assert widget.handle_chrome_click(unreal.Vector2D(tool.x+20, tool.y+92))
    assert not selected(), 'Visible reset button did not immediately clear selection'


def reset_ready():
    if pawn.is_pose_transition_active() or browser().get('detail') is not None or browser().get('transition', {}).get('phase') != 'idle':
        return False
    assert not selected() and snapshot().get('selection') is None
    assert not any(row['selected'] for row in poi()['labels']), 'Reset retained a selected POI'
    assert not pawn.uses_object_pivot()
    assert distance(xyz(pawn.get_actor_location()), xyz(pawn.get_editor_property('overview_center'))) < .1
    record('visible_reset_restores_overview_and_clears_all_selection', pose=pose())


def filter_start(index):
    global filter_watch
    before = poi()
    assert 'pointFilter' in before, 'Native POI report needs pointFilter diagnostic to verify empty filtered results'
    x, y = 32+index*104+48, header()+147+20
    assert widget.handle_chrome_click(unreal.Vector2D(x, y)), ('New filter button is not clickable', index, x, y)
    filter_watch = dict(index=index, expected=('all', 'rack', 'truck', 'charger')[index],
                        before_builds=before['performance']['candidateBuilds'], started=time.monotonic())


def filter_ready():
    report = poi()
    if report['performance']['candidateBuilds'] <= filter_watch['before_builds'] or time.monotonic()-filter_watch['started'] < .25:
        return False
    expected = filter_watch['expected']
    assert report['pointFilter'] == expected, (expected, report)
    if expected != 'all':
        assert all(row['icon'] == expected or row['id'] == selected() for row in report['labels']), (expected, report['labels'])
    else:
        assert report['performance']['candidateCount'] > 1, 'All filter unexpectedly lost the point catalogue'
    before = report['pointFilter']
    for gap in range(3):
        assert not widget.handle_chrome_click(unreal.Vector2D(32+gap*104+96+4, header()+147+20)), '8px filter gap still changes filter'
    for index in range(4):
        assert not widget.handle_chrome_click(unreal.Vector2D(20+index*104+48, header()+84)), 'Old filter row still accepts clicks'
    assert poi()['pointFilter'] == before, 'Gap or old filter row changed filter state'
    record('filter_'+expected+'_and_noninteractive_gaps', resolution=list(current_size),
           visible_labels=report['labels'], candidate_count=report['performance']['candidateCount'])


def check_hidden_filters():
    assert current_size == (600, 900) or current_size == (800, 480)
    before = poi()
    panel, size = widget.get_panel_visual_position(), widget.get_panel_visual_size()
    for index in range(4):
        for offset in (20, 39):
            point = unreal.Vector2D(32+index*104+48, header()+147+offset)
            assert not widget.handle_chrome_click(point), ('Hidden filter still accepts clicks', current_size, index, offset)
            if panel.x <= point.x < panel.x+size.x and panel.y <= point.y < panel.y+size.y:
                assert not widget.is_scene_point(point), ('Hidden filter position leaks through bottom panel', current_size, point)
    assert poi()['pointFilter'] == before['pointFilter']
    record('hidden_filter_row_has_no_hit_targets_or_panel_input_leak', resolution=list(current_size))


def check_poi_clearance():
    if not widget or tuple(pc.get_viewport_size()) != current_size:
        return
    panel, size = widget.get_panel_visual_position(), widget.get_panel_visual_size()
    if abs(panel.x+size.x-current_size[0]) > .1 or abs(panel.y+size.y-current_size[1]) > .1:
        return
    if widget.get_panel_transition_progress() != 1:
        return
    scene_width = current_size[0] if current_size[0] < 900 else panel.x
    scene_height = panel.y-header() if current_size[0] < 900 else current_size[1]-header()
    protected = [('heading', (24, header()+16, 220, 80))]
    if scene_width > 660 and scene_height >= 195:
        protected.append(('filters', (24, header()+108, 424, 87)))
    stats = result['poi_clearance']
    stats['frames'] += 1
    for label in poi()['labels']:
        width = 176 if label['id'].startswith('REGION:') else 246 if label['id'].startswith('GROUP:') else 236
        x, y, height = label['x'], label['y'], label['height']
        stats['labels'] += 1
        stats['selected_labels'] += int(label['selected'])
        for name, (left, top, rect_width, rect_height) in protected:
            overlap = x < left+rect_width and x+width > left and y < top+rect_height and y+height > top
            assert not overlap, ('POI overlaps protected '+name, current_size, label, width)


def inspect_rack_geometry():
    global rack_geometry
    low, high = [math.inf]*3, [-math.inf]*3
    instances = main_instances = 0
    # Independent CAD footprint of the large 1472-rack field. Do not use the
    # full 1629-rack bounds: detached peripheral racks caused the reported drift.
    main_roi = (-24000., -7000., -5400., 4200.)
    for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor):
        for component in actor.get_components_by_class(unreal.InstancedStaticMeshComponent):
            mesh = component.get_editor_property('static_mesh')
            if not mesh or not mesh.get_name().startswith('SM_GHS_V2Rack_'):
                continue
            bounds = mesh.get_bounds()
            local = [unreal.Vector(bounds.origin.x+sx*bounds.box_extent.x,
                                   bounds.origin.y+sy*bounds.box_extent.y,
                                   bounds.origin.z+sz*bounds.box_extent.z)
                     for sx, sy, sz in itertools.product((-1, 1), repeat=3)]
            for index in range(component.get_instance_count()):
                transform = component.get_instance_transform(index, world_space=True)
                center = unreal.MathLibrary.transform_location(transform, bounds.origin)
                instances += 1
                if not (main_roi[0] < center.x < main_roi[1] and main_roi[2] < center.y < main_roi[3]):
                    continue
                for corner in local:
                    point = xyz(unreal.MathLibrary.transform_location(transform, corner))
                    low = [min(a, b) for a, b in zip(low, point)]
                    high = [max(a, b) for a, b in zip(high, point)]
                main_instances += 1
    assert instances > 0 and instances == snapshot()['rackInstanceCount']
    assert main_instances == 1472, ('CAD main rack field changed; update its independent acceptance footprint', main_instances)
    rack_geometry = dict(low=low, high=high, center=[(a+b)*.5 for a, b in zip(low, high)],
                         instances=instances, main_instances=main_instances, cad_roi_xy_cm=list(main_roi),
                         reference_center_cm=[-15515.82495, -575.719, 457.7000141],
                         reference_sources=['SourceAssets/GHS/ue_scene_registry.json',
                                            'SourceAssets/GHS/RefinementV2/Racks/refined_rack_cargo.json'])
    assert all(abs(actual-expected) < 20 for actual, expected in zip(rack_geometry['center'], rack_geometry['reference_center_cm'])), rack_geometry
    result['rack_geometry'] = rack_geometry
    record('main_rack_field_center_from_live_instance_bounds', geometry=rack_geometry)


def check_region_anchor():
    report = poi()
    assert 'regionPoints' in report, 'Native POI report needs regionPoints containing id/worldPosition'
    rows = {row['id']: row for row in report['regionPoints']}
    assert 'REGION:racks' in rows, rows
    row = rows['REGION:racks']
    assert isinstance(row['worldPosition'], list) and len(row['worldPosition']) == 3, row
    point, center = [float(value) for value in row['worldPosition']], rack_geometry['center']
    assert distance(point[:2], center[:2]) < 20, ('Rack POI XY is not at the main rack field center', row, center)
    assert all(math.isfinite(v) for v in point+center)
    assert abs(point[2]-(center[2]+80)) < 20, ('Rack POI anchor is not near the main field mid-height', row, center)
    assert abs(point[0]-(-600.)) > 10000, 'Rack POI regressed to the full warehouse rack bbox near the floor storage'
    record('rack_region_poi_uses_main_field_center_xy', resolution=list(current_size), region_point=row,
           expected_region_center=center, rack_instance_count=snapshot()['rackInstanceCount'])


def rack_view():
    command('preset', value='racks')


def rack_ready():
    if pawn.is_pose_transition_active():
        return False
    assert not selected()
    check_region_anchor()
    record('rack_region_view_settled', resolution=list(current_size), pose=pose(), poi=poi())


def overview():
    command('overview')


def capture(label):
    global pending_capture
    assert pending_capture is None
    path = OUT / f'rounded_{current_size[0]}x{current_size[1]}_{label}.png'
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
    current_size = (width, height)
    unreal.SystemLibrary.execute_console_command(world, f'r.SetRes {width}x{height}w', pc)


steps = [('discover', discover), ('layout', layout_ready), ('rack_geometry', inspect_rack_geometry), ('region_anchor', check_region_anchor),
         ('overview_capture', lambda: capture('overview')), ('select_agv', select_agv),
         ('selection_ready', selected_ready), ('agv_capture', lambda: capture('agv01')),
         ('static_title_input', title_input), ('static_title_settled', title_settled),
         ('reset_button', reset_button), ('reset_ready', reset_ready)]
for index in range(4):
    steps += [(f'filter_{index}_click', lambda i=index: filter_start(i)), (f'filter_{index}_ready', filter_ready)]
steps += [('filter_restore_all', lambda: filter_start(0)), ('filter_restore_ready', filter_ready),
          ('racks', rack_view), ('racks_ready', rack_ready), ('racks_capture', lambda: capture('racks')),
          ('overview_again', overview), ('overview_ready', reset_ready)]
for width, height in ((1366, 768), (600, 900), (800, 480)):
    steps += [(f'resize_{width}', lambda w=width, h=height: resize(w, h)),
              (f'layout_{width}', layout_ready), (f'overview_{width}', overview),
              (f'overview_{width}_ready', reset_ready), (f'region_anchor_{width}', check_region_anchor)]
    if width in (600, 800):
        steps += [(f'filters_hidden_{width}', check_hidden_filters)]
    steps += [(f'capture_{width}', lambda: capture('overview'))]


def finish(error=None):
    if error is None:
        assert result['poi_clearance']['frames'] > 0 and result['poi_clearance']['labels'] > 0, 'No visible POI clearance frames were checked'
    result.update(success=error is None, error=error,
                  failed_step=steps[step][0] if error and step < len(steps) else None,
                  elapsed_seconds=time.monotonic()-START)
    write()
    if handle:
        unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log_error if error else unreal.log)('ROUNDED_HUD_' + ('FAILED '+str(error) if error else 'SUCCESS'))
    if world:
        unreal.SystemLibrary.execute_console_command(world, 'quit', pc)


def tick(delta_seconds):
    global step
    try:
        assert time.monotonic()-START < 210, ('Rounded HUD acceptance timeout', steps[step][0],
                                             tuple(pc.get_viewport_size()) if pc else None, current_size)
        check_poi_clearance()
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
