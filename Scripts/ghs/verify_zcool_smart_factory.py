"""Fresh acceptance in an owned -game -RenderOffscreen process; never saves assets.

Launch the ZcoolSmartFactory map at 1920x1080 with -ForceRes -windowed and
-ExecCmds="py D:/UEPro/Test/Scripts/ghs/verify_zcool_smart_factory.py".
The frame-driven verifier records real HUD interactions and observed PNG writes,
then quits only this offscreen game. No desktop input or editor API is used.
"""
import hashlib
import json
import math
import re
import struct
import time
import traceback
from pathlib import Path

import unreal

ROOT = Path('D:/UEPro/Test')
MAP = '/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
MAP_FILE = ROOT / ('Content' + MAP[5:] + '.umap')
ORIGINAL = ROOT / 'Content/Maps/GHS_CAD_NormalWarehouse.umap'
ORIGINAL_HASH = 'f7201ef820bcfca947071a5e936427362a0c002ba50398dba2e17755d7e40066'
REPORT = ROOT / 'Saved/GHS_Zcool_Runtime.json'
STARTED = time.monotonic()
COMMAND = unreal.SystemLibrary.get_command_line()
OWNED_GAME = all(re.search(r'(?:^|\s)-'+flag+r'(?=\s|$)', COMMAND, re.I)
                 for flag in ('game', 'RenderOffscreen'))
result = dict(success=False, status='running', map=MAP, tests=[], captures=[],
              assets_saved=False, visual_review_required=True)
world = pc = pawn = widget = camera = handle = None
actors, kinds, initial_scene = {}, {}, {}
stage, finished, target_hash = 'initialization', False, None


def sha(path):
    with path.open('rb') as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def save():
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


def record(name, **values):
    result['tests'].append(dict(name=name, passed=True, **values))
    unreal.log('ZCOOL_VERIFY_PASS ' + name)
    save()


def xyz(value):
    return [float(value.x), float(value.y), float(value.z)]


def transform(actor):
    r = actor.get_actor_rotation()
    return [xyz(actor.get_actor_location()), xyz(actor.get_actor_scale3d()),
            [float(r.pitch), float(r.yaw), float(r.roll)]]


def instance_digest(component):
    count = component.get_instance_count()
    digest = hashlib.sha256()
    for index in range(count):
        value = component.get_instance_transform(index, world_space=True)
        p, s, q = value.translation, value.scale3d, value.rotation
        digest.update(struct.pack('<10d', p.x, p.y, p.z, s.x, s.y, s.z, q.x, q.y, q.z, q.w))
    return dict(count=count, sha256=digest.hexdigest())


def scene_snapshot():
    snapshot = {}
    for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor):
        if isinstance(actor, (unreal.Pawn, unreal.PlayerController, unreal.PlayerCameraManager)):
            continue
        parent = actor.get_attach_parent_actor()
        row = dict(transform=transform(actor), parent=parent.get_name() if parent else None,
                   tags=sorted(str(t) for t in actor.tags))
        components = actor.get_components_by_class(unreal.InstancedStaticMeshComponent)
        row['instances'] = {c.get_name(): instance_digest(c) for c in components}
        snapshot[actor.get_name()] = row
    return snapshot


def labels():
    rows = []
    for item in widget.get_visible_labels():
        ids = [str(i) for i in item.get_editor_property('equipment_ids')]
        p, size = item.get_editor_property('position'), item.get_editor_property('size')
        assert ids and all(i in actors for i in ids), ('Unknown HUD identity', ids)
        assert len({kinds[i] for i in ids}) == 1, ('Mixed equipment types', ids)
        rows.append(dict(key=str(item.get_editor_property('key')), ids=ids,
                         position=[p.x, p.y], size=[size.x, size.y],
                         opacity=float(item.get_editor_property('opacity'))))
    return rows


