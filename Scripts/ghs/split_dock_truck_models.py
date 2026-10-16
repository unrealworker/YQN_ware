"""Replace only the truck HISM with individually editable native mesh placements."""
import copy
import hashlib
import json
import shutil
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import unreal

ROOT = Path(r'D:\UEPro\Test')
sys.path.insert(0, str(ROOT / 'Scripts/ghs'))
from sync_wall_heights import snapshot, transform, normalized

MAPS = ['/Game/Maps/GHS_CAD_DigitalTwin', '/Game/Maps/GHS_CAD_NormalWarehouse']
REGS = ['SourceAssets/GHS/ue_scene_registry.json', 'SourceAssets/GHS_Normal/ue_scene_registry.json',
        'SourceAssets/GHS/Presentation/visual_layout.json']
TARGET = 'GHS_V2_WaitingDockTrucks'
FOLDER = 'GHS/Vehicles/LoadingTrucks'
REPORT = ROOT / 'Saved/GHS_TruckModelsSplit.json'
VERIFY = ROOT / 'Saved/GHS_TruckModelsSplitVerification.json'
LEVELS = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
ACTORS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
EDITOR = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)


def read(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def write(p, value): Path(p).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def labels(): return {a.get_actor_label(): a for a in ACTORS.get_all_level_actors()}
def content_state(): return {p.relative_to(ROOT).as_posix(): sha(p) for p in (ROOT/'Content').rglob('*') if p.is_file()}
def map_file(scene): return 'Content/Maps/' + scene.rsplit('/', 1)[-1] + '.umap'


def revised_registry(old, state):
    data = copy.deepcopy(old)
    data['groups'] = [g for g in data['groups'] if g['actor'] != TARGET]
    data['individuals'].extend(state['models'])
    data['presentation'].update(expected_actor_count=state['actor_count'],
                                expected_hism_group_count=state['hism_group_count'],
                                expected_instance_count=state['hism_instance_count'])
    data['truck_models_split'] = dict(version=1, count=len(state['models']), folder=FOLDER,
        source_group=TARGET, representation='independent_native_static_mesh_placements',
        shared_mesh_asset=True, blueprint_created=False, report=str(REPORT))
    return data


def close_transform(actual, expected):
    for key in ('position_cm', 'scale', 'rotation_deg'):
        assert len(actual[key]) == len(expected[key])
        for a, b in zip(actual[key], expected[key]):
            error = abs(a-b) if key != 'rotation_deg' else abs((a-b+180) % 360 - 180)
            assert error < .001, (key, a, b)


def validate_map(state, before, by):
    after = snapshot(by)
    assert TARGET not in by
    expected_names = set(before) - {TARGET}
    truck_names = {m['id'] for m in state['models']}
    assert set(by) == expected_names | truck_names
    assert all(a.get_class().get_name() != 'GroupActor' for a in by.values()), 'Unexpected editor group'
    for name in expected_names:
        assert after[name] == before[name], 'Unrelated scene object changed: ' + name
    source = before[TARGET]
    for model in state['models']:
        a = by[model['id']]
        assert a.get_class() == unreal.StaticMeshActor.static_class(), model['id']
        assert a.get_attach_parent_actor() is None, model['id'] + ' attached'
        assert str(a.get_folder_path()) == FOLDER
        component = a.get_component_by_class(unreal.StaticMeshComponent)
        assert component and not isinstance(component, unreal.InstancedStaticMeshComponent)
        close_transform(transform(a.get_actor_transform()), model['world_transform'])
        assert after[model['id']]['mesh'] == source['mesh']
        assert after[model['id']]['materials'] == source['materials']
        assert after[model['id']]['hidden'] == source['hidden']
        for prop in ('visible', 'hidden_in_game', 'cast_shadow', 'mobility'):
            assert after[model['id']]['mesh_properties'][prop] == source['mesh_properties'][prop]
        assert str(component.get_collision_profile_name()) == state['collision_profile']
    assert len(by) == state['actor_count']
    hisms = [a.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent) for a in by.values()]
    hisms = [c for c in hisms if c]
    assert len(hisms) == state['hism_group_count']
    assert sum(c.get_instance_count() for c in hisms) == state['hism_instance_count']
    return dict(map=state['map'], independent_trucks=len(truck_names), actors=len(by),
                unchanged_other_objects=len(expected_names), materials_and_transforms_preserved=True,
                no_blueprint_no_parent_no_group=True)


