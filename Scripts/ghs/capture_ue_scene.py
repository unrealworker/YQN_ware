"""Use the verified editor capture queue with GHS-specific cameras and paths."""
from pathlib import Path
capture_source=(Path(r'D:\UEPro\Test')/'Scripts/capture_video_warehouse.py').read_text(encoding='utf-8')
capture_source=capture_source.replace('/Game/Maps/VideoDigitalTwinWarehouse','/Game/Maps/GHS_CAD_DigitalTwin')
capture_source=capture_source.replace("VIEWS = ['Overview', 'Route', 'Racks', 'Alarm', 'Elevator']", "VIEWS = ['Overview', 'CADPlan', 'RackAisles', 'FloorStorage', 'Charging', 'AGV_Charger']")
capture_source=capture_source.replace('CAM_Video_','CAM_GHS_').replace('VideoWarehouse','GHS').replace('VIDEO_WAREHOUSE','GHS')
capture_source=capture_source.replace('== 5','== 6').replace('five 1920x1080','six 1920x1080')
capture_source=capture_source.replace('RESOLUTION = (1920, 1080)','RESOLUTION = (3840, 2160)').replace('1920x1080','3840x2160')
exec(compile(capture_source,'ghs_capture_queue.py','exec'),globals())
