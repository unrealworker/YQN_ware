"""Capture real UE Editor images after importing and verifying the saved AGV.

Execute in the full editor, not UnrealEditor-Cmd: Slate ticks drive the captures.
The saved CAM_AGV_Reference transform and field of view are never changed.
"""
import json
import time
import traceback
from pathlib import Path

import unreal


ROOT = Path(r"D:\UEPro\Test")
MAP = "/Game/Maps/LogisticsWarehouse"
REPORT = ROOT / "Saved" / "AGV_CaptureReport.json"
WARMUP_SECONDS = 15.0
CAPTURE_DELAY_SECONDS = 3.0
TIMEOUT_SECONDS = 360.0
RESOLUTION = (1600, 1200)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)


def camera_state(camera):
    position = camera.get_actor_location()
    rotation = camera.get_actor_rotation()
    component = camera.get_component_by_class(unreal.CameraComponent)
    assert component, "Expected a camera component"
    return {
        "position_cm": [float(position.x), float(position.y), float(position.z)],
        "rotation_degrees": [float(rotation.pitch), float(rotation.yaw), float(rotation.roll)],
        "fov": float(component.get_editor_property("field_of_view")),
    }


def write_report():
    REPORT.write_text(json.dumps(agv_report, indent=2), encoding="utf-8")


def restore_editor():
    global agv_context_camera
    if agv_context_camera is not None:
        assert actors.destroy_actor(agv_context_camera), "Could not remove the temporary capture camera"
        agv_context_camera = None
    if agv_actor is not None:
        # The editor viewport's usual 90-degree FOV needs a closer viewpoint.
        position = unreal.Vector(-2820, 4790, 130)
        rotation = unreal.MathLibrary.find_look_at_rotation(position, unreal.Vector(-2700, 4700, 60))
        editor.set_level_viewport_camera_info(position, rotation)
        actors.set_selected_level_actors([agv_actor])
        assert levels.save_current_level(), "Could not save the final editor view"


def finish_capture(error=None):
    global agv_done
    agv_done = True
    if agv_handle is not None:
        unreal.unregister_slate_post_tick_callback(agv_handle)
    try:
        restore_editor()
        if agv_camera is not None:
            assert camera_state(agv_camera) == agv_original_camera, "The saved AGV camera changed during capture"
    except Exception:
        cleanup_error = traceback.format_exc()
        error = (error + "\nCleanup error:\n" + cleanup_error) if error else cleanup_error
    agv_report["success"] = error is None
    agv_report["status"] = "failed" if error else "complete"
    agv_report["screenshots_complete"] = error is None and len(agv_report["screenshots"]) == 2
    agv_report["elapsed_seconds"] = round(time.monotonic() - agv_started, 2)
    agv_report["temporary_camera_removed"] = agv_context_camera is None
    if error:
        agv_report["error"] = error
        unreal.log_error("AGV_CAPTURE_FAILED " + error)
    else:
        agv_report["reference_camera_unchanged"] = True
        unreal.log("AGV_CAPTURE_COMPLETE")
    write_report()


