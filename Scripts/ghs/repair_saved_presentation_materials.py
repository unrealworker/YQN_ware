"""Repair saved GHS material parameter duplication in an isolated editor."""
from pathlib import Path
import runpy
import unreal
root=Path(r'D:\UEPro\Test')
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assert levels.load_level('/Game/Maps/GHS_CAD_DigitalTwin')
runpy.run_path(str(root/'Scripts/ghs/inspect_presentation_materials.py'),run_name='__main__')
runpy.run_path(str(root/'Scripts/ghs/refine_presentation_materials.py'),run_name='__main__')
unreal.log('GHS_SAVED_MATERIAL_REPAIR_COMPLETE')
