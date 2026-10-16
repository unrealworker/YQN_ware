"""Preserve approved scene state before visual height and material refinement."""
import json,shutil,hashlib
from pathlib import Path
from datetime import datetime
import unreal
ROOT=Path(r'D:\UEPro\Test')
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assert editor.get_editor_world().get_path_name().split('.')[0]=='/Game/Maps/GHS_CAD_DigitalTwin'
assert levels.save_current_level()
backup=ROOT/'Saved/Backups'/('GHS_Presentation_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
backup.mkdir(parents=True,exist_ok=True)
paths=['Content/Maps/GHS_CAD_DigitalTwin.umap','SourceAssets/GHS/ue_scene_registry.json','SourceAssets/GHS/lighting_style.json',
       'Saved/GHS_BuildReport.json','Saved/GHS_InstanceMaterials.json','Saved/GHS_LightingApplied.json','Scripts/ghs/uniform_lighting.py']
for relative in paths:
    shutil.copy2(ROOT/relative,backup/Path(relative).name)
shutil.copytree(ROOT/'Content/GHSDigitalTwin/Materials/Instanced',backup/'Materials')
p,r=editor.get_level_viewport_camera_info()
report=dict(success=True,backup=str(backup),viewport=dict(position_cm=[p.x,p.y,p.z],rotation=[r.pitch,r.yaw,r.roll]),
    registry_sha256=hashlib.sha256((ROOT/'SourceAssets/GHS/ue_scene_registry.json').read_bytes()).hexdigest())
(ROOT/'Saved/GHS_PresentationBefore.json').write_text(json.dumps(report,indent=2))
exec(compile((ROOT/'Scripts/ghs/temporary_capture_performance.py').read_text(),'capture_performance.py','exec'),{})
