"""Verify the truck HUD in an owned offscreen game, without saving assets.

Launch with -game -RenderOffscreen -ExecCmds="py <this script>". Add
-TruckHUDSmall for the separate 960x540 run. Normal runs expect 1920x1080.
Uses Shot showui (FScreenshotRequest with bShowUI=true), because HighResShot
does not include the Slate/UMG overlay. All supplied telemetry is demo data.
This is the truck telemetry regression: stackers are hidden only in this owned
game process. Mixed-equipment coverage lives in verify_stacker_hud_runtime.py.
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
COMMAND_LINE = unreal.SystemLibrary.get_command_line()


def flag(name):
    return bool(re.search(r'(?:^|\s)-' + re.escape(name) + r'(?=\s|$)',
                          COMMAND_LINE, re.IGNORECASE))


assert flag('game') and flag('RenderOffscreen'), (
    'Truck HUD validation requires an owned -game -RenderOffscreen process; '
    'the live editor is not a valid target.')
SMALL = flag('TruckHUDSmall')
SUFFIX = 'Small' if SMALL else 'Full'
EXPECTED_VIEWPORT = (960, 540) if SMALL else (1920, 1080)
REPORT = ROOT / ('Saved/GHS_TruckHUD_Runtime_' + SUFFIX + '.json')
MAP = '/Game/Maps/GHS_CAD_NormalWarehouse'
STARTED = time.monotonic()
result = dict(success=False, status='running', variant=SUFFIX,
              expected_viewport=list(EXPECTED_VIEWPORT), tests=[], captures=[],
              capture_method='Shot showui filename=<absolute path> -nosuffix',
              telemetry_source='explicit test demo; no business feed',
              test_scope='dock-truck telemetry and interaction regression',
              assets_saved=False, visual_review_required=True)
world = pc = pawn = widget = data = selected_actor = None
truck_id = None
trucks = {}
step_index = 0
next_action_at = STARTED
capture_pending = None
handle = None


def write_report():
    REPORT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf8')


def xy(value):
    return [float(value.x), float(value.y)]


def xyz(value):
    return [float(value.x), float(value.y), float(value.z)]


def record(name, **details):
    result['tests'].append(dict(name=name, passed=True,
                                elapsed_seconds=round(time.monotonic() - STARTED, 3),
                                **details))
    write_report()
    unreal.log('TRUCK_HUD_RUNTIME_PASS ' + name)


def telemetry(component):
    return dict(truck_id=str(component.get_editor_property('truck_id')),
                dock_id=str(component.get_editor_property('dock_id')),
                loaded=int(component.get_editor_property('loaded_pallets')),
                total=int(component.get_editor_property('total_pallets')),
                remaining=int(component.get_remaining_pallets()),
                status=str(component.get_editor_property('status')),
                order_id=str(component.get_editor_property('order_id')),
                is_demo_data=bool(component.get_editor_property('is_demo_data')),
                has_telemetry=bool(component.has_telemetry()))


def assert_unknown(component, expected_status):
    state = telemetry(component)
    assert state['loaded'] == state['total'] == state['remaining'] == -1, state
    assert not state['has_telemetry'] and state['order_id'] == '', state
    assert component.get_editor_property('status') == expected_status, state
    return state


def discover():
    global world, pc, pawn, widget
    for candidate in unreal.ObjectIterator(unreal.World):
        controller = unreal.GameplayStatics.get_player_controller(candidate, 0)
        if controller:
            world, pc = candidate, controller
            break
    if pc is None:
        return False
    assert world.get_path_name().split('.')[0] == MAP, world.get_path_name()
    assert pc.get_class().get_path_name() == '/Script/Test.GHSWarehousePlayerController'
    pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
    widget = pc.get_editor_property('truck_hud_widget')
    if not pawn or not widget:
        return False
    widget_class = unreal.load_class(None, '/Script/Test.GHSDockTruckHUDWidget')
    assert widget_class and unreal.MathLibrary.class_is_child_of(widget.get_class(), widget_class)
    assert widget.is_in_viewport(), 'HUD exists but is not attached to the actual viewport'
    unreal.SystemLibrary.execute_console_command(world, 'DisableAllScreenMessages', pc)
    viewport = tuple(pc.get_viewport_size())
    assert viewport == EXPECTED_VIEWPORT, (viewport, EXPECTED_VIEWPORT)
    result.update(map=world.get_path_name(), controller=pc.get_class().get_path_name(),
                  pawn=pawn.get_class().get_path_name(), widget=widget.get_class().get_path_name(),
                  viewport=list(viewport))
    record('actual_game_controller_owns_visible_truck_hud')
    return True


def isolate_truck_regression():
    # The ownership assertion above prevents modifying the interactive editor.
    # Runtime hiding excludes unrelated labels from hit testing, while preserving
    # every registered truck and all production aggregation/selection behavior.
    stackers = unreal.GameplayStatics.get_all_actors_with_tag(world, 'NormalWarehouseFloorStacker')
    for actor in stackers:
        actor.set_actor_hidden_in_game(True)
    result['stackers_hidden_in_owned_test_process'] = len(stackers)
    record('isolate_truck_telemetry_regression_without_saving_assets',
           hidden_stacker_count=len(stackers))
    return True


def verify_registry():
    global data, selected_actor, truck_id
    actors = unreal.GameplayStatics.get_all_actors_with_tag(world, 'IndependentDockTruck')
    assert actors, 'No tagged dock trucks exist in the actual game world'
    for actor in actors:
        tags = [str(tag) for tag in actor.get_editor_property('tags')]
        identities = [tag[len('TwinId='):] for tag in tags if tag.startswith('TwinId=')]
        assert len(identities) == 1, tags
        match = re.fullmatch(r'GHS_DockTruck_([0-9]+)', identities[0])
        assert match, tags
        identifier = 'TRUCK-' + format(int(match.group(1)), '03d')
        assert identifier not in trucks, 'Duplicate runtime identity ' + identifier
        trucks[identifier] = actor
        component = widget.get_truck_data(identifier)
        assert component and component.get_owner() == actor, identifier
        assert str(component.get_editor_property('truck_id')) == identifier
        assert_unknown(component, unreal.GHSDockTruckStatus.AWAITING_DATA)
        assert not component.get_editor_property('is_demo_data'), identifier
    assert widget.get_registered_truck_count() == len(trucks), (
        widget.get_registered_truck_count(), len(trucks))
    truck_id = 'TRUCK-002' if 'TRUCK-002' in trucks else sorted(trucks)[0]
    selected_actor = trucks[truck_id]
    data = widget.get_truck_data(truck_id)
    result.update(actual_tagged_truck_count=len(trucks), truck_ids=sorted(trucks),
                  selected_test_truck=truck_id)
    record('all_actual_tagged_trucks_registered_with_unknown_telemetry', count=len(trucks))
    assert widget.select_truck_by_id(truck_id), truck_id
    assert str(widget.get_selected_truck_id()) == truck_id
    assert not widget.select_truck_by_id('TRUCK-NOT-A-REAL-ID')
    assert str(widget.get_selected_truck_id()) != 'TRUCK-NOT-A-REAL-ID'
    assert widget.get_truck_data('TRUCK-NOT-A-REAL-ID') is None
    assert widget.select_truck_by_id(truck_id)
    record('select_existing_truck_and_reject_missing_identity')
    return True


def position_camera():
    origin, extent = selected_actor.get_actor_bounds(False)
    # Ground-pivot API preserves the camera system's zero-Z invariant.
    pawn.set_desired_location(unreal.Vector(origin.x, origin.y, 0.0), True)
    pawn.set_desired_rotation(unreal.Rotator(pitch=-42.0, yaw=-135.0, roll=0.0), True)
    pawn.set_desired_zoom(max(4200.0, math.hypot(extent.x, extent.y) * 5.0), True)
    record('move_runtime_camera_to_selected_truck', truck_bounds_origin=xyz(origin),
           truck_bounds_extent=xyz(extent))
    return True


def layout_state():
    # RenderOffscreen does not cache Slate's public widget geometry. The native
    # overlay fills the viewport; derive its logical extent from viewport pixels
    # and the same UMG DPI scale used by ProjectWorldLocationToWidgetPosition.
    scale = float(unreal.WidgetLayoutLibrary.get_viewport_scale(world))
    pixel_width, pixel_height = pc.get_viewport_size()
    size = unreal.Vector2D(pixel_width / scale, pixel_height / scale)
    position = widget.get_visible_label_position(truck_id)
    detail_position = widget.get_editor_property('detail_position')
    detail_size = widget.get_editor_property('detail_size')
    return dict(viewport_pixels=list(pc.get_viewport_size()),
                viewport_scale=float(unreal.WidgetLayoutLibrary.get_viewport_scale(world)),
                widget_local_size=xy(size), label_position=xy(position),
                detail_position=xy(detail_position), detail_size=xy(detail_size),
                detail_visible=bool(widget.get_editor_property('detail_visible')),
                visible_labels=int(widget.get_visible_label_count()))


def verify_layout():
    state = layout_state()
    width, height = state['widget_local_size']
    assert width > 0 and height > 0, state
    assert state['visible_labels'] > 0, state
    label_x, label_y = state['label_position']
    assert 0 <= label_x < width and 0 <= label_y < height, state
    assert state['detail_visible'], state
    x, y = state['detail_position']
    w, h = state['detail_size']
    assert w > 0 and h > 0 and x >= -0.5 and y >= -0.5, state
    assert x + w <= width + 0.5 and y + h <= height + 0.5, state
    assert abs(w / h - 320.0 / 184.0) < 0.001, state
    # Keep the expanded card below 7% of either supported viewport. This also
    # catches accidental double DPI scaling in the 960x540 readability path.
    state['detail_viewport_fraction'] = w * h / (width * height)
    assert state['detail_viewport_fraction'] < 0.07, state
    assert abs(pawn.get_actor_location().z) < 0.01
    record('label_and_selected_detail_fit_actual_viewport', **state)
    return True


def clear_selection():
    widget.clear_selection()
    return True


def click_label():
    assert str(widget.get_selected_truck_id()) == ''
    assert not widget.get_editor_property('detail_visible')
    position = widget.get_visible_label_position(truck_id)
    assert position.x >= 0 and position.y >= 0, xy(position)
    # Public positions and HandlePointerClick both use widget-local, DPI-adjusted units.
    assert widget.handle_pointer_click(unreal.Vector2D(position.x + 8.0, position.y + 8.0))
    if str(widget.get_selected_truck_id()) == truck_id:
        record('click_visible_single_label_selects_its_truck')
        return True
    # A grouped label opens its member list without choosing an arbitrary truck.
    assert str(widget.get_selected_truck_id()) == ''
    members = [str(member) for member in widget.get_expanded_cluster_members()]
    assert truck_id in members, (truck_id, members)
    page = members.index(truck_id) // 5
    assert widget.set_cluster_page(page)
    record('click_grouped_label_opens_list_for_requested_truck',
           members=members, requested_page=page)
    return True


def select_clicked_member():
    if str(widget.get_selected_truck_id()) == truck_id:
        return True
    position = widget.get_member_row_position(truck_id)
    assert position.x >= 0 and position.y >= 0, (truck_id, xy(position))
    assert widget.handle_pointer_click(unreal.Vector2D(position.x + 12.0, position.y + 12.0))
    assert str(widget.get_selected_truck_id()) == truck_id
    record('click_requested_member_row_selects_exact_truck', truck_id=truck_id)
    return True


def click_close():
    verify_layout()
    position = widget.get_editor_property('detail_position')
    size = widget.get_editor_property('detail_size')
    # Close-button center is (304,18) in the unscaled 320x184 detail card.
    point = unreal.Vector2D(position.x + size.x * (304.0 / 320.0),
                            position.y + size.y * (18.0 / 184.0))
    assert widget.handle_pointer_click(point), xy(point)
    record('click_selected_detail_close_button', local_position=xy(point))
    return True


def verify_closed_and_reselect():
    assert str(widget.get_selected_truck_id()) == ''
    assert not widget.get_editor_property('detail_visible')
    assert widget.select_truck_by_id(truck_id)
    record('close_clears_selection_and_detail')
    return True


def request_capture(state_name):
    global capture_pending
    path = ROOT / ('Saved/GHS_TruckHUD_' + state_name + '_' + SUFFIX + '.png')
    state = layout_state()
    assert state['detail_visible'] and widget.is_in_viewport(), state
    capture_pending = dict(state=state_name, path=path, requested_at=time.time(),
                           requested_monotonic=time.monotonic(), layout=state,
                           telemetry=telemetry(data))
    # UE 5.4 GameViewportClient.cpp HandleScreenshotCommand explicitly supports
    # SHOWUI, filename= and nosuffix, including the complete Slate window.
    command = 'Shot showui filename="' + path.as_posix() + '" -nosuffix'
    unreal.SystemLibrary.execute_console_command(world, command, pc)
    return True


def await_capture():
    global capture_pending
    pending = capture_pending
    path = pending['path']
    assert time.monotonic() - pending['requested_monotonic'] < 30.0, (
        'Timed out waiting for fresh Shot showui output', str(path))
    if not path.is_file() or path.stat().st_mtime < pending['requested_at']:
        return False
    if path.stat().st_size < 10000:
        return False
    with path.open('rb') as stream:
        header = stream.read(24)
    assert header[:8] == b'\x89PNG\r\n\x1a\n', ('Not a PNG capture', str(path))
    width, height = struct.unpack('>II', header[16:24])
    assert width > 400 and height > 300, (width, height)
    captured = dict(state=pending['state'], path=str(path), bytes=path.stat().st_size,
                    resolution=[width, height], layout=pending['layout'],
                    telemetry=pending['telemetry'], contains_ui_requested=True)
    result['captures'].append(captured)
    capture_pending = None
    record('fresh_' + pending['state'].lower() + '_game_screenshot_with_showui',
           image=str(path), resolution=[width, height])
    return True


def apply_demo():
    assert data.set_telemetry(18, 24, unreal.GHSDockTruckStatus.LOADING, 'OUT-1026', True)
    return True


def verify_demo():
    state = telemetry(data)
    assert state['loaded'] == 18 and state['total'] == 24 and state['remaining'] == 6, state
    assert state['is_demo_data'] and state['has_telemetry'], state
    assert state['order_id'] == 'OUT-1026', state
    assert data.get_editor_property('status') == unreal.GHSDockTruckStatus.LOADING
    assert abs(float(data.get_loading_progress()) - 0.75) < 0.001
    record('explicit_demo_update_has_18_loaded_6_remaining_and_demo_marker', telemetry=state)
    return True


def apply_offline():
    # Supplying the previous numbers deliberately checks they cannot survive
    # an offline state transition and be mistaken for current telemetry.
    assert data.set_telemetry(18, 24, unreal.GHSDockTruckStatus.OFFLINE, 'OUT-1026', True)
    return True


def verify_offline():
    state = assert_unknown(data, unreal.GHSDockTruckStatus.OFFLINE)
    record('offline_clears_previous_loaded_total_remaining_and_order', telemetry=state)
    return request_capture('Offline')


def apply_long_values():
    assert data.set_telemetry(2100000000, 2147483647, unreal.GHSDockTruckStatus.WARNING,
                              'OUT-20261019-WAREHOUSE-02-LONG-ORDER-IDENTIFIER', True)
    return True


def verify_long_values():
    assert data.get_remaining_pallets() == 47483647
    assert data.has_telemetry() and data.get_editor_property('is_demo_data')
    verify_layout()
    record('long_counts_and_order_keep_compact_card_within_viewport', telemetry=telemetry(data))
    return request_capture('LongValues')


STEPS = [
    ('find_game_hud', discover, 2.0),
    ('isolate_truck_telemetry_regression', isolate_truck_regression, 0.2),
    ('registry_and_default_data', verify_registry, 0.2),
    ('position_camera', position_camera, 3.0),
    ('layout', verify_layout, 0.1),
    ('clear_selection', clear_selection, 0.3),
    ('click_label', click_label, 0.4),
    ('select_clicked_member', select_clicked_member, 0.4),
    ('click_close', click_close, 0.4),
    ('verify_close', verify_closed_and_reselect, 0.4),
    ('capture_default', lambda: request_capture('Default'), 0.2),
    ('apply_demo', apply_demo, 0.4),
    ('verify_demo', verify_demo, 0.1),
    ('apply_offline', apply_offline, 0.4),
    ('verify_offline', verify_offline, 0.2),
    ('apply_long_values', apply_long_values, 0.4),
    ('verify_long_values', verify_long_values, 0.2),
    ('restore_demo', apply_demo, 0.4),
    ('verify_restored_demo', verify_demo, 0.1),
    ('final_layout', verify_layout, 1.0),
    ('capture_demo', lambda: request_capture('Demo'), 0.2),
]


def finish(error=None):
    result.update(success=error is None, status='failed' if error else 'success',
                  elapsed_seconds=round(time.monotonic() - STARTED, 3))
    if error:
        result.update(error=error, failed_step=STEPS[step_index][0]
                      if step_index < len(STEPS) else 'finish')
    write_report()
    if handle is not None:
        unreal.unregister_slate_post_tick_callback(handle)
    if error:
        unreal.log_error('TRUCK_HUD_RUNTIME_FAILED ' + error)
    else:
        unreal.log('TRUCK_HUD_RUNTIME_SUCCESS ' + str(REPORT))
    if world and pc:
        unreal.SystemLibrary.quit_game(world, pc, unreal.QuitPreference.QUIT, False)
    else:
        # The command-line ownership guard also covers boot/class failures.
        unreal.SystemLibrary.execute_console_command(None, 'quit')


def tick(delta_seconds):
    global step_index, next_action_at
    try:
        now = time.monotonic()
        assert now - STARTED < 150.0, 'Truck HUD runtime validation timed out'
        if capture_pending is not None and not await_capture():
            return
        if now < next_action_at:
            return
        if step_index == len(STEPS):
            finish()
            return
        name, action, settle_seconds = STEPS[step_index]
        if action() is False:
            assert now - STARTED < 45.0, 'Game HUD did not become ready: ' + name
            return
        step_index += 1
        next_action_at = now + settle_seconds
    except Exception:
        finish(traceback.format_exc())


write_report()
handle = unreal.register_slate_post_tick_callback(tick)
unreal.log('TRUCK_HUD_RUNTIME_VERIFIER_READY ' + SUFFIX)
