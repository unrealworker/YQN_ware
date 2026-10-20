"""Preserve the current Zcool editor session before the native Twin UI build.

Only the explicitly identified editor process may run this script. Save only
its current Zcool map after validating the pre-existing disk backup; request a
normal editor exit only after all preservation checks pass.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import traceback

import unreal

ROOT = Path(r'D:/UEPro/Test')
BACKUP = ROOT / 'Saved/Backups/TwinUI-20261020/20261020-165858'
REPORT = ROOT / 'Saved/GHS_TwinUI_PrepareBuild.json'
TARGET_MAP = '/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
EXPECTED_PID = 55560
result = dict(success=False, status='started', expected_pid=EXPECTED_PID,
              actual_pid=os.getpid(), target_map=TARGET_MAP, backup_dir=str(BACKUP),
              started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
              normal_exit_requested=False)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_report():
    text = json.dumps(result, ensure_ascii=False, indent=2)
    REPORT.write_text(text, encoding='utf-8')
    (BACKUP / 'prepare_build_report.json').write_text(text, encoding='utf-8')


def scene_state(editor, levels, actors):
    eye, rotation = editor.get_level_viewport_camera_info()
    level_actors = actors.get_all_level_actors()
    return dict(
        editor_world=editor.get_editor_world().get_path_name(),
        in_pie=bool(levels.is_in_play_in_editor()),
        dirty_maps=[p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()],
        dirty_assets=[p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()],
        actor_count=len(level_actors),
        actor_paths=sorted(a.get_path_name() for a in level_actors),
        viewport_position=[eye.x, eye.y, eye.z],
        viewport_rotation=[rotation.pitch, rotation.yaw, rotation.roll])


try:
    assert os.getpid() == EXPECTED_PID, 'Refusing to operate on a different editor process'
    manifest = json.loads((BACKUP / 'preflight.json').read_text(encoding='utf-8-sig'))
    assert manifest['expected_pid'] == EXPECTED_PID
    map_file = Path(manifest['map_file'])
    original_file = Path(manifest['original_map_file'])
    assert sha(manifest['backup_file']) == manifest['backup_sha256'] == manifest['map_sha256_before']
    assert sha(map_file) == manifest['map_sha256_before'], 'Disk target changed since backup'
    assert sha(original_file) == manifest['original_map_sha256'], 'Original map changed since backup'

    editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    before = scene_state(editor, levels, actors)
    result.update(before=before, map_sha256_before=sha(map_file),
                  original_map_sha256_before=sha(original_file),
                  backup_file=manifest['backup_file'], backup_sha256=sha(manifest['backup_file']))
    write_report()
    assert before['editor_world'].split('.')[0] == TARGET_MAP, 'Current map is not the authorized Zcool target'
    assert not before['in_pie'], 'PIE must already be stopped'
    assert not before['dirty_assets'], 'Unsaved content assets require preservation'
    assert before['dirty_maps'] == [TARGET_MAP], 'Expected only the authorized target map to be dirty'
    assert before['actor_count'] > 0, 'Unexpected empty scene'

    result['status'] = 'saving_target_map'
    write_report()
    assert levels.save_current_level(), 'Current target-map save failed'
    after = scene_state(editor, levels, actors)
    result.update(after=after, map_sha256_after=sha(map_file),
                  original_map_sha256_after=sha(original_file), save_current_level_returned=True)
    write_report()
    assert after['editor_world'] == before['editor_world'], 'Editor map changed during save'
    assert not after['in_pie'] and not after['dirty_maps'] and not after['dirty_assets'], 'Save left dirty packages or PIE'
    assert after['actor_paths'] == before['actor_paths'], 'Saving changed level actor identities'
    assert after['viewport_position'] == before['viewport_position'], 'Saving changed viewport position'
    assert after['viewport_rotation'] == before['viewport_rotation'], 'Saving changed viewport rotation'
    assert result['original_map_sha256_after'] == manifest['original_map_sha256'], 'Original map was altered'
    assert sha(manifest['backup_file']) == manifest['backup_sha256'], 'Original disk backup was altered'

    result.update(success=True, status='preserved_normal_exit_requested', normal_exit_requested=True,
                  finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    write_report()
    unreal.log('GHS_TWIN_UI_PREPARE_BUILD_VERIFIED ' + str(REPORT))
    unreal.SystemLibrary.quit_editor()
except Exception:
    result.update(success=False, status='failed_editor_left_open', error=traceback.format_exc(),
                  normal_exit_requested=False)
    write_report()
    unreal.log_error('GHS_TWIN_UI_PREPARE_BUILD_FAILED ' + result['error'])
    raise
