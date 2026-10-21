"""Read-only snapshot before floor restoration and sequential door numbering."""
import json
import os
from pathlib import Path
import unreal

OUT = Path('D:/UEPro/Test/Saved/DockNumbers')
OUT.mkdir(parents=True, exist_ok=True)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
eye, rotation = editor.get_level_viewport_camera_info()
data = dict(pid=os.getpid(), map=editor.get_editor_world().get_path_name(),
    pie=levels.is_in_play_in_editor(),
    dirty_maps=[p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()],
    dirty_assets=[p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()],
    eye=[eye.x, eye.y, eye.z], rotation=[rotation.pitch, rotation.yaw, rotation.roll], actors=[])
for actor in actors.get_all_level_actors():
    item=dict(label=actor.get_actor_label(), name=actor.get_name(), tags=[str(t) for t in actor.tags],components=[])
    for component in actor.get_components_by_class(unreal.StaticMeshComponent):
        if not component.static_mesh: continue
        record=dict(mesh=component.static_mesh.get_path_name(), materials=[component.get_material(i).get_path_name() if component.get_material(i) else None for i in range(component.get_num_materials())])
        if isinstance(component, unreal.InstancedStaticMeshComponent):
            record['count']=component.get_instance_count()
            if 'DockDoor' in component.static_mesh.get_name():
                record['positions']=[[t.translation.x,t.translation.y,t.translation.z] for t in [component.get_instance_transform(i,world_space=True) for i in range(component.get_instance_count())]]
        item['components'].append(record)
    data['actors'].append(item)
(OUT/'editor_before.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
unreal.log('GHS_DOCK_UPDATE_INSPECTED')
