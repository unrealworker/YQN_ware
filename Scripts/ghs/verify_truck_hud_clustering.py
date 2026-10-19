"""Exercise distance-gated 2x2 HUD aggregation; never save assets.

Run the real warehouse with -game -RenderOffscreen -ResX=1920 -ResY=1080
-ExecCmds="py <this script>". Supported viewport variants are:
Full 1920x1080; -TruckHUDSmall 960x540; -TruckHUDUltraWide 2560x1080;
-TruckHUDPortrait 800x1200; -TruckHUDNarrow 360x800.
Full also resizes the live viewport to 1280x960.
The Pawn threshold defaults to 10000: nearer views show every truck separately.
All waits observe real per-frame geometry/progress or screenshot completion.
Screenshots are requested at measured progress; UE renders them on a later frame.
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
    'Clustering validation requires an owned -game -RenderOffscreen process.')
VARIANTS = {'TruckHUDSmall': ('Small', (960, 540)),
            'TruckHUDUltraWide': ('UltraWide', (2560, 1080)),
            'TruckHUDPortrait': ('Portrait', (800, 1200)),
            'TruckHUDNarrow': ('Narrow', (360, 800))}
active_variants = [value for name, value in VARIANTS.items() if flag(name)]
assert len(active_variants) <= 1, 'Choose only one viewport variant flag.'
SUFFIX, EXPECTED_VIEWPORT = active_variants[0] if active_variants else ('Full', (1920, 1080))
RESIZED_VIEWPORT = (1280, 960)
REPORT = ROOT / ('Saved/GHS_TruckHUD_Clustering_' + SUFFIX + '.json')
STARTED = time.monotonic()
result = dict(success=False, status='running', variant=SUFFIX, tests=[], samples=[],
              captures=[], assets_saved=False, visual_review_required=True,
              grid_dimensions=[2, 2], maximum_aggregated_labels=4,
              capture_method='Shot showui; progress measured at request')
world = pc = pawn = widget = spring_arm = None
trucks = {}
stage = 'discover'
stage_started = STARTED
stage_frames = []
last_signature = None
stable_frames = 0
stationary_keys = None
wide_center = None
wide_zoom = 0.0
group = None
selected_id = None
members = []
jitter_index = 0
pending_captures = []
captured_states = set()
toggle_progress = {}
singleton_zoom_attempts = 0
resize_before_partition = None
threshold_camera_state = None
saved_actor_tick_enabled = None
DEFAULT_CLUSTER_THRESHOLD = 10000.0
handle = None


def xy(value):
    return [float(value.x), float(value.y)]


def write_report():
    REPORT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf8')


def record(name, **details):
    result['tests'].append(dict(name=name, passed=True, **details))
    write_report()
    unreal.log('TRUCK_HUD_CLUSTER_PASS ' + name)


def advance(name):
    global stage, stage_started, stage_frames, last_signature, stable_frames
    stage = name
    stage_started = time.monotonic()
    stage_frames = []
    last_signature = None
    stable_frames = 0


def discover():
    global world, pc, pawn, widget, spring_arm, wide_center, wide_zoom
    for candidate in unreal.ObjectIterator(unreal.World):
        controller = unreal.GameplayStatics.get_player_controller(candidate, 0)
        if controller:
            world, pc = candidate, controller
            break
    if pc is None:
        return False
    pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
    widget = pc.get_editor_property('truck_hud_widget')
    if not pawn or not widget:
        return False
    assert world.get_path_name().split('.')[0] == '/Game/Maps/GHS_CAD_NormalWarehouse'
    assert widget.is_in_viewport()
    assert tuple(pc.get_viewport_size()) == EXPECTED_VIEWPORT
    required = ('get_visible_labels', 'get_expanded_cluster_members', 'toggle_cluster',
                'set_cluster_page', 'get_member_row_position')
    missing = [name for name in required if not callable(getattr(widget, name, None))]
    assert not missing, 'Missing animated cluster public API: ' + ', '.join(missing)
    for name in ('detail_transition_progress', 'cluster_transition_progress',
                 'cluster_list_visible', 'cluster_list_position', 'cluster_list_size'):
        widget.get_editor_property(name)
    try:
        threshold = float(pawn.get_editor_property('hud_cluster_min_arm_length'))
    except Exception as error:
        raise AssertionError('Camera Pawn must expose hud_cluster_min_arm_length') from error
    assert threshold == DEFAULT_CLUSTER_THRESHOLD, ('Unexpected default HUD threshold', threshold)
    spring_arm = pawn.get_component_by_class(unreal.SpringArmComponent)
    assert spring_arm is not None, 'The warehouse camera must have a real spring arm'
    record('pawn_exposes_default_10000_cluster_threshold', threshold=threshold)
    for actor in unreal.GameplayStatics.get_all_actors_with_tag(world, 'IndependentDockTruck'):
        tags = [str(tag) for tag in actor.get_editor_property('tags')]
        identities = [tag[len('TwinId='):] for tag in tags if tag.startswith('TwinId=')]
        assert len(identities) == 1, tags
        match = re.fullmatch(r'GHS_DockTruck_([0-9]+)', identities[0])
        assert match, identities
        truck_id = 'TRUCK-' + format(int(match.group(1)), '03d')
        assert truck_id not in trucks
        trucks[truck_id] = actor
        assert widget.get_truck_data(truck_id).get_owner() == actor
    assert len(trucks) == 52, ('Actual supplied warehouse must contain 52 trucks', len(trucks))
    assert widget.get_registered_truck_count() == len(trucks)
    bounds = [actor.get_actor_bounds(False) for actor in trucks.values()]
    min_x = min(origin.x - extent.x for origin, extent in bounds)
    max_x = max(origin.x + extent.x for origin, extent in bounds)
    min_y = min(origin.y - extent.y for origin, extent in bounds)
    max_y = max(origin.y + extent.y for origin, extent in bounds)
    wide_center = unreal.Vector((min_x + max_x) / 2, (min_y + max_y) / 2, 0)
    wide_zoom = max(18000.0, math.hypot(max_x - min_x, max_y - min_y) * 1.1)
    unreal.SystemLibrary.execute_console_command(world, 'DisableAllScreenMessages', pc)
    result.update(map=world.get_path_name(), truck_count=len(trucks),
                  viewport=list(pc.get_viewport_size()), wide_zoom=wide_zoom)
    record('real_game_exposes_cluster_interactions_and_52_trucks')
    widget.clear_selection()
    set_wide_camera()
    return True


def set_wide_camera():
    pawn.set_desired_location(wide_center, True)
    pawn.set_desired_rotation(unreal.Rotator(pitch=-60.0, yaw=-135.0, roll=0.0), True)
    pawn.set_desired_zoom(wide_zoom, True)


def camera_state():
    location = pawn.get_actor_location()
    rotation = pawn.get_actor_rotation()
    return [float(location.x), float(location.y), float(location.z),
            float(rotation.pitch), float(rotation.yaw), float(rotation.roll),
            float(spring_arm.get_editor_property('target_arm_length')),
            float(pawn.get_editor_property('desired_zoom'))]


def assert_threshold_preserves_selected_detail(frame):
    current_camera = camera_state()
    assert all(abs(a-b) <= .001 for a, b in zip(current_camera, threshold_camera_state)), (
        'Threshold-only test moved the camera', threshold_camera_state, current_camera)
    assert frame['selected'] == selected_id and frame['detail_visible'], (
        'Changing aggregation mode lost the selected truck detail', selected_id, frame)
    assert frame['detail_progress'] >= .999, 'Changing mode restarted or closed the open detail'


def read_frame(delta_seconds):
    labels = []
    for label in widget.get_visible_labels():
        labels.append(dict(key=str(label.get_editor_property('key')),
                           ids=[str(value) for value in label.get_editor_property('truck_ids')],
                           position=xy(label.get_editor_property('position')),
                           size=xy(label.get_editor_property('size')),
                           opacity=float(label.get_editor_property('opacity'))))
    labels.sort(key=lambda label: label['key'])
    frame = dict(stage=stage, time=round(time.monotonic() - STARTED, 6),
                 delta_seconds=float(delta_seconds), labels=labels,
                 viewport=list(pc.get_viewport_size()),
                 actual_arm_length=float(spring_arm.get_editor_property('target_arm_length')),
                 desired_zoom=float(pawn.get_editor_property('desired_zoom')),
                 cluster_threshold=float(pawn.get_editor_property('hud_cluster_min_arm_length')),
                 detail_progress=float(widget.get_editor_property('detail_transition_progress')),
                 list_progress=float(widget.get_editor_property('cluster_transition_progress')),
                 detail_visible=bool(widget.get_editor_property('detail_visible')),
                 list_visible=bool(widget.get_editor_property('cluster_list_visible')),
                 detail_position=xy(widget.get_editor_property('detail_position')),
                 detail_size=xy(widget.get_editor_property('detail_size')),
                 list_position=xy(widget.get_editor_property('cluster_list_position')),
                 list_size=xy(widget.get_editor_property('cluster_list_size')),
                 selected=str(widget.get_selected_truck_id()))
    for label in labels:
        assert label['ids'] and len(label['ids']) == len(set(label['ids'])), label
        assert set(label['ids']) <= trucks.keys(), label
        assert -0.001 <= label['opacity'] <= 1.001, label
        assert all(math.isfinite(value) for value in label['position'] + label['size']), label
    assert 0 <= frame['detail_progress'] <= 1.001, frame
    assert 0 <= frame['list_progress'] <= 1.001, frame
    frame['aggregate_expected'] = frame['actual_arm_length'] >= frame['cluster_threshold']
    if frame['aggregate_expected']:
        assert len(labels) <= 4, ('More than four active quadrant labels in the distant view', labels)
    assert abs(pawn.get_actor_location().z) < .01, 'Camera pawn left the ground plane'
    stage_frames.append(frame)
    result['samples'].append(frame)
    return frame


def signature(frame):
    return tuple((label['key'], tuple(label['ids']),
                  tuple(round(value, 1) for value in label['position']),
                  round(label['opacity'], 3)) for label in frame['labels'])


def settled(frame):
    global stable_frames, last_signature
    value = signature(frame)
    stable_frames = stable_frames + 1 if value == last_signature else 0
    last_signature = value
    # A spatial partition can be unchanged during the 200 ms crossing dwell;
    # do not mistake those early frames for the committed, animated result.
    return stable_frames >= 8 and time.monotonic() - stage_started >= .55


def viewport_size():
    dpi = float(unreal.WidgetLayoutLibrary.get_viewport_scale(world))
    width, height = pc.get_viewport_size()
    # Slate local geometry and UE's widget projection use float32 coordinates.
    # Keep their precision: a double-precision PC-size/DPI reconstruction can
    # put an exactly centered projected point just left of the strict boundary.
    as_slate_float = lambda value: struct.unpack('f', struct.pack('f', value))[0]
    return as_slate_float(width / dpi), as_slate_float(height / dpi)


def projected_grid():
    # The expected partition comes from real world anchors and current viewport
    # dimensions, never from a cluster key, public cell index, or label position.
    # Normalized coordinates cancel DPI and the widget's internal draw scale.
    dpi = float(unreal.WidgetLayoutLibrary.get_viewport_scale(world))
    width, height = viewport_size()
    pixel_width, pixel_height = pc.get_viewport_size()
    draw_scale = min(max(dpi, .75), min(pixel_width / 640, pixel_height / 540)) / dpi
    inset = 8 * draw_scale
    cells = {}
    for truck_id, actor in trucks.items():
        origin, extent = actor.get_actor_bounds(False)
        point = unreal.WidgetLayoutLibrary.project_world_location_to_widget_position(
            pc, unreal.Vector(origin.x, origin.y, origin.z + extent.z + 80), True)
        if point is not None and inset <= point.x <= width - inset and inset <= point.y <= height - inset:
            column = min(1, max(0, math.floor(point.x / width * 2)))
            row = min(1, max(0, math.floor(point.y / height * 2)))
            cells.setdefault(row * 2 + column, []).append(truck_id)
    return {cell: sorted(ids) for cell, ids in sorted(cells.items())}


def assert_conservation(frame, name):
    actual = [truck_id for label in frame['labels'] for truck_id in label['ids']]
    expected_cells = projected_grid()
    expected = sorted(truck_id for ids in expected_cells.values() for truck_id in ids)
    assert len(actual) == len(set(actual)), ('Truck is counted in multiple active labels', actual)
    assert sorted(actual) == expected, dict(expected=expected, actual=sorted(actual))
    assert len(frame['labels']) == widget.get_visible_label_count()
    aggregate = frame['aggregate_expected']
    if aggregate:
        assert len(frame['labels']) == len(expected_cells) <= 4, (
            'Every occupied screen cell must have exactly one label', expected_cells, frame['labels'])
    else:
        assert len(frame['labels']) == len(expected), (
            'Near view must show one individual label for every visible truck', expected, frame['labels'])
    truck_cells = {truck_id: cell for cell, ids in expected_cells.items() for truck_id in ids}
    actual_cells = {}
    width, height = viewport_size()
    for label in frame['labels']:
        x, y = label['position']
        w, h = label['size']
        assert x >= -.5 and y >= -.5 and x + w <= width + .5 and y + h <= height + .5, label
        if not aggregate:
            assert len(label['ids']) == 1, ('Near view unexpectedly aggregated trucks', label)
            continue
        member_cells = {truck_cells[truck_id] for truck_id in label['ids']}
        assert len(member_cells) == 1, ('A label combined trucks across screen cells', label, member_cells)
        cell = next(iter(member_cells))
        assert cell not in actual_cells, ('An occupied cell has multiple labels', cell, label)
        actual_cells[cell] = sorted(label['ids'])
        row, column = divmod(cell, 2)
        left, top = column * width / 2, row * height / 2
        right, bottom = (column + 1) * width / 2, (row + 1) * height / 2
        assert w <= width / 2 + .5 and h <= height / 2 + .5, (
            'Label is larger than its screen cell', cell, label, [width / 2, height / 2])
        assert (x >= left - .5 and y >= top - .5
                and x + w <= right + .5 and y + h <= bottom + .5), (
            'Settled label extends outside its member cell', cell, label,
            [left, top, right, bottom])
    if aggregate:
        assert actual_cells == expected_cells, dict(expected=expected_cells, actual=actual_cells)
    record(name, projected_count=len(expected), label_count=len(frame['labels']),
           viewport=list(pc.get_viewport_size()), viewport_scale=float(unreal.WidgetLayoutLibrary.get_viewport_scale(world)),
           aggregate_expected=aggregate, actual_arm_length=frame['actual_arm_length'],
           cluster_threshold=frame['cluster_threshold'],
           grid_partition=expected_cells, cluster_sizes=[len(label['ids']) for label in frame['labels']])


def capture(name, frame):
    if name in captured_states:
        return
    # FScreenshotRequest owns one slot; wait for the previous real capture.
    if pending_captures:
        return
    path = ROOT / ('Saved/GHS_TruckHUD_Cluster_' + name + '_' + SUFFIX + '.png')
    pending_captures.append(dict(name=name, path=path, requested_at=time.time(),
                                 requested_monotonic=time.monotonic(), frame=frame))
    captured_states.add(name)
    unreal.SystemLibrary.execute_console_command(
        world, 'Shot showui filename="' + path.as_posix() + '" -nosuffix', pc)


def collect_capture():
    if not pending_captures:
        return
    pending = pending_captures[0]
    path = pending['path']
    assert time.monotonic() - pending['requested_monotonic'] < 30, ('Screenshot timeout', str(path))
    if not path.is_file() or path.stat().st_mtime < pending['requested_at'] or path.stat().st_size < 10000:
        return
    with path.open('rb') as stream:
        header = stream.read(24)
    assert header[:8] == b'\x89PNG\r\n\x1a\n', str(path)
    resolution = list(struct.unpack('>II', header[16:24]))
    result['captures'].append(dict(state=pending['name'], path=str(path),
                                   resolution=resolution, bytes=path.stat().st_size,
                                   request_frame=pending['frame']))
    pending_captures.pop(0)


def sample_transition(prefix, frame, field, opening):
    progress = frame[field]
    if opening:
        bucket = 'Early' if progress < .25 else 'Mid' if progress < .9 else 'End'
    else:
        bucket = 'Early' if progress > .75 else 'Mid' if progress > .1 else 'End'
    capture(prefix + bucket, frame)


def assert_transition(field, opening, name):
    values = [frame[field] for frame in stage_frames]
    assert any(.001 < value < .999 for value in values), (
        'No actual intermediate animation frame observed', field, values)
    pairs = list(zip(values, values[1:]))
    assert all(b >= a - .002 if opening else b <= a + .002 for a, b in pairs), values
    assert values[-1] >= .999 if opening else values[-1] <= .001, values
    record(name, samples=len(values), progress=values)


def assert_motion(name):
    # Instant camera placement removes camera interpolation as the explanation
    # for multiple subsequent box positions; fractional alpha also proves paint animation.
    fractional = [frame for frame in stage_frames
                  if any(.001 < label['opacity'] < .999 for label in frame['labels'])]
    positions = {}
    for frame in stage_frames:
        for label in frame['labels']:
            positions.setdefault(label['key'], set()).add(tuple(round(v, 2) for v in label['position']))
    moving = {key: len(values) for key, values in positions.items() if len(values) >= 3}
    assert fractional or moving, ('No label fade or continuous position change observed', name)
    record(name, sampled_frames=len(stage_frames), fractional_opacity_frames=len(fractional),
           moving_labels=moving)


def click_group(frame):
    global group, members
    groups = [label for label in frame['labels'] if len(label['ids']) > 1]
    assert groups, 'Wide real-camera view did not aggregate trucks within a screen cell'
    group = max(groups, key=lambda label: len(label['ids']))
    x, y = group['position']
    w, h = group['size']
    assert widget.handle_pointer_click(unreal.Vector2D(x + w / 2, y + h / 2))
    assert str(widget.get_selected_truck_id()) == '', 'Opening a group arbitrarily selected a truck'
    members = [str(value) for value in widget.get_expanded_cluster_members()]
    assert set(members) == set(group['ids']), (members, group)
    record('click_group_opens_its_members_without_selecting_first', members=members)


def check_list_bounds(frame):
    width, height = viewport_size()
    x, y = frame['list_position']
    w, h = frame['list_size']
    assert w > 0 and h > 0 and x >= -.5 and y >= -.5
    assert x + w <= width + .5 and y + h <= height + .5, frame


def click_list_control(frame, control):
    x, y = frame['list_position']
    w, h = frame['list_size']
    scale = w / 260.0
    if control == 'close':
        point = unreal.Vector2D(x + 245 * scale, y + 17 * scale)
    else:
        point = unreal.Vector2D(x + (238 if control == 'next' else 196) * scale,
                                y + h - 14 * scale)
    assert widget.handle_pointer_click(point), (control, xy(point))


def choose_nonfirst_member(frame):
    global selected_id
    selected_id = members[5] if len(members) > 5 else members[1]
    if len(members) > 5:
        click_list_control(frame, 'next')
        assert widget.get_member_row_position(members[0]).x < 0, 'Previous page row remained clickable'
        assert widget.get_member_row_position(selected_id).x >= 0, 'Next button did not expose page two'
        click_list_control(frame, 'previous')
        assert widget.get_member_row_position(members[0]).x >= 0, 'Previous button did not restore page one'
        assert widget.get_member_row_position(selected_id).x < 0, 'Page two remained exposed after previous'
        click_list_control(frame, 'next')
        assert widget.get_member_row_position(selected_id).x >= 0
        record('click_next_and_previous_buttons_pages_visible_members', target=selected_id)
    else:
        record('cluster_has_single_page', count=len(members))


def click_singleton(frame):
    labels = [label for label in frame['labels'] if selected_id in label['ids']]
    assert len(labels) == 1 and labels[0]['ids'] == [selected_id], labels
    x, y = labels[0]['position']
    w, h = labels[0]['size']
    # Click the drawn plus/minus toggle, using current rendered label bounds.
    scale = h / 34.0
    point = unreal.Vector2D(x + w - 13 * scale, y + h / 2)
    assert widget.handle_pointer_click(point), (selected_id, xy(point))


def open_visible_singleton(frame):
    global selected_id, singleton_zoom_attempts
    singles = [label for label in frame['labels'] if len(label['ids']) == 1]
    if not singles:
        # A near view must already use individual labels. If its camera fixture
        # has no visible truck, move closer until an actual label can be clicked.
        zooms = (1400.0, 1000.0, 800.0)
        assert singleton_zoom_attempts < len(zooms), (
            'No actual singleton available after closer camera views', frame['labels'])
        pawn.set_desired_zoom(zooms[singleton_zoom_attempts], True)
        singleton_zoom_attempts += 1
        advance('singleton_settle')
        return
    target = next((label for label in singles if selected_id in label['ids']), singles[0])
    selected_id = target['ids'][0]
    assert frame['selected'] == '' and frame['detail_progress'] <= .001
    click_singleton(frame)
    assert str(widget.get_selected_truck_id()) == selected_id
    record('click_actual_singleton_opens_its_detail', truck_id=selected_id,
           viewport=list(pc.get_viewport_size()), position=target['position'], size=target['size'])
    advance('singleton_partial_open')


def assert_unchanged_progress(before):
    after = float(widget.get_editor_property('detail_transition_progress'))
    assert abs(after - before) < .0001, ('Toggle snapped animation progress', before, after)


def restore_camera_tick():
    global saved_actor_tick_enabled
    if pawn is not None and saved_actor_tick_enabled is not None:
        pawn.set_actor_tick_enabled(saved_actor_tick_enabled)
        saved_actor_tick_enabled = None


def finish(error=None):
    try:
        restore_camera_tick()
    except Exception:
        error = (error or '') + '\nCamera tick restoration failed:\n' + traceback.format_exc()
    result.update(success=error is None, status='failed' if error else 'success',
                  elapsed_seconds=round(time.monotonic() - STARTED, 3))
    if error:
        result.update(error=error, failed_stage=stage)
    write_report()
    if handle is not None:
        unreal.unregister_slate_post_tick_callback(handle)
    if error:
        unreal.log_error('TRUCK_HUD_CLUSTER_FAILED ' + error)
    else:
        unreal.log('TRUCK_HUD_CLUSTER_SUCCESS ' + str(REPORT))
    if world and pc:
        unreal.SystemLibrary.quit_game(world, pc, unreal.QuitPreference.QUIT, False)
    else:
        unreal.SystemLibrary.execute_console_command(None, 'quit')


def tick(delta_seconds):
    global stationary_keys, jitter_index, resize_before_partition
    global threshold_camera_state, saved_actor_tick_enabled
    try:
        now = time.monotonic()
        assert now - STARTED < 240, 'Cluster validation timed out'
        assert now - stage_started < 40, ('Stage did not converge', stage)
        collect_capture()
        if stage == 'discover':
            if discover():
                advance('wide_settle')
            return
        frame = read_frame(delta_seconds)
        if stage == 'wide_settle':
            if not settled(frame):
                return
            assert_conservation(frame, 'wide_clusters_conserve_all_current_projected_trucks')
            assert any(len(label['ids']) > 5 for label in frame['labels']), (
                'Wide view must exercise a group larger than one page', frame['labels'])
            stationary_keys = tuple(label['key'] for label in frame['labels'])
            capture('Wide', frame)
            advance('stationary')
        elif stage == 'stationary':
            assert tuple(label['key'] for label in frame['labels']) == stationary_keys
            if len(stage_frames) >= 24:
                record('stationary_view_keeps_cluster_keys_stable', frames=len(stage_frames),
                       keys=list(stationary_keys))
                advance('jitter')
        elif stage == 'jitter':
            # Alternate every rendered frame, so brief boundary crossings cannot
            # satisfy the per-truck 200 ms dwell even at a slow rendering rate.
            assert tuple(label['key'] for label in frame['labels']) == stationary_keys, (
                'Small real camera jitter churned cluster membership', frame['labels'])
            direction = 1 if jitter_index % 2 == 0 else -1
            pawn.set_desired_rotation(unreal.Rotator(pitch=-60.0, yaw=-135.0 + .03 * direction, roll=0), True)
            pawn.set_desired_zoom(wide_zoom * (1 + .0005 * direction), True)
            jitter_index += 1
            if jitter_index >= 32:
                record('real_orbit_and_zoom_jitter_do_not_churn_group_keys', perturbations=jitter_index)
                set_wide_camera()
                advance('before_list')
        elif stage == 'before_list':
            if settled(frame) and not pending_captures:
                click_group(frame)
                advance('list_open')
        elif stage == 'list_open':
            assert frame['selected'] == '', 'Group opening selected its first member'
            sample_transition('ListOpen', frame, 'list_progress', True)
            if (frame['list_progress'] >= .999 and frame['list_visible']
                    and 'ListOpenEnd' in captured_states):
                assert_transition('list_progress', True, 'member_list_opens_over_multiple_frames')
                check_list_bounds(frame)
                advance('before_list_close_button')
        elif stage == 'before_list_close_button':
            if pending_captures:
                return
            click_list_control(frame, 'close')
            assert not widget.get_expanded_cluster_members(), 'List close button kept the group expanded'
            assert str(widget.get_selected_truck_id()) == ''
            advance('list_close_button')
        elif stage == 'list_close_button':
            if frame['list_progress'] == 0.0 and not frame['list_visible']:
                assert_transition('list_progress', False, 'click_list_close_button_animates_to_closed')
                assert not frame['list_visible'] and not widget.get_expanded_cluster_members()
                click_group(frame)
                advance('list_reopen')
        elif stage == 'list_reopen':
            if frame['list_progress'] >= .999:
                assert frame['list_visible'] and frame['selected'] == ''
                choose_nonfirst_member(frame)
                advance('member_page')
        elif stage == 'member_page':
            if pending_captures:
                return
            capture('MemberPage', frame)
            advance('select_member')
        elif stage == 'select_member':
            if pending_captures:
                return
            position = widget.get_member_row_position(selected_id)
            assert position.x >= 0 and position.y >= 0, selected_id
            assert selected_id != members[0]
            # Row position is the actual visible, animated hit-test geometry.
            assert widget.handle_pointer_click(unreal.Vector2D(position.x + 12, position.y + 12))
            assert str(widget.get_selected_truck_id()) == selected_id
            record('click_nonfirst_visible_member_selects_exact_truck', truck_id=selected_id)
            advance('detail_open')
        elif stage == 'detail_open':
            assert frame['selected'] == selected_id
            sample_transition('DetailOpen', frame, 'detail_progress', True)
            if (frame['detail_progress'] >= .999 and frame['list_progress'] == 0.0
                    and not frame['list_visible']
                    and 'DetailOpenEnd' in captured_states):
                assert_transition('detail_progress', True, 'member_detail_opens_over_multiple_frames')
                assert_transition('list_progress', False, 'member_selection_closes_list_over_multiple_frames')
                assert frame['detail_visible'] and not frame['list_visible']
                capture('SelectedMember', frame)
                advance('before_threshold_individual')
        elif stage == 'before_threshold_individual':
            if pending_captures:
                return
            threshold_camera_state = camera_state()
            assert frame['actual_arm_length'] >= DEFAULT_CLUSTER_THRESHOLD
            # Hold the real camera still and move only the editable Pawn threshold.
            # This also catches a HUD that hard-codes 10000 instead of reading it.
            pawn.set_editor_property('hud_cluster_min_arm_length', frame['actual_arm_length'] + 1.0)
            advance('threshold_individual')
        elif stage == 'threshold_individual':
            assert_threshold_preserves_selected_detail(frame)
            assert frame['actual_arm_length'] < frame['cluster_threshold']
            if any(.01 < label['opacity'] < .99 for label in frame['labels']):
                capture('ThresholdIndividualMid', frame)
            if not settled(frame) or pending_captures:
                return
            assert_conservation(frame, 'actual_arm_below_runtime_threshold_shows_every_individual_truck')
            assert len(frame['labels']) > 4, 'Fixture must exercise more than four independent labels'
            assert_motion('threshold_change_splits_labels_with_animation_and_preserves_detail')
            capture('ThresholdIndividualEnd', frame)
            advance('before_threshold_equal')
        elif stage == 'before_threshold_equal':
            assert_threshold_preserves_selected_detail(frame)
            if pending_captures:
                return
            pawn.set_editor_property('hud_cluster_min_arm_length', frame['actual_arm_length'])
            advance('threshold_equal')
        elif stage == 'threshold_equal':
            assert_threshold_preserves_selected_detail(frame)
            assert frame['actual_arm_length'] == frame['cluster_threshold'], (
                'The inclusive boundary fixture is not exactly equal', frame['actual_arm_length'],
                frame['cluster_threshold'])
            if any(.01 < label['opacity'] < .99 for label in frame['labels']):
                capture('ThresholdEqualMid', frame)
            if not settled(frame) or pending_captures:
                return
            assert_conservation(frame, 'actual_arm_equal_to_runtime_threshold_aggregates_quadrants')
            assert_motion('threshold_change_merges_labels_with_animation_and_preserves_detail')
            capture('ThresholdEqualEnd', frame)
            pawn.set_editor_property('hud_cluster_min_arm_length', DEFAULT_CLUSTER_THRESHOLD)
            advance('before_detail_close')
        elif stage == 'before_detail_close':
            if pending_captures:
                return
            x, y = frame['detail_position']
            w, h = frame['detail_size']
            assert widget.handle_pointer_click(unreal.Vector2D(x + w * 304 / 320, y + h * 18 / 184))
            assert str(widget.get_selected_truck_id()) == ''
            advance('detail_close')
        elif stage == 'detail_close':
            sample_transition('DetailClose', frame, 'detail_progress', False)
            if (frame['detail_progress'] == 0.0 and not frame['detail_visible']
                    and 'DetailCloseEnd' in captured_states):
                assert_transition('detail_progress', False, 'detail_closes_over_multiple_frames')
                assert not frame['detail_visible']
                advance('before_split')
        elif stage == 'before_split':
            if pending_captures:
                return
            origin, extent = trucks[selected_id].get_actor_bounds(False)
            pawn.set_desired_location(unreal.Vector(origin.x, origin.y, 0), True)
            pawn.set_desired_rotation(unreal.Rotator(pitch=-42, yaw=-135, roll=0), True)
            # Hold only the Pawn tick for one frame while the HUD keeps ticking.
            # DesiredZoom changes, but the current physical arm remains distant.
            saved_actor_tick_enabled = pawn.is_actor_tick_enabled()
            pawn.set_actor_tick_enabled(False)
            pawn.set_desired_zoom(2400.0, False)
            advance('actual_arm_pending_zoom')
        elif stage == 'actual_arm_pending_zoom':
            assert frame['desired_zoom'] < frame['cluster_threshold'] < frame['actual_arm_length'], (
                'Lag fixture must put current and desired arm lengths on opposite sides', frame)
            assert len(frame['labels']) <= 4 and any(len(label['ids']) > 1 for label in frame['labels']), (
                'HUD followed DesiredZoom before the actual spring arm crossed the threshold', frame)
            record('aggregation_uses_actual_spring_arm_instead_of_pending_desired_zoom',
                   actual_arm_length=frame['actual_arm_length'], desired_zoom=frame['desired_zoom'],
                   threshold=frame['cluster_threshold'], label_count=len(frame['labels']))
            restore_camera_tick()
            pawn.set_desired_zoom(2400.0, True)
            advance('split')
        elif stage == 'split':
            if len(stage_frames) <= 3:
                capture('SplitEarly', frame)
            elif any(.01 < label['opacity'] < .99 for label in frame['labels']):
                capture('SplitMid', frame)
            if not settled(frame) or pending_captures:
                return
            assert_conservation(frame, 'near_split_conserves_current_projected_trucks')
            assert frame['actual_arm_length'] < DEFAULT_CLUSTER_THRESHOLD
            assert all(len(label['ids']) == 1 for label in frame['labels'])
            selected_labels = [label for label in frame['labels'] if selected_id in label['ids']]
            assert len(selected_labels) == 1, selected_labels
            assert len(selected_labels[0]['ids']) < len(group['ids']), (selected_labels, group)
            assert_motion('zoom_in_splits_group_with_animated_label_geometry')
            capture('SplitEnd', frame)
            advance('before_singleton_toggle')
        elif stage == 'before_singleton_toggle':
            if pending_captures:
                return
            open_visible_singleton(frame)
        elif stage == 'singleton_settle':
            if not settled(frame):
                return
            assert_conservation(frame, 'closer_view_preserves_exact_grid_partition_' + str(singleton_zoom_attempts))
            open_visible_singleton(frame)
        elif stage == 'singleton_partial_open':
            progress = frame['detail_progress']
            assert frame['selected'] == selected_id
            assert progress < .999, 'No partial opening frame was available for reversal'
            if progress >= .25:
                toggle_progress['close_from'] = progress
                click_singleton(frame)
                assert str(widget.get_selected_truck_id()) == '', (
                    'Clicking the selected singleton minus label must clear selection', selected_id)
                assert_unchanged_progress(progress)
                record('click_selected_singleton_during_opening_clears_selection', progress=progress)
                advance('singleton_partial_close')
        elif stage == 'singleton_partial_close':
            progress = frame['detail_progress']
            assert frame['selected'] == ''
            values = [toggle_progress['close_from']] + [value['detail_progress'] for value in stage_frames]
            assert all(b <= a + .002 for a, b in zip(values, values[1:])), values
            assert progress > .001, 'Closing reached zero before a partial reversal frame could be checked'
            if progress < toggle_progress['close_from'] - .0001:
                toggle_progress['reopen_from'] = progress
                click_singleton(frame)
                assert str(widget.get_selected_truck_id()) == selected_id
                assert_unchanged_progress(progress)
                record('click_singleton_during_closing_reverses_without_snap', progress=values)
                advance('singleton_reopen')
        elif stage == 'singleton_reopen':
            assert frame['selected'] == selected_id
            values = [toggle_progress['reopen_from']] + [value['detail_progress'] for value in stage_frames]
            assert all(b >= a - .002 for a, b in zip(values, values[1:])), values
            if frame['detail_progress'] >= .999:
                assert frame['detail_visible']
                record('singleton_reversal_grows_continuously_to_fully_open', progress=values)
                click_singleton(frame)
                assert str(widget.get_selected_truck_id()) == ''
                assert_unchanged_progress(frame['detail_progress'])
                advance('singleton_final_close')
        elif stage == 'singleton_final_close':
            assert frame['selected'] == ''
            if frame['detail_progress'] == 0.0 and not frame['detail_visible']:
                assert_transition('detail_progress', False, 'singleton_minus_click_closes_continuously_to_zero')
                assert not frame['detail_visible']
                advance('before_merge')
        elif stage == 'before_merge':
            if pending_captures:
                return
            set_wide_camera()
            advance('merge')
        elif stage == 'merge':
            if len(stage_frames) <= 3:
                capture('MergeEarly', frame)
            elif any(.01 < label['opacity'] < .99 for label in frame['labels']):
                capture('MergeMid', frame)
            if not settled(frame) or pending_captures:
                return
            assert_conservation(frame, 'zoom_out_merged_groups_conserve_projected_trucks')
            assert any(len(label['ids']) > 5 for label in frame['labels'])
            assert_motion('zoom_out_merges_trucks_with_animated_label_geometry')
            capture('MergeEnd', frame)
            advance('before_resize' if SUFFIX == 'Full' else 'finish_captures')
        elif stage == 'before_resize':
            if pending_captures:
                return
            resize_before_partition = projected_grid()
            unreal.SystemLibrary.execute_console_command(
                world, 'r.SetRes ' + str(RESIZED_VIEWPORT[0]) + 'x' + str(RESIZED_VIEWPORT[1]) + 'w', pc)
            advance('resize_wait')
        elif stage == 'resize_wait':
            if tuple(pc.get_viewport_size()) != RESIZED_VIEWPORT:
                assert now - stage_started < 15, (
                    'Live viewport did not accept the resize command', list(pc.get_viewport_size()), RESIZED_VIEWPORT)
                return
            record('same_game_viewport_resizes_without_restarting', before=list(EXPECTED_VIEWPORT),
                   after=list(pc.get_viewport_size()))
            advance('resize_settle')
        elif stage == 'resize_settle':
            if not settled(frame) or pending_captures:
                return
            assert_conservation(frame, 'live_resize_repartitions_using_new_normalized_screen_cells')
            assert projected_grid() != resize_before_partition, (
                'Resize fixture did not exercise any membership change', resize_before_partition)
            capture('Resized', frame)
            advance('finish_captures')
        elif stage == 'finish_captures' and not pending_captures:
            finish()
    except Exception:
        finish(traceback.format_exc())


write_report()
handle = unreal.register_slate_post_tick_callback(tick)
unreal.log('TRUCK_HUD_CLUSTER_VERIFIER_READY ' + SUFFIX)
