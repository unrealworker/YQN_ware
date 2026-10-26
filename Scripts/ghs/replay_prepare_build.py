"""Preserve the saved editor session before compiling the replay module."""
import hashlib
import json
import os
import shutil
from pathlib import Path
import unreal

ROOT = Path('D:/UEPro/Test')
OUT = ROOT / 'Saved/OrderReplay'
TARGET = '/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert editor.get_editor_world().get_path_name().split('.')[0] == TARGET
assert not levels.is_in_play_in_editor()
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
location, rotation = editor.get_level_viewport_camera_info()
map_path = ROOT / 'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'
backup = OUT / 'before-replay-build.umap'
if not backup.exists():
    shutil.copy2(map_path, backup)
report = dict(pid=os.getpid(), map=TARGET, map_sha256=hashlib.sha256(map_path.read_bytes()).hexdigest(),
              location=[location.x, location.y, location.z],
              rotation=[rotation.pitch, rotation.yaw, rotation.roll],
              selection=[a.get_actor_label() for a in actors.get_selected_level_actors()],
              actor_count=len(actors.get_all_level_actors()))
(OUT / 'editor_session.json').write_text(json.dumps(report, indent=2), encoding='utf8')
unreal.log('ORDER_REPLAY_BUILD_SESSION_PRESERVED')
unreal.SystemLibrary.quit_editor()
