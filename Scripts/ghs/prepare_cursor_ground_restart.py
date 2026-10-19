"""Preserve current editor packages before loading the final cursor camera build."""
import hashlib
import json
import shutil
from pathlib import Path
import unreal

root=Path(r'D:/UEPro/Test')
backup=root/'Saved/Backups/GHS_CursorGround_20261019'
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assert not levels.is_in_play_in_editor(), 'Stop Play before restart'
dirty=list(unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())+list(unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
assert all(p.get_name().startswith('/Game/') for p in dirty)
for package in dirty:
    for suffix in ('.umap','.uasset'):
        src=root/'Content'/(package.get_name()[6:]+suffix)
        if src.exists():
            dest=backup/'Content'/(package.get_name()[6:]+suffix)
            dest.parent.mkdir(parents=True,exist_ok=True)
            if not dest.exists():shutil.copy2(src,dest)
if dirty: assert unreal.EditorLoadingAndSavingUtils.save_packages(dirty,True)
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
hashes={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'Content').rglob('*') if p.is_file()}
(backup/'content_before_final_build.json').write_text(json.dumps(hashes,indent=2),encoding='utf8')
(root/'Saved/GHS_CursorGround_Restart.json').write_text(json.dumps(dict(success=True,saved_packages=[p.get_name() for p in dirty]),indent=2),encoding='utf8')
unreal.SystemLibrary.quit_editor()
