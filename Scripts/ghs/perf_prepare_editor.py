"""Preserve a clean live editor for the authorized P0/P1 build and benchmark."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import unreal

root = Path(r'D:/UEPro/Test')
assert os.getpid() == 17616, 'Unexpected editor; leave open'
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert not levels.is_in_play_in_editor(), 'PIE active; leave open'
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages(), 'Unsaved map; leave open'
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages(), 'Unsaved assets; leave open'
world = editor.get_editor_world()
assert world.get_path_name().split('.')[0] in {
    '/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory',
    '/Game/Maps/GHS_CAD_NormalWarehouse',
}, 'Unexpected map; leave open'
eye, rot = editor.get_level_viewport_camera_info()
result = dict(pid=os.getpid(), utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    map=world.get_path_name(), actor_count=len(actors.get_all_level_actors()),
    viewport_position=[eye.x,eye.y,eye.z], viewport_rotation=[rot.pitch,rot.yaw,rot.roll],
    selected_actors=[a.get_name() for a in actors.get_selected_level_actors()],
    map_sha256={n:hashlib.sha256((root/'Content/Maps'/n).read_bytes()).hexdigest()
        for n in ['GHS_CAD_NormalWarehouse.umap','GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap']},
    assets_saved=False,dirty_maps=[],dirty_assets=[])
(root/'Saved/PerformanceP0P1/editor_state_latest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
unreal.SystemLibrary.quit_editor()
