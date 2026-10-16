"""Disposable UE commandlet checks for the Normal warehouse orbit camera.

No map, asset, or configuration is saved. Add -WarehouseCameraSetupRequired
after the scene Blueprint/GameMode installation has completed.
"""
import hashlib
import json
import math
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import unreal


ROOT = Path(r'D:\UEPro\Test')
REPORT = ROOT / 'Saved/GHS_WarehouseCameraVerification.json'
MAP = '/Game/Maps/GHS_CAD_NormalWarehouse'
PAWN_CLASS = '/Script/Test.GHSWarehouseCameraPawn'
CONTROLLER_CLASS = '/Script/Test.GHSWarehousePlayerController'
GAMEMODE_CLASS = '/Script/Test.GHSWarehouseGameMode'
BP_PAWN = '/Game/GHSNormalWarehouse/Camera/BP_GHS_WarehouseCamera'
BP_GAMEMODE = '/Game/GHSNormalWarehouse/Camera/BP_GHS_WarehouseGameMode'
CENTER = (-646.665, 833.981, 0.0)


def vector(v):
    return [float(v.x), float(v.y), float(v.z)]


def near(actual, expected, tolerance=0.05):
    assert math.isfinite(float(actual)), f'Non-finite value: {actual}'
    assert abs(float(actual) - float(expected)) <= tolerance, (actual, expected)


def near_vector(actual, expected, tolerance=0.05):
    for a, b in zip(vector(actual), expected):
        near(a, b, tolerance)


def angular_distance(a, b):
    return abs((float(a) - float(b) + 180.0) % 360.0 - 180.0)


def pose(pawn):
    rotation = pawn.get_editor_property('desired_rotation')
    return dict(location=vector(pawn.get_editor_property('desired_location')),
                socket_offset=vector(pawn.get_editor_property('desired_socket_offset')),
                target_offset=vector(pawn.get_editor_property('desired_target_offset')),
                rotation=[float(rotation.pitch), float(rotation.yaw), float(rotation.roll)],
                zoom=float(pawn.get_editor_property('desired_zoom')))


def poses_equal(a, b, tolerance=0.05):
    for key in ('location', 'socket_offset', 'target_offset', 'rotation'):
        for x, y in zip(a[key], b[key]):
            near(x, y, tolerance)
    near(a['zoom'], b['zoom'], tolerance)


def watched_hashes():
    paths = list((ROOT / 'Content/Maps').glob('GHS_CAD*.umap'))
    paths += list((ROOT / 'Content/GHSNormalWarehouse/Camera').rglob('*.uasset'))
    paths += list((ROOT / 'Config').glob('*.ini'))
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths)}


def defaults(pawn, check_registered_attachment=True):
    expected = dict(overview_distance=53500.0, overview_pitch=-30.0,
                    overview_yaw=-90.0, orbit_degrees_per_pixel=0.18,
                    pitch_degrees_per_pixel=0.14, wheel_zoom_exponent=0.12,
                    minimum_zoom=900.0, maximum_zoom=95000.0,
                    minimum_pitch=-80.0, maximum_pitch=-15.0)
    near_vector(pawn.get_editor_property('overview_center'), CENTER)
    for key, value in expected.items():
        near(pawn.get_editor_property(key), value, 0.001)
    assert pawn.get_editor_property('constrain_pitch')
    assert pawn.get_editor_property('constrain_zoom_minimum')
    assert pawn.get_editor_property('constrain_zoom_maximum')
    assert not pawn.get_editor_property('draw_debug_spheres')
    camera = pawn.get_camera_component() if check_registered_attachment else pawn.get_editor_property('warehouse_camera')
    assert camera, 'CameraComponent missing from plugin SpringArm'
    spring = pawn.get_editor_property('spring_arm_component')
    if check_registered_attachment:
        assert camera.get_attach_parent() == spring, 'Camera must attach directly to SpringArm'
    assert not spring.get_editor_property('do_collision_test')
    return expected