def run(headless=False):
    assert not REPORT.exists(), 'Already applied; verify or review the existing report before a further edit.'
    current = MAPS[-1] if headless else EDITOR.get_editor_world().get_path_name().split('.')[0]
    # Holding a UPackage Python reference across LoadLevel prevents GC in UE 5.4.
    dirty = [p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()]
    assert all(p == current for p in dirty) and (not dirty or current in MAPS), 'Unrelated dirty level; do not unload it.'
    camera = None if headless else EDITOR.get_level_viewport_camera_info()
    backup = ROOT/'Saved/Backups'/('GHS_TruckModelsSplit_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
    backup.mkdir(parents=True)
    for scene in MAPS:
        relative = map_file(scene)
        destination = backup/'disk_before_user_save'/relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/relative, destination)
    if dirty:
        write(backup/'current_unsaved_scene_preserved.json', snapshot(labels()))
        assert LEVELS.save_current_level(), 'Could not preserve current user edits'
    report = dict(success=False, backup_root=str(backup), maps=[], files={}, initial_map=current,
                  preserved_current_user_edits=bool(dirty))
    content_before = content_state()
    write(backup/'content_hashes.json', content_before)
    history = {p.relative_to(ROOT).as_posix(): sha(p) for p in (ROOT/'Saved').glob('GHS_*.json')}
    write(backup/'historical_reports.json', history)
    for relative in [map_file(m) for m in MAPS] + REGS:
        dest = backup/relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/relative, dest)
        report['files'][relative] = dict(before_sha256=sha(ROOT/relative), backup=str(dest))
    # Preflight and snapshot both maps before modifying either.
    for scene, relative in zip(MAPS, REGS[:2]):
        assert LEVELS.load_level(scene)
        by = labels()
        source = by[TARGET].get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
        group = next(g for g in read(ROOT/relative)['groups'] if g['actor'] == TARGET)
        assert source and source.get_instance_count() == group['count'] == 87
        assert not any(n.startswith('GHS_DockTruck_') for n in by)
        write(backup/(scene.rsplit('/',1)[-1]+'_before.json'), snapshot(by))
    write(REPORT, report)
    try:
        for scene, relative in zip(MAPS, REGS[:2]):
            assert LEVELS.load_level(scene)
            by = labels()
            before = read(backup/(scene.rsplit('/',1)[-1]+'_before.json'))
            source_actor = by[TARGET]
            source = source_actor.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
            mesh = source.get_editor_property('static_mesh')
            materials = [source.get_material(i) for i in range(source.get_num_materials())]
            transforms = [source.get_instance_transform(i, world_space=True) for i in range(source.get_instance_count())]
            old = read(ROOT/relative)
            group = next(g for g in old['groups'] if g['actor'] == TARGET)
            state = dict(map=scene, models=[], actor_count=len(by)-1+len(transforms),
                         hism_group_count=len(old['groups'])-1,
                         hism_instance_count=sum(g['count'] for g in old['groups'])-len(transforms),
                         collision_profile=str(source.get_collision_profile_name()))
            for index, (t, row) in enumerate(zip(transforms, group['instances'])):
                name = f'GHS_DockTruck_{index+1:03d}'
                a = ACTORS.spawn_actor_from_class(unreal.StaticMeshActor, t.translation, t.rotation.rotator())
                assert a
                a.set_actor_label(name)
                a.set_folder_path(FOLDER)
                a.set_editor_property('tags', ['GHSDigitalTwin', 'IndependentDockTruck', 'TwinId='+name, 'Dock='+row['dock_number'], 'Door='+row['door_id']])
                a.set_actor_hidden_in_game(source_actor.get_editor_property('hidden'))
                a.set_actor_scale3d(t.scale3d)
                c = a.get_component_by_class(unreal.StaticMeshComponent)
                c.set_mobility(source.get_editor_property('mobility'))
                c.set_static_mesh(mesh)
                for i, material in enumerate(materials): c.set_material(i, material)
                c.set_collision_profile_name(source.get_collision_profile_name())
                for prop in ('visible', 'hidden_in_game', 'cast_shadow', 'receives_decals', 'render_custom_depth', 'translucency_sort_priority'):
                    c.set_editor_property(prop, source.get_editor_property(prop))
                world = transform(t)
                model = copy.deepcopy(row)
                model.update(id=name, source_instance_id=row['id'], mesh=mesh.get_name(), mesh_path=mesh.get_path_name(),
                             position_m=[world['position_cm'][0]/100, -world['position_cm'][1]/100, world['position_cm'][2]/100],
                             rotation_deg=-world['rotation_deg'][1], scale=world['scale'], folder='Vehicles/LoadingTrucks',
                             world_transform=world, material_overrides=[m.get_path_name() for m in materials])
                state['models'].append(model)
            assert ACTORS.destroy_actor(source_actor)
            by = labels()
            validate_map(state, before, by)
            # Exercise independent movement, then restore exactly before saving.
            first = by[state['models'][0]['id']]
            others = snapshot({k:v for k,v in by.items() if v != first})
            original = first.get_actor_transform()
            moved = first.get_actor_location() + unreal.Vector(100, 0, 0)
            first.set_actor_location(moved, sweep=False, teleport=True)
            assert abs(first.get_actor_location().x-moved.x) < .001
            assert snapshot({k:v for k,v in by.items() if v != first}) == others
            first.set_actor_transform(original, sweep=False, teleport=True)
            validate_map(state, before, by)
            ACTORS.set_selected_level_actors([])
            assert LEVELS.save_current_level()
            state['independent_move_and_restore_verified'] = True
            report['maps'].append(state)
            write(REPORT, report)
        for relative in REGS:
            state = report['maps'][1 if 'GHS_Normal/' in relative else 0]
            write(ROOT/relative, revised_registry(read(report['files'][relative]['backup']), state))
        after = content_state()
        assert set(after) == set(content_before), 'Unexpected created or deleted assets'
        changed = [p for p in after if after[p] != content_before[p]]
        assert set(changed) == {map_file(m) for m in MAPS}, changed
        for relative, entry in report['files'].items(): entry['after_sha256'] = sha(ROOT/relative)
        for relative, digest in history.items(): assert sha(ROOT/relative) == digest
        report.update(success=True, changed_content=changed, no_mesh_or_material_assets_modified=True,
                      completed_utc=datetime.now(timezone.utc).isoformat())
        if current != MAPS[-1]: assert LEVELS.load_level(current)
        if camera: EDITOR.set_level_viewport_camera_info(*camera)
        unreal.log('GHS_TRUCK_MODELS_SPLIT_SAVED: 87 independent static mesh placements in each of 2 maps')
    except Exception:
        report['error'] = traceback.format_exc()
        raise
    finally:
        write(REPORT, report)


