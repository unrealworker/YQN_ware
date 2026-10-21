"""Read the current editor scene before the additive park extension."""
import hashlib
import json
import os
from pathlib import Path
import unreal

root = Path('D:/UEPro/Test')
out = root/'Saved/ParkExpansion'
out.mkdir(parents=True, exist_ok=True)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
def xyz(v): return [round(float(v.x),4),round(float(v.y),4),round(float(v.z),4)]
def xf(t): return dict(position=xyz(t.translation),scale=xyz(t.scale3d),rotation=[round(float(v),6) for v in [t.rotation.x,t.rotation.y,t.rotation.z,t.rotation.w]])
result=dict(pid=os.getpid(),map=editor.get_editor_world().get_path_name(),pie=levels.is_in_play_in_editor(),
    dirty_maps=[p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()],
    dirty_assets=[p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()],actors=[])
for actor in actors.get_all_level_actors():
    row=dict(label=actor.get_actor_label(),actor_class=actor.get_class().get_path_name(),transform=xf(actor.get_actor_transform()),tags=[str(t) for t in actor.tags],components=[])
    origin,extent=actor.get_actor_bounds(False)
    row['bounds']=dict(origin=xyz(origin),extent=xyz(extent))
    for component in actor.get_components_by_class(unreal.StaticMeshComponent):
        item=dict(name=component.get_name(),mesh=component.static_mesh.get_path_name() if component.static_mesh else None,
            materials=[component.get_material(i).get_path_name() if component.get_material(i) else None for i in range(component.get_num_materials())],transform=xf(component.get_world_transform()))
        if isinstance(component,unreal.InstancedStaticMeshComponent):
            transforms=[xf(component.get_instance_transform(i,world_space=True)) for i in range(component.get_instance_count())]
            item.update(count=len(transforms),instances_sha256=hashlib.sha256(json.dumps(transforms,sort_keys=True).encode()).hexdigest())
        row['components'].append(item)
    if 'GHSWarehouseCameraPawn' in row['actor_class'] or actor.get_actor_label().startswith('GHS_WarehouseCamera'):
        row['camera']={}
        for prop in ['overview_center','overview_distance','overview_pitch','overview_yaw','navigation_min','navigation_max','min_zoom_distance','max_zoom_distance']:
            try:
                value=actor.get_editor_property(prop)
                row['camera'][prop]=xyz(value) if hasattr(value,'z') else str(value)
            except Exception: pass
    result['actors'].append(row)
v,r=editor.get_level_viewport_camera_info()
result['viewport']=dict(eye=xyz(v),rotation=[r.pitch,r.yaw,r.roll])
result['success']=True
# The first snapshot is the preservation baseline. Later inspections must not
# silently replace it with the changed scene they are intended to validate.
target=out/('scene_inspection_latest.json' if (out/'scene_inspection.json').exists() else 'scene_inspection.json')
target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
unreal.log('GHS_PARK_INSPECTION_COMPLETE')
