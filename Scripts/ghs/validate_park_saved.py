"""Load the saved map in a fresh commandlet and run preservation validation."""
import json
import runpy
from pathlib import Path
import unreal

ROOT=Path('D:/UEPro/Test')
assert '-run=pythonscript' in unreal.SystemLibrary.get_command_line().lower()
assert unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).load_level('/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory')
validator=runpy.run_path(str(ROOT/'Scripts/ghs/validate_park_expansion.py'))
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
rows=[validator['snapshot'](actor,unreal) for actor in actors]
(ROOT/'Saved/ParkExpansion/reloaded_actors.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
validator['main']()
source=ROOT/'Saved/ParkExpansion/validation.json'
report=json.loads(source.read_text(encoding='utf-8'))
report['validation_scope']='fresh commandlet reload of saved map'
(ROOT/'Saved/ParkExpansion/saved_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
unreal.log('GHS_PARK_SAVED_RELOAD_VALIDATION_COMPLETE')
