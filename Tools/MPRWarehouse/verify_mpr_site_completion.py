"""Read-only verification of the currently open MPR map, without map reload/save.

Execute this file in the editor, or import it and call run(unreal). The stage is
read from Saved/MPR/site_completion_20261105/run_config.json. Ordinary Python
can import compare_snapshot for offline negative checks without loading Unreal.
"""
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import traceback

ROOT = Path(__file__).resolve().parents[2]
MAP = '/Game/Maps/MPR_CAD_Warehouse_B50B57'
SOURCE = 'SourceAssets/MPR/site_completion_20261105'
OUTPUT = 'Saved/MPR/site_completion_20261105'
OLD_TREE = '/Game/MPRWarehouse/ReferenceV4/Props/Meshes/SM_MPR4_Tree_Oak'
DEST = '/Game/MPRWarehouse/SiteComplete'
NEW_TREE = DEST+'/Meshes/SM_MPRSC_Tree_Canopy'
OLD_SITE = '/Game/MPRWarehouse/RebuildB50B57/Site/Meshes/'
PREFIXES = ('SM_MPRR_MainApron_', 'SM_MPRR_CampusGreen_',
            'SM_MPRR_ParkingLines_', 'SM_MPRR_DockLines_')
POSE_EXCEPTIONS = {'MPR4_KeyLight', 'MPR_ReviewCamera'}
TREE_ROLES = ['Bark', 'LeafMid', 'LeafLight', 'LeafShade']
OWNER = 'mpr-site-completion-round2-20261105'
POSITION_TOLERANCE_CM = .05
ROTATION_TOLERANCE_DEG = .002
SCALE_TOLERANCE = 1e-5
CAMERA_PROXY_OWNERS = {
    ('CameraActor_0', 'MPR_ReviewCamera', 'CameraActor'),
    ('BP_GHS_WarehouseCamera_C_0', 'MPR_WarehouseCamera', 'BP_GHS_WarehouseCamera_C'),
}