def agv_tick(delta):
    global agv_busy, agv_index, agv_task, agv_pending, agv_task_finished_at
    if agv_busy or agv_done:
        return
    agv_busy = True
    try:
        now = time.monotonic()
        assert now - agv_started < TIMEOUT_SECONDS, "Timed out waiting for UE screenshot capture"
        if now - agv_started < WARMUP_SECONDS:
            return
        if agv_task is not None:
            if not agv_task.is_task_done():
                return
            if agv_task_finished_at is None:
                agv_task_finished_at = now
            path = agv_pending["path"]
            # The render task can finish immediately before the PNG is flushed.
            valid = path.is_file() and path.stat().st_size > 0
            if valid and agv_pending["previous_mtime_ns"] is not None:
                valid = path.stat().st_mtime_ns != agv_pending["previous_mtime_ns"]
            if not valid and now - agv_task_finished_at < 10.0:
                return
            assert valid, "Screenshot was not written or refreshed: " + str(path)
            agv_report["screenshots"].append({
                "view": agv_pending["view"],
                "path": str(path),
                "bytes": path.stat().st_size,
                "resolution": list(RESOLUTION),
                "camera": agv_pending["camera_state"],
            })
            agv_task = None
            agv_pending = None
            agv_task_finished_at = None
            write_report()
        if agv_index >= len(agv_views):
            finish_capture()
            return
        view, camera, path = agv_views[agv_index]
        agv_index += 1
        agv_pending = {
            "view": view,
            "path": path,
            "previous_mtime_ns": path.stat().st_mtime_ns if path.is_file() else None,
            "camera_state": camera_state(camera),
        }
        agv_report["status"] = "capturing_" + view.lower()
        write_report()
        agv_task = unreal.AutomationLibrary.take_high_res_screenshot(
            RESOLUTION[0], RESOLUTION[1], str(path), camera=camera, delay=CAPTURE_DELAY_SECONDS
        )
        assert agv_task is not None, "UE did not create a screenshot task"
    except Exception:
        finish_capture(traceback.format_exc())
    finally:
        agv_busy = False


REPORT.parent.mkdir(parents=True, exist_ok=True)
agv_actor = None
agv_camera = None
agv_context_camera = None
agv_original_camera = None
agv_views = []
agv_index = 0
agv_task = None
agv_pending = None
agv_task_finished_at = None
agv_busy = False
agv_done = False
agv_handle = None
agv_started = time.monotonic()
agv_report = {
    "success": False,
    "status": "initializing",
    "map": MAP,
    "screenshots_complete": False,
    "screenshots": [],
    "warmup_seconds": WARMUP_SECONDS,
    "capture_delay_seconds": CAPTURE_DELAY_SECONDS,
}
write_report()

try:
    assert levels.load_level(MAP), "Could not load the saved warehouse map"
    existing = actors.get_all_level_actors()
    agv_matches = [actor for actor in existing if actor.get_actor_label() == "AGV_01_Reference"]
    camera_matches = [actor for actor in existing if actor.get_actor_label() == "CAM_AGV_Reference"]
    assert len(agv_matches) == 1, "Expected one AGV actor"
    assert len(camera_matches) == 1, "Expected one saved AGV inspection camera"
    agv_actor = agv_matches[0]
    agv_camera = camera_matches[0]
    agv_original_camera = camera_state(agv_camera)
    agv_report["reference_camera"] = agv_original_camera

    # A closer context camera keeps the AGV legible while including the loading
    # apron, nearby vehicles and warehouse frontage behind it.
    context_position = unreal.Vector(-3300, 5800, 450)
    context_rotation = unreal.MathLibrary.find_look_at_rotation(context_position, unreal.Vector(-2700, 3800, 150))
    agv_context_camera = actors.spawn_actor_from_class(unreal.CameraActor, context_position, context_rotation)
    assert agv_context_camera, "Could not create temporary context camera"
    agv_context_camera.set_actor_label("AGV_TemporaryCapture_Context")
    context_component = agv_context_camera.get_component_by_class(unreal.CameraComponent)
    assert context_component
    context_component.set_field_of_view(55.0)
    context_component.set_editor_property("constrain_aspect_ratio", False)
    agv_views = [
        ("Closeup", agv_camera, ROOT / "Saved" / "AGV_UE_Closeup.png"),
        ("Context", agv_context_camera, ROOT / "Saved" / "AGV_UE_Context.png"),
    ]
    actors.set_selected_level_actors([])
    editor.set_level_viewport_camera_info(agv_camera.get_actor_location(), agv_camera.get_actor_rotation())
    # Start warmup after map loading and camera setup, not before them.
    agv_started = time.monotonic()
    agv_report["status"] = "waiting_for_shaders"
    write_report()
    agv_handle = unreal.register_slate_post_tick_callback(agv_tick)
    unreal.log("AGV_CAPTURE_QUEUED: 15-second warmup, then Closeup and Context")
except Exception:
    finish_capture(traceback.format_exc())
    raise
