import json
from pathlib import Path
import unreal
aa=unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).load_level("/Game/Maps/LogisticsWarehouse")
aa=unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
data={"rotator_doc":unreal.Rotator.__doc__,"examples":[]}
data["environment"]=[dict(label=a.get_actor_label(),cls=a.get_class().get_name()) for a in aa if any(s in a.get_actor_label().lower() for s in ["sky","fog","sun","post","lightmass"])]
for a in aa:
    if a.get_actor_label() in ["TRK_01_Docked","WH01_MainWarehouse","Terrain_Context","Sun_LateAfternoon"]:
        c=a.get_component_by_class(unreal.StaticMeshComponent)
        data["examples"].append(dict(label=a.get_actor_label(),rotation=str(a.get_actor_rotation()),
            materials=[c.get_material(i).get_path_name() if c.get_material(i) else None for i in range(c.get_num_materials())] if c else []))
Path(r"D:\UEPro\Test\Saved\Warehouse_Probe.json").write_text(json.dumps(data,indent=2),encoding="utf-8")