def setup_check(world):
    native_gm = unreal.load_class(None, GAMEMODE_CLASS)
    native_pc = unreal.load_class(None, CONTROLLER_CLASS)
    assert native_gm and native_pc, 'Native GameMode/PlayerController missing'
    bp_pawn = unreal.EditorAssetLibrary.load_blueprint_class(BP_PAWN)
    bp_gm = unreal.EditorAssetLibrary.load_blueprint_class(BP_GAMEMODE)
    assert bp_pawn and bp_gm, 'Camera/GameMode Blueprint assets missing'
    native_pawn = unreal.load_class(None, PAWN_CLASS)
    assert unreal.MathLibrary.class_is_child_of(bp_pawn, native_pawn)
    assert unreal.MathLibrary.class_is_child_of(bp_gm, native_gm)
    settings = world.get_world_settings()
    assert settings.get_editor_property('default_game_mode') == bp_gm, 'Normal map GameMode override missing'
    gm = unreal.get_default_object(bp_gm)
    assert gm.get_editor_property('default_pawn_class') == bp_pawn
    assert unreal.MathLibrary.class_is_child_of(gm.get_editor_property('player_controller_class'), native_pc)
    pawn_defaults = unreal.get_default_object(bp_pawn)
    defaults(pawn_defaults, check_registered_attachment=False)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
    placed = [a for a in actors if unreal.MathLibrary.class_is_child_of(a.get_class(), native_pawn)]
    assert len(placed) <= 1, f'Duplicate placed warehouse camera pawns: {len(placed)}'
    for actor in placed:
        defaults(actor)
        assert actor.get_editor_property('auto_possess_player') == unreal.AutoReceiveInput.PLAYER0
    sys.path.insert(0, str(ROOT / 'Scripts/ghs'))
    from sync_wall_heights import snapshot, transform
    revision_report_path = ROOT / 'Saved/GHS_GroundCameraLongTrucks.json'
    revision_details = {}
    if revision_report_path.exists():
        # This revision starts from the user's current 264 actors, including
        # the existing camera and 52 independently placed dock trucks. The
        # earlier 263-actor camera-install baseline is no longer authoritative.
        def read_revision(path):
            return json.loads(Path(path).read_text(encoding='utf-8-sig'))

        revision = read_revision(revision_report_path)
        assert revision.get('success') is True, 'Ground-camera/long-truck revision has not completed successfully'
        assert revision.get('map') == MAP
        checkpoint = read_revision(ROOT / 'Saved/GHS_WarehouseCameraGroundRevision.json')
        assert checkpoint.get('map') == MAP
        backup = Path(checkpoint['backup_root'])
        assert Path(revision['backup_root']).resolve() == backup.resolve(), 'Revision report and checkpoint disagree'
        baseline = read_revision(backup / 'live_before.json')
        expected_after = read_revision(backup / 'expected_after.json')
        by_label = {a.get_actor_label(): a for a in actors}
        assert len(by_label) == len(actors), 'Duplicate actor labels prevent preservation verification'
        assert len(actors) == len(baseline) == len(expected_after) == revision['actor_count'] == 264
        assert snapshot(by_label) == expected_after, 'Saved scene differs from the completed ground-camera/long-truck revision'

        truck_rows = {row['name']: row for row in revision['trucks']}
        truck_names = {name for name in by_label if name.startswith('GHS_DockTruck_')}
        assert len(truck_rows) == len(revision['trucks']) == revision['truck_count'] == 52
        assert truck_names == set(truck_rows) == {name for name in baseline if name.startswith('GHS_DockTruck_')}
        assert revision.get('materials_and_placements_preserved') is True
        long_mesh_path = '/Game/GHSNormalWarehouse/TrucksLong/SM_GHN_LongDockTruck'
        assert revision['new_mesh'] == long_mesh_path
        long_mesh = unreal.EditorAssetLibrary.load_asset(long_mesh_path)
        assert long_mesh, 'Long dock-truck mesh missing'
        slots = long_mesh.get_editor_property('static_materials')
        roles = [str(slot.get_editor_property('imported_material_slot_name')).rsplit('_', 1)[-1]
                 for slot in slots]
        assert len(roles) == len(set(roles)) == 7
        assert set(roles) == {'Trim', 'Body', 'Accent', 'Headlight', 'Rubber', 'TailLight', 'Glass'}
        for name, row in truck_rows.items():
            truck = by_label[name]
            assert truck.get_class() == unreal.StaticMeshActor.static_class(), name + ' must remain an independent StaticMeshActor'
            assert truck.get_attach_parent_actor() is None, name + ' unexpectedly attached to another actor'
            component = truck.get_component_by_class(unreal.StaticMeshComponent)
            assert component and component.get_editor_property('static_mesh') == long_mesh, name + ' has the wrong truck mesh'
            assert transform(truck.get_actor_transform()) == row['transform'] == baseline[name]['transform'], name + ' placement changed'
            actual_materials = {role: component.get_material(index).get_path_name()
                                for index, role in enumerate(roles)}
            assert actual_materials == row['materials_by_role'], name + ' materials changed'
            assert sorted(actual_materials.values()) == sorted(baseline[name]['materials']), name + ' lost original material assignments'

        assert len(placed) == 1 and placed[0].get_actor_label() == 'GHS_WarehouseCamera', 'Expected one installed warehouse camera Pawn'
        native_defaults = unreal.get_default_object(native_pawn)
        for obj in [pawn_defaults, placed[0]]:
            near_vector(obj.get_editor_property('overview_center'), CENTER)
            for key in ('enabled_features', 'location_constrain_type'):
                assert obj.get_editor_property(key) == native_defaults.get_editor_property(key), 'Stale Blueprint camera setting: ' + key
            for key in ('constrain_location_minimum', 'constrain_location_maximum'):
                actual_constraint = obj.get_editor_property(key)
                expected_constraint = native_defaults.get_editor_property(key)
                assert all(actual_constraint.get_editor_property(axis) == expected_constraint.get_editor_property(axis)
                           for axis in ('x', 'y', 'z')), 'Stale Blueprint ground constraint: ' + key
            near(obj.get_editor_property('movement_lag_speed'), native_defaults.get_editor_property('movement_lag_speed'), 0.001)
            for key in ('minimum_location', 'maximum_location'):
                near_vector(obj.get_editor_property(key), vector(native_defaults.get_editor_property(key)))
            for key in ('desired_socket_offset', 'desired_target_offset'):
                near_vector(obj.get_editor_property(key), (0.0, 0.0, 0.0))
            spring = obj.get_editor_property('spring_arm_component')
            for key in ('socket_offset', 'target_offset'):
                near_vector(spring.get_editor_property(key), (0.0, 0.0, 0.0))
        near_vector(placed[0].get_actor_location(), CENTER)
        near_vector(placed[0].get_editor_property('desired_location'), CENTER)
        near(placed[0].get_actor_rotation().pitch, -30.0)
        near(angular_distance(placed[0].get_actor_rotation().yaw, -90.0), 0.0)
        revision_details = dict(revision_report=str(revision_report_path), preserved_actor_count=len(baseline),
                                long_truck_count=len(truck_rows), truck_mesh=long_mesh.get_path_name(),
                                truck_materials_and_placements_preserved=True,
                                initial_pawn_z_cm=float(placed[0].get_actor_location().z), camera_offsets_zero=True)
    else:
        checkpoint = json.loads((ROOT / 'Saved/GHS_WarehouseCameraCheckpoint.json').read_text())
        baseline = json.loads(Path(checkpoint['backup_root'], 'live_before.json').read_text())
        original_actors = {a.get_actor_label(): a for a in actors if a not in placed}
        assert snapshot(original_actors) == baseline, 'Original warehouse objects or materials changed'
    config = (ROOT / 'Config/DefaultEngine.ini').read_text(encoding='utf-8')
    assert 'GameDefaultMap=' + MAP in config
    return dict(blueprint_pawn=bp_pawn.get_path_name(), blueprint_game_mode=bp_gm.get_path_name(),
                controller_class=gm.get_editor_property('player_controller_class').get_path_name(),
                placed_pawns=[a.get_actor_label() for a in placed], original_actors_preserved=len(baseline),
                **revision_details)