def verify():
    result = dict(success=False, maps=[])
    try:
        report = read(REPORT)
        assert report['success']
        backup = Path(report['backup_root'])
        disk_before = content_state()
        baseline = read(backup/'content_hashes.json')
        assert set(disk_before) == set(baseline)
        for relative, digest in baseline.items():
            assert disk_before[relative] == report['files'].get(relative, {}).get('after_sha256', digest), relative
        for relative, item in report['files'].items():
            assert sha(item['backup']) == item['before_sha256'] and sha(ROOT/relative) == item['after_sha256'], relative
        for state in report['maps']:
            assert LEVELS.load_level(state['map'])
            before = normalized(read(backup/(state['map'].rsplit('/',1)[-1]+'_before.json')))
            result['maps'].append(validate_map(state, before, labels()))
            assert state['independent_move_and_restore_verified']
        for relative in REGS:
            state = report['maps'][1 if 'GHS_Normal/' in relative else 0]
            assert read(ROOT/relative) == revised_registry(read(report['files'][relative]['backup']), state)
        for relative, digest in read(backup/'historical_reports.json').items(): assert sha(ROOT/relative) == digest
        assert content_state() == disk_before
        result.update(success=True, saved_maps_reloaded=True, independent_movement_verified=True,
                      unrelated_content_unchanged=True, shared_mesh_assets_preserved=True,
                      completed_utc=datetime.now(timezone.utc).isoformat())
        unreal.log('GHS_TRUCK_MODELS_SPLIT_VERIFIED: both maps saved; 174 independently editable trucks; no other scene changes')
    except Exception:
        result['error'] = traceback.format_exc()
        raise
    finally:
        write(VERIFY, result)


if __name__ == '__main__':
    run()
