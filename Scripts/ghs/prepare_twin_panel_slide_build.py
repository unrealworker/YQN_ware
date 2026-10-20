"""Record the user's clean editor state and normally quit only PID 22280.

No map or asset is saved. Any changed PID, map, PIE, or dirty state leaves
the editor running. Selection and view are recorded for the matching reopen.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import unreal

ROOT = Path(r'D:/UEPro/Test')
EXPECTED_PID = 22280
EXPECTED_MAP = '/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
assert os.getpid() == EXPECTED_PID, 'Unexpected editor process; keep it open'
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert not levels.is_in_play_in_editor(), 'PIE state changed; keep editor open'
dirty_maps = [p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()]
dirty_assets = [p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()]
assert not dirty_maps and not dirty_assets, 'Unsaved work; keep editor open'
world = editor.get_editor_world()
assert world and world.get_path_name().split('.')[0] == EXPECTED_MAP, 'Unexpected editor map'
eye, rot = editor.get_level_viewport_camera_info()
selected = [dict(name=a.get_name(), path=a.get_path_name(), label=a.get_actor_label())
            for a in actors.get_selected_level_actors()]
hashes = {name: hashlib.sha256((ROOT / 'Content/Maps' / name).read_bytes()).hexdigest()
          for name in ('GHS_CAD_NormalWarehouse.umap', 'GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap')}
result = dict(success=True, utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
              pid=os.getpid(), map=world.get_path_name(), in_pie=False,
              assets_saved=False, dirty_maps=dirty_maps, dirty_assets=dirty_assets,
              map_sha256=hashes, viewport_position=[eye.x, eye.y, eye.z],
              viewport_rotation=[rot.pitch, rot.yaw, rot.roll],
              selected_actors=selected, actor_count=len(actors.get_all_level_actors()))
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages(), 'Map became dirty; keep editor open'
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages(), 'Asset became dirty; keep editor open'
(ROOT / 'Saved/PanelSlide_EditorState.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
unreal.log('GHS_PANEL_SLIDE_EDITOR_STATE_RECORDED_NORMAL_QUIT')
unreal.SystemLibrary.quit_editor()
