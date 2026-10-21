"""Read-only material binding diagnostics for the imported campus."""
import json
from pathlib import Path
import unreal
rows=[]
for actor in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
    if not actor.get_actor_label().startswith('GHSPark_'):continue
    for c in actor.get_components_by_class(unreal.StaticMeshComponent):
        if not c.static_mesh:continue
        rows.append(dict(actor=actor.get_actor_label(),mesh=c.static_mesh.get_path_name(),
            materials=[c.get_material(i).get_path_name() if c.get_material(i) else None for i in range(c.get_num_materials())]))
Path('D:/UEPro/Test/Saved/ParkExpansion/material_diagnostics.json').write_text(json.dumps(rows,indent=2))
