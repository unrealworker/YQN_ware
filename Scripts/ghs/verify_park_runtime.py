"""Owned offscreen game acceptance for the full GHS campus.

Launch the saved Zcool map with -game -RenderOffscreen -TwinDiagnostics
-windowed -ForceRes -ResX=1920 -ResY=1080 and execute this file. No assets are
saved. Only the explicitly required owned game process is quit on completion.
"""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import time
import traceback

import unreal

ROOT = Path('D:/UEPro/Test')
OUT = ROOT / 'Saved/ParkExpansion'
MAP = '/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
MAP_FILE = ROOT / 'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'
SOURCE_FILE = ROOT / 'Content/Maps/GHS_CAD_NormalWarehouse.umap'
MANIFEST_FILE = ROOT / 'SourceAssets/GHS/Park/park_manifest.json'
REPORT = OUT / 'runtime_report.json'
CLI = unreal.SystemLibrary.get_command_line()
OWNED_GAME = all(re.search(r'(?:^|\s)-' + flag + r'(?=\s|$)', CLI, re.I)
                 for flag in ('game', 'RenderOffscreen'))
assert OWNED_GAME, 'This verifier requires its own -game -RenderOffscreen process'
assert re.search(r'(?:^|\s)-TwinDiagnostics(?=\s|$)', CLI, re.I), 'Add -TwinDiagnostics for browser evidence'

STARTED = time.monotonic()
world = pc = pawn = widget = camera = handle = None
finished = False
stage = 'initialization'
manifest = None
map_hashes = {}
result = dict(success=False, status='running', map=MAP, checks=[], captures=[],
              assets_saved=False, visual_review_required=True,
              performance_benchmark=False, maximum_runtime_seconds=240)


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write():
    OUT.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


def xyz(value):
    return [float(value.x), float(value.y), float(value.z)]


def record(name, **values):
    result['checks'].append(dict(name=name, passed=True, **values))
    write()
    unreal.log('GHS_PARK_RUNTIME_CHECK ' + name)


def snapshot():
    return json.loads(widget.get_snapshot())


def browser_report():
    raw = widget.get_editor_property('last_browser_report')
    return json.loads(raw) if raw else {}


def poi_report():
    return json.loads(widget.get_poi_report())


def command(action, **values):
    widget.command(json.dumps(dict(action=action, **values)))


def wait_for(name, condition, timeout=25, stable_frames=4):
    global stage
    stage = name
    start, stable = time.monotonic(), 0
    while True:
        assert time.monotonic() - start < timeout, 'Timed out: ' + name
        stable = stable + 1 if condition() else 0
        if stable >= stable_frames:
            return
        yield


def pause(seconds):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        yield


def discover():
    global world, pc, pawn, widget, camera
    for candidate in unreal.ObjectIterator(unreal.World):
        if candidate.get_path_name().split('.')[0] != MAP:
            continue
        controller = unreal.GameplayStatics.get_player_controller(candidate, 0)
        if not controller or not hasattr(controller, 'twin_hud_widget'):
            continue
        hud = controller.get_editor_property('twin_hud_widget')
        if not hud or not hud.get_editor_property('browser_ready'):
            continue
        world, pc, widget = candidate, controller, hud
        pawn = controller.get_controlled_pawn()
        camera = unreal.GameplayStatics.get_player_camera_manager(world, 0)
        return bool(pawn and camera and browser_report())
    return False


def camera_settled():
    if pawn.is_pose_transition_active():
        return False
    actual = pawn.get_actor_rotation()
    desired = pawn.get_editor_property('desired_rotation')
    rotation_error = max(abs((a - b + 180) % 360 - 180) for a, b in
                         ((actual.pitch, desired.pitch), (actual.yaw, desired.yaw)))
    spring = pawn.get_editor_property('spring_arm_component')
    return (rotation_error < .05 and
            math.dist(xyz(pawn.get_actor_location()), xyz(pawn.get_editor_property('desired_location'))) < .6 and
            abs(spring.get_editor_property('target_arm_length') - pawn.get_editor_property('desired_zoom')) < .6)


def camera_state():
    rotation = camera.get_camera_rotation()
    component = pawn.get_editor_property('warehouse_camera')
    return dict(eye=xyz(camera.get_camera_location()),
                rotation=[rotation.pitch, rotation.yaw, rotation.roll],
                pivot=xyz(pawn.get_actor_location()),
                focus_target=xyz(pawn.get_focus_target()),
                component_horizontal_fov=float(component.get_editor_property('field_of_view')),
                camera_manager_fov=float(camera.get_fov_angle()),
                actual_arm_length=float(pawn.get_editor_property('spring_arm_component').get_editor_property('target_arm_length')),
                desired_zoom=float(pawn.get_editor_property('desired_zoom')),
                overview_center=xyz(pawn.get_editor_property('overview_center')),
                overview_distance=float(pawn.get_editor_property('overview_distance')))


