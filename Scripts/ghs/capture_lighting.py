"""Matched before/after screenshots from the user's warehouse overview."""
from pathlib import Path
root=Path(r'D:\UEPro\Test')
source=(root/'Scripts/ghs/capture_wall_detail.py').read_text()
source=source.replace('GHS_WallCapturePhase.txt','GHS_LightingCapturePhase.txt')
source=source.replace('GHS_WallEdgeLiveBefore.json','GHS_LightingBefore.json')
source=source.replace('GHS_WallJoints_','GHS_Lighting_')
source=source.replace('GHS_WallCapture','GHS_LightingCapture')
source=source.replace('2400,1600','2400,1350')
source=source.replace("'Wall screenshot timed out'","'Lighting screenshot timed out'")
exec(compile(source,str(root/'Scripts/ghs/capture_wall_detail.py'),'exec'),globals())
