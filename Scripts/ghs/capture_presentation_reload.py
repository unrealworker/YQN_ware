"""Isolated render-only reload capture; never save the loaded scene."""
from pathlib import Path
import unreal
root=Path(r'D:\UEPro\Test')
settings=unreal.get_default_object(unreal.load_class(None,'/Script/UnrealEd.EditorPerformanceSettings'))
original_throttle=settings.get_editor_property('bThrottleCPUWhenNotForeground')
settings.set_editor_property('bThrottleCPUWhenNotForeground',False)
source=(root/'Scripts/capture_video_warehouse.py').read_text()
source=source.replace('/Game/Maps/VideoDigitalTwinWarehouse','/Game/Maps/GHS_CAD_DigitalTwin')
source=source.replace("VIEWS = ['Overview', 'Route', 'Racks', 'Alarm', 'Elevator']", "VIEWS = ['Overview', 'FloorStorage', 'RackAisles', 'AGV_Charger']")
source=source.replace('CAM_Video_','CAM_GHS_').replace('VideoWarehouse','GHS_PresentationReload').replace('VIDEO_WAREHOUSE','GHS_PRESENTATION_RELOAD')
source=source.replace('== 5','== 4').replace('RESOLUTION = (1920, 1080)','RESOLUTION = (2400, 1350)')
source=source.replace("assert vw_levels.save_current_level(), 'Could not save final overview viewport'", "# Read-only reload: preserve the saved user viewport and map bytes.")
exec(compile(source,str(root/'Scripts/capture_video_warehouse.py'),'exec'),globals())
original_finish=vw_finish
def vw_finish(error=None):
    original_finish(error)
    settings.set_editor_property('bThrottleCPUWhenNotForeground',original_throttle)
    unreal.SystemLibrary.quit_editor()
