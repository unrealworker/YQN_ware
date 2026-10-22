"""Read the active floor-storage bindings before a scoped visual mesh revision."""
import hashlib
import json
from pathlib import Path
import unreal

ROOT = Path('D:/UEPro/Test')
OUT = ROOT / 'Saved/DoublePallet'
OUT.mkdir(parents=True, exist_ok=True)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
world = editor.get_editor_world()
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()

def path(obj):
    return obj.get_path_name() if obj else None

def transform(value):
    return dict(position=list(value.translation.to_tuple()),
                rotation=[value.rotation.x, value.rotation.y, value.rotation.z, value.rotation.w],
                scale=list(value.scale3d.to_tuple()))

def snapshot(actor):
    comps = []
    for component in actor.get_components_by_class(unreal.StaticMeshComponent):
        entry = dict(name=component.get_name(), mesh=path(component.static_mesh),
                     transform=transform(component.get_world_transform()),
                     materials=[path(component.get_material(i)) for i in range(component.get_num_materials())])
        if isinstance(component, unreal.InstancedStaticMeshComponent):
            values = [transform(component.get_instance_transform(i, world_space=True))
                      for i in range(component.get_instance_count())]
            entry.update(count=len(values), instances_sha256=hashlib.sha256(json.dumps(values,sort_keys=True).encode()).hexdigest())
        comps.append(entry)
    return dict(name=actor.get_name(), label=actor.get_actor_label(), transform=transform(actor.get_actor_transform()),
                tags=[str(tag) for tag in actor.tags], components=comps)

result = dict(world=world.get_path_name(), playing=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor(),
              dirty_content=[path(p) for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()],
              dirty_maps=[path(p) for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()],
              actors={a.get_actor_label():snapshot(a) for a in actors}, targets=[])
for actor in actors:
    if actor.get_actor_label() not in ('GHS_CAD_PalletCargo','GHS_CAD_PalletCargoLow','GHS_CAD_PalletCargoHigh'):
        continue
    component = actor.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
    mesh = component.static_mesh
    b = mesh.get_bounds()
    result['targets'].append(dict(actor=actor.get_actor_label(), path=path(mesh),
        bounds_cm=dict(min=list((b.origin-b.box_extent).to_tuple()),max=list((b.origin+b.box_extent).to_tuple())),
        slots=[str(s.get_editor_property('imported_material_slot_name')) for s in mesh.static_materials],
        materials=[path(component.get_material(i)) for i in range(component.get_num_materials())],
        lods=[dict(triangles=mesh.get_num_triangles(i),sections=mesh.get_num_sections(i)) for i in range(mesh.get_num_lods())]))
(OUT/'baseline.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print('DOUBLE_PALLET_BASELINE '+json.dumps({k:v for k,v in result.items() if k!='actors'}))
