"""Translate existing MPR rack instances by the independently reviewed row plan.

No instances, actors, meshes, materials, or runtime settings are recreated.
Apply only in the current live editor world. An owned Python commandlet using
-MPRRackClearanceVerify independently reloads the saved map without saving it.
Use --offline-check outside UE to validate the complete mutation whitelist.
"""
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
import json
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
import rebuild_preservation as guard
import mpr_scene_patch_guard as patch
import refine_mpr_interior_cad_20261112 as prior

MAP = patch.MAP
MAP_REL = 'Content/Maps/MPR_CAD_Warehouse_B50B57.umap'
BASE = ROOT/'Saved/MPR/optimization_20261112'
OUT = BASE/'rack_clearance'
SOURCE = ROOT/'SourceAssets/MPR/rack_clearance_20261112'
PLAN = SOURCE/'placement_plan.json'
VALIDATION = SOURCE/'validation.json'
IDENTITY = dict(translation_cm=[0., 0., 0.], rotation_xyzw=[0., 0., 0., 1.], scale=[1., 1., 1.])


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def actor_records(snapshot, *, commandlet=False):
    rows = snapshot['actors']
    result = {a['guid']: patch.normalize(a, commandlet_compat=commandlet) for a in rows}
    require(len(result) == len(rows), 'Duplicate actor GUIDs in preservation capture')
    return result


def reviewed_inputs():
    """Only read files; this preflight also runs under ordinary Python."""
    before = patch.read(BASE/'baseline.json.gz')
    plan = patch.read(PLAN)
    validation = patch.read(VALIDATION)
    hashes = patch.read(BASE/'original_package_hashes.json')
    configuration = patch.read(BASE/'preserved_configuration.json')
    require(plan['schema_version'] == 1 and plan['status'] == 'geometry_verified', 'Unvalidated plan')
    require(validation['success'] and validation['plan_sha256'] == guard.sha(PLAN),
            'Independent geometry validation belongs to a different plan')
    require(before['map'] == plan['map'] == MAP, 'Unexpected target map')
    require(before['map_file_sha256'] == plan['map_sha256'] == validation['map_sha256'] == hashes[MAP_REL],
            'Map baseline and geometry evidence differ')
    require(len(configuration['simulation']) == 14 and len(configuration['viewport']) == 6,
            'Incomplete original sorter/camera configuration')
    for relative, digest in plan['input_sha256'].items():
        source = (ROOT/relative).resolve()
        require(source.is_relative_to(ROOT.resolve()) and source.is_file(), 'Invalid source input '+relative)
        require(guard.sha(source) == digest, 'Reviewed input changed: '+relative)
    require(validation['rack_count'] == 2867 and validation['row_count'] == 109 and
            validation['column_positions'] == 303 and validation['door_openings'] == 154,
            'Incomplete geometric audit')
    require(validation['final_column_base_clearance_contacts'] == 0 and
            validation['new_fixed_obstacle_contacts'] == 0 and validation['cross_row_contacts'] == 0,
            'Geometric audit still has new intersections')
    return before, plan, hashes, configuration


