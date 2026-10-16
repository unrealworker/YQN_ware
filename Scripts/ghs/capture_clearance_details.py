"""Refresh the two affected UE views after the saved column-clearance repair."""
from pathlib import Path
capture_source=(Path(r'D:\UEPro\Test')/'Scripts/capture_video_warehouse.py').read_text(encoding='utf-8')
capture_source=capture_source.replace('/Game/Maps/VideoDigitalTwinWarehouse','/Game/Maps/GHS_CAD_DigitalTwin')
capture_source=capture_source.replace("VIEWS = ['Overview', 'Route', 'Racks', 'Alarm', 'Elevator']", "VIEWS = ['FloorStorage', 'RackAisles']")
capture_source=capture_source.replace('CAM_Video_','CAM_GHS_').replace('VideoWarehouse','GHS_Clearance').replace('VIDEO_WAREHOUSE','GHS_CLEARANCE')
capture_source=capture_source.replace('== 5','== 2').replace('five 1920x1080','two 1920x1080')
capture_source=capture_source.replace('RESOLUTION = (1920, 1080)','RESOLUTION = (3840, 2160)').replace('1920x1080','3840x2160')
capture_source=capture_source.replace('WARMUP_SECONDS = 15.0','WARMUP_SECONDS = 2.0')
capture_source=capture_source.replace('CAPTURE_DELAY_SECONDS = 3.0','CAPTURE_DELAY_SECONDS = 0.2')
exec(compile(capture_source,'ghs_clearance_capture_queue.py','exec'),globals())