def camera_settled():
    if not pawn or not camera:
        return False
    actual, desired = pawn.get_actor_rotation(), pawn.get_editor_property('desired_rotation')
    rotation_error = max(abs((a-b+180) % 360-180) for a, b in
                         ((actual.pitch, desired.pitch), (actual.yaw, desired.yaw)))
    spring = pawn.get_editor_property('spring_arm_component')
    return (rotation_error < .04 and
            math.dist(xyz(pawn.get_actor_location()), xyz(pawn.get_editor_property('desired_location'))) < .5 and
            abs(spring.get_editor_property('target_arm_length') - pawn.get_editor_property('desired_zoom')) < .5)


def wait_for(name, condition, timeout=35, stable_frames=3):
    global stage
    stage = name
    start, stable = time.monotonic(), 0
    while True:
        assert time.monotonic()-start < timeout, 'Timed out: ' + name
        stable = stable + 1 if condition() else 0
        if stable >= stable_frames:
            return
        yield


def hud_settled():
    rows = labels()
    return camera_settled() and rows and all(row['opacity'] >= .999 for row in rows)


def panel_bounds(prefix):
    dpi = unreal.WidgetLayoutLibrary.get_viewport_scale(world)
    width, height = pc.get_viewport_size()
    p, size = widget.get_editor_property(prefix+'_position'), widget.get_editor_property(prefix+'_size')
    assert p.x >= -.5 and p.y >= -.5 and size.x > 0 and size.y > 0
    assert p.x+size.x <= width/dpi+.5 and p.y+size.y <= height/dpi+.5
    return p, size


def click_label(row):
    x, y = row['position']
    width, height = row['size']
    assert widget.handle_pointer_click(unreal.Vector2D(x+width/2, y+height/2))


def capture(name):
    path = ROOT / ('Saved/GHS_Zcool_' + name + '.png')
    old = (path.stat().st_mtime_ns, path.stat().st_size) if path.exists() else None
    requested = time.time()
    unreal.SystemLibrary.execute_console_command(world, 'Shot showui filename="'+path.as_posix()+'" -nosuffix', pc)

    def written():
        if not path.is_file():
            return False
        stat = path.stat()
        return (stat.st_mtime_ns, stat.st_size) != old and stat.st_mtime >= requested-1 and stat.st_size > 10000

    yield from wait_for('capture_'+name, written, timeout=40, stable_frames=2)
    header = path.read_bytes()[:24]
    assert header[:8] == b'\x89PNG\r\n\x1a\n'
    dimensions = list(struct.unpack('>II', header[16:24]))
    assert dimensions == [1920, 1080], dimensions
    result['captures'].append(dict(name=name, path=str(path), dimensions=dimensions,
                                    bytes=path.stat().st_size, sha256=sha(path),
                                    selected=str(widget.get_selected_equipment_id()), labels=labels(),
                                    detail=bool(widget.get_editor_property('detail_visible')),
                                    group_list=bool(widget.get_editor_property('cluster_list_visible'))))
    save()


def discover():
    global world, pc, pawn, widget, camera
    for candidate in unreal.ObjectIterator(unreal.World):
        if candidate.get_path_name().split('.')[0] != MAP:
            continue
        controller = unreal.GameplayStatics.get_player_controller(candidate, 0)
        if controller:
            world, pc = candidate, controller
            break
    if not pc:
        return False
    pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
    camera = unreal.GameplayStatics.get_player_camera_manager(world, 0)
    widget = pc.get_editor_property('truck_hud_widget')
    return bool(pawn and camera and widget and widget.get_registered_equipment_count() == 74)


