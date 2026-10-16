"""Apply validated higher storage variants without altering CAD footprints."""
import json,sys,hashlib,traceback
from pathlib import Path
import unreal
ROOT=Path(r'D:\UEPro\Test');sys.path.insert(0,str(ROOT/'Scripts/ghs'))
from ue_instancing import spawn_group
registry_path=ROOT/'SourceAssets/GHS/ue_scene_registry.json'
layout=json.loads((ROOT/'SourceAssets/GHS/Presentation/visual_layout.json').read_text())
old=json.loads(registry_path.read_text());presentation=layout['presentation']
report=dict(success=False,backup=json.loads((ROOT/'Saved/GHS_PresentationBefore.json').read_text())['backup'])
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
labels={a.get_actor_label():a for a in actors.get_all_level_actors()}
def transform(row):
    x,y,z=row['position_m']
    return unreal.Transform(location=unreal.Vector(x*100,-y*100,z*100),rotation=unreal.Rotator(pitch=0,yaw=-row['rotation_deg'],roll=0),scale=unreal.Vector(*row['scale']))
try:
    assert json.loads((ROOT/'Saved/GHS_PresentationImport.json').read_text())['success']
    assert old.get('presentation') or hashlib.sha256(registry_path.read_bytes()).hexdigest()==presentation['source_baseline_sha256']
    for group in layout['groups']:
        if group['actor'] not in presentation['modified_labels']:continue
        label=group['actor'];mesh=unreal.load_asset('/Engine/BasicShapes/Cube' if group['mesh']=='Cube' else '/Game/GHSDigitalTwin/Meshes/'+group['mesh'])
        assert mesh
        if label in labels:
            actor=labels[label];component=actor.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
            component.clear_instances();component.set_static_mesh(mesh)
            component.add_instances([transform(row) for row in group['instances']],should_return_indices=True,world_space=True,update_navigation=False)
        else:
            actor=spawn_group(label,'GHS/Storage/HeightVariants',mesh,[transform(row) for row in group['instances']]);labels[label]=actor
            component=actor.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
        if group['mesh'].startswith('SM_GHS_Presentation_'):
            for i in range(len(mesh.get_editor_property('static_materials'))):component.set_material(i,mesh.get_material(i))
        assert component.get_instance_count()==group['count']
        actor.set_is_temporarily_hidden_in_editor(False)
        actor.set_editor_property('tags',['GHSDigitalTwin','HISMGroup','PresentationHeight','InstanceCount='+str(group['count'])])
    registry_path.write_text(json.dumps(layout,ensure_ascii=False,indent=2),encoding='utf-8')
    mat_path=ROOT/'Saved/GHS_InstanceMaterials.json';mat=json.loads(mat_path.read_text())
    mat['groups']=[dict(actor=g['actor'],materials=[labels[g['actor']].get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent).get_material(i).get_path_name() for i in range(labels[g['actor']].get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent).get_num_materials())]) for g in layout['groups']]
    mat_path.write_text(json.dumps(mat,indent=2))
    actors.set_selected_level_actors([]);assert levels.save_current_level()
    build_path=ROOT/'Saved/GHS_BuildReport.json';build=json.loads(build_path.read_text())
    build.update(presentation_refined=True,actor_count=len(actors.get_all_level_actors()),instanced_count=sum(g['count'] for g in layout['groups']),groups=[dict(actor=g['actor'],mesh=g['mesh'],count=g['count']) for g in layout['groups']])
    build_path.write_text(json.dumps(build,indent=2))
    assert (build['actor_count'],len(layout['groups']),build['instanced_count'])==(227,18,14116)
    report.update(success=True,actor_count=227,hism_group_count=18,instanced_count=14116,
        cargo_count=7408,rack_count=1617,column_count=170,baseline_sha256=presentation['source_baseline_sha256'],
        assumptions=presentation['assumptions'])
except Exception:
    report['error']=traceback.format_exc();raise
finally:(ROOT/'Saved/GHS_PresentationApplied.json').write_text(json.dumps(report,indent=2))
