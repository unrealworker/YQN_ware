import unreal,json
from pathlib import Path
a=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
out=[]
for actor in a.get_all_level_actors():
    if actor.get_actor_label().startswith('GHS_CAD_Wall'):
        c=actor.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
        out.append(dict(label=actor.get_actor_label(),count=c.get_instance_count(),mesh=c.get_editor_property('static_mesh').get_path_name()))
Path(r'D:\UEPro\Test\Saved\GHS_RefinementV2LiveDiagnostic.json').write_text(json.dumps(out,indent=2))