def expected_scene(before, plan):
    """Build a closed whitelist from all 2867 existing GUID/component/index keys."""
    expected = actor_records(before)
    original = actor_records(before)
    rows = {row['row_id']: row for row in plan['rows']}
    require(len(rows) == len(plan['rows']) == 109, 'Duplicate/missing whole-row definitions')
    groups = defaultdict(list)
    row_members = defaultdict(set)
    handles = set()
    identities = set()
    moved = 0
    for change in plan['instances']:
        handle = change['source_handle']
        identity = (change['actor_guid'], change['component_name'], change['instance_index'])
        require(handle not in handles and identity not in identities, 'Duplicate planned rack instance')
        handles.add(handle)
        identities.add(identity)
        guid, component_name, index = identity
        require(guid in original, 'Missing planned actor '+guid)
        actor = original[guid]
        require(actor['label'] == change['actor_label'] and actor['folder'] == 'MPR/Storage/Racks',
                'Rack actor identity changed: '+handle)
        require(actor['class'] == '/Game/GHSDigitalTwin/Blueprints/BP_GHS_InstanceGroup.BP_GHS_InstanceGroup_C',
                'Unsupported actor class: '+handle)
        require(actor['transform'] == IDENTITY, 'Rack parent must retain its reviewed identity transform')
        matches = [c for c in actor['components'] if c['name'] == component_name]
        require(len(matches) == 1, 'Missing/duplicate rack component: '+handle)
        component = matches[0]
        require(component['class'] == '/Script/Engine.HierarchicalInstancedStaticMeshComponent',
                'Only existing HISM instances may move')
        require(component['transform'] == IDENTITY and component['mesh'] == change['mesh'],
                'Rack mesh/component transform changed: '+handle)
        require(type(index) is int and 0 <= index < component['instance_count'], 'Invalid rack instance index')
        old = component['instance_transforms'][index]
        target = change['proposed_transform']
        require(old == change['original_transform'], 'Original transform changed: '+handle)
        require(set(target) == set(old) == {'translation_cm', 'rotation_xyzw', 'scale'}, 'Unexpected pose fields')
        require(old['rotation_xyzw'] == target['rotation_xyzw'] and old['scale'] == target['scale'] and
                old['translation_cm'][2] == target['translation_cm'][2], 'Only horizontal translation is allowed')
        row = rows[change['row_id']]
        axis = row['axis']
        require(axis in (0, 1), 'Unexpected row movement axis')
        delta = [(target['translation_cm'][k]-old['translation_cm'][k])/100*(1 if k == 0 else -1)
                 for k in (0, 1)]
        require(abs(delta[axis]-row['shift_m']) < 1.e-10 and abs(delta[1-axis]) < 1.e-10,
                'Whole-row rigid displacement differs: '+handle)
        require(abs(delta[axis]) <= plan['policy']['maximum_shift_m']+1.e-10, 'Shift exceeds reviewed bound')
        require(all(abs(a-b) < 1.e-10 for a, b in zip(delta, change['displacement_cad_m'])),
                'CAD/UE coordinate conversion differs')
        if row['locked_due_to_unchanged_existing_equipment_contact']:
            require(old == target, 'Previously contacting equipment row must stay fixed')
        row_members[row['row_id']].add(handle)
        groups[(guid, component_name)].append(change)
        new_component = next(c for c in expected[guid]['components'] if c['name'] == component_name)
        # Whitelist exactly this field. Rotation, scale, count, index, material,
        # custom data, mesh and every actor/component property stay captured.
        new_component['instance_transforms'][index]['translation_cm'] = list(target['translation_cm'])
        moved += old['translation_cm'] != target['translation_cm']
    actual_keys = {(a['guid'], c['name'], i) for a in original.values() if a['folder'] == 'MPR/Storage/Racks'
                   for c in a['components'] if 'instance_transforms' in c
                   for i in range(c['instance_count'])}
    require(identities == actual_keys and len(identities) == len(plan['instances']) == 2867,
            'Plan must map every existing rack once, without creating or removing any')
    require(len(groups) == 59, 'Unexpected current rack component count')
    for row_id, row in rows.items():
        require(row_members[row_id] == set(row['source_handles']) and
                len(row_members[row_id]) == row['member_count'], 'Incomplete whole row '+row_id)
    require(moved == plan['summary']['moved_instances'] == 2392, 'Moved-instance count differs from geometry proof')
    require(sum(abs(row['shift_m']) > 1.e-10 for row in rows.values()) == plan['summary']['moved_rows'] == 91,
            'Moved-row count differs from geometry proof')
    return expected, groups


def validate_scene(before, actual, expected, *, commandlet=False):
    observed = actor_records(actual, commandlet=commandlet)
    if commandlet:
        expected = {guid: patch.normalize(row, commandlet_compat=True) for guid, row in expected.items()}
    require(set(observed) == set(expected), 'Actor creation/deletion outside the translation plan')
    errors = []
    for guid in sorted(expected):
        errors.extend(patch.differences(expected[guid], observed[guid], expected[guid]['label']))
    errors.extend(patch.differences(before['world_settings'], actual['world_settings'], 'world_settings'))
    errors.extend(patch.differences(
        patch.normalized_coverage(before['world_actor_coverage'], commandlet_compat=commandlet),
        patch.normalized_coverage(actual['world_actor_coverage'], commandlet_compat=commandlet), 'world_auxiliaries'))
    require(not errors, 'Unexpected scene delta: '+json.dumps(errors[:24], ensure_ascii=False))
    require(actual['map'] == MAP, 'Current map changed')


def protected_hism_properties(u, actors, groups):
    """Also compare native render/culling/override fields omitted by old snapshots."""
    result = {}
    fields = ('receives_decals', 'instance_start_cull_distance', 'instance_end_cull_distance',
              'min_lod', 'forced_lod_model', 'override_min_lod', 'cast_shadow')
    for guid, name in sorted(groups):
        components = [c for c in actors[guid].get_components_by_class(u.HierarchicalInstancedStaticMeshComponent)
                      if c.get_name() == name]
        require(len(components) == 1, 'Native rack component identity changed')
        component = components[0]
        result[guid+':'+name] = {
            **{key: component.get_editor_property(key) for key in fields},
            'override_materials': [m.get_path_name() if m else None
                                   for m in component.get_editor_property('override_materials')]}
    return result


