"""Read-only live diagnosis of user-placed forklifts and planning geometry."""
import sys,json
from pathlib import Path
import unreal
ROOT=Path('D:/UEPro/Test');sys.path.insert(0,str(ROOT/'Scripts/ghs'))
import import_manned_forklift as u
from sync_wall_heights import snapshot,transform,xyz
assert u.E.get_editor_world().get_path_name().split('.')[0]==u.MAP and not u.E.get_game_world()
by=u.labels();items=[];forklifts=[]
for label,a in by.items():
    for c in a.get_components_by_class(unreal.StaticMeshComponent):
        if not c.static_mesh:continue
        row=dict(label=label,path=a.get_path_name(),component=c.get_name(),mesh=c.static_mesh.get_path_name(),tags=[str(t) for t in a.tags],
            hidden=bool(a.get_editor_property('hidden')),visible=bool(c.get_editor_property('visible')),hidden_in_game=bool(c.get_editor_property('hidden_in_game')),
            instances=[dict(index=i,transform=transform(t),bounds=u.mesh_box(c.static_mesh,t)) for i,t in enumerate(u.component_transforms(c))])
        items.append(row)
        if 'MannedForklift' in row['mesh']:forklifts.append(row)
walls=[]
for name in sorted(u.WALLS):
    for tri in u.world_triangles(by[name]):
        walls.append(dict(label=name,bounds_cm=[min(p[i] for p in tri) for i in range(3)]+[max(p[i] for p in tri) for i in range(3)]))
floor=[t for t in u.world_triangles(by['GHS_CAD_ExactFootprint']) if all(abs(p[2])<.01 for p in t)]
u.write(ROOT/'Saved/GHS_ManualFollowupProbe.json',dict(map=u.MAP,actor_count=len(by),items=items,forklifts=forklifts,walls=walls,floor=floor,
    dirty_maps=[p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()],
    dirty_content=[p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()]))
u.write(ROOT/'Saved/GHS_ManualFollowupBaseline.json',snapshot(by))
unreal.log('MANUAL_FOLLOWUP_PROBE '+str(len(forklifts))+' forklifts '+str(len(by))+' actors')
