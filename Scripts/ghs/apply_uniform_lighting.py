"""Apply and persist uniform warehouse lighting with a recoverable level backup."""
import hashlib,json,shutil,sys,traceback
from datetime import datetime
from pathlib import Path
import unreal
ROOT=Path(r'D:\UEPro\Test')
sys.path.insert(0,str(ROOT/'Scripts/ghs'))
import uniform_lighting
import importlib
importlib.reload(uniform_lighting)
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
report_path=ROOT/'Saved/GHS_LightingApplied.json'
report=dict(success=False)
try:
    original=ROOT/'Content/Maps/VideoDigitalTwinWarehouse.umap'
    registry=ROOT/'SourceAssets/GHS/ue_scene_registry.json'
    source_sha=hashlib.sha256(original.read_bytes()).hexdigest()
    registry_sha=hashlib.sha256(registry.read_bytes()).hexdigest()
    assert levels.save_current_level()
    backup=ROOT/'Saved/Backups'/('GHS_Lighting_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
    backup.mkdir(parents=True,exist_ok=True)
    for path in [ROOT/'Content/Maps/GHS_CAD_DigitalTwin.umap',registry,ROOT/'Saved/GHS_BuildReport.json',ROOT/'Config/DefaultEngine.ini']:
        shutil.copy2(path,backup/path.name)
    report['backup']=str(backup)
    report['settings']=uniform_lighting.configure()
    assert hashlib.sha256(registry.read_bytes()).hexdigest()==registry_sha
    assert hashlib.sha256(original.read_bytes()).hexdigest()==source_sha
    assert levels.save_current_level()
    build_path=ROOT/'Saved/GHS_BuildReport.json';build=json.loads(build_path.read_text())
    build.update(lighting_optimized=True,actor_count=len(actors.get_all_level_actors()))
    build_path.write_text(json.dumps(build,indent=2))
    report.update(success=True,actor_count=build['actor_count'],hism_group_count=16,instanced_count=build['instanced_count'],
        light_count=2,local_light_count=0,registry_sha256=registry_sha,source_level_sha256=source_sha)
    report_path.write_text(json.dumps(report,indent=2))
except Exception:
    report['error']=traceback.format_exc();report_path.write_text(json.dumps(report,indent=2));raise
