"""Read-only preservation check for the additive GHS campus scene.

Run through live_dispatcher.py after importing and saving the campus. Never
recapture scene_inspection.json after the change: it is the pre-change baseline.
This helper does not save, move, hide, or select any actor.
"""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import traceback


ROOT = Path('D:/UEPro/Test')
OUT = ROOT / 'Saved/ParkExpansion'
MAP = '/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
PREFIX = 'GHSPark_'
CONTEXT_TAG = 'GHS_ParkContext'
CAMERA_LABEL = 'GHS_WarehouseCamera'
BASELINE = OUT / 'scene_inspection.json'
SOURCE_BASELINE = OUT / 'source_map_baseline.json'
PRE_IMPORT_CHANGES = OUT / 'pre_import_changes.json'
MANIFEST = ROOT / 'SourceAssets/GHS/Park/park_manifest.json'
ASSET_ROOT = '/Game/GHSZcoolSmartFactory/Park'
REPORT = OUT / 'validation.json'
BUSINESS_TAGS = {
    'GHSDigitalTwin', 'IndependentDockTruck', 'NormalWarehouseMannedForklift',
    'NormalWarehouseFloorStacker', 'AGVAnimatedFX',
}
BUSINESS_PREFIXES = ('TwinId=', 'Dock=', 'FXOwner=')


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def xyz(value):
    return [round(float(value.x), 4), round(float(value.y), 4),
            round(float(value.z), 4)]


def xf(transform):
    return dict(
        position=xyz(transform.translation), scale=xyz(transform.scale3d),
        rotation=[round(float(value), 6) for value in (
            transform.rotation.x, transform.rotation.y,
            transform.rotation.z, transform.rotation.w)])


def snapshot(actor, unreal):
    """Use the same rounding and serialization as inspect_park_scene.py."""
    row = dict(label=actor.get_actor_label(),
               actor_class=actor.get_class().get_path_name(),
               transform=xf(actor.get_actor_transform()),
               tags=[str(tag) for tag in actor.tags], components=[])
    for component in actor.get_components_by_class(unreal.StaticMeshComponent):
        item = dict(
            name=component.get_name(),
            mesh=component.static_mesh.get_path_name() if component.static_mesh else None,
            materials=[component.get_material(i).get_path_name()
                       if component.get_material(i) else None
                       for i in range(component.get_num_materials())],
            transform=xf(component.get_world_transform()))
        if isinstance(component, unreal.InstancedStaticMeshComponent):
            transforms = [xf(component.get_instance_transform(i, world_space=True))
                          for i in range(component.get_instance_count())]
            item.update(count=len(transforms), instances_sha256=hashlib.sha256(
                json.dumps(transforms, sort_keys=True).encode()).hexdigest())
        row['components'].append(item)
    return row


def index_unique(rows, description):
    counts = Counter(row['label'] for row in rows)
    duplicates = sorted(label for label, count in counts.items() if count != 1)
    assert not duplicates, '{} has duplicate actor labels: {}'.format(description, duplicates)
    return {row['label']: row for row in rows}


def preservation_fields(row):
    # Bounds are derived, can include editor-only visuals, and are not the
    # preservation contract. Actual actor/component/instance transforms are.
    result = {key: row[key] for key in ('actor_class', 'tags')}
    is_camera = row['label'] == CAMERA_LABEL
    if not is_camera:
        result['transform'] = row['transform']
    components = []
    for component in sorted(row['components'], key=lambda value: value['name']):
        item = dict(component)
        if is_camera:
            item.pop('transform', None)
        components.append(item)
    result['components'] = components
    return result


def compare_preservation(before_rows, after_rows, commandlet=False):
    """Pure comparison; returns compact, actionable mismatches."""
    before = index_unique(before_rows, 'Baseline')
    after = index_unique(after_rows, 'Current scene')
    errors = []
    for label, old in before.items():
        if label not in after:
            errors.append({'label': label, 'reason': 'Original actor is missing'})
            continue
        expected = preservation_fields(old)
        actual = preservation_fields(after[label])
        if commandlet and (old['actor_class'] == '/Script/Engine.CameraActor' or label == CAMERA_LABEL):
            # Camera editor preview meshes are created only when rendering is
            # available; NullRHI commandlets omit them entirely. Do not mask a
            # changed component that is present, or any warehouse geometry.
            present = {part['name'] for part in actual['components']}
            expected['components'] = [part for part in expected['components']
                if part['name'] in present or part['mesh'] != '/Engine/EditorMeshes/MatineeCam_SM.MatineeCam_SM']
        for key in expected:
            if expected[key] != actual[key]:
                errors.append({'label': label, 'reason': 'Changed ' + key})
    for label in sorted(set(after) - set(before)):
        row = after[label]
        if not label.startswith(PREFIX) or CONTEXT_TAG not in row['tags']:
            errors.append({'label': label, 'reason': 'Unowned new actor'})
    return errors


