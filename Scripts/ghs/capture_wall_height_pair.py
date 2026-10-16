"""Render the same corrected wall junction in either warehouse style."""
from pathlib import Path
import unreal
root=Path(r'D:\UEPro\Test')
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
world_path=editor.get_editor_world().get_path_name().split('.')[0]
assert world_path in ['/Game/Maps/GHS_CAD_DigitalTwin','/Game/Maps/GHS_CAD_NormalWarehouse']
style='Normal' if world_path.endswith('NormalWarehouse') else 'Blue'
prefix='GHS_WallHeight_'+style
position=unreal.Vector(22600,-3600,2000)
target=unreal.Vector(21400,-5100,200)
camera=actors.spawn_actor_from_class(unreal.CameraActor,position,unreal.MathLibrary.find_look_at_rotation(position,target))
camera.set_actor_label('CAM_GHS_WallDetail')
camera.get_component_by_class(unreal.CameraComponent).set_editor_property('field_of_view',60)
settings=unreal.get_default_object(unreal.load_class(None,'/Script/UnrealEd.EditorPerformanceSettings'))
original_throttle=settings.get_editor_property('bThrottleCPUWhenNotForeground')
settings.set_editor_property('bThrottleCPUWhenNotForeground',False)
source=(root/'Scripts/capture_video_warehouse.py').read_text()
source=source.replace('/Game/Maps/VideoDigitalTwinWarehouse',world_path)
source=source.replace("VIEWS = ['Overview', 'Route', 'Racks', 'Alarm', 'Elevator']","VIEWS = ['WallDetail', 'Overview']")
source=source.replace('CAM_Video_','CAM_GHS_').replace('VideoWarehouse',prefix).replace('VIDEO_WAREHOUSE',prefix.upper())
source=source.replace('== 5','== 2').replace('RESOLUTION = (1920, 1080)','RESOLUTION = (2400, 1350)')
source=source.replace("assert vw_levels.save_current_level(), 'Could not save final overview viewport'",'# Do not save temporary review camera or viewport.')
exec(compile(source,str(root/'Scripts/capture_video_warehouse.py'),'exec'),globals())
original_finish=vw_finish
def vw_finish(error=None):
    original_finish(error)
    settings.set_editor_property('bThrottleCPUWhenNotForeground',original_throttle)
    unreal.SystemLibrary.quit_editor()
