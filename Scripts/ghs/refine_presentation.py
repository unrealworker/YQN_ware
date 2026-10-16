"""Correct presentation cameras and flat annotation reading direction."""
from pathlib import Path
import json
import unreal
root=Path(r'D:\UEPro\Test')
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
assert editor.get_editor_world().get_path_name().split('.')[0]=='/Game/Maps/GHS_CAD_DigitalTwin'
by_label={a.get_actor_label():a for a in actors.get_all_level_actors()}
def p(v):return unreal.Vector(v[0]*100,-v[1]*100,v[2]*100)
camera=by_label['CAM_GHS_CADPlan']
camera.set_actor_rotation(unreal.Rotator(pitch=-90,yaw=-90,roll=0),False)
camera=by_label['CAM_GHS_AGV_Charger']
camera.set_actor_location(p((142,40,3.4)),False,False)
camera.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(p((142,40,3.4)),p((146.3,44.4,.8))),False)
for label,a in by_label.items():
    if label.startswith('CH_BayLabel_') or label in ['GHS_SiteTitle','GHS_RackZone','GHS_PalletZone','GHS_ChargingZone']:
        a.set_actor_rotation(unreal.Rotator(pitch=90,yaw=90,roll=0),False)
assert levels.save_current_level()
(root/'Saved/GHS_PresentationRefinement.json').write_text(json.dumps(dict(success=True,cad_plan_north_up=True,charger_camera_faces_photo_front=True,flat_text_faces_south=True)))
