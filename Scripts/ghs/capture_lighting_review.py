"""Full warehouse and AGV close-up review with saved presentation cameras."""
from pathlib import Path
root=Path(r'D:\UEPro\Test')
source=(root/'Scripts/capture_video_warehouse.py').read_text()
source=source.replace('/Game/Maps/VideoDigitalTwinWarehouse','/Game/Maps/GHS_CAD_DigitalTwin')
source=source.replace("VIEWS = ['Overview', 'Route', 'Racks', 'Alarm', 'Elevator']", "VIEWS = ['Overview', 'AGV_Charger']")
source=source.replace('CAM_Video_','CAM_GHS_').replace('VideoWarehouse','GHS_LightingReview').replace('VIDEO_WAREHOUSE','GHS_LIGHTING')
source=source.replace('== 5','== 2').replace('RESOLUTION = (1920, 1080)','RESOLUTION = (2400, 1350)')
exec(compile(source,str(root/'Scripts/capture_video_warehouse.py'),'exec'),globals())
