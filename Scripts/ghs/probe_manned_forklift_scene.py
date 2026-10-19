"""Capture the current live warehouse without reloading or saving user edits."""
import sys,json,itertools
from pathlib import Path
import unreal
ROOT=Path(r'D:/UEPro/Test');sys.path.insert(0,str(ROOT/'Scripts/ghs'))
from sync_wall_heights import snapshot,xyz,transform
A=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);E=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
world=E.get_editor_world();assert world.get_path_name().split('.')[0]=='/Game/Maps/GHS_CAD_NormalWarehouse'
assert not E.get_game_world()
by={a.get_actor_label():a for a in A.get_all_level_actors()}
def box(mesh,t):
 b=mesh.get_bounds();ps=[xyz(unreal.MathLibrary.transform_location(t,unreal.Vector(*(getattr(b.origin,k)+s[i]*getattr(b.box_extent,k) for i,k in enumerate('xyz'))))) for s in itertools.product((-1,1),repeat=3)]
 return [min(p[i] for p in ps) for i in range(3)]+[max(p[i] for p in ps) for i in range(3)]
items=[]
for name,a in by.items():
 for c in a.get_components_by_class(unreal.StaticMeshComponent):
  if not c.static_mesh:continue
  ts=[c.get_instance_transform(i,world_space=True) for i in range(c.get_instance_count())] if isinstance(c,unreal.InstancedStaticMeshComponent) else [c.get_world_transform()]
  items.append(dict(label=name,component=c.get_name(),mesh=c.static_mesh.get_path_name(),hidden=bool(a.get_editor_property('hidden')),
    visible=bool(c.get_editor_property('visible')),hidden_in_game=bool(c.get_editor_property('hidden_in_game')),
    instances=[dict(index=i,transform=transform(t),bounds=box(c.static_mesh,t)) for i,t in enumerate(ts)]))
pos,rot=E.get_level_viewport_camera_info()
result=dict(map=world.get_path_name(),actor_count=len(by),dirty_maps=[p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()],
 dirty_content=[p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()],
 viewport_location=xyz(pos),viewport_rotation=[rot.pitch,rot.yaw,rot.roll],selected=[a.get_path_name() for a in A.get_selected_level_actors()],
 equipment_tags={n:[str(t) for t in a.tags] for n,a in by.items() if any(s in n for s in ['Stacker','Truck','Forklift'])},items=items)
(ROOT/'Saved/GHS_MannedForkliftLiveProbe.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
(ROOT/'Saved/GHS_MannedForkliftLiveBaseline.json').write_text(json.dumps(snapshot(by),indent=2),encoding='utf-8')
unreal.log('MANNED_FORKLIFT_LIVE_PROBE_COMPLETE '+str(len(by)))