def scene_rectangle():
    """HUD reports design units; world projection returns physical pixels."""
    width, height = pc.get_viewport_size()
    scale = float(widget.get_hud_scale())
    panel_at, panel_size = widget.get_panel_position(), widget.get_panel_size()
    assert width >= 900, 'This acceptance covers desktop viewports'
    return dict(left=0., top=panel_at.y * scale,
                right=panel_at.x * scale if panel_size.x > 0 else float(width),
                bottom=float(height), viewport=[width, height], hud_scale=scale,
                panel_position_design=[panel_at.x, panel_at.y],
                panel_size_design=[panel_size.x, panel_size.y])


def project(point):
    screen = pc.project_world_location_to_screen(unreal.Vector(*point), False)
    if screen is None:
        return None
    return [float(screen.x), float(screen.y)]


def campus_fit(name, margin=10):
    global stage
    stage = name
    bounds = scene_rectangle()
    corners, failures = [], []
    for index, point in enumerate(manifest['campus_boundary_ue_cm']):
        pixel = project(point)
        inside = bool(pixel and bounds['left'] + margin <= pixel[0] <= bounds['right'] - margin
                      and bounds['top'] + margin <= pixel[1] <= bounds['bottom'] - margin)
        unobscured = bool(pixel and widget.is_scene_point(unreal.Vector2D(*pixel)))
        row = dict(index=index, world_cm=point, screen_px=pixel,
                   inside_margin=inside, unobscured_by_chrome=unobscured)
        corners.append(row)
        if not inside or not unobscured:
            failures.append(row)
    evidence = dict(name=name, passed=not failures, margin_px=margin,
                    scene=bounds, camera=camera_state(), corners=corners, failures=failures)
    result.setdefault('campus_framing', []).append(evidence)
    write()
    assert not failures, '{}: campus corners outside visible scene: {}'.format(name, json.dumps(failures))
    record(name, scene=bounds, corner_count=len(corners), minimum_margin_px=margin)


def assert_browser_layout(name):
    report = browser_report()
    assert report, 'No browser diagnostics'
    assert not report.get('overflow'), report
    assert not report.get('imageFailures'), report
    assert report.get('equipmentCount') == 106 and report.get('facilityCount') == 56, report
    width, height = pc.get_viewport_size()
    pixels = widget.get_viewport_pixel_size()
    assert abs(pixels.x - width) < 1 and abs(pixels.y - height) < 1, (pixels, width, height)
    scale = float(widget.get_hud_scale())
    expected_scale = max(1., min(width / 1920., height / 1080.))
    assert abs(scale - expected_scale) < .001, (scale, expected_scale)
    position, size = widget.get_panel_position(), widget.get_panel_size()
    assert abs((position.x + size.x) * scale - width) < 1
    assert abs((position.y + size.y) * scale - height) < 1
    record(name, browser=report, hud_scale=scale, viewport=[width, height])


def verify_registry():
    data = snapshot()
    assert len(data['equipment']) == 106 and len(data['facilities']) == 56
    identifiers = [row['id'] for row in data['equipment'] + data['facilities']]
    assert len(set(identifiers)) == len(identifiers), 'Duplicate business identities'
    assert 'AGV-07' in identifiers
    assert not any('GHSPark_' in identifier or 'GHS_ParkContext' in identifier for identifier in identifiers)
    park_actors = [actor for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor)
                   if actor.actor_has_tag('GHS_ParkContext')]
    assert len(park_actors) == int(manifest['asset_count']) + 3, ('Park actor count', len(park_actors), manifest['asset_count'])
    used_meshes = Counter()
    instance_counts = {}
    capture_cameras = []
    for actor in park_actors:
        label = actor.get_actor_label()
        assert label.startswith('GHSPark_'), label
        assert not any(str(tag).startswith('TwinId=') for tag in actor.tags), label
        if isinstance(actor, unreal.CameraActor):
            capture_cameras.append(label)
        for component in actor.get_components_by_class(unreal.StaticMeshComponent):
            mesh = component.static_mesh
            if mesh and mesh.get_name().startswith('SM_GHSPark_'):
                used_meshes[mesh.get_name()] += 1
                if isinstance(component,unreal.InstancedStaticMeshComponent):
                    instance_counts[mesh.get_name()]=component.get_instance_count()
                    assert component.get_collision_enabled()==unreal.CollisionEnabled.NO_COLLISION
                    assert component.get_editor_property('mobility')==unreal.ComponentMobility.STATIC
                    assert not actor.is_actor_tick_enabled() and not actor.get_actor_enable_collision()
    expected_meshes = Counter({row['name']: 1 for row in manifest['meshes']})
    assert used_meshes == expected_meshes, (dict(used_meshes), dict(expected_meshes))
    expected_instances={row['name']:len(row['instances']) for row in manifest['meshes'] if 'instances' in row}
    assert instance_counts==expected_instances, (instance_counts,expected_instances)
    assert len(capture_cameras) == 3, capture_cameras
    result['initial_business_ids'] = identifiers
    record('saved_campus_loaded_and_business_registry_preserved', equipment=106, facilities=56,
           park_actors=len(park_actors), mesh_components=dict(used_meshes), capture_cameras=capture_cameras,
           static_display_instances=instance_counts)


