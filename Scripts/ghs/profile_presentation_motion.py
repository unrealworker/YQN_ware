"""Opt-in live 8-second, 25-metre camera pan; queued by the live dispatcher.

Uses the LightingBefore viewpoint and preserves the caller's starting camera.
No UI resizing, asset changes, saves, screenshot capture, or Before/After writes.
"""
from datetime import datetime, timezone
import importlib
import json
from pathlib import Path
import sys
import traceback

ROOT = Path(r'D:\UEPro\Test')
STATUS = ROOT / 'Saved/GHS_PresentationMotionStatus.json'
REPORT = ROOT / 'Saved/GHS_PresentationMotionReport.json'


def run():
    import unreal
    script_dir = str(ROOT / 'Scripts/ghs')
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    import profile_lighting
    profiler = importlib.reload(profile_lighting)
    assert profiler._active is None, 'An existing GPU profile is still active'
    # A second wrapper may own another module namespace; its persisted status
    # provides an additional guard against overlapping profiling/screenshots.
    status_files = list((ROOT / 'Saved').glob('GHS_*ProfileStatus.json'))
    status_files += list((ROOT / 'Saved').glob('GHS_*CaptureReport.json'))
    if STATUS.exists():
        status_files.append(STATUS)
    busy = {'warmup', 'capturing', 'running', 'pending', 'queued',
            'draining_gpu_queries', 'writing_csv'}
    for path in status_files:
        record = json.loads(path.read_text(encoding='utf-8-sig'))
        assert record.get('status') not in busy, ('Another capture is active', str(path), record.get('status'))

    original_view = profiler._view(unreal)
    reference_path = ROOT / 'Saved/GHS_LightingBefore.json'
    reference = json.loads(reference_path.read_text(encoding='utf-8-sig'))
    view = reference.get('viewport', reference.get('camera', reference))
    position = view['position_cm']
    rotation = view.get('rotation_deg', view.get('rotation'))
    if isinstance(rotation, dict):
        rotation = [rotation[name] for name in ('pitch', 'yaw', 'roll')]
    assert len(position) == 3 and len(rotation) == 3
    editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    original_world = editor.get_editor_world()
    try:
        editor.set_level_viewport_camera_info(
            unreal.Vector(*position), unreal.Rotator(pitch=rotation[0], yaw=rotation[1], roll=rotation[2]))
        return profiler.start(
            label='Motion', planned_movement={'duration_seconds': 8.0, 'distance_cm': 2500.0},
            warmup_frames=120, warmup_seconds=3.0, timeout_seconds=180,
            report_path=REPORT, status_path=STATUS, csv_prefix='GHS_Presentation_',
            restore_camera=original_view)
    except Exception:
        # start() also restores on setup failure, but this covers errors that
        # occur before it can establish its cleanup callback.
        current = profiler._view(unreal)
        if current['viewport_config_key'] == original_view['viewport_config_key'] and editor.get_editor_world() == original_world:
            p, r = original_view['position_cm'], original_view['rotation_deg']
            editor.set_level_viewport_camera_info(
                unreal.Vector(*p), unreal.Rotator(pitch=r[0], yaw=r[1], roll=r[2]))
        raise


if __name__ == '__main__':
    try:
        run()
    except Exception:
        STATUS.write_text(json.dumps(dict(status='failed', success=False,
            error=traceback.format_exc(), updated_utc=datetime.now(timezone.utc).isoformat()), indent=2), encoding='utf-8')
        raise