def verify_fleet():
    definitions = (
        ('truck', 'IndependentDockTruck', r'TwinId=GHS_DockTruck_([0-9]+)', 'TRUCK-', 3, 52, widget.get_truck_data),
        ('stacker', 'NormalWarehouseFloorStacker', r'TwinId=GHN_FloorStacker_([0-9]+)', 'STACKER-', 2, 6, widget.get_stacker_data),
        ('forklift', 'NormalWarehouseMannedForklift', r'TwinId=GHN_MannedForklift_([0-9]+)', 'FORK-', 2, 16, widget.get_manned_forklift_data),
    )
    all_actors = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor)
    counts = {}
    for kind, tag, pattern, prefix, digits, expected, getter in definitions:
        fleet = [a for a in all_actors if a.actor_has_tag(tag)]
        assert len(fleet) == expected, (kind, len(fleet), expected)
        ids = []
        for actor in fleet:
            matches = [re.fullmatch(pattern, str(t)) for t in actor.tags]
            matches = [m for m in matches if m]
            assert len(matches) == 1
            identifier = prefix+format(int(matches[0][1]), '0'+str(digits)+'d')
            assert identifier not in actors, ('Duplicate identity', identifier)
            data = getter(identifier)
            assert data and data.get_owner() == actor, ('HUD owner mismatch', identifier)
            actors[identifier], kinds[identifier] = actor, kind
            ids.append(identifier)
        counts[kind] = dict(count=len(fleet), ids=sorted(ids))
    agvs = [a for a in all_actors if any(re.fullmatch(r'TwinId=GHS_AGV_[0-9]+', str(t)) for t in a.tags)]
    assert len(agvs) == 32, len(agvs)
    assert widget.get_registered_truck_count() == 52
    assert widget.get_registered_stacker_count() == 6
    assert widget.get_registered_manned_forklift_count() == 16
    native = unreal.load_class(None, '/Script/Test.GHSWarehouseCameraPawn')
    assert len(unreal.GameplayStatics.get_all_actors_of_class(world, native)) == 1
    assert widget.is_in_viewport() and tuple(pc.get_viewport_size()) == (1920, 1080)
    record('saved_fleet_all_unique_and_bound_to_original_HUD', equipment=counts, agvs=len(agvs), camera_count=1)


def focus(identifier):
    center, extent = actors[identifier].get_actor_bounds(False)
    widget.clear_selection()
    pawn.set_desired_location(unreal.Vector(center.x, center.y, 0), True)
    pawn.set_desired_rotation(unreal.Rotator(pitch=-42, yaw=-135, roll=0), True)
    pawn.set_desired_zoom(3200 if kinds[identifier] == 'truck' else 1600, True)


def selected_ready(identifier):
    return (str(widget.get_selected_equipment_id()) == identifier and
            widget.get_editor_property('detail_visible') and
            widget.get_editor_property('detail_transition_progress') >= .999)


def verify_static_scene():
    final = scene_snapshot()
    assert set(final) == set(initial_scene), ('Actor set changed', set(final)^set(initial_scene))
    for key, original in initial_scene.items():
        assert final[key] == original, ('Actor/attachment/instance/tag mutation', key)
    assert sha(ORIGINAL) == ORIGINAL_HASH, 'Original map modified'
    assert sha(MAP_FILE) == target_hash, 'Saved new map modified by runtime'
    record('all_non_camera_actor_transforms_attachments_instances_and_maps_unchanged',
           actor_count=len(final), original_sha256=ORIGINAL_HASH, new_map_sha256=target_hash,
           instance_count=sum(v['count'] for a in final.values() for v in a['instances'].values()))