def verify():
    command_line = unreal.SystemLibrary.get_command_line()
    assert '-run=pythonscript' in command_line.lower(), 'Run only in a disposable Python commandlet'
    result = dict(status='running', started_at=datetime.now(timezone.utc).isoformat(),
                  scope='Normal warehouse camera; no files saved', tests=[])
    before = watched_hashes()
    actor = None
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

    def passed(name, details=None):
        result['tests'].append(dict(name=name, status='passed', details=details))

    def invariant():
        near(actor.get_editor_property('desired_location').z, 0.0)
        near(actor.get_actor_location().z, 0.0)
        near_vector(actor.get_editor_property('desired_socket_offset'), (0.0, 0.0, 0.0))
        near_vector(actor.get_editor_property('desired_target_offset'), (0.0, 0.0, 0.0))
        spring = actor.get_editor_property('spring_arm_component')
        near_vector(spring.get_editor_property('socket_offset'), (0.0, 0.0, 0.0))
        near_vector(spring.get_editor_property('target_offset'), (0.0, 0.0, 0.0))
        near(actor.get_editor_property('desired_rotation').roll, 0.0)
        assert actor.get_desired_camera_world_location().z >= 149.9, 'Camera would go below floor clearance'

    try:
        native = unreal.load_class(None, PAWN_CLASS)
        assert native, 'RED: native GHSWarehouseCameraPawn is not implemented/compiled yet'
        plugin = unreal.load_class(None, '/Script/UniversalCameraPlugin.UniversalCamera')
        assert plugin and unreal.MathLibrary.class_is_child_of(native, plugin), 'Pawn must inherit UniversalCamera plugin'
        passed('native_plugin_inheritance')
        levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        assert levels.load_level(MAP)
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        if '-warehousecamerasetuprequired' in command_line.lower():
            passed('normal_scene_blueprints_and_game_mode', setup_check(world))
        actor = actors.spawn_actor_from_class(native, unreal.Vector(0.0, 0.0, 0.0))
        assert actor, 'Temporary verification Pawn failed to spawn'
        actor.set_actor_label('VERIFY_ONLY_WarehouseCamera_DO_NOT_SAVE')
        passed('camera_configuration', defaults(actor))
        actor.reset_overview(True)
        original = pose(actor)
        near_vector(actor.get_editor_property('desired_location'), CENTER)
        near(original['rotation'][0], -30.0)
        near(original['rotation'][1], -90.0)
        near(original['zoom'], 53500.0)
        near_vector(actor.get_editor_property('desired_socket_offset'), (0.0, 0.0, 0.0))
        invariant()
        passed('initial_overview', original)

        actor.orbit_pixels(unreal.Vector2D(100.0, 50.0))
        state = pose(actor)
        near(state['rotation'][1], -72.0)
        near(state['rotation'][0], -37.0)
        near_vector(actor.get_editor_property('desired_location'), CENTER)
        invariant()
        passed('left_drag_yaw_and_inverted_pitch', state)
        actor.orbit_pixels(unreal.Vector2D(0.0, -25.0))
        near(actor.get_editor_property('desired_rotation').pitch, -33.5)
        passed('screen_up_drag_raises_pitch')
        actor.orbit_pixels(unreal.Vector2D(0.0, 100000.0))
        near(actor.get_editor_property('desired_rotation').pitch, -80.0)
        actor.orbit_pixels(unreal.Vector2D(0.0, -100000.0))
        near(actor.get_editor_property('desired_rotation').pitch, -15.0)
        invariant()
        passed('pitch_limits')
        actor.reset_overview(True)
        actor.orbit_pixels(unreal.Vector2D(2500.0, 0.0))
        near(angular_distance(actor.get_editor_property('desired_rotation').yaw, 360.0), 0.0)
        invariant()
        passed('yaw_wrap_full_revolution')

        actor.reset_overview(True)
        actor.zoom_steps(1.0)
        near(actor.get_editor_property('desired_zoom'), 53500.0 * math.exp(-0.12), 0.1)
        actor.zoom_steps(-1.0)
        near(actor.get_editor_property('desired_zoom'), 53500.0, 0.1)
        passed('proportional_reversible_wheel_zoom')
        actor.zoom_steps(10000.0)
        near(actor.get_editor_property('desired_zoom'), 900.0)
        invariant()
        actor.zoom_steps(-10000.0)
        near(actor.get_editor_property('desired_zoom'), 95000.0)
        invariant()
        passed('zoom_limits_large_wheel_input')

        actor.reset_overview(True)
        fov = float(actor.get_camera_component().get_editor_property('field_of_view'))
        per_pixel = 2.0 * 53500.0 * math.tan(math.radians(fov) * 0.5) / 1600.0
        actor.pan_pixels(unreal.Vector2D(10.0, 5.0), 1600)
        pivot = actor.get_editor_property('desired_location')
        near_vector(pivot, (CENTER[0] - 10.0 * per_pixel, CENTER[1] - 10.0 * per_pixel, 0.0), 0.1)
        invariant()
        passed('right_drag_moves_ground_pivot', dict(pivot=vector(pivot), cm_per_pixel=per_pixel))
        actor.reset_overview(True)
        actor.set_desired_rotation(unreal.Rotator(pitch=-30.0, yaw=0.0, roll=0.0), True)
        actor.pan_pixels(unreal.Vector2D(10.0, 5.0), 1600)
        near_vector(actor.get_editor_property('desired_location'),
                    (CENTER[0] + 10.0 * per_pixel, CENTER[1] - 10.0 * per_pixel, 0.0), 0.1)
        invariant()
        passed('ground_pan_follows_camera_yaw')
        actor.reset_overview(True)
        actor.set_desired_rotation(unreal.Rotator(pitch=-60.0, yaw=0.0, roll=0.0), True)
        actor.pan_pixels(unreal.Vector2D(10.0, 5.0), 1600)
        near_vector(actor.get_editor_property('desired_location'),
                    (CENTER[0] + 5.0 * per_pixel / math.sin(math.radians(60.0)),
                     CENTER[1] - 10.0 * per_pixel, 0.0), 0.1)
        invariant()
        passed('ground_pan_compensates_pitch_projection')
        actor.reset_overview(True)
        actor.pan_pixels(unreal.Vector2D(10.0, 5.0), 800)
        near_vector(actor.get_editor_property('desired_location'),
                    (CENTER[0] - 20.0 * per_pixel, CENTER[1] - 20.0 * per_pixel, 0.0), 0.1)
        invariant()
        passed('pan_scales_with_viewport_width')
        actor.reset_overview(True)
        actor.zoom_steps(1.0)
        actor.pan_pixels(unreal.Vector2D(10.0, 5.0), 1600)
        near_vector(actor.get_editor_property('desired_location'),
                    (CENTER[0] - 10.0 * per_pixel * math.exp(-0.12),
                     CENTER[1] - 10.0 * per_pixel * math.exp(-0.12), 0.0), 0.1)
        invariant()
        passed('pan_scales_with_zoom_distance')

        stable = pose(actor)
        actor.pan_pixels(unreal.Vector2D(100.0, 100.0), 0)
        poses_equal(pose(actor), stable)
        # Python's Vector2D binding sanitizes NaN before the C++ function sees
        # it. Non-finite inputs are exercised directly by the native suite.
        passed('zero_size_viewport_leaves_view_unchanged')

        actor.reset_overview(True)
        actor.pan_pixels(unreal.Vector2D(-20000.0 / per_pixel, 0.0), 1600)
        moved_pivot = vector(actor.get_editor_property('desired_location'))
        near_vector(actor.get_editor_property('desired_location'), (CENTER[0] + 20000.0, CENTER[1], 0.0))
        actor.zoom_steps(10000.0)
        near_vector(actor.get_editor_property('desired_location'), moved_pivot)
        invariant()
        passed('zoom_preserves_moved_ground_pivot')
        actor.orbit_pixels(unreal.Vector2D(250.0, 80.0))
        near_vector(actor.get_editor_property('desired_location'), moved_pivot)
        invariant()
        passed('orbit_preserves_moved_ground_pivot')

        actor.reset_overview(True)
        actor.pan_pixels(unreal.Vector2D(1000000.0, -1000000.0), 1600)
        invariant()
        state = pose(actor)
        assert all(math.isfinite(v) for v in state['location'])
        maximum_pan = actor.get_editor_property('maximum_pan')
        assert abs(state['location'][0] - CENTER[0]) <= float(maximum_pan.x) + 0.1, 'Ground pan X exceeded warehouse range'
        assert abs(state['location'][1] - CENTER[1]) <= float(maximum_pan.y) + 0.1, 'Ground pan Y exceeded warehouse range'
        extreme_pivot = state['location']
        actor.zoom_steps(10000.0)
        near_vector(actor.get_editor_property('desired_location'), extreme_pivot)
        invariant()
        actor.orbit_pixels(unreal.Vector2D(1900.0, 100000.0))
        near_vector(actor.get_editor_property('desired_location'), extreme_pivot)
        invariant()
        passed('extreme_pan_zoom_orbit_keep_ground_pivot_and_zero_offsets', pose(actor))

        actor.reset_overview(True)
        actor.orbit_pixels(unreal.Vector2D(120.0, 30.0))
        single = pose(actor)
        actor.reset_overview(True)
        for _ in range(12):
            actor.orbit_pixels(unreal.Vector2D(10.0, 2.5))
        poses_equal(pose(actor), single)
        passed('mouse_delta_independent_of_event_count')
        actor.reset_overview(False)
        poses_equal(pose(actor), original)
        invariant()
        passed('home_reset_restores_overview_targets')
        actor.reset_overview(True)
        near_vector(actor.get_actor_location(), CENTER)
        near(actor.get_actor_rotation().pitch, -30.0)
        near(angular_distance(actor.get_actor_rotation().yaw, -90.0), 0.0)
        near(actor.get_editor_property('spring_arm_component').get_editor_property('target_arm_length'), 53500.0)
        passed('immediate_reset_synchronizes_actual_transform')
        result['status'] = 'success'
    except Exception as exc:
        result['status'] = 'failed'
        result['error'] = str(exc)
        result['traceback'] = traceback.format_exc()
        raise
    finally:
        if actor:
            actors.destroy_actor(actor)
        after = watched_hashes()
        result['files_unchanged'] = before == after
        result['file_hashes_before'] = before
        result['file_hashes_after'] = after
        result['completed_at'] = datetime.now(timezone.utc).isoformat()
        if before != after:
            result['status'] = 'failed'
            result['file_change_error'] = 'Verification must not change map, Camera assets, or configuration'
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
        unreal.log('Warehouse camera verification: ' + result['status'] + '; ' + str(REPORT))
        assert before == after, result.get('file_change_error')
    return result


if __name__ == '__main__':
    verify()
