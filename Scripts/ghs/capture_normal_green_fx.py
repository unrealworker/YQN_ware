"""Read-only UE close-up of AGV34's green diffusion and radar."""
from pathlib import Path
import unreal
root=Path(r'D:\UEPro\Test');actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
assert editor.get_editor_world().get_path_name().split('.')[0]=='/Game/Maps/GHS_CAD_NormalWarehouse'
by={a.get_actor_label():a for a in actors.get_all_level_actors()}
robot=by['GHS_AGV_34'];center=robot.get_actor_location()
# The original radar faces across the aisle; a top view shows its complete fan.
camera=actors.spawn_actor_from_class(unreal.CameraActor,center+unreal.Vector(0,0,900),unreal.Rotator(pitch=-90,yaw=-90,roll=0))
camera.set_actor_label('CAM_GHS_GreenFX');camera.get_component_by_class(unreal.CameraComponent).set_field_of_view(50)
settings=unreal.get_default_object(unreal.load_class(None,'/Script/UnrealEd.EditorPerformanceSettings'))
original_throttle=settings.get_editor_property('bThrottleCPUWhenNotForeground');settings.set_editor_property('bThrottleCPUWhenNotForeground',False)
source=(root/'Scripts/capture_video_warehouse.py').read_text()
source=source.replace('/Game/Maps/VideoDigitalTwinWarehouse','/Game/Maps/GHS_CAD_NormalWarehouse')
source=source.replace("VIEWS = ['Overview', 'Route', 'Racks', 'Alarm', 'Elevator']","VIEWS = ['GreenFX']")
source=source.replace('CAM_Video_','CAM_GHS_').replace('VideoWarehouse','GHS_NormalGreenFX').replace('VIDEO_WAREHOUSE','GHS_NORMAL_GREEN_FX')
source=source.replace('== 5','== 1')
source=source.replace("assert vw_levels.save_current_level(), 'Could not save final overview viewport'",'# Do not save temporary capture actors or viewport.')
exec(compile(source,str(root/'Scripts/capture_video_warehouse.py'),'exec'),globals())
original_finish=vw_finish
def vw_finish(error=None):
    original_finish(error);settings.set_editor_property('bThrottleCPUWhenNotForeground',original_throttle)
    unreal.SystemLibrary.quit_editor()
