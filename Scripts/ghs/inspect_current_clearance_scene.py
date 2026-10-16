"""Read the live GHS world before applying the user-requested clearance fix."""
import json
from pathlib import Path
import unreal
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
world=editor.get_editor_world()
assert world.get_path_name().split('.')[0]=='/Game/Maps/GHS_CAD_DigitalTwin'
data=dict(map=world.get_path_name(),groups=[])
for a in actors.get_all_level_actors():
    c=a.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
    if not c:continue
    mesh=c.get_editor_property('static_mesh');b=mesh.get_bounds()
    data['groups'].append(dict(actor=a.get_actor_label(),count=c.get_instance_count(),mesh=mesh.get_path_name(),
        mesh_center=[b.origin.x,b.origin.y,b.origin.z],mesh_extent=[b.box_extent.x,b.box_extent.y,b.box_extent.z],
        materials=[c.get_material(i).get_path_name() for i in range(c.get_num_materials())]))
Path(r'D:\UEPro\Test\Saved\GHS_ClearanceLiveBefore.json').write_text(json.dumps(data,indent=2))
