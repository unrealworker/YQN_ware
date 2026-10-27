"""Read-only inventory for replacing the screenshot's cart/stacker visuals."""
import json
from pathlib import Path
import unreal

ROOT = Path('D:/UEPro/Test')
A = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
E = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)

def xyz(v): return [float(v.x), float(v.y), float(v.z)]
def rot(v): return [float(v.pitch), float(v.yaw), float(v.roll)]
def tf(t): return dict(position_cm=xyz(t.translation), scale=xyz(t.scale3d), rotation=rot(t.rotation.rotator()))

world = E.get_editor_world()
report = dict(map=world.get_path_name(), selected=[a.get_actor_label() for a in A.get_selected_level_actors()], actors=[])
for name in ('get_dirty_map_packages','get_dirty_content_packages'):
    try: report[name] = [p.get_path_name() for p in getattr(unreal.EditorLoadingAndSavingUtils,name)()]
    except Exception as exc: report[name] = str(exc)
try:
    pos,rotation=E.get_level_viewport_camera_info()
    report['viewport_camera']=dict(position_cm=xyz(pos),rotation=rot(rotation))
except Exception as exc: report['viewport_camera_error']=str(exc)
for actor in A.get_all_level_actors():
    tags = [str(t) for t in actor.tags]
    components = actor.get_components_by_class(unreal.StaticMeshComponent)
    if not (any('FloorStacker' in t or 'GHS_AGV_' in t for t in tags)
            or any(c.static_mesh and 'BlueStacker' in c.static_mesh.get_name() for c in components)):
        continue
    center,extent = actor.get_actor_bounds(False)
    parent=actor.get_attach_parent_actor()
    row=dict(label=actor.get_actor_label(),path=actor.get_path_name(),actor_class=actor.get_class().get_path_name(),
             tags=tags,folder=str(actor.get_folder_path()),transform=tf(actor.get_actor_transform()),
             bounds=dict(center_cm=xyz(center),extent_cm=xyz(extent)),parent=parent.get_path_name() if parent else None,
             components=[],component_classes=[c.get_class().get_path_name() for c in actor.get_components_by_class(unreal.ActorComponent)])
    for c in components:
        b=c.static_mesh.get_bounds() if c.static_mesh else None
        row['components'].append(dict(name=c.get_name(),mesh=c.static_mesh.get_path_name() if c.static_mesh else None,
            relative_transform=tf(c.get_relative_transform()),world_transform=tf(c.get_world_transform()),
            mesh_bounds_cm=dict(center=xyz(b.origin),extent=xyz(b.box_extent)) if b else None,
            materials=[c.get_material(i).get_path_name() if c.get_material(i) else None for i in range(c.get_num_materials())],
            collision_profile=str(c.get_collision_profile_name()),mobility=str(c.get_editor_property('mobility'))))
    report['actors'].append(row)
report['actor_count']=len(A.get_all_level_actors())
report['matching_count']=len(report['actors'])
report['saved_assets']=False
(ROOT/'Saved/GHS_CartShellTargets.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
unreal.log('GHS_CART_SHELL_TARGETS_INSPECTED '+str(report['matching_count']))