def read(path):
    path = Path(path)
    raw = gzip.decompress(path.read_bytes()) if path.suffix == '.gz' else path.read_bytes()
    return json.loads(raw.decode('utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def package(obj):
    return obj.get_path_name().split('.')[0] if obj else None


def xyz(vector):
    return [float(vector.x), float(vector.y), float(vector.z)]


def rotation(value):
    return [float(value.pitch), float(value.yaw), float(value.roll)]


def ue_position(point):
    return [100*point[0], -100*point[1], 100*point[2]]


def close(a, b, tolerance, angular=False):
    if len(a) != len(b):
        return False
    differences = [(x-y+180) % 360-180 if angular else x-y for x, y in zip(a, b)]
    return all(math.isfinite(v) and abs(v) <= tolerance for v in differences)


def is_old_site(mesh):
    return mesh.startswith(OLD_SITE) and mesh.rsplit('/', 1)[-1].startswith(PREFIXES)


def native_camera_proxy(actor, component):
    """The two observed transient camera visuals, absent in commandlets.

    Engine/Private/Camera/CameraComponent.cpp creates this component only when
    !IsRunningCommandlet(), with SetIsVisualizationComponent(true). Do not
    exempt ordinary mesh components or arbitrary Engine meshes/camera actors.
    """
    return ((actor['name'], actor['label'], actor['cls']) in CAMERA_PROXY_OWNERS
            and component['name'] == 'CameraProxyMeshComponent_0'
            and component['cls'] == 'CameraProxyMeshComponent'
            and component['mesh'] == '/Engine/EditorMeshes/MatineeCam_SM'
            and component['materials'] == ['/Engine/EditorMaterials/MatineeCam_mat']
            and component.get('hidden_in_game') is True
            and 'instances' not in component)


def capture(u):
    """Read the same fields as inspect_mpr_site_completion, plus live visibility."""
    actors = u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors()
    result = []
    meshes = {}
    for actor in actors:
        center, extent = actor.get_actor_bounds(False)
        row = dict(name=actor.get_name(), label=actor.get_actor_label(),
                   guid=u.GuidLibrary.conv_guid_to_string(actor.get_editor_property('actor_guid')),
                   cls=actor.get_class().get_name(), tags=[str(t) for t in actor.tags],
                   location_cm=xyz(actor.get_actor_location()),
                   rotation_deg=rotation(actor.get_actor_rotation()),
                   scale=xyz(actor.get_actor_scale3d()),
                   bounds_center_cm=xyz(center), bounds_extent_cm=xyz(extent),
                   hidden=bool(actor.get_editor_property('hidden')),
                   components=[])
        for component in actor.get_components_by_class(u.StaticMeshComponent):
            mesh = component.static_mesh
            if mesh is None:
                continue
            mesh_path = package(mesh)
            meshes[mesh_path] = mesh
            materials = list(component.get_materials())
            item = dict(name=component.get_name(), cls=component.get_class().get_name(),
                        mesh=mesh_path, materials=[package(m) for m in materials],
                        materials_valid=all(isinstance(m, u.MaterialInterface) for m in materials),
                        visible=bool(component.visible), hidden_in_game=bool(component.hidden_in_game))
            if isinstance(component, u.InstancedStaticMeshComponent):
                item['instances'] = []
                for index in range(component.get_instance_count()):
                    tr = component.get_instance_transform(index, world_space=True)
                    item['instances'].append(dict(location_cm=xyz(tr.translation),
                        rotation_deg=rotation(tr.rotation.rotator()), scale=xyz(tr.scale3d)))
            row['components'].append(item)
        if isinstance(actor, u.CameraActor):
            camera = actor.get_component_by_class(u.CameraComponent)
            row['camera'] = dict(fov=float(camera.field_of_view), aspect=float(camera.aspect_ratio),
                                 constrain_aspect=bool(camera.constrain_aspect_ratio))
        result.append(row)
    return dict(map=MAP, actors=result), meshes


def core_identities(root):
    """Use the retained GUID set to identify the original 256 core actors."""
    source = root/'SourceAssets/MPR/rebuild_b50b57'
    ownership = read(source/'scene_ownership.json')
    guids = set(ownership['retention']['source_to_copy_guid'].values())
    historical = read(source/'transport_revision_20261105/validation/reload/current_snapshot.json.gz')
    core = {a['name']: a['guid'] for a in historical['actors'] if a['guid'] in guids}
    assert len(guids) == len(core) == 256, 'Expected 256 retained core GUIDs'
    return core


def compare_snapshot(baseline, current, stage, plan, manifest, core):
    """Compare original actor/component identities and every ordered instance."""
    errors = []

    def check(condition, message):
        if not condition:
            errors.append(message)
        return bool(condition)

    def transform(before, after, identity, allow_pose=False, target=None):
        check(close(before['scale'], after['scale'], SCALE_TOLERANCE), identity+': scale changed')
        if not allow_pose:
            check(close(before['rotation_deg'], after['rotation_deg'], ROTATION_TOLERANCE_DEG, True),
                  identity+': rotation changed')
            check(close(target if target is not None else before['location_cm'],
                        after['location_cm'], POSITION_TOLERANCE_CM), identity+': position differs')

    check(stage in {'round1', 'round2'}, 'Invalid verification stage')
    check(baseline['map'] == current['map'] == MAP, 'Wrong map')
    before = {a['name']: a for a in baseline['actors']}
    after = {a['name']: a for a in current['actors']}
    check(len(before) == len(baseline['actors']) == 877, 'Original actor baseline must contain 877 unique actors')
    check(len(after) == len(current['actors']), 'Duplicate current actor names')
    check(set(before) <= set(after), 'Original actors removed: '+str(sorted(set(before)-set(after))))
    check(len(core) == 256 and set(core) <= set(before), 'Protected core identities missing from baseline')
    for name, guid in core.items():
        check(name in after and after[name].get('guid') == guid, 'Protected core GUID missing/changed: '+name)
    check(tuple(plan['replacement_mesh_prefixes']) == PREFIXES, 'Unexpected old-site replacement scope')
    check(not plan['tree_removals'], 'Tree removal is not authorized')
    check(len(plan['tree_relocations']) == 39, 'Expected exactly 39 planned tree relocations')

    # Match the immutable original positions, never an already modified scene.
    trees = {(a['name'], c['name'], i): tr for a in before.values() for c in a['components']
             if c['mesh'] == OLD_TREE for i, tr in enumerate(c.get('instances', []))}
    tree_groups = {(a, c) for a, c, _ in trees}
    check(len(trees) == 1282 and len(tree_groups) == 63, 'Expected 1282 original trees in 63 groups')
    moves = {}
    for relocation in plan['tree_relocations']:
        source_id = relocation['source_id']
        check(source_id.startswith('CampusRow_'), 'Source CAD trees must remain in place: '+source_id)
        original = ue_position(relocation['from_position_m'])
        matches = [key for key, tr in trees.items()
                   if math.dist(tr['location_cm'], original) <= 100*relocation['match_position_tolerance_m']]
        if not check(len(matches) == 1, 'Ambiguous/missing baseline tree: '+source_id):
            continue
        key = matches[0]
        if not check(key not in moves, 'Duplicate relocation instance: '+source_id):
            continue
        check(close(trees[key]['scale'], relocation['scale'], SCALE_TOLERANCE),
              'Relocation scale differs from original: '+source_id)
        moves[key] = dict(source_id=source_id, target=ue_position(relocation['to_position_m']))
    check(len(moves) == 39, 'The 39 relocations did not bind to 39 original instances')

    new_names = set(after)-set(before)
    expected_meshes = {DEST+'/Meshes/'+r['name']: r for r in manifest['meshes']}
    check(len(expected_meshes) == 7, 'Expected seven site mesh definitions')
    site_rows = []
    if stage == 'round1':
        check(not new_names, 'Round1 added actors: '+str(sorted(new_names)))
    else:
        check(len(new_names) == 7 and len(after) == 884, 'Round2 must retain 877 actors and add exactly seven')
        found = Counter()
        for name in sorted(new_names):
            actor = after[name]
            check(actor['cls'] == 'StaticMeshActor' and OWNER in actor['tags'], 'Unowned new actor: '+name)
            check(not actor['hidden'], 'New site actor hidden: '+name)
            transform(dict(location_cm=[0, 0, 0], rotation_deg=[0, 0, 0], scale=[1, 1, 1]), actor, name)
            check(len(actor['components']) == 1, 'New site actor must have one mesh: '+name)
            for component in actor['components']:
                found[component['mesh']] += 1
                check(component['mesh'] in expected_meshes, 'Unexpected new mesh: '+component['mesh'])
                check(component['visible'] and not component['hidden_in_game'], 'New site component hidden: '+name)
                check(component.get('materials_valid') and len(component['materials']) == 1,
                      'New site material invalid: '+name)
                check('instances' not in component, 'New site mesh unexpectedly instanced: '+name)
                site_rows.append(dict(actor=name, label=actor['label'], mesh=component['mesh'],
                                      visible=component['visible'], hidden_in_game=component['hidden_in_game']))
        check(found == Counter({name: 1 for name in expected_meshes}), 'Six new site meshes not present exactly once')

    counts_before, counts_after = Counter(), Counter()
    material_changes, hidden_old, observed_moves = [], [], []
    bounds_diagnostics, ignored_camera_proxies = [], []
    non_tree_instances = 0
    unchanged_tree_instances = 0
    protected_building_components = 0
    for name in sorted(set(before) & set(after)):
        old, current_actor = before[name], after[name]
        for field in ('label', 'cls', 'tags'):
            check(old[field] == current_actor[field], name+': '+field+' changed')
        transform(old, current_actor, name, old['label'] in POSE_EXCEPTIONS)
        # Commandlets/NullRHI and a live editor include different visualization
        # primitives and HISM bounds readiness. Aggregate actor bounds are not a
        # geometry-preservation invariant; retain the differences as evidence.
        for field in ('bounds_center_cm', 'bounds_extent_cm'):
            if not close(old[field], current_actor[field], POSITION_TOLERANCE_CM):
                bounds_diagnostics.append(dict(actor=name, field=field,
                    baseline=old[field], current=current_actor[field]))
        if 'camera' in old and old['label'] != 'MPR_ReviewCamera':
            check(old['camera'] == current_actor.get('camera'), name+': protected camera settings changed')
        old_components = {c['name']: c for c in old['components']}
        current_components = {c['name']: c for c in current_actor['components']}
        check(len(old_components) == len(old['components']) and
              len(current_components) == len(current_actor['components']), name+': duplicate component names')
        for cname in set(current_components)-set(old_components):
            component = current_components[cname]
            if native_camera_proxy(current_actor, component):
                ignored_camera_proxies.append(dict(actor=name, component=cname,
                    cls=component['cls'], mesh=component['mesh'], hidden_in_game=True,
                    reason='Native transient editor camera visualization; absent in commandlets'))
                del current_components[cname]
        check(set(old_components) == set(current_components), name+': mesh component set changed')
        for cname in sorted(set(old_components) & set(current_components)):
            a, b = old_components[cname], current_components[cname]
            identity = name+'/'+cname
            tree = a['mesh'] == OLD_TREE
            check(a['cls'] == b['cls'], identity+': component class changed')
            expected_mesh = NEW_TREE if tree and stage == 'round2' else a['mesh']
            check(b['mesh'] == expected_mesh, identity+': mesh changed outside allowed tree replacement')
            if a['materials'] != b['materials']:
                material_changes.append(dict(actor=name, component=cname,
                                             before=a['materials'], after=b['materials']))
            if any(k in a['mesh'].lower() for k in ('roof', 'dock', 'facade', 'solar')):
                if not is_old_site(a['mesh']):
                    protected_building_components += 1
            if is_old_site(a['mesh']):
                if stage == 'round2':
                    check(not b['visible'] and b['hidden_in_game'], identity+': old paving/markings still visible')
                else:
                    check(b['visible'] and not b['hidden_in_game'], identity+': old site hidden in round1')
                hidden_old.append(dict(actor=name, component=cname, mesh=b['mesh'],
                                       visible=b['visible'], hidden_in_game=b['hidden_in_game']))
            if tree and stage == 'round2':
                check(len(b['materials']) == 4 and b.get('materials_valid'), identity+': tree materials invalid')
            check(('instances' in a) == ('instances' in b), identity+': instance component type changed')
            ia, ib = a.get('instances', []), b.get('instances', [])
            check(len(ia) == len(ib), identity+': instance count changed')
            counts_before[a['mesh'].rsplit('/', 1)[-1]] += len(ia)
            count_name = 'SM_MPR4_Tree_Oak' if b['mesh'] == NEW_TREE else b['mesh'].rsplit('/', 1)[-1]
            counts_after[count_name] += len(ib)
            for index, (old_instance, new_instance) in enumerate(zip(ia, ib)):
                key = (name, cname, index)
                move = moves.get(key) if stage == 'round2' else None
                transform(old_instance, new_instance, identity+' instance '+str(index),
                          target=move['target'] if move else None)
                if move:
                    observed_moves.append(dict(actor=name, component=cname, index=index,
                        source_id=move['source_id'], before_cm=old_instance['location_cm'],
                        target_cm=move['target'], current_cm=new_instance['location_cm']))
                elif tree:
                    unchanged_tree_instances += 1
                else:
                    non_tree_instances += 1
    check(len(hidden_old) == 29, 'Expected 29 old paving/green/marking components')
    check(counts_before == counts_after, 'Original per-mesh instance counts changed')
    for mesh, expected_count in plan['preserved_instance_counts'].items():
        check(counts_after[mesh] == expected_count, 'Preserved tree/vehicle count differs: '+mesh)
    check(len(observed_moves) == (39 if stage == 'round2' else 0), 'Tree relocation verification incomplete')
    check(unchanged_tree_instances == (1243 if stage == 'round2' else 1282), 'Unchanged tree count differs')
    return dict(success=not errors, errors=errors, original_actors=len(before), current_actors=len(after),
        retained_core_actors=sum(n in after and after[n].get('guid') == g for n, g in core.items()),
        tree_groups=len(tree_groups), tree_count=counts_after['SM_MPR4_Tree_Oak'],
        trees_relocated=len(observed_moves), trees_unchanged=unchanged_tree_instances,
        non_tree_instances_unchanged=non_tree_instances,
        protected_roof_dock_facade_solar_components=protected_building_components,
        original_instance_counts=dict(sorted(counts_before.items())),
        current_instance_counts=dict(sorted(counts_after.items())),
        planned_vehicle_counts={k: v for k, v in plan['preserved_instance_counts'].items()
                                if k != 'SM_MPR4_Tree_Oak'},
        material_slot_changes=material_changes, old_site_components=hidden_old,
        new_site_actors=site_rows, tree_relocations=observed_moves,
        actor_bounds_diagnostics=bounds_diagnostics,
        actor_bounds_used_for_preservation=False,
        ignored_native_camera_proxies=ignored_camera_proxies,
        allowed_actor_pose_changes=sorted(POSE_EXCEPTIONS),
        tolerances=dict(position_cm=POSITION_TOLERANCE_CM, rotation_deg=ROTATION_TOLERANCE_DEG,
                        scale=SCALE_TOLERANCE))


def tree_asset_audit(u, mesh, source):
    bounds = mesh.get_bounds()
    actual = [[a-b, a+b] for a, b in zip(xyz(bounds.origin), xyz(bounds.box_extent))]
    x, y, z = source['bounds_m']
    expected = [[100*x[0], 100*x[1]], [-100*y[1], -100*y[0]], [100*z[0], 100*z[1]]]
    error = max(abs(a-b) for aa, bb in zip(actual, expected) for a, b in zip(aa, bb))
    slots = list(mesh.static_materials)
    roles = [str(s.get_editor_property('imported_material_slot_name')) for s in slots]
    materials = [package(s.material_interface) for s in slots]
    triangles = int(mesh.get_num_triangles(0))
    valid = (package(mesh) == NEW_TREE and triangles == source['triangles'] == 11292
             and roles == TREE_ROLES and len(slots) == 4
             and all(isinstance(s.material_interface, u.MaterialInterface) for s in slots)
             and error < 2)
    return dict(success=valid, package=package(mesh), triangles=triangles, material_roles=roles,
                materials=materials, bounds_cm=actual, expected_bounds_cm=expected,
                max_bounds_error_cm=error, bounds_tolerance_cm=2)


def run(u=None, *, root=ROOT):
    """Write the stage report, then assert on any failure. No editor mutations."""
    root = Path(root).resolve()
    output = root/OUTPUT
    stage = 'invalid'
    report = dict(success=False, mode='current_editor_read_only', map=MAP,
                  editor_mutations=False, map_loaded=False, map_saved=False,
                  timestamp_utc=datetime.now(timezone.utc).isoformat())
    caught = None
    map_file = root/'Content/Maps/MPR_CAD_Warehouse_B50B57.umap'
    map_hash_before = None
    try:
        config = read(output/'run_config.json')
        stage = config['stage']
        assert stage in {'round1', 'round2'}, 'stage must be round1 or round2'
        report['stage'] = stage
        if u is None:
            import unreal as u
        actual_root = Path(u.Paths.convert_relative_path_to_full(u.Paths.project_dir())).resolve()
        assert actual_root == root, 'Verification is running in another project'
        level = u.get_editor_subsystem(u.LevelEditorSubsystem)
        world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
        # LevelEditor PIE state requires its UI module; it crashes in a commandlet.
        commandlet = '-run=pythonscript' in u.SystemLibrary.get_command_line().lower()
        if not commandlet:
            assert not level.is_in_play_in_editor(), 'Run in the editor world, outside PIE'
        report['mode'] = 'owned_read_only_commandlet' if commandlet else 'current_editor_read_only'
        assert package(world) == MAP, 'Open the existing MPR map first; verification never loads a level'
        report['dirty_maps_before'] = sorted(p.get_path_name() for p in
                                            u.EditorLoadingAndSavingUtils.get_dirty_map_packages())
        map_hash_before = sha(map_file)
        baseline_file = root/SOURCE/'validation/baseline_scene.json.gz'
        if not baseline_file.is_file():
            baseline_file = output/'scene_snapshot.json'
        baseline = read(baseline_file)
        plan_file = root/SOURCE/'site_plan.json'
        manifest_file = root/SOURCE/'geometry/manifest.json'
        plan, manifest = read(plan_file), read(manifest_file)
        assert manifest['plan_sha256'] == sha(plan_file), 'Site geometry does not match current plan'
        report['inputs'] = {str(p.relative_to(root)).replace('\\', '/'): sha(p)
                            for p in (baseline_file, plan_file, manifest_file, output/'run_config.json')}
        current, meshes = capture(u)
        comparison = compare_snapshot(baseline, current, stage, plan, manifest, core_identities(root))
        report.update(comparison)
        if stage == 'round2':
            assert NEW_TREE in meshes, 'New canopy mesh is absent from current scene'
            source = read(root/SOURCE/'tree/geometry_audit.json')
            report['tree_asset'] = tree_asset_audit(u, meshes[NEW_TREE], source)
            if not report['tree_asset']['success']:
                report['errors'].append('New tree native triangles, bounds, or material slots are invalid')
        report['dirty_maps_after'] = sorted(p.get_path_name() for p in
                                           u.EditorLoadingAndSavingUtils.get_dirty_map_packages())
        if report['dirty_maps_before'] != report['dirty_maps_after']:
            report['errors'].append('Dirty map state changed during read-only verification')
        if world != u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world():
            report['errors'].append('Current editor world changed during verification')
        report['success'] = not report['errors']
    except Exception as error:
        caught = error
        report.update(success=False, error=str(error), traceback=traceback.format_exc())
    finally:
        if map_hash_before is not None:
            report['map_sha256_before'] = map_hash_before
            report['map_sha256_after'] = sha(map_file)
            if report['map_sha256_after'] != map_hash_before:
                report['success'] = False
                report.setdefault('errors', []).append('Map file changed during read-only verification')
        output.mkdir(parents=True, exist_ok=True)
        safe_stage = stage if stage in {'round1', 'round2'} else 'invalid'
        report_file = output/(safe_stage+'_verification.json')
        report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
        if u is not None:
            u.log('MPR_SITE_VERIFICATION '+json.dumps(dict(success=report['success'], report=str(report_file))))
    assert report['success'], 'MPR '+str(stage)+' verification failed; see '+str(report_file) + (': '+str(caught) if caught else '')
    return report


if __name__ == '__main__':
    run()
