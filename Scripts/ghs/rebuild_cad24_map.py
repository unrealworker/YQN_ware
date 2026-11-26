"""Apply prepared CAD 2.4 manifests, verify instance transforms and save the GHS level."""
import json
import sys
from pathlib import Path
import unreal

ROOT = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
sys.path.insert(0,str(ROOT / 'Scripts/ghs'))
from apply_cad24_racks import apply_racks, MAP
from cad24_floor import apply_ground, DATA, read
from apply_refinement_v2 import transform


def check_scene():
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    cap = read(DATA/'storage-capacity.json')
    scene = read(DATA/'scene-bindings.json')
    groups = {g['actor']:g for g in scene['groups']}
    prepared = {}
    for actor in actors.get_all_level_actors():
        for comp in actor.get_components_by_class(unreal.InstancedStaticMeshComponent):
            if comp.static_mesh and comp.static_mesh.get_name().startswith(('SM_GHS_V2Rack_','SM_GHS_Presentation_Cargo')):
                tag = actor.get_actor_label()
                assert tag not in prepared and 'GHSStorageGroup:'+tag in map(str,comp.component_tags), tag
                prepared[tag] = comp
    assert set(prepared)=={g['actor'] for g in cap['groups']}, sorted(prepared)
    for g in cap['groups']:
        comp = prepared[g['actor']]
        mesh = comp.static_mesh
        records = groups[g['actor']]['instances']
        assert comp.get_instance_count()==len(records)==g['count'] and mesh.get_name()==g['mesh']
        for i,row in enumerate(records):
            expected = transform(row)
            actual = comp.get_instance_transform(i,True)
            assert (expected.translation-actual.translation).length()<.1, row['id']
            assert (expected.scale3d-actual.scale3d).length()<.0001, row['id']
            assert expected.rotation.angular_distance(actual.rotation)<.001, row['id']
    return {g['actor']:g['count'] for g in cap['groups']}


def main():
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
    if editor.get_editor_world().get_path_name().split('.')[0] != MAP:
        assert levels.load_level(MAP)
    # Commandlets do not initialize GUnrealEd, which IsInPlayInEditor dereferences.
    assert editor.get_game_world() is None
    apply_racks()
    apply_ground()
    counts = check_scene()
    assert levels.save_current_level()
    output = ROOT/'Saved/GHS_CAD24/map-verified.json'
    output.parent.mkdir(exist_ok=True,parents=True)
    output.write_text(json.dumps(counts,indent=2),encoding='utf8')
    unreal.log('GHS CAD 2.4 saved '+str(output))


if __name__=='__main__':
    main()
