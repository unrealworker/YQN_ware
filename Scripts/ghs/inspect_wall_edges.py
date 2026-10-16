"""Read the user's affected viewport and saved/live wall geometry without edits."""
import json
from pathlib import Path
import unreal
root=Path(r'D:\UEPro\Test')
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
actor_system=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
def xyz(v):return [float(v.x),float(v.y),float(v.z)]
location,rotation=editor.get_level_viewport_camera_info()
result=dict(map=editor.get_editor_world().get_path_name(),viewport=dict(position_cm=xyz(location),rotation=[rotation.pitch,rotation.yaw,rotation.roll]),groups=[])
for a in actor_system.get_all_level_actors():
    if a.get_actor_label() not in ['GHS_CAD_WallFaces','GHS_CAD_WallSections','GHS_CAD_WallEdges','GHS_CAD_DoorClearances']:continue
    c=a.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
    mesh=c.get_editor_property('static_mesh');b=mesh.get_bounds()
    result['groups'].append(dict(label=a.get_actor_label(),count=c.get_instance_count(),actor_location=xyz(a.get_actor_location()),actor_scale=xyz(a.get_actor_scale3d()),mesh=mesh.get_path_name(),bounds_origin=xyz(b.origin),bounds_extent=xyz(b.box_extent),materials=[c.get_material(i).get_path_name() for i in range(c.get_num_materials())],instances=[dict(index=i,position_cm=xyz(c.get_instance_transform(i,world_space=True).translation),scale=xyz(c.get_instance_transform(i,world_space=True).scale3d),rotation=str(c.get_instance_transform(i,world_space=True).rotation.rotator())) for i in range(c.get_instance_count())]))
(root/'Saved/GHS_WallEdgeLiveBefore.json').write_text(json.dumps(result,indent=2))
