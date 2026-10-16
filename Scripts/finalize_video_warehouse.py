"""Correct coordinate presentation, translucency, and fault panel readability."""
import json
from pathlib import Path
import unreal
root=Path(r'D:\UEPro\Test')
actor_sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
level_sub=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
lib=unreal.EditorAssetLibrary
ml=unreal.MaterialEditingLibrary
base=(root/'Scripts/build_video_warehouse.py').read_text(encoding='utf-8')
exec(compile(base.split('\ntry:main()')[0],'build_video_warehouse.py','exec'),globals())
all_actors=actor_sub.get_all_level_actors();by={a.get_actor_label():a for a in all_actors}
if 'VideoTwinPresentationMirrored' not in [str(t) for t in by['Warehouse_Footprint'].tags]:
    for a in all_actors:
        if isinstance(a,unreal.CameraActor):continue
        loc=a.get_actor_location();loc.x=-loc.x;a.set_actor_location(loc,False,False)
        rot=a.get_actor_rotation();rot.yaw=-rot.yaw;a.set_actor_rotation(rot,False)
    by['Warehouse_Footprint'].set_editor_property('tags',list(by['Warehouse_Footprint'].tags)+['VideoTwinPresentationMirrored'])
    registry_path=root/'SourceAssets/VideoReference/scene_registry.json'
    records=json.loads(registry_path.read_text())
    for r in records:r['position_m'][0]=-r['position_m'][0];r['yaw']=-r['yaw']
    registry_path.write_text(json.dumps(records,indent=2),encoding='utf-8')
make_material(dict(name='M_VR_Wall',base_color=[.018,.20,.46,1],opacity=.16,unlit=True,emission=.28,wall_gradient=True,two_sided=True))
newviews=[('Overview',(-35,-42,39),(0,0,.2),50),('Route',(2,-12,15),(-9.7,1.8,.4),45),('Racks',(26,-17,15),(10.3,-1.7,1.0),43),('Alarm',(21,-4,14),(10.8,8.2,.2),43),('Elevator',(11,-3,11),(1.5,10.8,1.0),42)]
for name,pos,target,fov in newviews:
    a=by['CAM_Video_'+name];a.set_actor_location(v(pos),False,False);a.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(v(pos),v(target)),False)
    a.get_component_by_class(unreal.CameraComponent).set_field_of_view(fov)
for a in all_actors:
    c=a.get_component_by_class(unreal.TextRenderComponent)
    if c:a.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(a.get_actor_location(),v((-35,-42,39))),False)
panel=by['ALARM_DN1_DiagnosticPanel'];panel.set_actor_location(v((8.8,7.2,2.2)),False,False)
look=unreal.MathLibrary.find_look_at_rotation(panel.get_actor_location(),v((21,-4,14)))
panel.set_actor_rotation(unreal.Rotator(pitch=0,yaw=look.yaw-90,roll=-look.pitch),False)
panel.get_component_by_class(unreal.StaticMeshComponent).set_editor_property('translucency_sort_priority',20)
tex=lib.load_asset('/Game/VideoDigitalTwin/Textures/T_VR_AlarmPanel')
tex.set_editor_property('mip_gen_settings',unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
tex.set_editor_property('lod_group',unreal.TextureGroup.TEXTUREGROUP_UI)
tex.set_editor_property('compression_settings',unreal.TextureCompressionSettings.TC_EDITOR_ICON)
save(tex)
make_material(dict(name='M_VR_AlarmPanel',base_color=[1,1,1,1],texture='T_VR_AlarmPanel',unlit=True,opacity=1,two_sided=True))
records=json.loads((SOURCE/'scene_registry.json').read_text())
for r in records:
    if r['id']=='ALARM_DN1_DiagnosticPanel':r['position_m']=[8.8,7.2,2.2];r['yaw']=look.yaw-90
(SOURCE/'scene_registry.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
assert level_sub.save_current_level()
exec(compile((root/'Scripts/capture_video_warehouse.py').read_text(encoding='utf-8'),'capture_video_warehouse.py','exec'),globals())
