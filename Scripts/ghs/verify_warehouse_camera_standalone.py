"""Verify and capture the actual game camera in a disposable offscreen game."""
import json
import math
import time
import traceback
from pathlib import Path
import unreal

ROOT = Path(r'D:\UEPro\Test')
REPORT = ROOT / 'Saved/GHS_WarehouseCameraStandalone.json'
IMAGE = ROOT / 'Saved/GHS_WarehouseCameraOverview.png'
TRUCK_IMAGE = ROOT / 'Saved/GHS_LongDockTrucksInScene.png'
started = time.monotonic()
stage = 0
deadline = 0.0
result = dict(success=False, started=started, tests=[], monitored_frames=0,
              max_observed_pawn_z=0.0, max_observed_roll=0.0)
world = None
pc = None
pawn = None
camera = None
selected_pivot = None
image_requested_at = 0.0
SETTLE_SECONDS = 1.5
CENTER = [-646.665, 833.981, 0.0]

def vec(v): return [float(v.x), float(v.y), float(v.z)]
def near(x, y, tolerance=0.1):
    assert math.isfinite(float(x)) and abs(float(x)-float(y)) <= tolerance, (x, y)


def near_vector(actual, expected, tolerance=0.1):
    for a, b in zip(vec(actual), expected):
        near(a, b, tolerance)


def near_angle(actual, expected, tolerance=0.1):
    near((float(actual)-float(expected)+180.0) % 360.0 - 180.0, 0.0, tolerance)


def state():
    rotation = camera.get_camera_rotation()
    actual_rotation = pawn.get_actor_rotation()
    desired_rotation = pawn.get_editor_property('desired_rotation')
    spring = pawn.get_editor_property('spring_arm_component')
    return dict(pawn_location=vec(pawn.get_actor_location()),
                desired_location=vec(pawn.get_editor_property('desired_location')),
                pawn_rotation=[actual_rotation.pitch, actual_rotation.yaw, actual_rotation.roll],
                desired_rotation=[desired_rotation.pitch, desired_rotation.yaw, desired_rotation.roll],
                actual_distance=float(spring.get_editor_property('target_arm_length')),
                desired_distance=float(pawn.get_editor_property('desired_zoom')),
                camera_location=vec(camera.get_camera_location()),
                camera_rotation=[rotation.pitch, rotation.yaw, rotation.roll],
                socket_offset=vec(spring.get_editor_property('socket_offset')),
                target_offset=vec(spring.get_editor_property('target_offset')))


def record(name):
    result['tests'].append(dict(name=name, passed=True, elapsed_seconds=time.monotonic()-started,
                                actual_runtime_state=state()))
    REPORT.write_text(json.dumps(result, indent=2), encoding='utf8')


def monitor_ground_and_roll():
    actual = pawn.get_actor_location()
    desired = pawn.get_editor_property('desired_location')
    actual_roll = pawn.get_actor_rotation().roll
    camera_roll = camera.get_camera_rotation().roll
    near(actual.z, 0.0, 0.001)
    near(desired.z, 0.0, 0.001)
    near_angle(actual_roll, 0.0, 0.01)
    near_angle(camera_roll, 0.0, 0.01)
    spring = pawn.get_editor_property('spring_arm_component')
    for name in ('socket_offset', 'target_offset'):
        near_vector(spring.get_editor_property(name), [0.0, 0.0, 0.0], 0.001)
    result['monitored_frames'] += 1
    result['max_observed_pawn_z'] = max(result['max_observed_pawn_z'], abs(actual.z))
    result['max_observed_roll'] = max(result['max_observed_roll'], abs(actual_roll), abs(camera_roll))


