"""Reapply the approved presentation pass after rebuilding the original CAD scene."""
from pathlib import Path
import runpy,json,sys
import unreal
root=Path(r'D:\UEPro\Test')
sys.path.insert(0,str(root/'Scripts/ghs'))
from cad_rack_revision_state import refuse_legacy_rebuild
refuse_legacy_rebuild('rebuild_presentation_refinement.py')
for name in ['start_presentation_session','import_presentation_storage','prepare_visual_layout',
             'apply_presentation_layout','refine_presentation_materials']:
    runpy.run_path(str(root/'Scripts/ghs'/(name+'.py')),run_name='__main__')
restore=root/'Saved/GHS_CapturePerformanceRestore.json'
if restore.is_file():
    old=json.loads(restore.read_text())
    unreal.get_default_object(unreal.load_class(None,'/Script/UnrealEd.EditorPerformanceSettings')).set_editor_property(old['property_name'],old['throttle'])
    restore.unlink()
