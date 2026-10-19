"""Verify stacker/truck HUDs in an owned offscreen game; never save assets.

Run -game -RenderOffscreen -ResX=1920 -ResY=1080 -ForceRes -windowed
-ExecCmds="py <this script>". Add -StackerHUDNarrow with ResX=360 ResY=800.
Use -StackerHUDLowAngle at 1920x1080 for the near-horizontal warehouse view.
Uses actual tagged map actors, actor-bound projections, hit testing, per-frame
animation geometry, and screenshots. Aggregation is by (equipment type, screen
quadrant), at most four truck and four stacker labels, with no mixed groups.
Demo telemetry is explicitly identified.
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
    return bool(re.search(r'(?:^|\s)-' + re.escape(name) + r'(?=\s|$)', COMMAND_LINE, re.I))


assert flag('game') and flag('RenderOffscreen'), 'An owned offscreen game is required.'
assert not (flag('StackerHUDNarrow') and flag('StackerHUDLowAngle')), 'Choose only one viewport fixture.'
SUFFIX, EXPECTED_VIEWPORT = ('Narrow', (360, 800)) if flag('StackerHUDNarrow') else (
    ('LowAngle', (1920, 1080)) if flag('StackerHUDLowAngle') else ('Full', (1920, 1080)))
ANCHOR_BASELINE = flag('StackerHUDAnchorBaseline')
REPORT = ROOT / ('Saved/GHS_StackerHUD_' + ('AnchorBaseline_' if ANCHOR_BASELINE else 'Runtime_') + SUFFIX + '.json')
STARTED = time.monotonic()
result = dict(success=False, status='running', variant=SUFFIX, tests=[], samples=[],
              captures=[], assets_saved=False, visual_review_required=True,
              capture_method='Shot showui; real measured frame geometry',
              scene_actor_transform_changes=False)
world = pc = pawn = widget = spring_arm = None
actors = {}
stackers = {}
initial_data = {}
status_examples = []
status_index = 0
stage = 'discover'
stage_started = STARTED
stage_game_started = 0
stage_frames = []
pending_capture = None
captured_states = set()
selected_id = None
group_members = []
wide_center = None
wide_zoom = 0
fixed_camera_state = None
live_snapshot = None
hidden_equipment_ids = set()
reference_truck_labels = None
handle = None


def xy(value):
    return [float(value.x), float(value.y)]


def equipment_type(identifier):
    return 'stacker' if identifier in stackers else 'truck'


def save():
    REPORT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf8')


def record(name, **details):
    result['tests'].append(dict(name=name, passed=True, **details))
    save()
    unreal.log('STACKER_HUD_PASS ' + name)


def advance(name):
    global stage, stage_started, stage_frames, stage_game_started
    stage, stage_started, stage_frames = name, time.monotonic(), []
    stage_game_started = float(unreal.GameplayStatics.get_time_seconds(world))


def snapshot(data):
    return dict(id=str(data.get_editor_property('stacker_id')),
                battery=float(data.get_editor_property('battery_percent')),
                fork_height_cm=float(data.get_editor_property('fork_height_cm')),
                task=str(data.get_editor_property('task_id')),
                status=str(data.get_editor_property('status')),
                demo=bool(data.get_editor_property('is_demo_data')),
                updated=float(data.get_editor_property('last_update_seconds')),
                has_telemetry=bool(data.has_telemetry()))


def discover():
    global world, pc, pawn, widget, spring_arm, wide_center, wide_zoom, status_examples
    for candidate in unreal.ObjectIterator(unreal.World):
        controller = unreal.GameplayStatics.get_player_controller(candidate, 0)
        if controller:
            world, pc = candidate, controller
            break
    if not pc:
        return False
    widget = pc.get_editor_property('truck_hud_widget')
    pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
    if not widget or not pawn:
        return False
    assert world.get_path_name().split('.')[0] == '/Game/Maps/GHS_CAD_NormalWarehouse'
    assert tuple(pc.get_viewport_size()) == EXPECTED_VIEWPORT
    required = ('get_registered_stacker_count', 'get_stacker_data', 'select_equipment_by_id',
                'get_selected_equipment_id', 'get_registered_equipment_count')
    missing = [name for name in required if not callable(getattr(widget, name, None))]
    assert not missing, 'Missing stacker HUD API: ' + ', '.join(missing)
    assert widget.is_in_viewport()
    spring_arm = pawn.get_component_by_class(unreal.SpringArmComponent)
    assert spring_arm and float(pawn.get_editor_property('hud_cluster_min_arm_length')) == 10000.0
    for actor in unreal.GameplayStatics.get_all_actors_with_tag(world, 'IndependentDockTruck'):
        matches = [re.fullmatch(r'TwinId=GHS_DockTruck_([0-9]+)', str(tag)) for tag in actor.tags]
        ids = ['TRUCK-' + format(int(match.group(1)), '03d') for match in matches if match]
        assert len(ids) == 1 and ids[0] not in actors
        assert widget.get_truck_data(ids[0]).get_owner() == actor
        actors[ids[0]] = actor
    assert len(actors) == 52 and widget.get_registered_truck_count() == 52
    for actor in unreal.GameplayStatics.get_all_actors_with_tag(world, 'NormalWarehouseFloorStacker'):
        matches = [re.fullmatch(r'TwinId=GHN_FloorStacker_([0-9]+)', str(tag)) for tag in actor.tags]
        ids = ['STACKER-' + format(int(match.group(1)), '02d') for match in matches if match]
        assert len(ids) == 1 and ids[0] not in actors, (actor.get_name(), [str(t) for t in actor.tags])
        data = widget.get_stacker_data(ids[0])
        assert data and data.get_owner() == actor
        actors[ids[0]], stackers[ids[0]], initial_data[ids[0]] = actor, data, snapshot(data)
    assert sorted(stackers) == ['STACKER-' + format(i, '02d') for i in range(1, 13)]
    assert widget.get_registered_stacker_count() == 12
    assert widget.get_registered_equipment_count() == 64
    record('12_actual_stackers_and_52_trucks_registered_with_distinct_identity', count=len(actors))
    first_truck = next(identifier for identifier in sorted(actors) if identifier.startswith('TRUCK-'))
    assert widget.select_truck_by_id(first_truck)
    assert str(widget.get_selected_truck_id()) == first_truck
    assert str(widget.get_selected_equipment_id()) == first_truck
    assert not widget.select_equipment_by_id('STACKER-NOT-REAL')
    assert str(widget.get_selected_equipment_id()) == first_truck
    assert widget.get_stacker_data(first_truck) is None
    assert widget.get_truck_data('STACKER-01') is None
    record('legacy_truck_selection_and_new_identity_validation_remain_compatible')
    states = ('RUNNING', 'IDLE', 'WARNING', 'FAULT', 'OFFLINE')
    for name in states:
        expected = getattr(unreal.GHSStackerStatus, name)
        found = [identifier for identifier, data in stackers.items() if data.get_editor_property('status') == expected]
        assert found, ('Missing demo status', name, initial_data)
        status_examples.append((name, sorted(found)[0]))
    assert all(data['demo'] for data in initial_data.values()), initial_data
    for data in stackers.values():
        if data.get_editor_property('status') == unreal.GHSStackerStatus.OFFLINE:
            state = snapshot(data)
            assert state['battery'] == state['fork_height_cm'] == -1 and state['task'] == ''
            assert not state['has_telemetry']
    record('five_explicit_demo_statuses_and_unknown_offline_metrics', data=initial_data)
    for identifier, data in stackers.items():
        data.apply_demo_state(4)
        assert snapshot(data) == initial_data[identifier], 'A repeated demo seed overwrote data'
    record('demo_seed_is_idempotent_for_every_stacker')
    bounds = [actor.get_actor_bounds(False) for actor in actors.values()]
    left = min(o.x-e.x for o, e in bounds)
    right = max(o.x+e.x for o, e in bounds)
    top = min(o.y-e.y for o, e in bounds)
    bottom = max(o.y+e.y for o, e in bounds)
    wide_center = unreal.Vector((left+right)/2, (top+bottom)/2, 0)
    wide_zoom = max(18000, math.hypot(right-left, bottom-top)*1.35)
    result.update(viewport=list(pc.get_viewport_size()), map=world.get_path_name(),
                  stacker_ids=sorted(stackers), initial_data=initial_data)
    widget.clear_selection()
    unreal.SystemLibrary.execute_console_command(world, 'DisableAllScreenMessages', pc)
    set_wide_camera()
    return True


def set_wide_camera():
    pawn.set_desired_location(wide_center, True)
    pitch, yaw = (-18, -90) if SUFFIX == 'LowAngle' else (-60, -135)
    pawn.set_desired_rotation(unreal.Rotator(pitch=pitch, yaw=yaw, roll=0), True)
    pawn.set_desired_zoom(wide_zoom, True)


def logical_viewport():
    dpi = float(unreal.WidgetLayoutLibrary.get_viewport_scale(world))
    width, height = pc.get_viewport_size()
    f32 = lambda value: struct.unpack('f', struct.pack('f', value))[0]
    return f32(width/dpi), f32(height/dpi)


def draw_scale():
    dpi = float(unreal.WidgetLayoutLibrary.get_viewport_scale(world))
    width, height = pc.get_viewport_size()
    return min(max(dpi, .75), min(width/640, height/540))/dpi


def camera_state():
    position, rotation = pawn.get_actor_location(), pawn.get_actor_rotation()
    return [position.x, position.y, position.z, rotation.pitch, rotation.yaw, rotation.roll,
            float(spring_arm.get_editor_property('target_arm_length'))]


def frame(delta):
    labels = []
    for item in widget.get_visible_labels():
        ids = [str(value) for value in item.get_editor_property('equipment_ids')]
        assert ids == [str(value) for value in item.get_editor_property('truck_ids')]
        labels.append(dict(key=str(item.get_editor_property('key')), ids=ids,
                           position=xy(item.get_editor_property('position')),
                           size=xy(item.get_editor_property('size')),
                           opacity=float(item.get_editor_property('opacity'))))
    value = dict(stage=stage, elapsed=round(time.monotonic()-stage_started, 6),
                 game_elapsed=float(unreal.GameplayStatics.get_time_seconds(world))-stage_game_started,
                 delta=float(delta), labels=labels,
                 selected=str(widget.get_selected_equipment_id()),
                 detail=bool(widget.get_editor_property('detail_visible')),
                 detail_progress=float(widget.get_editor_property('detail_transition_progress')),
                 list_progress=float(widget.get_editor_property('cluster_transition_progress')))
    assert abs(pawn.get_actor_location().z) < .01
    for label in labels:
        assert label['ids'] and set(label['ids']) <= actors.keys()
        assert len({equipment_type(identifier) for identifier in label['ids']}) == 1, (
            'Different equipment types must never aggregate into one label', label)
        assert all(math.isfinite(v) for v in label['position'] + label['size'])
        assert -.001 <= label['opacity'] <= 1.001
    stage_frames.append(value)
    result['samples'].append(value)
    return value


def settled(value):
    return (len(stage_frames) >= 10 and value['elapsed'] >= .6
            and all(label['opacity'] >= .999 for label in value['labels']))


def projected_cells():
    width, height = logical_viewport()
    inset = 8*draw_scale()
    cells = {}
    for identifier, actor in actors.items():
        if identifier in hidden_equipment_ids:
            continue
        origin, extent = actor.get_actor_bounds(False)
        point = unreal.WidgetLayoutLibrary.project_world_location_to_widget_position(
            pc, unreal.Vector(origin.x, origin.y, origin.z+extent.z+80), True)
        if point is not None and inset <= point.x <= width-inset and inset <= point.y <= height-inset:
            cell = min(1, max(0, math.floor(point.y/height*2)))*2 + min(1, max(0, math.floor(point.x/width*2)))
            cells.setdefault((equipment_type(identifier), cell), []).append(identifier)
    return {cell: sorted(ids) for cell, ids in cells.items()}


def anchor_geometry(value):
    """Independently measure label displacement from the real projected owners."""
    width, height = logical_viewport()
    scale = draw_scale()
    margin = 12*scale
    measured = []
    for label in value['labels']:
        projections = []
        for identifier in label['ids']:
            origin, extent = actors[identifier].get_actor_bounds(False)
            point = unreal.WidgetLayoutLibrary.project_world_location_to_widget_position(
                pc, unreal.Vector(origin.x, origin.y, origin.z+extent.z+80), True)
            assert point is not None
            projections.append(xy(point))
        anchor = [sum(point[axis] for point in projections)/len(projections) for axis in (0, 1)]
        w, h = label['size']
        natural = [min(max(anchor[0]-w/2, margin), max(margin, width-margin-w)),
                   min(max(anchor[1]-50*scale, margin), max(margin, height-margin-h))]
        measured.append(dict(key=label['key'], ids=label['ids'], anchor=anchor,
                             position=label['position'], natural_position=natural,
                             extra_displacement_logical=math.dist(label['position'], natural)/scale,
                             anchor_to_label_edge_logical=math.dist(
                                 anchor, [label['position'][0]+w/2, label['position'][1]+h])/scale))
    return measured


def conserve(value, aggregate, name):
    cells = projected_cells()
    expected = sorted(identifier for ids in cells.values() for identifier in ids)
    actual = [identifier for label in value['labels'] for identifier in label['ids']]
    assert len(actual) == len(set(actual)) and sorted(actual) == expected, (actual, expected)
    assert len(value['labels']) == (len(cells) if aggregate else len(expected))
    width, height = logical_viewport()
    reverse = {identifier: cell for cell, ids in cells.items() for identifier in ids}
    actual_cells = {}
    type_counts = {'truck': 0, 'stacker': 0}
    for label in value['labels']:
        x, y = label['position']
        w, h = label['size']
        assert x >= -.5 and y >= -.5 and x+w <= width+.5 and y+h <= height+.5, label
        if aggregate:
            partitions = {reverse[i] for i in label['ids']}
            assert len(partitions) == 1, label
            partition = next(iter(partitions))
            assert partition not in actual_cells, ('Duplicate type and quadrant group', partition)
            actual_cells[partition] = sorted(label['ids'])
            type_counts[partition[0]] += 1
        else:
            assert len(label['ids']) == 1, label
    if aggregate:
        assert actual_cells == cells, (actual_cells, cells)
        assert len(value['labels']) <= 8 and max(type_counts.values()) <= 4, type_counts
        expected_types = {kind for kind, cell in cells}
        assert {kind for kind, count in type_counts.items() if count} == expected_types
        for index, first in enumerate(value['labels']):
            first_partition = reverse[first['ids'][0]]
            for second in value['labels'][index+1:]:
                second_partition = reverse[second['ids'][0]]
                x, y = first['position']
                w, h = first['size']
                u, v = second['position']
                q, r = second['size']
                overlap_x, overlap_y = min(x+w, u+q)-max(x, u), min(y+h, v+r)-max(y, v)
                assert overlap_x <= .5 or overlap_y <= .5, (
                    'Aggregated equipment labels must remain readable and clickable across screen cells',
                    first_partition, second_partition, [overlap_x, overlap_y])
    assert widget.get_registered_equipment_count() == 64
    geometry = anchor_geometry(value)
    maximum_displacement = max((item['extra_displacement_logical'] for item in geometry), default=0)
    assert maximum_displacement <= (41 if aggregate else 1), (
        'Labels must remain beside their own projected equipment, with at most one local row offset',
        maximum_displacement, geometry)
    record(name, visible_count=len(actual), label_count=len(value['labels']), type_counts=type_counts,
           partition=[dict(equipment_type=kind, cell=cell, ids=ids) for (kind, cell), ids in sorted(cells.items())],
           maximum_anchor_relative_displacement=maximum_displacement, anchor_geometry=geometry)


def capture(name, value):
    global pending_capture
    if pending_capture or name in captured_states:
        return
    path = ROOT / ('Saved/GHS_StackerHUD_' + name + '_' + SUFFIX + '.png')
    pending_capture = dict(name=name, path=path, requested=time.time(), started=time.monotonic(), frame=value)
    captured_states.add(name)
    unreal.SystemLibrary.execute_console_command(world, 'Shot showui filename="' + path.as_posix() + '" -nosuffix', pc)


def collect_capture():
    global pending_capture
    if not pending_capture:
        return
    pending = pending_capture
    assert time.monotonic()-pending['started'] < 30, 'Screenshot timeout'
    path = pending['path']
    if not path.is_file() or path.stat().st_mtime < pending['requested'] or path.stat().st_size < 10000:
        return
    with path.open('rb') as stream:
        header = stream.read(24)
    assert header[:8] == b'\x89PNG\r\n\x1a\n'
    result['captures'].append(dict(state=pending['name'], path=str(path),
                                   resolution=list(struct.unpack('>II', header[16:24])),
                                   request_frame=pending['frame']))
    pending_capture = None


def check_popup_bounds(prefix):
    width, height = logical_viewport()
    x, y = xy(widget.get_editor_property(prefix+'_position'))
    w, h = xy(widget.get_editor_property(prefix+'_size'))
    assert w > 0 and h > 0 and x >= -.5 and y >= -.5 and x+w <= width+.5 and y+h <= height+.5


def check_transition(name):
    # The camera is unchanged: variation here is HUD animation, not projection.
    assert all(abs(a-b) < .001 for a, b in zip(camera_state(), fixed_camera_state))
    samples = {}
    first_complete = None
    simulated = 0.0
    max_delta = 0.0
    previous_game_elapsed = 0.0
    max_game_delta = 0.0
    for index, value in enumerate(stage_frames):
        delta = min(value['delta'], .1)
        simulated += delta
        max_delta = max(max_delta, delta)
        max_game_delta = max(max_game_delta, value['game_elapsed']-previous_game_elapsed)
        previous_game_elapsed = value['game_elapsed']
        for label in value['labels']:
            samples.setdefault(label['key'], []).append(label)
        if first_complete is None and all(label['opacity'] >= .999 for label in value['labels']):
            first_complete = dict(frame=index, elapsed=value['elapsed'], simulated=simulated,
                                  game_elapsed=value['game_elapsed'])
    assert first_complete is not None
    # A post-Slate callback can precede the first UMG tick; permit one frame.
    assert first_complete['simulated'] <= .12 + 2*max_delta + .004, first_complete
    assert first_complete['game_elapsed'] <= .12 + max_game_delta + .004, first_complete
    max_motion = 0.0
    for labels in samples.values():
        target = labels[-1]['position']
        max_motion = max(max_motion, max(math.dist(label['position'], target) for label in labels))
    assert max_motion <= 8*draw_scale()+.5, ('Aggregation moved labels across the screen', max_motion)
    fractional = sum(any(.001 < label['opacity'] < .999 for label in value['labels']) for value in stage_frames)
    assert fractional or max_delta >= .1, 'No intermediate fade frame observed'
    record(name, first_complete=first_complete, maximum_position_change=max_motion,
           draw_scale=draw_scale(), fractional_frames=fractional, target_duration_seconds=.12,
           maximum_game_frame_seconds=max_game_delta)


def click_label(label):
    x, y = label['position']
    w, h = label['size']
    assert widget.handle_pointer_click(unreal.Vector2D(x+w/2, y+h/2))


def set_stackers_hidden(hidden):
    for identifier in stackers:
        actors[identifier].set_actor_hidden_in_game(hidden)
    if hidden:
        hidden_equipment_ids.update(stackers)
    else:
        hidden_equipment_ids.difference_update(stackers)


def truck_label_geometry(value):
    return {label['key']: (label['position'], label['size']) for label in value['labels']
            if all(equipment_type(identifier) == 'truck' for identifier in label['ids'])}


def check_truck_slots_unchanged(value):
    current = truck_label_geometry(value)
    assert current.keys() == reference_truck_labels.keys(), (current, reference_truck_labels)
    for key, (position, size) in current.items():
        before_position, before_size = reference_truck_labels[key]
        assert math.dist(position, before_position) < .5 and math.dist(size, before_size) < .5, (
            'Another equipment type entering or leaving moved an unchanged label', key,
            before_position, position)


def begin_status():
    global selected_id
    widget.clear_selection()
    name, selected_id = status_examples[status_index]
    origin, extent = actors[selected_id].get_actor_bounds(False)
    pawn.set_desired_location(unreal.Vector(origin.x, origin.y, 0), True)
    pawn.set_desired_rotation(unreal.Rotator(pitch=-48, yaw=-135, roll=0), True)
    pawn.set_desired_zoom(1800, True)
    pawn.set_editor_property('hud_cluster_min_arm_length', 10000.0)
    advance('status_label')


def finish(error=None):
    for identifier in tuple(hidden_equipment_ids):
        actors[identifier].set_actor_hidden_in_game(False)
    hidden_equipment_ids.clear()
    result.update(success=error is None, status='failed' if error else 'success',
                  elapsed_seconds=round(time.monotonic()-STARTED, 3))
    if error:
        result.update(error=error, failed_stage=stage)
    save()
    if handle is not None:
        unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log_error if error else unreal.log)('STACKER_HUD_' + ('FAILED '+error if error else 'SUCCESS '+str(REPORT)))
    unreal.SystemLibrary.execute_console_command(world, 'quit', pc)


def tick(delta):
    global group_members, selected_id, fixed_camera_state, status_index, live_snapshot
    global reference_truck_labels
    try:
        assert time.monotonic()-STARTED < 180, 'Overall verification timed out'
        assert time.monotonic()-stage_started < 35, ('Stage timed out', stage)
        collect_capture()
        if stage == 'discover':
            if discover():
                advance('wide')
            return
        value = frame(delta)
        if stage == 'wide' and ANCHOR_BASELINE and settled(value) and not pending_capture:
            result['anchor_geometry'] = anchor_geometry(value)
            result['maximum_extra_displacement_logical'] = max(
                item['extra_displacement_logical'] for item in result['anchor_geometry'])
            capture('DistantAnchorBaseline', value)
            save()
            advance('anchor_baseline_capture')
        elif stage == 'anchor_baseline_capture' and not pending_capture:
            assert result['maximum_extra_displacement_logical'] <= 40.5, (
                'Label is detached from its real projected equipment group',
                result['maximum_extra_displacement_logical'], result['anchor_geometry'])
            finish()
        elif stage == 'wide' and settled(value) and not pending_capture:
            conserve(value, True, 'separate_equipment_types_preserve_four_quadrants_each')
            partitions = projected_cells()
            shared_cells = sorted({cell for kind, cell in partitions if ('truck', cell) in partitions and ('stacker', cell) in partitions})
            assert shared_cells, 'Fixture must show both equipment types in the same screen quadrant'
            result['same_quadrant_separate_type_examples'] = shared_cells
            capture('SeparateTypesWide', value)
            reference_truck_labels = truck_label_geometry(value)
            advance('before_hide_stackers')
        elif stage == 'before_hide_stackers' and not pending_capture:
            set_stackers_hidden(True)
            advance('stackers_hidden')
        elif stage == 'stackers_hidden' and settled(value):
            check_truck_slots_unchanged(value)
            conserve(value, True, 'removing_stacker_type_keeps_truck_groups_in_their_fixed_slots')
            set_stackers_hidden(False)
            advance('stackers_restored')
        elif stage == 'stackers_restored' and settled(value):
            check_truck_slots_unchanged(value)
            conserve(value, True, 'restoring_stacker_type_keeps_truck_groups_in_their_fixed_slots')
            advance('choose_stacker_group')
        elif stage == 'choose_stacker_group' and not pending_capture:
            groups = [label for label in value['labels']
                      if len(label['ids']) > 1 and all(equipment_type(i) == 'stacker' for i in label['ids'])]
            assert groups, 'Expected a stacker-only group with selectable members'
            target = max(groups, key=lambda label: len(label['ids']))
            click_label(target)
            group_members = [str(i) for i in widget.get_expanded_cluster_members()]
            assert set(group_members) == set(target['ids'])
            assert str(widget.get_selected_equipment_id()) == ''
            assert all(equipment_type(i) == 'stacker' for i in group_members)
            selected_id = group_members[1]
            record('click_stacker_only_group_lists_real_members_without_arbitrary_selection', members=group_members)
            advance('group_open')
        elif stage == 'group_open' and value['list_progress'] >= .999 and not pending_capture:
            assert any(.001 < v['list_progress'] < .999 for v in stage_frames)
            check_popup_bounds('cluster_list')
            assert widget.set_cluster_page(group_members.index(selected_id)//5)
            row = widget.get_member_row_position(selected_id)
            assert row.x >= 0
            assert widget.handle_pointer_click(unreal.Vector2D(row.x+12*draw_scale(), row.y+12*draw_scale()))
            assert str(widget.get_selected_equipment_id()) == selected_id
            record('click_stacker_member_in_its_type_group_selects_its_detail', selected=selected_id)
            advance('group_detail')
        elif stage == 'group_detail' and value['detail_progress'] >= .999 and not pending_capture:
            assert any(.001 < v['detail_progress'] < .999 for v in stage_frames)
            check_popup_bounds('detail')
            record('stacker_detail_expands_with_intermediate_animation_frames')
            fixed_camera_state = camera_state()
            pawn.set_editor_property('hud_cluster_min_arm_length', fixed_camera_state[-1]+1)
            advance('split')
        elif stage == 'split':
            # Screenshot GPU readback can stall a frame by >120ms. Measure the
            # complete fade first, then capture its end independently.
            if settled(value) and not pending_capture:
                conserve(value, False, 'current_arm_below_threshold_shows_every_equipment_individually')
                check_transition('split_is_local_and_completes_in_120ms_plus_render_frame')
                assert value['selected'] == selected_id and value['detail_progress'] >= .999
                capture('FastSplitEnd', value)
                advance('before_merge')
        elif stage == 'before_merge' and not pending_capture:
            pawn.set_editor_property('hud_cluster_min_arm_length', fixed_camera_state[-1])
            advance('merge')
        elif stage == 'merge':
            if settled(value) and not pending_capture:
                conserve(value, True, 'threshold_equality_restores_separate_type_quadrant_groups')
                check_transition('merge_is_local_and_completes_in_120ms_plus_render_frame')
                assert value['selected'] == selected_id and value['detail_progress'] >= .999
                record('mode_changes_preserve_selected_stacker_detail')
                capture('FastMergeEnd', value)
                advance('before_status')
        elif stage == 'before_status' and not pending_capture:
            begin_status()
        elif stage == 'status_label' and settled(value) and not pending_capture:
            assert value['detail_progress'] <= .001
            targets = [label for label in value['labels'] if label['ids'] == [selected_id]]
            assert len(targets) == 1, (selected_id, value)
            conserve(value, False, 'closeup_'+status_examples[status_index][0].lower()+'_individual_geometry')
            click_label(targets[0])
            assert str(widget.get_selected_equipment_id()) == selected_id
            advance('status_detail')
        elif stage == 'status_detail' and value['detail_progress'] >= .999 and not pending_capture:
            name, identifier = status_examples[status_index]
            assert value['selected'] == identifier and value['detail']
            assert stackers[identifier].get_editor_property('status') == getattr(unreal.GHSStackerStatus, name)
            check_popup_bounds('detail')
            capture(name.title(), value)
            record('actual_'+name.lower()+'_stacker_label_and_detail', equipment=identifier,
                   telemetry=snapshot(stackers[identifier]))
            advance('next_status')
        elif stage == 'next_status' and not pending_capture:
            status_index += 1
            if status_index < len(status_examples):
                begin_status()
            else:
                data = stackers[selected_id]
                assert data.set_telemetry(73.0, 125.0, unreal.GHSStackerStatus.RUNNING, 'LIVE-STACKER-VERIFY', False)
                live_snapshot = snapshot(data)
                assert not live_snapshot['demo'] and live_snapshot['has_telemetry']
                # UE 5.4's Python property bridge may treat NaN as identical to
                # zero and omit assignment (PyConversion.cpp inline-property
                # conversion/EmitPropertyChangeNotifications). Probe that path
                # independently instead of calling a native zero "invalid".
                nan_roundtrip = float(unreal.LinearColor(r=float('nan'), g=0, b=0, a=1).r)
                result['python_nan_roundtrip'] = 'NaN' if math.isnan(nan_roundtrip) else nan_roundtrip
                result['nonfinite_native_coverage'] = 'GHS.StackerHUD.Data.RejectsInvalidTelemetryAtomically'
                invalid = [(101, 100), (-2, 100), (75, -1), (75, float('inf'))]
                if math.isnan(nan_roundtrip):
                    invalid.append((float('nan'), 100))
                for battery, height in invalid:
                    accepted = data.set_telemetry(battery, height, unreal.GHSStackerStatus.WARNING, 'INVALID', True)
                    assert not accepted, dict(battery=battery, height=height, accepted=accepted, after=snapshot(data))
                    assert snapshot(data) == live_snapshot
                assert not data.apply_demo_state(3)
                assert snapshot(data) == live_snapshot
                record('live_telemetry_accepts_valid_values_and_atomically_rejects_invalid_metrics')
                advance('rediscover')
        elif stage == 'rediscover' and value['elapsed'] >= 1.4:
            assert snapshot(stackers[selected_id]) == live_snapshot
            assert widget.get_registered_equipment_count() == 64
            assert widget.get_registered_stacker_count() == 12
            record('periodic_actor_discovery_does_not_duplicate_or_overwrite_live_telemetry')
            data = stackers[selected_id]
            assert data.set_telemetry(-1, -1, unreal.GHSStackerStatus.OFFLINE, 'STALE', False)
            offline = snapshot(data)
            assert offline['battery'] == offline['fork_height_cm'] == -1
            assert offline['task'] == '' and not offline['has_telemetry'] and not offline['demo']
            record('live_offline_update_clears_stale_metrics_and_task', telemetry=offline)
            advance('finish')
        elif stage == 'finish' and not pending_capture:
            finish()
    except Exception:
        finish(traceback.format_exc())


save()
handle = unreal.register_slate_post_tick_callback(tick)
unreal.log('STACKER_HUD_VERIFIER_READY ' + SUFFIX)