def verify_settled(pivot):
    """Validate real Pawn and PlayerCameraManager transforms after game ticks."""
    near_vector(pawn.get_editor_property('desired_location'), pivot, 0.01)
    near_vector(pawn.get_actor_location(), pivot, 0.5)
    desired = pawn.get_editor_property('desired_rotation')
    actual = pawn.get_actor_rotation()
    near_angle(actual.pitch, desired.pitch, 0.03)
    near_angle(actual.yaw, desired.yaw, 0.03)
    near_angle(actual.roll, 0.0, 0.01)
    spring = pawn.get_editor_property('spring_arm_component')
    distance = float(spring.get_editor_property('target_arm_length'))
    near(distance, pawn.get_editor_property('desired_zoom'), 0.5)

    # Inspect the camera manager, not only the Pawn's desired state. A stale
    # view target, detached camera, or nonzero SpringArm offset fails here.
    position = camera.get_camera_location()
    camera_rotation = camera.get_camera_rotation()
    forward = unreal.MathLibrary.get_forward_vector(camera_rotation)
    delta = [a-b for a, b in zip(vec(pawn.get_actor_location()), vec(position))]
    actual_distance = math.sqrt(sum(v*v for v in delta))
    near(actual_distance, distance, 1.0)
    alignment = sum(a*b for a, b in zip(vec(forward), delta)) / actual_distance
    assert alignment > 0.999999, ('Camera is not looking at the moved Pawn', alignment)
    near_angle(camera_rotation.pitch, actual.pitch, 0.03)
    near_angle(camera_rotation.yaw, actual.yaw, 0.03)
    near_angle(camera_rotation.roll, 0.0, 0.01)
    assert position.z >= 149.9, 'Actual camera fell below ground clearance'


def verify_overview():
    verify_settled(CENTER)
    near(pawn.get_editor_property('desired_zoom'), 53500.0, 0.01)
    near_angle(pawn.get_editor_property('desired_rotation').pitch, -30.0, 0.01)
    near_angle(pawn.get_editor_property('desired_rotation').yaw, -90.0, 0.01)
    expected = [-646.665, 833.981 + 53500.0 * math.cos(math.radians(30)), 26750.0]
    near_vector(camera.get_camera_location(), expected, 1.0)
    near(camera.get_fov_angle(), 56.0, 0.01)

