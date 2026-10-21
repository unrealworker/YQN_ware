"""Read the current editor scene before the five warehouse refinements."""
import json
import os
from pathlib import Path
import unreal

root = Path('D:/UEPro/Test')
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
eye, rotation = editor.get_level_viewport_camera_info()
def path(obj):
    return obj.get_path_name() if obj else None
data = dict(pid=os.getpid(), map=path(editor.get_editor_world()), pie=levels.is_in_play_in_editor(),
    dirty_maps=[path(x) for x in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()],
    dirty_assets=[path(x) for x in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()],
    eye=[eye.x,eye.y,eye.z], rotation=[rotation.pitch,rotation.yaw,rotation.roll],
    selected=[a.get_name() for a in actors.get_selected_level_actors()], actors=[])
for actor in actors.get_all_level_actors():
    row=dict(label=actor.get_actor_label(), name=actor.get_name(), tags=[str(t) for t in actor.tags], components=[])
    for c in actor.get_components_by_class(unreal.ActorComponent):
        item=dict(name=c.get_name(), type=c.get_class().get_name())
        if isinstance(c, unreal.StaticMeshComponent):
            item.update(mesh=path(c.static_mesh), materials=[path(c.get_material(i)) for i in range(c.get_num_materials())])
            if isinstance(c, unreal.InstancedStaticMeshComponent):
                item['count']=c.get_instance_count()
        elif isinstance(c, unreal.TextRenderComponent):
            item.update(text=str(c.text), color=str(c.text_render_color), material=path(c.text_material))
        elif isinstance(c, unreal.DecalComponent):
            item.update(material=path(c.get_decal_material()))
        else:
            continue
        row['components'].append(item)
    data['actors'].append(row)
target=root/'Saved/SceneRefinements/editor_before.json'
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
unreal.log('GHS_SCENE_REFINEMENTS_INSPECTED '+data['map'])
