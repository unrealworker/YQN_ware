"""Fixed cameras for before/after visual comparisons of the storage refinement."""
from pathlib import Path
root=Path(r'D:\UEPro\Test')
phase=(root/'Saved/GHS_PresentationCapturePhase.txt').read_text().strip()
assert phase in ['Before','After']
source=(root/'Scripts/capture_video_warehouse.py').read_text()
source=source.replace('/Game/Maps/VideoDigitalTwinWarehouse','/Game/Maps/GHS_CAD_DigitalTwin')
source=source.replace("VIEWS = ['Overview', 'Route', 'Racks', 'Alarm', 'Elevator']", "VIEWS = ['Overview', 'FloorStorage', 'RackAisles', 'AGV_Charger']")
source=source.replace('CAM_Video_','CAM_GHS_').replace('VideoWarehouse','GHS_Presentation'+phase).replace('VIDEO_WAREHOUSE','GHS_PRESENTATION')
source=source.replace('== 5','== 4').replace('RESOLUTION = (1920, 1080)','RESOLUTION = (2400, 1350)')
exec(compile(source,str(root/'Scripts/capture_video_warehouse.py'),'exec'),globals())