def tick(dt):
    global stage, deadline, world, pc, pawn, camera, selected_pivot, image_requested_at
    now = time.monotonic()
    try:
        assert now-started < 90, 'Standalone camera validation timed out'
        if pawn and camera:
            monitor_ground_and_roll()
        if stage == 0:
            for candidate in unreal.ObjectIterator(unreal.World):
                controller = unreal.GameplayStatics.get_player_controller(candidate, 0)
                if controller:
                    world, pc = candidate, controller
                    break
            if pc is None:
                return
            native = unreal.load_class(None, '/Script/Test.GHSWarehouseCameraPawn')
            pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
            assert unreal.MathLibrary.class_is_child_of(pawn.get_class(), native)
            pawns = unreal.GameplayStatics.get_all_actors_of_class(world, native)
            assert len(pawns) == 1, f'Duplicate cameras: {len(pawns)}'
            assert pc.get_class().get_path_name() == '/Script/Test.GHSWarehousePlayerController'
            camera = unreal.GameplayStatics.get_player_camera_manager(world, 0)
            assert camera, 'PlayerCameraManager missing'
            result.update(map=world.get_path_name(), pawn=pawn.get_class().get_path_name(),
                          controller=pc.get_class().get_path_name(), pawn_count=len(pawns),
                          fov=camera.get_fov_angle(),viewport=list(pc.get_viewport_size()))
            stage = 1
            deadline = now + SETTLE_SECONDS
        elif stage == 1 and now >= deadline:
            verify_overview()
            record('initial_pawn_z_zero_and_actual_overview_camera')
            width, height = pc.get_viewport_size()
            assert width > 0 and height > 0, 'Game viewport has no usable dimensions'
            pawn.pan_pixels(unreal.Vector2D(160.0, -40.0), width)
            selected_pivot = vec(pawn.get_editor_property('desired_location'))
            assert math.dist(selected_pivot, CENTER) > 1000.0, 'Pan did not move the orbit center'
            stage = 2
            deadline = now + SETTLE_SECONDS
        elif stage == 2 and now >= deadline:
            verify_settled(selected_pivot)
            record('actual_pawn_converges_to_panned_xy_pivot_on_ground')
            pawn.orbit_pixels(unreal.Vector2D(240.0, 90.0))
            near_angle(pawn.get_editor_property('desired_rotation').pitch, -42.6, 0.01)
            near_angle(pawn.get_editor_property('desired_rotation').yaw, -46.8, 0.01)
            pawn.zoom_steps(3.0)
            near_vector(pawn.get_editor_property('desired_location'), selected_pivot, 0.001)
            stage = 3
            deadline = now + SETTLE_SECONDS
        elif stage == 3 and now >= deadline:
            verify_settled(selected_pivot)
            near(pawn.get_editor_property('desired_zoom'), 53500.0*math.exp(-0.36), 0.1)
            record('orbit_and_zoom_preserve_moved_pivot_and_camera_aim')
            pawn.reset_overview(False)
            stage = 4
            deadline = now + SETTLE_SECONDS
        elif stage == 4 and now >= deadline:
            verify_overview()
            record('smooth_reset_restores_actual_overview')
            stage = 5
            deadline = now + 8.0
        elif stage == 5 and now >= deadline:
            verify_overview()
            final = state()
            result.update(camera_location=final['camera_location'], camera_rotation=final['camera_rotation'],
                          pawn_location=final['pawn_location'])
            image_requested_at = time.time()
            unreal.SystemLibrary.execute_console_command(world, 'HighResShot 1920x1080 filename="' + IMAGE.as_posix() + '"', pc)
            stage = 6
            deadline = now + 3
        elif stage == 6 and now >= deadline and IMAGE.exists() and IMAGE.stat().st_mtime >= image_requested_at:
            assert IMAGE.stat().st_size > 10000
            record('final_overview_captured_after_runtime_interaction_checks')
            result.update(image=str(IMAGE), image_bytes=IMAGE.stat().st_size)
            pawn.set_desired_location(unreal.Vector(-5000.0, 7000.0, 0.0), True)
            pawn.set_desired_rotation(unreal.Rotator(pitch=-35.0, yaw=-140.0, roll=0.0), True)
            pawn.set_desired_zoom(5000.0, True)
            stage = 7
            deadline = now + 4
        elif stage == 7 and now >= deadline:
            image_requested_at = time.time()
            unreal.SystemLibrary.execute_console_command(world, 'HighResShot 1920x1080 filename="' + TRUCK_IMAGE.as_posix() + '"', pc)
            stage = 8
            deadline = now + 3
        elif stage == 8 and now >= deadline and TRUCK_IMAGE.exists() and TRUCK_IMAGE.stat().st_mtime >= image_requested_at:
            assert TRUCK_IMAGE.stat().st_size > 10000
            result.update(success=True, truck_image=str(TRUCK_IMAGE))
            REPORT.write_text(json.dumps(result,indent=2),encoding='utf8')
            unreal.unregister_slate_post_tick_callback(handle)
            unreal.SystemLibrary.quit_game(world,pc,unreal.QuitPreference.QUIT,False)
    except Exception:
        result['failed_stage'] = stage
        result['error']=traceback.format_exc()
        REPORT.write_text(json.dumps(result,indent=2),encoding='utf8')
        unreal.unregister_slate_post_tick_callback(handle)
        if world and pc:
            unreal.SystemLibrary.quit_game(world,pc,unreal.QuitPreference.QUIT,False)

handle=unreal.register_slate_post_tick_callback(tick)
REPORT.write_text(json.dumps(result,indent=2),encoding='utf8')
unreal.log('WAREHOUSE_CAMERA_STANDALONE_VERIFIER_READY')
