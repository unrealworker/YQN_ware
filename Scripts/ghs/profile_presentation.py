"""Same stable benchmark camera as lighting comparison, separate report names."""
from pathlib import Path
root=Path(r'D:\UEPro\Test')
source=(root/'Scripts/ghs/profile_lighting.py').read_text()
source=source.replace('GHS_LightingProfile','GHS_PresentationProfile').replace('GHS_LightingPerformance','GHS_PresentationPerformance').replace("'GHS_Lighting_'", "'GHS_Presentation_'")
exec(compile(source,str(root/'Scripts/ghs/profile_lighting.py'),'exec'),globals())
