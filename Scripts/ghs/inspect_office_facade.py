"""Capture the untouched scene once before adding the office glazing."""
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import unreal

ROOT=Path('D:/UEPro/Test')
OUT=ROOT/'Saved/OfficeFacade'
BEFORE=OUT/'Before'
MAP='/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert not levels.is_in_play_in_editor()
assert editor.get_editor_world().get_path_name().split('.')[0]==MAP
fn=runpy.run_path(str(ROOT/'Scripts/ghs/validate_park_expansion.py'))['snapshot']
rows=sorted([fn(a,unreal) for a in actors.get_all_level_actors()],key=lambda r:r['label'])
assert not any(r['label']=='GHS_OfficeGlassFacade' for r in rows)
BEFORE.mkdir(parents=True,exist_ok=True)
source=ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'
result=dict(map=MAP,actors=rows,actor_count=len(rows),
    dirty_maps=[p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()],
    dirty_assets=[p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()],
    map_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
target=BEFORE/'scene_state.json'
assert not target.exists(),'Do not replace the pre-change baseline'
target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
shutil.copy2(source,BEFORE/source.name)
unreal.log('GHS_OFFICE_FACADE_BASELINE_CAPTURED')
