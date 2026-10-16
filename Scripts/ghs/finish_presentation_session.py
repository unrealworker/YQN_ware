"""Persist the selected appearance and leave a close warehouse view for review."""
from pathlib import Path
import json
import unreal
root=Path(r'D:\UEPro\Test')
previous=json.loads((root/'Saved/GHS_PresentationProfile_Before.json').read_text())['original_console_values']
readback={name:unreal.SystemLibrary.get_console_variable_string_value(name) for name in previous}
assert readback==previous,('Temporary benchmark settings not restored',readback,previous)
(root/'Saved/GHS_PresentationSettingsRestored.json').write_text(json.dumps(dict(success=True,console_values=readback),indent=2))
source=(root/'Scripts/ghs/finish_session.py').read_text()
source=source.replace("=='CAM_GHS_Overview'","=='CAM_GHS_FloorStorage'").replace("viewport='Overview'","viewport='PresentationFloorStorage'")
exec(compile(source,str(root/'Scripts/ghs/finish_session.py'),'exec'),globals())
applied=root/'Saved/GHS_PresentationApplied.json';report=json.loads(applied.read_text())
report['material_style']=json.loads((root/'SourceAssets/GHS/Presentation/material_style.json').read_text())
report['lighting_style']=json.loads((root/'SourceAssets/GHS/lighting_style.json').read_text())
report['assumptions']=json.loads((root/'SourceAssets/GHS/Presentation/visual_layout.json').read_text())['presentation']['assumptions']
applied.write_text(json.dumps(report,indent=2))