def camera_properties(actor):
    values = {}
    for key in ('overview_center', 'overview_distance', 'overview_pitch',
                'overview_yaw', 'maximum_pan', 'maximum_zoom'):
        value = actor.get_editor_property(key)
        if hasattr(value, 'z'):
            value = xyz(value)
        elif hasattr(value, 'x'):
            value = [float(value.x), float(value.y)]
        else:
            value = float(value)
        values[key] = value
    return values


def effective_baseline(baseline, current_rows):
    """Honor only the separately evidenced title deletion before our import."""
    if not PRE_IMPORT_CHANGES.exists():
        return baseline['actors'], []
    changes = read(PRE_IMPORT_CHANGES)
    assert changes['version'] == 1 and changes['map'] == MAP
    assert changes['baseline_sha256'] == sha(BASELINE), 'Pre-import change evidence belongs to another baseline'
    removals = changes['removed_before_import']
    assert len(removals) == 1 and removals[0]['label'] == 'GHS_SiteTitle', \
        'Only the independently evidenced pre-import SiteTitle deletion is permitted'
    removal = removals[0]
    assert removal['observed_delete_utc'] == '2026-10-21T11:24:34.955Z'
    assert removal['baseline_capture_utc'] == '2026-10-21T11:21:48.033Z'
    assert removal['first_import_utc'] == '2026-10-21T11:40:17.388Z'
    assert 'Deleted Actor: TextRenderActor' in '\n'.join(removal['log_evidence'])
    originals = index_unique(baseline['actors'], 'Baseline')
    assert originals['GHS_SiteTitle']['actor_class'] == '/Script/Engine.TextRenderActor'
    assert not any(row['label'] == 'GHS_SiteTitle' for row in current_rows), \
        'The pre-import user-deleted title was unexpectedly restored'
    return [row for row in baseline['actors'] if row['label'] != 'GHS_SiteTitle'], removals


