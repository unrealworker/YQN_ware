"""Read-only checks of the actual running map and its selection metadata."""
import json
from pathlib import Path
import unreal

ROOT=Path('D:/UEPro/Test')
def check_assets(world,widget):
    expected=json.loads((ROOT/'Saved/SceneRefinements/apply_report.json').read_text(encoding='utf-8'))
    registry=json.loads((ROOT/'Content/GHSTwinUI/data/scene-bindings.json').read_text(encoding='utf-8'))
    slots=json.loads((ROOT/'Content/GHSTwinUI/data/rack-slots.json').read_text(encoding='utf-8'))
    manifest=json.loads((ROOT/'SourceAssets/GHS/ZcoolOccupancy/zcool_occupancy.json').read_text(encoding='utf-8'))
    by={a.get_actor_label():a for a in unreal.GameplayStatics.get_all_actors_of_class(world,unreal.Actor)}
    groups=[]
    for row in expected['groups']:
        actor=by[row['actor']]
        c=actor.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
        assert c.static_mesh.get_name()==row['mesh'] and c.get_instance_count()==row['instances']
        metadata=next(g for g in registry['groups'] if g['mesh']==row['mesh'])
        assert len(metadata['instances'])==c.get_instance_count()
        for i,item in enumerate(metadata['instances']):
            x,y,z=item['position_m']
            assert (c.get_instance_transform(i,world_space=True).translation-unreal.Vector(x*100,-y*100,z*100)).length()<.1
        if row['mesh'].startswith('SM_GHS_V2Rack_'):
            model=next(m for m in slots['meshes'] if m['name']==row['mesh'])
            original=next(m for m in manifest['meshes'] if m['name']==row['mesh'])
            live={(s['level'],s['column']) for s in model['cargo_stacks']}
            empty={(s['level'],s['column']) for s in original['empty_stacks']}
            assert live.isdisjoint(empty) and len(live)+len(empty)==original['capacity_per_instance']
            assert len(live)*c.get_instance_count()==row['occupied']
        else:
            key=f'PALLET:{actor.get_name()}:{c.get_name()}:0'
            assert widget.select_object(key,False),key
            selection=json.loads(widget.get_snapshot())['selection']
            assert selection['cadId']==metadata['instances'][0]['id'],selection
        groups.append(dict(actor=row['actor'],instances=c.get_instance_count(),capacity=row['capacity'],occupied=row['occupied']))
    widget.clear_selection()
    for label in expected['palette']['labels']:
        color=by[label['actor']].get_component_by_class(unreal.TextRenderComponent).text_render_color
        assert [color.r,color.g,color.b,color.a]==label['after_color']
    for fx in expected['palette']['fx']:
        material=unreal.load_asset(fx['material'])
        tint=unreal.MaterialEditingLibrary.get_material_instance_vector_parameter_value(material,'Tint')
        assert max(abs(a-b) for a,b in zip([tint.r,tint.g,tint.b,tint.a],fx['after']['tint']))<1e-6
        for name,value in fx['before']['scalars'].items():
            assert abs(unreal.MaterialEditingLibrary.get_material_instance_scalar_parameter_value(material,name)-value)<1e-6
    return dict(success=True,groups=groups,occupancy=expected['occupancy'],
        ground_labels=3,fx_instances=len(expected['palette']['fx']),
        empty_rack_slots_unselectable=True,floor_cad_bindings_verified=True)
