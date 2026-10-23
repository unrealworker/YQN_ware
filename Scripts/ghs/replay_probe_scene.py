"""Read-only snapshot for order-replay route planning; never changes a level."""
import json, sys, hashlib
from pathlib import Path
import unreal
ROOT=Path('D:/UEPro/Test'); sys.path.insert(0,str(ROOT/'Scripts/ghs'))
import import_manned_forklift as u
from sync_wall_heights import snapshot,transform
OUT=ROOT/'Saved/OrderReplay'; OUT.mkdir(parents=True,exist_ok=True)
world=u.E.get_editor_world()
assert world and not u.E.get_game_world(), 'Only inspect the editor world outside PIE'
by=u.labels(); before=snapshot(by)
items=[]
for label,a in by.items():
    for c in a.get_components_by_class(unreal.StaticMeshComponent):
        if not c.static_mesh: continue
        items.append(dict(label=label,actor=a.get_name(),component=c.get_name(),mesh=c.static_mesh.get_path_name(),
            tags=[str(t) for t in a.tags],hidden=bool(a.get_editor_property('hidden')),
            visible=bool(c.get_editor_property('visible')),hidden_in_game=bool(c.get_editor_property('hidden_in_game')),
            materials=[c.get_material(i).get_path_name() if c.get_material(i) else None for i in range(c.get_num_materials())],
            instances=[dict(index=i,transform=transform(t),bounds_cm=u.mesh_box(c.static_mesh,t)) for i,t in enumerate(u.component_transforms(c))]))
triangles={}
for name in sorted(u.WALLS|{'GHS_CAD_ExactFootprint'}):
    if name in by: triangles[name]=list(u.world_triangles(by[name]))
after=snapshot(u.labels()); assert before==after,'Read-only probe changed actor state'
report=dict(map=world.get_path_name(),actor_count=len(by),items=items,triangles_cm=triangles,unchanged=True,
            dirty_maps=[p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()],
            dirty_content=[p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()])
(OUT/'scene_probe.json').write_text(json.dumps(report,ensure_ascii=False),encoding='utf-8')
(OUT/'scene_snapshot.json').write_text(json.dumps(before,ensure_ascii=False),encoding='utf-8')
unreal.log('ORDER_REPLAY_READONLY_PROBE '+str(len(items))+' components')