def live_actors(u):
    actors = u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors()
    result = {u.GuidLibrary.conv_guid_to_string(a.get_editor_property('actor_guid')): a for a in actors}
    require(len(result) == len(actors), 'Duplicate live actor GUIDs')
    return result


def check_packages(original, *, map_changed):
    current = guard.content_hashes(ROOT)
    require(set(current) == set(original), 'No Content packages may be added or deleted by rack translation')
    changed = sorted(path for path, digest in original.items() if current[path] != digest)
    require(changed == ([MAP_REL] if map_changed else []), 'Unexpected Content changes: '+str(changed))
    return current


def apply(u):
    command = u.SystemLibrary.get_command_line().lower()
    require('-run=pythonscript' not in command, 'Apply in the existing editor; commandlet entry is read-only')
    require(not u.get_editor_subsystem(u.UnrealEditorSubsystem).get_game_world(), 'Exit PIE before applying rack placement')
    before, plan, hashes, configuration = reviewed_inputs()
    expected, groups = expected_scene(before, plan)
    require(not (OUT/'before.json.gz').exists(), 'A prior apply checkpoint exists; inspect it instead of overwriting')
    current = guard.capture(u, ROOT, MAP)
    guard.assert_clean(current)
    require(current['map_file_sha256'] == before['map_file_sha256'], 'Saved map changed after geometry audit')
    validate_scene(before, current, actor_records(before))
    require(prior.sim_properties(u) == configuration['simulation'], 'Original sorter configuration changed')
    require(prior.viewport(u) == configuration['viewport'], 'Review camera differs from the protected baseline')
    check_packages(hashes, map_changed=False)
    actors = live_actors(u)
    render_properties = protected_hism_properties(u, actors, groups)
    OUT.mkdir(parents=True, exist_ok=True)
    patch.write(OUT/'before.json.gz', current)
    patch.write(OUT/'protected_hism_properties.json', render_properties)
    patch.write(OUT/'reviewed_inputs.json', dict(plan_sha256=guard.sha(PLAN),
        validation_sha256=guard.sha(VALIDATION), baseline_sha256=guard.sha(BASE/'baseline.json.gz'),
        package_hashes_sha256=guard.sha(BASE/'original_package_hashes.json'),
        configuration_sha256=guard.sha(BASE/'preserved_configuration.json')))
    updated = 0
    try:
        with u.ScopedEditorTransaction('MPR货架整列侧移避柱并保留原设备工作区'):
            for (guid, name), changes in sorted(groups.items()):
                changes = [c for c in changes if c['original_transform']['translation_cm'] !=
                           c['proposed_transform']['translation_cm']]
                if not changes:
                    continue
                actor = actors[guid]
                component = next(c for c in actor.get_components_by_class(u.HierarchicalInstancedStaticMeshComponent)
                                 if c.get_name() == name)
                actor.modify()
                component.modify()
                for ordinal, change in enumerate(changes):
                    index = change['instance_index']
                    transform = component.get_instance_transform(index, world_space=False)
                    # Copy UE's original Transform and replace translation only;
                    # rebuilding it through Rotator can round existing quaternions.
                    require(not patch.differences(guard.interior._transform(transform), change['original_transform']),
                            'Instance changed immediately before mutation: '+change['source_handle'])
                    transform.translation = u.Vector(*change['proposed_transform']['translation_cm'])
                    require(component.update_instance_transform(index, transform, world_space=False,
                            mark_render_state_dirty=ordinal == len(changes)-1, teleport=True),
                            'HISM translation failed: '+change['source_handle'])
                    updated += 1
            require(updated == plan['summary']['moved_instances'], 'Not all reviewed instances were moved')
            after = guard.capture(u, ROOT, MAP)
            require(not after['dirty_content'] and set(after['dirty_maps']) <= {MAP}, 'An unrelated package became dirty')
            validate_scene(before, after, expected)
            require(protected_hism_properties(u, actors, groups) == render_properties, 'Rack rendering/material overrides changed')
            require(prior.sim_properties(u) == configuration['simulation'], 'Sorter configuration changed during apply')
            require(prior.viewport(u) == configuration['viewport'], 'Camera moved during apply')
            check_packages(hashes, map_changed=False)
            require(u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level(), 'Could not save the original map')
        after = guard.capture(u, ROOT, MAP)
        guard.assert_clean(after)
        validate_scene(before, after, expected)
        require(protected_hism_properties(u, actors, groups) == render_properties, 'Saved rack render properties changed')
        require(prior.sim_properties(u) == configuration['simulation'] and prior.viewport(u) == configuration['viewport'],
                'Saved sorter configuration or camera changed')
        now = check_packages(hashes, map_changed=True)
        require(now[MAP_REL] == after['map_file_sha256'], 'Saved map hash differs from scene capture')
        patch.write(OUT/'after.json.gz', after)
        report = dict(success=True, plan_sha256=guard.sha(PLAN), actors=len(after['actors']),
            rack_instances=2867, rack_components=len(groups), moved_rows=91, moved_instances=updated,
            maximum_shift_m=plan['summary']['maximum_displacement_m'],
            before_map_sha256=before['map_file_sha256'], map_sha256=after['map_file_sha256'],
            changed_packages=[MAP_REL], existing_other_packages_preserved=len(hashes)-1,
            existing_actor_and_instance_identities_preserved=True,
            only_instance_translation_changed=True, camera_unchanged=True, simulation_properties_unchanged=True,
            materials_meshes_lods_and_culling_unchanged=True, column_and_equipment_poses_unchanged=True,
            original_fixed_contacts_retained=plan['before']['fixed_contacts'])
        patch.write(OUT/'validation.json', report)
        print('MPR_RACK_CLEARANCE_SAVED '+json.dumps(report, ensure_ascii=False))
        return report
    except Exception:
        patch.write(OUT/'failure.json', dict(updated_instances=updated, error=traceback.format_exc(),
            note='No recovery or map reload was attempted. Inspect the existing transaction and saved checkpoint.'))
        raise


