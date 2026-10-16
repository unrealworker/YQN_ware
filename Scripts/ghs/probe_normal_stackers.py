"""Read current NormalWarehouse state without reloading or saving the level."""
import json, sys, itertools
from pathlib import Path
import unreal
ROOT=Path(r'D:\UEPro\Test')
sys.path.insert(0,str(ROOT/'Scripts/ghs'))
from sync_wall_heights import snapshot, xyz, transform
A=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
E=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
world=E.get_editor_world()
assert world.get_path_name().split('.')[0]=='/Game/Maps/GHS_CAD_NormalWarehouse',world.get_path_name()
by={a.get_actor_label():a for a in A.get_all_level_actors()}
mesh=unreal.EditorAssetLibrary.load_asset('/Game/VideoDigitalTwin/Meshes/SM_VR_BlueStacker')
assert mesh
def bounds(m):
    b=m.get_bounds()
    return dict(origin=xyz(b.origin),extent=xyz(b.box_extent))
def box(m,t):
    b=m.get_bounds();o=xyz(b.origin);e=xyz(b.box_extent)
    ps=[xyz(unreal.MathLibrary.transform_location(t,unreal.Vector(*(o[i]+s[i]*e[i] for i in range(3))))) for s in itertools.product((-1,1),repeat=3)]
    return [min(p[i] for p in ps) for i in range(3)]+[max(p[i] for p in ps) for i in range(3)]
items=[]
for name,a in by.items():
    c=a.get_component_by_class(unreal.StaticMeshComponent)
    if not c or not c.static_mesh:continue
    m=c.static_mesh
    ts=([c.get_instance_transform(i,world_space=True) for i in range(c.get_instance_count())]
        if isinstance(c,unreal.InstancedStaticMeshComponent) else [c.get_world_transform()])
    items.append(dict(label=name,mesh=m.get_path_name(),mesh_bounds=bounds(m),
        hidden=bool(a.get_editor_property('hidden')),visible=bool(c.get_editor_property('visible')),
        materials=[c.get_material(i).get_path_name() if c.get_material(i) else None for i in range(c.get_num_materials())],
        instances=[dict(index=i,transform=transform(t),bounds=box(m,t)) for i,t in enumerate(ts)]))
result=dict(map=world.get_path_name(),actor_count=len(by),dirty_maps=[p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()],
    stacker=dict(asset=mesh.get_path_name(),bounds=bounds(mesh),slots=[dict(name=str(s.material_slot_name),material=s.material_interface.get_path_name() if s.material_interface else None) for s in mesh.static_materials]),items=items)
(ROOT/'Saved/GHS_NormalStackerProbe.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
(ROOT/'Saved/GHS_NormalStackerLiveBaseline.json').write_text(json.dumps(snapshot(by)),encoding='utf-8')
unreal.log('GHS_NORMAL_STACKER_PROBE_COMPLETE')
