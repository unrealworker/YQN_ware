"""Keep the editor capture queue rendering while another user app is foreground."""
import json
from pathlib import Path
import unreal
settings=unreal.get_default_object(unreal.load_class(None,'/Script/UnrealEd.EditorPerformanceSettings'))
path=Path(r'D:\UEPro\Test\Saved\GHS_CapturePerformanceRestore.json')
property_name='bThrottleCPUWhenNotForeground'
if not path.is_file():path.write_text(json.dumps(dict(throttle=settings.get_editor_property(property_name),property_name=property_name)))
settings.set_editor_property(property_name,False)
# Deliberately no save_config; finish_session restores the prior in-memory value.
