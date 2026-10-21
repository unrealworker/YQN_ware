"""Verify the saved map in a fresh editor process; never save project assets."""
import importlib
import json
import sys
import traceback
from pathlib import Path
import unreal
ROOT=Path('D:/UEPro/Test')
OUT=ROOT/'Saved/DockNumbers'
sys.path.insert(0,str(ROOT/'Scripts/ghs'))
import apply_dock_numbers as dock
import restore_zcool_floor as floor

report=dict(success=False,assets_saved=False)
try:
    assert dock.EDITOR.get_editor_world().get_path_name().split('.')[0]==dock.MAP
    by={a.get_actor_label():a for a in dock.ACTORS.get_all_level_actors()}
    rows=dock.make_rows()
    report['scene']=dock.verify(rows,dock.geometry_signature(by))
    historical=json.loads((ROOT/'Saved/GHS_ZcoolBuild.json').read_text(encoding='utf-8'))['after']
    restored=0
    for label,actor in by.items():
        c=actor.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
        if not c:continue
        prior=historical[label]['components'][c.get_name()]
        assert len(prior['instances'])==c.get_instance_count(),label
        for index,t in enumerate(prior['instances']):
            floor._assert_transform(c.get_instance_transform(index,world_space=True),t,(label,index))
        if label in floor.EXPECTED:restored+=c.get_instance_count()
    assert restored==7530
    bindings=json.loads((ROOT/'Content/GHSTwinUI/data/scene-bindings.json').read_text(encoding='utf-8'))
    groups={g['mesh']:g for g in bindings['groups']}
    for label,(mesh,count) in floor.EXPECTED.items():
        c=by[label].get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
        for i,binding in enumerate(groups[mesh]['instances']):
            x,y,z=binding['position_m']
            assert (c.get_instance_transform(i,world_space=True).translation-unreal.Vector(x*100,-y*100,z*100)).length()<.02
    rack_slots=json.loads((ROOT/'Content/GHSTwinUI/data/rack-slots.json').read_text(encoding='utf-8'))['meshes']
    slot_models={m['name']:m for m in rack_slots}
    occupied=capacity=instances=0
    for actor in by.values():
        c=actor.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
        if not c or not c.static_mesh:continue
        name=c.static_mesh.get_name()
        if not name.startswith('SM_GHS_V2Rack_'):continue
        assert name.endswith('_Occ70')
        n=c.get_instance_count();instances+=n
        occupied+=n*len(slot_models[name]['cargo_stacks'])
        capacity+=n*len(slot_models[name.removesuffix('_Occ70')]['cargo_stacks'])
    assert (instances,occupied,capacity)==(1629,17539,25056)
    originals=json.loads((ROOT/'Saved/SceneRefinements/source_hashes_before.json').read_text(encoding='utf-8'))
    for relative,expected in originals.items(): assert dock.sha(ROOT/relative)==expected,relative
    assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
    report.update(success=True,all_original_hism_transforms_preserved=True,floor_metadata_matches=True,
        rack=dict(instances=instances,occupied=occupied,capacity=capacity),rows=rows,
        original_map_and_shared_assets_preserved=True,actor_count=len(by))
    dock.write(ROOT/'SourceAssets/GHS/ZcoolDockNumbers.json',dict(numbering='East wall north to south, then south wall east to west',rows=rows))
except Exception:
    report['error']=traceback.format_exc()
    unreal.log_error(report['error'])
dock.write(OUT/'saved_verification.json',report)
assert report['success'],report.get('error')
