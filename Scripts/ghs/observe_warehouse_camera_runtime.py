"""Observe the live Play session without modifying scene assets or game input."""
import json
import time
import traceback
from pathlib import Path
import unreal

ROOT = Path(r'D:\UEPro\Test')
REPORT = ROOT / 'Saved/GHS_WarehouseCameraRuntime.json'
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assert editor.get_editor_world().get_path_name().split('.')[0] == '/Game/Maps/GHS_CAD_NormalWarehouse'
native = unreal.load_class(None, '/Script/Test.GHSWarehouseCameraPawn')
editor.set_level_viewport_camera_info(unreal.Vector(-646.665, 47166.59, 27000.0), unreal.Rotator(pitch=-30.0, yaw=-90.0, roll=0.0))
data = dict(observer_ready=True, map='/Game/Maps/GHS_CAD_NormalWarehouse', samples=[])
last_time = 0.0
last_state = None

def xyz(v): return [round(float(v.x), 3), round(float(v.y), 3), round(float(v.z), 3)]
def rot(r): return [round(float(r.pitch), 3), round(float(r.yaw), 3), round(float(r.roll), 3)]

def observe(dt):
    global last_time, last_state
    now = time.monotonic()
    if now - last_time < 0.25:
        return
    last_time = now
    try:
        world = editor.get_game_world()
        if not world:
            return
        pc = unreal.GameplayStatics.get_player_controller(world, 0)
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0) if pc else None
        if not pawn:
            return
        assert unreal.MathLibrary.class_is_child_of(pawn.get_class(), native), pawn.get_class().get_path_name()
        camera = unreal.GameplayStatics.get_player_camera_manager(world, 0)
        state = dict(pawn=pawn.get_class().get_path_name(), controller=pc.get_class().get_path_name(),
                     game_mode=unreal.GameplayStatics.get_game_mode(world).get_class().get_path_name(),
                     pawn_count=len(unreal.GameplayStatics.get_all_actors_of_class(world, native)),
                     pivot=xyz(pawn.get_actor_location()), desired_rotation=rot(pawn.get_editor_property('desired_rotation')),
                     desired_zoom=float(pawn.get_editor_property('desired_zoom')),
                     desired_pan=xyz(pawn.get_editor_property('desired_socket_offset')),
                     actual_rotation=rot(pawn.get_actor_rotation()), camera_position=xyz(camera.get_camera_location()),
                     camera_rotation=rot(camera.get_camera_rotation()), fov=float(camera.get_fov_angle()),
                     viewport=list(pc.get_viewport_size()), drag_mode=str(pc.get_editor_property('drag_mode')))
        if state != last_state:
            data['samples'].append(dict(elapsed=round(now, 3), **state))
            data['latest'] = state
            data['runtime_seen'] = True
            last_state = state
            REPORT.write_text(json.dumps(data, indent=2), encoding='utf-8')
    except Exception:
        data['error'] = traceback.format_exc()
        REPORT.write_text(json.dumps(data, indent=2), encoding='utf-8')
        unreal.unregister_slate_post_tick_callback(handle)

REPORT.write_text(json.dumps(data, indent=2), encoding='utf-8')
handle = unreal.register_slate_post_tick_callback(observe)
unreal.log('WAREHOUSE_CAMERA_RUNTIME_OBSERVER_READY')