def capture(name):
    path = OUT / ('Runtime_' + name + '.png')
    old = (path.stat().st_mtime_ns, path.stat().st_size) if path.exists() else None
    viewport = list(pc.get_viewport_size())
    requested = time.time()
    unreal.SystemLibrary.execute_console_command(
        world, 'Shot showui filename="' + path.as_posix() + '" -nosuffix', pc)

    def written():
        if not path.exists():
            return False
        stat = path.stat()
        return ((stat.st_mtime_ns, stat.st_size) != old and
                stat.st_mtime >= requested - 1 and stat.st_size > 10000)

    yield from wait_for('capture_' + name, written, timeout=30, stable_frames=2)
    header = path.read_bytes()[:24]
    assert header[:8] == b'\x89PNG\r\n\x1a\n'
    dimensions = list(struct.unpack('>II', header[16:24]))
    assert dimensions == viewport, (name, dimensions, viewport)
    result['captures'].append(dict(name=name, path=str(path), dimensions=dimensions,
                                    bytes=path.stat().st_size, sha256=sha(path),
                                    selection=str(widget.get_editor_property('selected_id')),
                                    camera=camera_state()))
    write()


def toggle_panel():
    width, _ = pc.get_viewport_size()
    scale = float(widget.get_hud_scale())
    assert widget.handle_chrome_click(unreal.Vector2D(width - 30 * scale, 25 * scale))


def assert_no_selection():
    data = snapshot()
    assert not str(widget.get_editor_property('selected_id'))
    assert not (data.get('selection') or {}).get('id'), data.get('selection')
    assert not any(row.get('selected') for row in poi_report().get('labels', []))


def assert_device_visible():
    data = snapshot()
    selection = data.get('selection') or {}
    assert selection.get('id') == 'AGV-07', selection
    point = selection.get('worldPosition')
    assert point and len(point) == 3, selection
    pixel = project(point)
    assert pixel and widget.is_scene_point(unreal.Vector2D(*pixel)), ('Selected device hidden', pixel, scene_rectangle())
    assert browser_report().get('detail', {}).get('id') == 'AGV-07', browser_report()
    assert browser_report().get('detailActionsVisible') is not False, browser_report()
    labels = poi_report().get('labels', [])
    assert any(row.get('id') == 'AGV-07' and row.get('selected') for row in labels), labels
    record('agv_selection_focus_and_details_visible', selection=selection, screen_px=pixel,
           camera=camera_state(), poi=poi_report())


def assert_region_visible(region):
    points = poi_report()
    expected = 'REGION:' + region
    labels = points.get('labels', [])
    assert any(row.get('id') == expected and row.get('selected') for row in labels), points
    assert not str(widget.get_editor_property('selected_id')), 'Region focus retained device selection'
    assert pawn.uses_object_pivot(), 'Region command did not set a focus pivot'
    pixel = project(xyz(pawn.get_focus_target()))
    assert pixel and widget.is_scene_point(unreal.Vector2D(*pixel)), (region, pixel)
    assert abs(pawn.get_actor_rotation().pitch + 58) < .05
    record('region_' + region + '_focus_preserved', screen_px=pixel, camera=camera_state(), poi=points)


def verify_saved_maps():
    for path, expected in map_hashes.items():
        assert sha(Path(path)) == expected, 'Runtime changed saved map: ' + path
    record('runtime_did_not_modify_either_saved_map', map_sha256=map_hashes)