def verify_reload(u):
    command = u.SystemLibrary.get_command_line().lower()
    require('-run=pythonscript' in command and '-mprrackclearanceverify' in command,
            'Independent reload verification is read-only and commandlet-only')
    before, plan, hashes, configuration = reviewed_inputs()
    expected, groups = expected_scene(before, plan)
    report = patch.read(OUT/'validation.json')
    provenance = patch.read(OUT/'reviewed_inputs.json')
    require(report['success'] and report['plan_sha256'] == provenance['plan_sha256'] == guard.sha(PLAN),
            'Saved apply evidence is from a different plan')
    for filename, key in [(VALIDATION, 'validation_sha256'), (BASE/'baseline.json.gz', 'baseline_sha256'),
                          (BASE/'original_package_hashes.json', 'package_hashes_sha256'),
                          (BASE/'preserved_configuration.json', 'configuration_sha256')]:
        require(guard.sha(filename) == provenance[key], 'Apply provenance changed: '+str(filename))
    on_disk = check_packages(hashes, map_changed=True)
    require(on_disk[MAP_REL] == report['map_sha256'], 'Map changed since scoped save')
    require(u.EditorLoadingAndSavingUtils.load_map(MAP), 'Could not load the saved original map')
    actual = guard.capture(u, ROOT, MAP)
    guard.assert_clean(actual)
    validate_scene(before, actual, expected, commandlet=True)
    saved = patch.read(OUT/'after.json.gz')
    validate_scene(saved, actual, actor_records(saved), commandlet=True)
    require(actual['map_file_sha256'] == report['map_sha256'], 'Reloaded map hash differs')
    require(prior.sim_properties(u) == configuration['simulation'], 'Reload changed original sorter properties')
    require(protected_hism_properties(u, live_actors(u), groups) == patch.read(OUT/'protected_hism_properties.json'),
            'Reloaded rack render properties or material overrides differ')
    require(check_packages(hashes, map_changed=True) == on_disk, 'Read-only verification wrote Content')
    result = dict(success=True, map_sha256=actual['map_file_sha256'], plan_sha256=guard.sha(PLAN),
        actors=len(actual['actors']), rack_instances=2867, rack_components=len(groups),
        all_saved_actor_records_verified=True, original_sorter_configuration_preserved=True,
        camera_actor_settings_preserved=True, original_other_packages_preserved=len(hashes)-1,
        commandlet_read_only=True, editor_viewport_checked_during_apply=True)
    patch.write(OUT/'reload_validation.json', result)
    print('MPR_RACK_CLEARANCE_RELOAD_VERIFIED '+json.dumps(result, ensure_ascii=False))
    return result


def offline_check():
    before, plan, hashes, configuration = reviewed_inputs()
    expected, groups = expected_scene(before, plan)
    projected = deepcopy(before)
    projected['actors'] = list(expected.values())
    validate_scene(before, projected, expected)
    validate_scene(before, projected, expected, commandlet=True)
    result = dict(success=True, baseline_actors=len(expected), existing_rack_components=len(groups),
        original_content_packages=len(hashes), simulation_properties=len(configuration['simulation']),
        rack_instances=len(plan['instances']), moved_instances=plan['summary']['moved_instances'],
        whitelist='existing HISM instance translation only; native apply has not been run')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == '__main__':
    if '--offline-check' in sys.argv:
        offline_check()
    else:
        import unreal
        if '-mprrackclearanceverify' in unreal.SystemLibrary.get_command_line().lower():
            verify_reload(unreal)
        else:
            apply(unreal)
