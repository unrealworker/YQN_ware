import unreal,json
from pathlib import Path
A=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
def v(x):return [x.x,x.y,x.z]
out=[]
for a in A.get_all_level_actors():
 if a.get_actor_label().startswith('FX_GHN_FloorStacker_'):
  p=a.get_attach_parent_actor();r=a.get_actor_rotation();c=a.get_root_component()
  out.append(dict(label=a.get_actor_label(),rotation=[r.pitch,r.yaw,r.roll],parent_yaw=p.get_actor_rotation().yaw,
   forward=v(a.get_actor_forward_vector()),right=v(a.get_actor_right_vector()),up=v(a.get_actor_up_vector()),
   has_relative_transform=hasattr(c,'get_relative_transform')))
Path(r'D:\UEPro\Test\Saved\GHS_NormalStackerFXRotationProbe.json').write_text(json.dumps(out,indent=2))