def run():
    global manifest, map_hashes
    manifest = read(MANIFEST_FILE)
    assert len(manifest['campus_boundary_ue_cm']) >= 3
    result['manifest_sha256'] = sha(MANIFEST_FILE)
    map_hashes = {str(path): sha(path) for path in (MAP_FILE, SOURCE_FILE)}
    source_baseline = read(OUT / 'source_map_baseline.json')
    assert map_hashes[str(SOURCE_FILE)] == source_baseline['sha256'], 'Original map changed before runtime'
    yield from wait_for('discover_live_hud_browser', discover, timeout=55)
    verify_registry()
    unreal.SystemLibrary.execute_console_command(world, 'DisableAllScreenMessages', pc)
    yield from wait_for('initial_1920x1080_viewport', lambda: tuple(pc.get_viewport_size()) == (1920, 1080))
    yield from wait_for('initial_camera_and_panel', lambda: camera_settled() and widget.get_panel_transition_progress() >= .999, stable_frames=10)
    yield from pause(1.2)
    assert_browser_layout('initial_1080p_hud_ready')
    yield from capture('Overview_1920x1080')
    campus_fit('initial_full_campus_1920x1080')

    unreal.SystemLibrary.execute_console_command(world, 'r.SetRes 2560x1600w', pc)
    yield from wait_for('live_resize_2560x1600', lambda: tuple(pc.get_viewport_size()) == (2560, 1600))
    yield from wait_for('resized_camera_settled', camera_settled, stable_frames=12)
    yield from pause(1.)
    assert_browser_layout('resized_2560x1600_hud_ready')
    yield from capture('Overview_2560x1600')
    campus_fit('full_campus_after_live_resize_2560x1600')

    before = camera_state()
    toggle_panel()
    yield from wait_for('panel_collapsed', lambda: widget.get_panel_transition_progress() <= .001)
    yield from wait_for('collapsed_camera_settled', camera_settled)
    after = camera_state()
    assert math.dist(before['eye'], after['eye']) < 1., ('Panel collapse moved camera', before, after)
    yield from capture('PanelCollapsed_2560x1600')
    campus_fit('full_campus_after_panel_collapse')
    toggle_panel()
    yield from wait_for('panel_expanded', lambda: widget.get_panel_transition_progress() >= .999)
    yield from pause(.5)
    campus_fit('full_campus_after_panel_expand')

    previous = xyz(camera.get_camera_location())
    assert widget.select_object('AGV-07', True)
    assert math.dist(previous, xyz(camera.get_camera_location())) < 1., 'Selecting AGV teleported camera'
    yield from wait_for('agv_focus_settled', camera_settled, stable_frames=8)
    yield from wait_for('agv_browser_detail', lambda: (browser_report().get('detail') or {}).get('id') == 'AGV-07')
    yield from pause(.5)
    assert_device_visible()
    yield from capture('AGV07_Focus')
    command('overview')
    yield from wait_for('overview_reset_settled', camera_settled, stable_frames=8)
    yield from pause(.5)
    assert_no_selection()
    yield from capture('Overview_Reset')
    campus_fit('overview_command_clears_selection_and_restores_campus')

    for region in ('racks', 'floor'):
        command('preset', value=region)
        yield from wait_for(region + '_focus_settled', camera_settled, stable_frames=8)
        yield from pause(.5)
        assert_region_visible(region)
        yield from capture('Region_' + region)
    command('overview')
    yield from wait_for('final_overview_settled', camera_settled, stable_frames=8)
    yield from pause(.4)
    assert_no_selection()
    campus_fit('final_full_campus_after_region_focus')
    data = snapshot()
    final_ids = [row['id'] for row in data['equipment'] + data['facilities']]
    assert final_ids == result['initial_business_ids'], 'Business registry changed during interaction'
    record('business_registry_unchanged_after_focus_resize_and_reset', equipment=106, facilities=56)
    verify_saved_maps()


def finish(error=None):
    global finished
    if finished:
        return
    finished = True
    result.update(success=error is None, status='failed' if error else 'success',
                  elapsed_seconds=time.monotonic() - STARTED)
    if error:
        result.update(error=error, failed_stage=stage)
    write()
    if handle is not None:
        unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log_error if error else unreal.log)(
        'GHS_PARK_RUNTIME_' + ('FAILED ' + error if error else 'SUCCESS ' + str(REPORT)))
    if not OWNED_GAME:
        return
    if world and pc:
        unreal.SystemLibrary.execute_console_command(world, 'quit', pc)
    else:
        context = next((candidate for candidate in unreal.ObjectIterator(unreal.World)
                        if unreal.GameplayStatics.get_player_controller(candidate, 0)), None)
        if context:
            unreal.SystemLibrary.execute_console_command(context, 'quit')


steps = run()


def tick(delta):
    try:
        assert time.monotonic() - STARTED < 240, 'Overall runtime acceptance timeout'
        next(steps)
    except StopIteration:
        finish()
    except Exception:
        finish(traceback.format_exc())


write()
handle = unreal.register_slate_post_tick_callback(tick)
unreal.log('GHS_PARK_RUNTIME_VERIFIER_READY ' + str(REPORT))