def main():
    import unreal

    OUT.mkdir(parents=True, exist_ok=True)
    report = dict(success=False, map=MAP, validation_scope='saved editor scene',
                  started_utc=datetime.now(timezone.utc).isoformat(),
                  writes_scene=False, visual_review_required=True,
                  runtime_performance_measured=False)
    try:
        baseline = read(BASELINE)
        assert baseline.get('success'), 'Pre-change scene inspection is not successful'
        assert baseline['map'].split('.')[0] == MAP, 'Wrong baseline map'
        assert not baseline['pie'], 'Baseline was captured during PIE'
        assert not baseline['dirty_maps'], 'Baseline map was not saved'
        assert not any(row['label'].startswith(PREFIX) for row in baseline['actors']), \
            'Baseline has already been replaced with an expanded scene'
        report['baseline_sha256'] = sha(BASELINE)
        editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        assert editor.get_editor_world().get_path_name().split('.')[0] == MAP, 'Wrong current map'
        # UE 5.4's IsInPlayInEditor dereferences GUnrealEd, which is null in a
        # Python commandlet. A commandlet has no PIE session or Slate viewport.
        commandlet = '-run=pythonscript' in unreal.SystemLibrary.get_command_line().lower()
        if not commandlet:
            assert not levels.is_in_play_in_editor(), 'Exit PIE before scene preservation validation'
        dirty_maps = [package.get_path_name() for package in
                      unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()]
        report['dirty_maps'] = dirty_maps
        assert MAP not in dirty_maps, 'Save the expanded map before validation'

        current_actors = list(actors.get_all_level_actors())
        current_rows = [snapshot(actor, unreal) for actor in current_actors]
        checked_baseline, pre_import_removals = effective_baseline(baseline, current_rows)
        report['pre_import_user_changes_preserved'] = pre_import_removals
        mismatches = compare_preservation(checked_baseline, current_rows, commandlet=commandlet)
        report['absent_editor_camera_visuals_excluded_in_nullrhi'] = commandlet
        report['preservation_mismatches'] = mismatches
        assert not mismatches, 'Original scene changed: ' + json.dumps(mismatches, ensure_ascii=False)
        originals = {row['label'] for row in baseline['actors']}
        additions = [actor for actor in current_actors if actor.get_actor_label() not in originals]
        assert additions, 'No campus actors were added'
        groups = Counter()
        meshes = Counter()
        manifest = read(MANIFEST)
        expected_meshes = {row['name']: row for row in manifest['meshes']}
        assert len(expected_meshes) == manifest['asset_count']
        park_meshes = Counter()
        capture_cameras = []
        instances = 0
        added_rows = []
        for actor in additions:
            label = actor.get_actor_label()
            tags = [str(tag) for tag in actor.tags]
            assert label.startswith(PREFIX) and CONTEXT_TAG in tags, label + ': missing ownership'
            assert not any(tag in BUSINESS_TAGS or tag.startswith(BUSINESS_PREFIXES)
                           for tag in tags), label + ': business identity on context geometry'
            assert not actor.get_actor_enable_collision(), label + ': actor collision enabled'
            assert not actor.is_actor_tick_enabled(), label + ': actor Tick enabled'
            if isinstance(actor, unreal.CameraActor):
                capture_cameras.append(label)
            groups[actor.get_class().get_path_name()] += 1
            item = dict(label=label, tags=tags, collision=False, tick=False, components=[])
            for component in actor.get_components_by_class(unreal.PrimitiveComponent):
                assert component.get_collision_enabled() == unreal.CollisionEnabled.NO_COLLISION, \
                    label + '/' + component.get_name() + ': component collision enabled'
                part = dict(name=component.get_name(), collision='NoCollision',
                            mobility=str(component.get_editor_property('mobility')))
                if isinstance(component, unreal.StaticMeshComponent):
                    mesh = component.static_mesh
                    assert mesh, label + ': empty static mesh component'
                    part['mesh'] = mesh.get_path_name()
                    meshes[part['mesh']] += 1
                    name = mesh.get_name()
                    if name in expected_meshes:
                        mesh_path = ASSET_ROOT + '/Meshes/' + name + '.' + name
                        material_name = 'M_GHSPark_' + expected_meshes[name]['role']
                        material_path = ASSET_ROOT + '/Materials/' + material_name + '.' + material_name
                        assert part['mesh'] == mesh_path, (label, part['mesh'], mesh_path)
                        assert component.get_num_materials() == 1, label + ': unexpected material slots'
                        actual = component.get_material(0)
                        saved = mesh.get_material(0)
                        assert actual and actual.get_path_name() == material_path, (label, 'Component material mismatch', material_path)
                        assert saved and saved.get_path_name() == material_path, (label, 'Mesh material mismatch', material_path)
                        part['material'] = material_path
                        park_meshes[name] += 1
                    else:
                        assert isinstance(actor, unreal.CameraActor), (label, 'Mesh absent from park manifest', name)
                if isinstance(component, unreal.InstancedStaticMeshComponent):
                    part['instance_count'] = component.get_instance_count()
                    assert part['instance_count'] > 0, label + ': empty instance group'
                    instances += part['instance_count']
                item['components'].append(part)
            added_rows.append(item)
        assert park_meshes == Counter({name: 1 for name in expected_meshes}), (dict(park_meshes), list(expected_meshes))
        assert len(capture_cameras) == 3 and len(additions) == len(expected_meshes) + 3, \
            ('Unexpected park mesh/camera actor count', len(additions), capture_cameras)

        source = read(SOURCE_BASELINE)
        source_path = Path(source['path'])
        expected_source = ROOT / 'Content/Maps/GHS_CAD_NormalWarehouse.umap'
        assert source_path.resolve() == expected_source.resolve(), 'Unexpected original map hash target'
        assert sha(source_path) == source['sha256'], 'Original NormalWarehouse map bytes changed'
        current_by_label = {actor.get_actor_label(): actor for actor in current_actors}
        camera = camera_properties(current_by_label[CAMERA_LABEL])
        assert camera['maximum_zoom'] == 95000., 'Defaults-only zoom cap was changed'
        report.update(
            success=True, original_actor_count=len(originals),
            checked_original_actor_count=len(checked_baseline),
            checked_original_actor_transforms_materials_tags_instances_preserved=True,
            permitted_changed_actor=CAMERA_LABEL,
            camera=camera, manifest_material_bindings_verified=True,
            park_mesh_component_counts=dict(park_meshes), capture_cameras=capture_cameras,
            original_source_map_sha256=source['sha256'], original_source_map_preserved=True,
            current_map_sha256=sha(ROOT / 'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'),
            total_actor_count=len(current_actors), added_actor_count=len(additions),
            added_instanced_mesh_instances=instances, added_actor_classes=dict(groups),
            added_mesh_component_uses=dict(meshes), added_actors=added_rows,
            saved_current_map=True)
    except Exception:
        report['success'] = False
        report['error'] = traceback.format_exc()
        unreal.log_error(report['error'])
    report['finished_utc'] = datetime.now(timezone.utc).isoformat()
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    assert report['success'], report.get('error', 'Campus validation failed')
    unreal.log('GHS_PARK_VALIDATION_COMPLETE ' + str(REPORT))


if __name__ == '__main__':
    main()