def run():
    global initial_scene, target_hash
    command = unreal.SystemLibrary.get_command_line()
    for required in ('game', 'RenderOffscreen'):
        assert re.search(r'(?:^|\s)-'+required+r'(?=\s|$)', command, re.I), 'Requires owned offscreen game'
    assert sha(ORIGINAL) == ORIGINAL_HASH, 'Source differs from approved saved baseline'
    target_hash = sha(MAP_FILE)
    yield from wait_for('discover_new_map_and_all_74_HUD_devices', discover, timeout=55)
    verify_fleet()
    initial_scene = scene_snapshot()
    unreal.SystemLibrary.execute_console_command(world, 'DisableAllScreenMessages', pc)
    pawn.reset_overview(True)
    yield from wait_for('initial_overview', hud_settled, stable_frames=10)
    initial_rows = labels()
    assert {kinds[i] for row in initial_rows for i in row['ids']} == {'truck', 'stacker', 'forklift'}
    assert len(initial_rows) <= 12
    for kind in ('truck', 'stacker', 'forklift'):
        assert sum(kinds[row['ids'][0]] == kind for row in initial_rows) <= 4
    represented = [i for row in initial_rows for i in row['ids']]
    assert len(represented) == len(set(represented))
    record('original_full_viewport_and_three_separate_equipment_groups', labels=initial_rows,
           viewport=list(pc.get_viewport_size()), represented_equipment=len(represented))
    yield from capture('Overview')

    group = max((row for row in labels() if len(row['ids']) > 5), key=lambda row: len(row['ids']))
    click_label(group)
    members = [str(i) for i in widget.get_expanded_cluster_members()]
    assert members == group['ids']
    yield from wait_for('group_list_open', lambda: widget.get_editor_property('cluster_transition_progress') >= .999)
    position, size = panel_bounds('cluster_list')
    yield from capture('Group')
    # The actual next-page arrow is in the rightmost footer region. A row from
    # page two must become clickable, while page one's first row disappears.
    assert widget.get_member_row_position(members[5]).x < 0
    assert widget.handle_pointer_click(unreal.Vector2D(position.x+size.x*.92, position.y+size.y-10))
    yield from wait_for('group_next_page', lambda: widget.get_member_row_position(members[5]).x >= 0)
    assert widget.get_member_row_position(members[0]).x < 0
    row = widget.get_member_row_position(members[5])
    assert widget.handle_pointer_click(unreal.Vector2D(row.x+10, row.y+10))
    yield from wait_for('group_row_detail', lambda: selected_ready(members[5]))
    panel_bounds('detail')
    record('real_group_click_next_page_arrow_and_page_two_member_click', members=members, selected=members[5])
    widget.clear_selection()
    yield from wait_for('clear_selection_closes_popups', lambda: not widget.get_editor_property('detail_visible') and
                        not widget.get_editor_property('cluster_list_visible'))

    for kind, capture_name in (('forklift', 'ForkliftDetail'), ('stacker', 'StackerDetail'), ('truck', 'TruckDetail')):
        identifier = sorted(i for i in actors if kinds[i] == kind)[0]
        focus(identifier)
        yield from wait_for(kind+'_near_label', lambda: hud_settled() and any(r['ids'] == [identifier] for r in labels()), stable_frames=8)
        assert not pawn.should_aggregate_truck_hud()
        assert all(len(r['ids']) == 1 for r in labels())
        click_label(next(r for r in labels() if r['ids'] == [identifier]))
        yield from wait_for(kind+'_detail_click', lambda: selected_ready(identifier))
        position, size = panel_bounds('detail')
        assert str(widget.get_selected_truck_id()) == (identifier if kind == 'truck' else '')
        yield from capture(capture_name)
        # Detail uses the original 320x184 logical card, whose close button
        # center is (304,18); scaling comes from its current measured geometry.
        assert widget.handle_pointer_click(unreal.Vector2D(position.x+size.x*304/320, position.y+size.y*18/184))
        yield from wait_for(kind+'_close_button', lambda: not widget.get_selected_equipment_id() and
                            not widget.get_editor_property('detail_visible'))
        assert widget.select_equipment_by_id(identifier)
        yield from wait_for(kind+'_selection_API', lambda: selected_ready(identifier))
        widget.clear_selection()
        yield from wait_for(kind+'_selection_clear_API', lambda: not widget.get_editor_property('detail_visible'))
        record(kind+'_near_singleton_click_detail_close_and_selection_API', identifier=identifier)

    pawn.reset_overview(True)
    yield from wait_for('camera_before_orbit', camera_settled)
    center = xyz(pawn.get_actor_location())
    before = pawn.get_actor_rotation()
    original_zoom = float(pawn.get_editor_property('desired_zoom'))
    pawn.orbit_pixels(unreal.Vector2D(160, 60))
    pawn.zoom_steps(2)
    expected_pitch = before.pitch-60*float(pawn.get_editor_property('pitch_degrees_per_pixel'))
    expected_yaw = before.yaw+160*float(pawn.get_editor_property('orbit_degrees_per_pixel'))
    expected_zoom = original_zoom*math.exp(-2*float(pawn.get_editor_property('wheel_zoom_exponent')))
    yield from wait_for('camera_actual_orbit_zoom_converges', camera_settled, stable_frames=8)
    actual = pawn.get_actor_rotation()
    assert abs(actual.pitch-expected_pitch) < .05
    assert abs((actual.yaw-expected_yaw+180) % 360-180) < .05
    assert abs(float(pawn.get_editor_property('spring_arm_component').get_editor_property('target_arm_length'))-expected_zoom) < .6
    assert math.dist(xyz(pawn.get_actor_location()), center) < .5
    assert abs(pawn.get_actor_location().z) < .01 and abs(camera.get_camera_rotation().roll) < .01
    record('actual_camera_orbit_and_zoom_preserve_ground_pivot', pitch=actual.pitch, yaw=actual.yaw, distance=expected_zoom)
    pawn.pan_pixels(unreal.Vector2D(75, -30), pc.get_viewport_size()[0])
    yield from wait_for('camera_pan_converges', camera_settled, stable_frames=5)
    assert math.dist(xyz(pawn.get_actor_location()), center) > 100
    assert abs(pawn.get_actor_location().z) < .01
    record('camera_pan_API_moves_ground_pivot')
    pawn.reset_overview(False)
    yield from wait_for('smooth_overview_reset', hud_settled, stable_frames=8)
    assert math.dist(xyz(pawn.get_actor_location()), xyz(pawn.get_editor_property('overview_center'))) < .5
    assert abs(float(pawn.get_editor_property('desired_zoom'))-float(pawn.get_editor_property('overview_distance'))) < .1
    record('camera_smooth_reset_and_original_HUD_survive_interaction')
    verify_static_scene()
    assert [row['name'] for row in result['captures']] == ['Overview', 'Group', 'ForkliftDetail', 'StackerDetail', 'TruckDetail']


