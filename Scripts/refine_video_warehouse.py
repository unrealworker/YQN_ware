"""Apply reference comparison corrections in the live editor, without reimport."""
from pathlib import Path
import json
import unreal
root=Path(r'D:\UEPro\Test')
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assert unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world().get_path_name().startswith('/Game/Maps/VideoDigitalTwinWarehouse.')
by={a.get_actor_label():a for a in actors.get_all_level_actors()}
for name,a in by.items():
    c=a.get_component_by_class(unreal.LightComponent)
    if c:
        intensity=.22 if name=='Cool_Overhead_Key' else 50 if name=='Elevator_Cyan_Spill' else 4 if name=='Selected_Robot_Cyan' else 110
        c.set_intensity(intensity)
views=[('Overview',(-35,-42,39),(0,0,.2),46),('Route',(-2,-12,15),(9.7,1.8,.4),45),('Racks',(-26,-17,15),(-10.3,-1.7,1.0),43),('Alarm',(-21,-4,14),(-10.8,8.2,.2),43),('Elevator',(-11,-3,11),(-1.5,10.8,1.0),42)]
def v(a):return unreal.Vector(*(x*100 for x in a))
for name,pos,target,fov in views:
    a=by['CAM_Video_'+name];a.set_actor_location(v(pos),False,False);a.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(v(pos),v(target)),False)
    a.get_component_by_class(unreal.CameraComponent).set_field_of_view(fov)
for name,a in by.items():
    c=a.get_component_by_class(unreal.TextRenderComponent)
    if c:
        a.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(a.get_actor_location(),v((-35,-42,39))),False)
if 'DN-1_State' in by:actors.destroy_actor(by['DN-1_State'])
for name,a in by.items():
    if name=='HR-1' or name.startswith('HR-1_'):
        loc=a.get_actor_location();loc.x-=200;a.set_actor_location(loc,False,False)
panel=by['ALARM_DN1_DiagnosticPanel'];panel.set_actor_location(v((-8.8,8.5,1.7)),False,False);panel.set_actor_rotation(unreal.Rotator(pitch=0,yaw=-40,roll=0),False)
diagnostic={}
c=panel.get_component_by_class(unreal.StaticMeshComponent)
origin,extent=panel.get_actor_bounds(False)
diagnostic['panel']=dict(materials=[c.get_material(i).get_path_name() for i in range(c.get_num_materials())],origin=str(origin),extent=str(extent))
tex=unreal.EditorAssetLibrary.load_asset('/Game/VideoDigitalTwin/Textures/T_VR_AlarmPanel')
diagnostic['texture']=str(tex)
registry_path=root/'SourceAssets/VideoReference/scene_registry.json'
records=json.loads(registry_path.read_text())
for r in records:
    if r['id']=='HR-1' or r['id'].startswith('HR-1_'):r['position_m'][0]-=2
    if r['id']=='ALARM_DN1_DiagnosticPanel':r['position_m']=[-8.8,8.5,1.7];r['yaw']=-40
registry_path.write_text(json.dumps(records,indent=2),encoding='utf-8')
(root/'Saved/VideoWarehouse_Refinement.json').write_text(json.dumps(diagnostic,indent=2),encoding='utf-8')
assert levels.save_current_level()
exec(compile((root/'Scripts/capture_video_warehouse.py').read_text(encoding='utf-8'),'capture_video_warehouse.py','exec'),globals())
