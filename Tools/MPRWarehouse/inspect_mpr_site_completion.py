"""Read the saved MPR level into an owned commandlet and record site fixtures."""
import json
from pathlib import Path
import unreal as u

ROOT = Path(u.Paths.convert_relative_path_to_full(u.Paths.project_dir())).resolve()
OUT = ROOT / 'Saved/MPR/site_completion_20261105'
OUT.mkdir(parents=True, exist_ok=True)
LEVEL = '/Game/Maps/MPR_CAD_Warehouse_B50B57'
levels = u.get_editor_subsystem(u.LevelEditorSubsystem)
actors = u.get_editor_subsystem(u.EditorActorSubsystem)
assert levels.load_level(LEVEL)

def xyz(v):
    return [float(v.x), float(v.y), float(v.z)]

def rotation(r):
    return [float(r.pitch), float(r.yaw), float(r.roll)]

rows = []
for actor in actors.get_all_level_actors():
    center, extent = actor.get_actor_bounds(False)
    row = dict(label=actor.get_actor_label(), name=actor.get_name(),
               cls=actor.get_class().get_name(), tags=[str(t) for t in actor.tags],
               location_cm=xyz(actor.get_actor_location()),
               rotation_deg=rotation(actor.get_actor_rotation()),
               scale=xyz(actor.get_actor_scale3d()),
               bounds_center_cm=xyz(center), bounds_extent_cm=xyz(extent), components=[])
    for component in actor.get_components_by_class(u.StaticMeshComponent):
        mesh = component.static_mesh
        if mesh is None:
            continue
        item = dict(name=component.get_name(), cls=component.get_class().get_name(),
                    mesh=mesh.get_path_name().split('.')[0],
                    materials=[m.get_path_name().split('.')[0] if m else None
                               for m in component.get_materials()])
        if isinstance(component, u.InstancedStaticMeshComponent):
            item['instances'] = []
            for index in range(component.get_instance_count()):
                tr = component.get_instance_transform(index, world_space=True)
                item['instances'].append(dict(location_cm=xyz(tr.translation),
                    rotation_deg=rotation(tr.rotation.rotator()), scale=xyz(tr.scale3d)))
        row['components'].append(item)
    if isinstance(actor, u.CameraActor):
        c=actor.get_component_by_class(u.CameraComponent)
        row['camera']=dict(fov=c.field_of_view,aspect=c.aspect_ratio,
                          constrain_aspect=c.constrain_aspect_ratio)
    rows.append(row)

(OUT/'scene_snapshot.json').write_text(json.dumps(dict(map=LEVEL,actors=rows),indent=2),encoding='utf8')
u.log('MPR_SITE_INSPECT '+json.dumps(dict(actors=len(rows),report=str(OUT/'scene_snapshot.json'))))