def finish(error=None):
    global finished
    if finished:
        return
    finished = True
    result.update(success=error is None, status='success' if error is None else 'failed',
                  elapsed_seconds=time.monotonic()-STARTED)
    if error:
        result.update(error=error, failed_stage=stage)
    save()
    if handle is not None:
        unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log_error if error else unreal.log)('ZCOOL_RUNTIME_'+('FAILED '+error if error else 'SUCCESS '+str(REPORT)))
    if not OWNED_GAME:
        return
    if world and pc:
        unreal.SystemLibrary.execute_console_command(world, 'quit', pc)
    else:
        # Discovery failures must also exit this explicitly required offscreen
        # game; never leave the owned test process running indefinitely.
        context = next((w for w in unreal.ObjectIterator(unreal.World)
                        if unreal.GameplayStatics.get_player_controller(w, 0)), None)
        if context:
            unreal.SystemLibrary.execute_console_command(context, 'quit')


steps = run()


def tick(delta):
    try:
        assert time.monotonic()-STARTED < 300, 'Overall acceptance timeout'
        next(steps)
    except StopIteration:
        finish()
    except Exception:
        finish(traceback.format_exc())


save()
handle = unreal.register_slate_post_tick_callback(tick)
unreal.log('ZCOOL_RUNTIME_VERIFIER_READY '+str(REPORT))
