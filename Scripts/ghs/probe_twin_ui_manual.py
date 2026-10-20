"""Read the current editor/PIE state for genuine mouse QA; optionally capture UI.

Reads only the explicitly queued ManualAction JSON. Never selects devices,
changes the camera, saves packages, or changes gameplay inputs.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import unreal

ROOT = Path(r'D:/UEPro/Test')
ACTION = json.loads((ROOT / 'Saved/GHS_TwinUI_ManualAction.json').read_text(encoding='utf-8-sig'))
REPORT = ROOT / 'Saved/GHS_TwinUI_ManualQA.json'
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
label = ACTION['label']
assert label and all(c.isalnum() or c in '_-' for c in label)
in_pie = bool(levels.is_in_play_in_editor())
sample = dict(label=label, utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
              pid=os.getpid(), editor_map=editor.get_editor_world().get_path_name() if not in_pie else '/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory',
              in_pie=in_pie,
              dirty_maps=[p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()],
              dirty_assets=[p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()],
              editor_actor_count=len(actors.get_all_level_actors()) if not in_pie else None)
if not in_pie:
    eye, rot = editor.get_level_viewport_camera_info()
    sample['editor_viewport'] = dict(position=[eye.x, eye.y, eye.z], rotation=[rot.pitch, rot.yaw, rot.roll])
world = next((w for w in unreal.ObjectIterator(unreal.World) if 'UEDPIE_' in w.get_path_name() and unreal.GameplayStatics.get_player_controller(w, 0)), None)
pc = unreal.GameplayStatics.get_player_controller(world, 0) if world else None
if pc:
    pawn = pc.get_controlled_pawn()
    widget = pc.get_editor_property('twin_hud_widget')
    sample['game_world'] = world.get_path_name()
    sample['viewport_pixels'] = list(pc.get_viewport_size())
    sample['drag_mode'] = str(pc.get_editor_property('drag_mode'))
    if pawn:
        pos, rot = pawn.get_actor_location(), pawn.get_actor_rotation()
        desired_pos = pawn.get_editor_property('desired_location')
        desired_rot = pawn.get_editor_property('desired_rotation')
        sample['camera'] = dict(position=[pos.x, pos.y, pos.z], rotation=[rot.pitch, rot.yaw, rot.roll],
            desired_position=[desired_pos.x, desired_pos.y, desired_pos.z],
            desired_rotation=[desired_rot.pitch, desired_rot.yaw, desired_rot.roll],
            desired_zoom=float(pawn.get_editor_property('desired_zoom')))
    if widget:
        data = json.loads(widget.get_snapshot())
        raw = widget.get_editor_property('last_browser_report')
        sample['browser'] = json.loads(raw) if raw else {}
        sample['selected_id'] = widget.get_editor_property('selected_id')
        sample['selection'] = data.get('selection')
        sample['equipment_count'] = len(data.get('equipment', []))
        sample['visible_equipment_count'] = sum(bool(d.get('visible')) for d in data.get('equipment', []))
        sample['panel_position'] = [widget.get_panel_position().x, widget.get_panel_position().y]
        sample['panel_size'] = [widget.get_panel_size().x, widget.get_panel_size().y]
        if ACTION.get('capture'):
            path = ROOT / f'Saved/GHS_TwinUI_Manual_{label}.png'
            sample['capture_requested'] = str(path)
            unreal.SystemLibrary.execute_console_command(world, f'Shot showui filename="{path.as_posix()}" -nosuffix', pc)
sample['map_sha256'] = hashlib.sha256((ROOT / 'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap').read_bytes()).hexdigest()
sample['original_map_sha256'] = hashlib.sha256((ROOT / 'Content/Maps/GHS_CAD_NormalWarehouse.umap').read_bytes()).hexdigest()
report = json.loads(REPORT.read_text(encoding='utf-8')) if REPORT.is_file() else dict(success=False, status='manual_qa_in_progress', samples=[], checks=[], assets_saved=False)
report['samples'].append(sample)
report['latest'] = sample
REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
unreal.log('GHS_TWIN_UI_MANUAL_SAMPLE ' + label)
