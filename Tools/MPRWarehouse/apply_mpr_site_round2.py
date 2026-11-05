"""Apply the reviewed site completion to the OPEN B50B57 editor world.

Import/reload this module, then call run(unreal, apply=False) for preflight or
run(unreal, apply=True) to apply and save the current level. Never opens a map,
rebuilds a Blueprint, changes an existing actor's tags, or saves all packages.
Reports and the pre-apply on-disk map backup live under Saved/MPR.
"""
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import gzip
import importlib
import json
import math
from pathlib import Path
import shutil
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
SOURCE = 'SourceAssets/MPR/site_completion_20261105'
OUTPUT = 'Saved/MPR/site_completion_20261105'
MAP = '/Game/Maps/MPR_CAD_Warehouse_B50B57'
DEST = '/Game/MPRWarehouse/SiteComplete'
OLD_SITE = '/Game/MPRWarehouse/RebuildB50B57/Site/Meshes/'
OLD_MATERIALS = '/Game/MPRWarehouse/RebuildB50B57/Materials/MI_'
OLD_TREE = '/Game/MPRWarehouse/ReferenceV4/Props/Meshes/SM_MPR4_Tree_Oak'
NEW_TREE = DEST+'/Meshes/SM_MPRSC_Tree_Canopy'
PREFIXES = ('SM_MPRR_MainApron_', 'SM_MPRR_CampusGreen_',
            'SM_MPRR_ParkingLines_', 'SM_MPRR_DockLines_')
TREE_ROLES = {'Bark': 'MPRR_Bark', 'LeafMid': 'MPRR_LeafMid',
              'LeafLight': 'MPRR_LeafLight', 'LeafShade': 'MPRR_LeafShade'}
OWNER = 'mpr-site-completion-round2-20261105'
TAG_OWNER = 'MPRSiteCompletion.Owner'
TAG_SHA = 'MPRSiteCompletion.SourceSHA256'
SUFFIXES = {'.uasset', '.umap', '.uexp', '.ubulk', '.uptnl'}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    path = Path(path)
    return json.loads(gzip.decompress(path.read_bytes()).decode('utf8') if path.suffix == '.gz'
                      else path.read_text(encoding='utf-8-sig'))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')
    temporary.replace(path)


def package(obj):
    return obj.get_path_name().split('.')[0] if obj is not None else None


def object_path(path):
    return path+'.'+path.rsplit('/', 1)[-1]


def xyz(vector):
    return [float(vector.x), float(vector.y), float(vector.z)]


def ue_position(point):
    return [100*point[0], -100*point[1], 100*point[2]]


def content_inventory(root, allowed_packages):
    allowed = {'Content/'+p.removeprefix('/Game/') for p in allowed_packages}
    return {p.relative_to(root).as_posix(): sha(p)
            for p in sorted((root/'Content').rglob('*'))
            if p.is_file() and p.suffix in SUFFIXES
            and p.relative_to(root).with_suffix('').as_posix() not in allowed}


def source_inputs(root):
    plan_path = root/SOURCE/'site_plan.json'
    geometry_path = root/SOURCE/'geometry/manifest.json'
    tree_path = root/SOURCE/'tree/geometry_audit.json'
    plan, geometry, tree = read(plan_path), read(geometry_path), read(tree_path)
    require(plan['map'] == MAP and plan['coordinate_frame'] == 'CAD_METRES_POSITIVE_Y',
            'Site plan must target the existing B50B57 map in CAD metres')
    require(tuple(plan['replacement_mesh_prefixes']) == PREFIXES, 'Unexpected replacement scope')
    require(not plan['tree_removals'] and len(plan['tree_relocations']) == 39,
            'Reviewed plan must relocate exactly 39 trees without removal')
    require(plan['preserved_instance_counts']['SM_MPR4_Tree_Oak'] == 1282, 'Tree count changed')
    require(geometry['plan_sha256'] == sha(plan_path), 'Geometry was exported from another plan')
    require(geometry['source_plan'] == SOURCE+'/site_plan.json', 'Unexpected geometry source')
    for name, digest in plan['source_hashes'].items():
        path = (root/name).resolve()
        require(path.is_relative_to((root/'SourceAssets/MPR').resolve()), 'Source escaped MPR folder')
        require(path.is_file() and sha(path) == digest, 'Reviewed input changed: '+name)
    require(tree['success'] and tree['name'] == 'SM_MPRSC_Tree_Canopy'
            and tree['material_roles'] == list(TREE_ROLES), 'Invalid tree audit')
    require(tree['nonmanifold_edges'] == 0 and tree['fbx_roundtrip_bounds_error_m'] < .001,
            'Tree FBX did not pass round-trip validation')
    require(tree['source_manifest_sha256'] == sha(root/'SourceAssets/MPR/reference_v4/props/manifest.json'),
            'Original tree source manifest changed')
    rows = deepcopy(geometry['meshes'])
    expected_roles = {'MPR3_Concrete', 'MPRSC_Walkway', 'MPRR_CampusGreen',
                      'MPR3_YellowLine', 'MPR3_WhiteLine', 'MPR4_TerminalCurb', 'MPRSC_ParkingAsphalt'}
    require(len(rows) == 7 and {r['material_roles'][0] for r in rows} == expected_roles,
            'Expected exactly seven reviewed site meshes')
    for row in rows:
        require(row['name'] == 'SM_MPRSC_'+row['material_roles'][0]
                and len(row['material_roles']) == 1 and row['category'] == 'Site',
                'Unexpected site mesh identity')
    rows.append(dict(name=tree['name'], fbx=SOURCE+'/tree/'+tree['name']+'.fbx',
                     sha256=tree['fbx_sha256'], bounds_m=tree['bounds_m'],
                     material_roles=tree['material_roles'], category='Tree'))
    for row in rows:
        path = (root/row['fbx']).resolve()
        require(path.is_relative_to((root/SOURCE).resolve()) and path.suffix.lower() == '.fbx',
                'FBX escaped the new content folder')
        require(path.is_file() and sha(path) == row['sha256'], 'FBX hash mismatch: '+row['name'])
    return plan, rows, {str(p.relative_to(root)).replace('\\', '/'): sha(p)
                        for p in (plan_path, geometry_path, tree_path)}


def material_path(role):
    role = TREE_ROLES.get(role, role)
    if role in {'MPR3_WhiteLine', 'MPR3_YellowLine', 'MPRR_Bark'}:
        return OLD_MATERIALS+role
    return DEST+'/Materials/MI_SC_'+role


@contextmanager
def legacy_fbx(u):
    name = 'Interchange.FeatureFlags.Import.FBX'
    previous = u.SystemLibrary.get_console_variable_int_value(name)
    try:
        u.SystemLibrary.execute_console_command(None, name+' 0')
        require(u.SystemLibrary.get_console_variable_int_value(name) == 0, 'Cannot select legacy FBX')
        yield
    finally:
        u.SystemLibrary.execute_console_command(None, name+' '+str(previous))
        require(u.SystemLibrary.get_console_variable_int_value(name) == previous, 'FBX flag failed to restore')


def check_bounds(mesh, row):
    bounds = mesh.get_bounds()
    actual = [[a-b, a+b] for a, b in zip(xyz(bounds.origin), xyz(bounds.box_extent))]
    x, y, z = row['bounds_m']
    wanted = [[x[0]*100, x[1]*100], [-y[1]*100, -y[0]*100], [z[0]*100, z[1]*100]]
    error = max(abs(a-b) for aa, bb in zip(actual, wanted) for a, b in zip(aa, bb))
    require(error < 2, 'FBX units/axes/bounds mismatch: '+row['name']+' '+str(error)+' cm')
    return dict(bounds_cm=actual, expected_bounds_cm=wanted, max_error_cm=error)


def owned_asset(u, path, digest, allow_refresh=False):
    lib = u.EditorAssetLibrary
    if not lib.does_asset_exist(path):
        return None
    asset = lib.load_asset(path)
    require(asset is not None and lib.get_metadata_tag(asset, TAG_OWNER) == OWNER,
            'Existing new-content asset has unverified ownership/source; refusing overwrite: '+path)
    if allow_refresh and lib.get_metadata_tag(asset, TAG_SHA) != digest:
        return None
    require(lib.get_metadata_tag(asset, TAG_SHA) == digest, 'Existing owned asset source changed; explicitly review refresh: '+path)
    return asset


def mark_owned(u, asset, digest):
    u.EditorAssetLibrary.set_metadata_tag(asset, TAG_OWNER, OWNER)
    u.EditorAssetLibrary.set_metadata_tag(asset, TAG_SHA, digest)


def import_mesh(u, root, row, materials, refresh_owned=False):
    lib = u.EditorAssetLibrary
    target = DEST+'/Meshes/'+row['name']
    mesh = owned_asset(u, target, row['sha256'], refresh_owned)
    if mesh is not None:
        require(isinstance(mesh, u.StaticMesh), 'Destination is not a StaticMesh: '+target)
        require([package(s.material_interface) for s in mesh.static_materials]
                == [material_path(r) for r in row['material_roles']], 'Existing mesh materials changed: '+target)
        return mesh, dict(package=target, reused=True, fbx_sha256=row['sha256'],
                          material_roles=row['material_roles'], **check_bounds(mesh, row))
    task = u.AssetImportTask()
    for key, value in dict(filename=str(root/row['fbx']), destination_path=DEST+'/Meshes',
                           destination_name=row['name'], automated=True, replace_existing=lib.does_asset_exist(target),
                           replace_existing_settings=False, save=False).items():
        task.set_editor_property(key, value)
    options = u.FbxImportUI()
    for key, value in dict(import_mesh=True, import_as_skeletal=False, import_materials=False,
                           import_textures=False, import_animations=False,
                           mesh_type_to_import=u.FBXImportType.FBXIT_STATIC_MESH,
                           automated_import_should_detect_type=False).items():
        options.set_editor_property(key, value)
    data = options.static_mesh_import_data
    for key, value in dict(combine_meshes=True, auto_generate_collision=False,
                           generate_lightmap_u_vs=False, convert_scene=True, convert_scene_unit=True,
                           force_front_x_axis=False,
                           normal_import_method=u.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS,
                           normal_generation_method=u.FBXNormalGenerationMethod.BUILT_IN).items():
        data.set_editor_property(key, value)
    task.options = options
    task.factory = u.FbxFactory()
    u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    imported = {str(p).split('.')[0] for p in task.imported_object_paths}
    require(imported == {target}, 'Import produced unexpected objects: '+str(imported))
    mesh = lib.load_asset(target)
    require(isinstance(mesh, u.StaticMesh), 'FBX did not produce the expected mesh')
    bounds = check_bounds(mesh, row)
    slots = mesh.static_materials
    require(len(slots) == len(row['material_roles']), 'Unexpected FBX material count')
    seen = []
    for i, slot in enumerate(slots):
        role = str(slot.get_editor_property('imported_material_slot_name'))
        require(role in row['material_roles'], 'Unexpected imported material slot: '+role)
        seen.append(role)
        slot.material_interface = materials[role]
        slots[i] = slot
    require(seen == row['material_roles'], 'Material slot order changed')
    mesh.set_editor_property('static_materials', slots)
    subsystem = u.get_editor_subsystem(u.StaticMeshEditorSubsystem)
    if row['category'] == 'Tree':
        reduction = u.StaticMeshReductionOptions()
        reduction.auto_compute_lod_screen_size = False
        reduction.reduction_settings = [u.StaticMeshReductionSettings(percent_triangles=p, screen_size=s)
                                        for p, s in [(1., 1.), (.5, .06), (.25, .025), (.1, .01)]]
        require(subsystem.set_lods(mesh, reduction) >= 4, 'Tree distance LOD generation failed')
    for index in range(subsystem.get_lod_count(mesh)):
        settings = subsystem.get_lod_build_settings(mesh, index)
        settings.use_full_precision_u_vs = True
        settings.recompute_tangents = True
        subsystem.set_lod_build_settings(mesh, index, settings)
    mark_owned(u, mesh, row['sha256'])
    require(lib.save_loaded_asset(mesh, only_if_is_dirty=False), 'Could not save new mesh: '+target)
    return mesh, dict(package=target, reused=False, fbx_sha256=row['sha256'],
                      material_roles=row['material_roles'],
                      lod_triangles=[mesh.get_num_triangles(i) for i in range(subsystem.get_lod_count(mesh))], **bounds)


def capture(u, guard, root):
    state = guard.capture(u, root, MAP)
    lookup = {a.get_path_name(): a for a in u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors()}
    for row in state['actors']:
        components = {c.get_name(): c for c in lookup[row['path']].get_components_by_class(u.StaticMeshComponent)}
        for c in row['components']:
            if c['name'] in components:
                c['override_materials'] = [m.get_path_name() if m else None for m in
                                          components[c['name']].get_editor_property('override_materials')]
    return state


def live_targets(u, plan, historical):
    actors = list(u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors())
    old, trees, existing_new = {}, {}, {}
    counts = Counter()
    expected_old = {c['mesh'] for a in historical['actors'] for c in a['components']
                    if c['mesh'].startswith(OLD_SITE) and c['mesh'].rsplit('/', 1)[-1].startswith(PREFIXES)}
    for actor in actors:
        for component in actor.get_components_by_class(u.StaticMeshComponent):
            mesh_path = package(component.static_mesh)
            if mesh_path is None:
                continue
            key = (actor.get_path_name(), component.get_name())
            if mesh_path in expected_old:
                require(not isinstance(component, u.InstancedStaticMeshComponent), 'Old site component is instanced')
                old[key] = component
            if isinstance(component, u.InstancedStaticMeshComponent):
                name = 'SM_MPR4_Tree_Oak' if mesh_path == NEW_TREE else mesh_path.rsplit('/', 1)[-1]
                counts[name] += component.get_instance_count()
            if mesh_path in {OLD_TREE, NEW_TREE}:
                require(isinstance(component, u.HierarchicalInstancedStaticMeshComponent), 'Expected tree HISM')
                trees[key] = component
            if mesh_path.startswith(DEST+'/Meshes/') and mesh_path != NEW_TREE:
                require(isinstance(actor, u.StaticMeshActor) and OWNER in [str(t) for t in actor.tags],
                        'Unowned actor uses a new site mesh: '+actor.get_actor_label())
                require(mesh_path not in existing_new, 'Duplicate new site mesh actor: '+mesh_path)
                existing_new[mesh_path] = actor
    require(expected_old and {package(c.static_mesh) for c in old.values()} == expected_old
            and len(old) == len(expected_old) == 29, 'Old site component set changed; review before hiding')
    for name, count in plan['preserved_instance_counts'].items():
        require(counts[name] == count, 'Instance count differs from plan: '+name+' '+str(counts[name]))
    require(len(trees) == 63 and sum(c.get_instance_count() for c in trees.values()) == 1282,
            'Expected 63 tree groups / 1282 instances')
    all_trees = [(key, c, i, c.get_instance_transform(i, world_space=True))
                 for key, c in trees.items() for i in range(c.get_instance_count())]
    moves, used = [], set()
    for row in plan['tree_relocations']:
        require(row['source_id'].startswith('CampusRow_'), 'A source tree may not be moved')
        old_position, new_position = ue_position(row['from_position_m']), ue_position(row['to_position_m'])
        matches = [(key, c, i, tr) for key, c, i, tr in all_trees
                   if min(math.dist(xyz(tr.translation), old_position),
                          math.dist(xyz(tr.translation), new_position)) <= 100*row['match_position_tolerance_m']]
        require(len(matches) == 1, 'Ambiguous/missing CampusRow instance: '+row['source_id'])
        key, component, index, transform = matches[0]
        identity = (*key, index)
        require(identity not in used, 'Two relocations matched one instance')
        used.add(identity)
        require(max(abs(a-b) for a, b in zip(xyz(transform.scale3d), row['scale'])) < 1e-5,
                'Tree scale differs from clearance plan: '+row['source_id'])
        moves.append(dict(key=key, index=index, source_id=row['source_id'],
                          before_world_cm=xyz(transform.translation), target_world_cm=new_position,
                          already_applied=math.dist(xyz(transform.translation), new_position) < .05))
    return old, trees, existing_new, moves


def verify_preservation(before, after, expected, moved_keys, new_paths, guard):
    actual = {row['path']: row for row in after['actors']}
    require(set(actual) == set(expected) | set(new_paths), 'Actors added/deleted outside the reviewed site meshes')
    for path, wanted in expected.items():
        current = deepcopy(actual[path])
        wanted = deepcopy(wanted)
        for c in current['components']:
            wc = next(v for v in wanted['components'] if v['name'] == c['name'])
            for index in moved_keys.get((path, c['name']), []):
                ct, wt = c['instance_transforms'][index], wc['instance_transforms'][index]
                for prop, tolerance in [('translation_cm', .05), ('rotation_xyzw', 1e-6), ('scale', 1e-6)]:
                    require(max(abs(a-b) for a, b in zip(ct[prop], wt[prop])) < tolerance,
                            'Moved tree changed unexpected transform: '+path+' '+str(index)+' '+prop)
                c['instance_transforms'][index] = deepcopy(wt)
        require(guard.canonical_actor(current) == guard.canonical_actor(wanted),
                'An existing actor/component changed outside reviewed edits: '+path)
    require(before['world_settings'] == after['world_settings'], 'World settings changed')
    require(guard.canonical_coverage(before['world_actor_coverage']) ==
            guard.canonical_coverage(after['world_actor_coverage']), 'World auxiliary actors changed')
    require(set(after['dirty_content']) <= set(before['dirty_content']),
            'An original Content package became dirty in memory: '+str(
                sorted(set(after['dirty_content'])-set(before['dirty_content']))))


def run(u=None, *, apply=False, refresh_owned=False):
    """Preflight by default. apply=True imports only new assets and saves this map."""
    if u is None:
        import unreal as u
    scripts = str(ROOT/'Tools/MPRWarehouse')
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import mpr_site_completion_style as style
    import rebuild_preservation as guard
    style, guard = importlib.reload(style), importlib.reload(guard)
    require(style.MAP == MAP and style.DEST == DEST, 'Style map/namespace changed')
    root = Path(u.Paths.convert_relative_path_to_full(u.Paths.project_dir())).resolve()
    require(root == ROOT, 'Script is running in a different project')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    attempt = root/OUTPUT/('round2_'+stamp)
    report = dict(schema_version=1, success=False, apply_requested=apply, map=MAP,
                  imports=[], hidden_components=[], tree_changes=[], map_saved=False,
                  attempt_directory=str(attempt), phase='preflight')
    inventory_before = None
    allowed = {MAP, material_path('MPRSC_Walkway'), material_path('MPRSC_ParkingAsphalt')}
    try:
        levels = u.get_editor_subsystem(u.LevelEditorSubsystem)
        actors_sub = u.get_editor_subsystem(u.EditorActorSubsystem)
        world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
        require(not levels.is_in_play_in_editor() and world.get_path_name().split('.')[0] == MAP,
                'Open B50B57 in the non-PIE editor first; this script never switches or reloads maps')
        plan, rows, input_hashes = source_inputs(root)
        allowed.update(DEST+'/Meshes/'+r['name'] for r in rows)
        before = capture(u, guard, root)
        historical = read(root/SOURCE/'validation/baseline_scene.json.gz')
        require(historical['map'] == MAP, 'Historical scene snapshot is from another map')
        old, trees, existing_new, moves = live_targets(u, plan, historical)
        require(set(existing_new) <= {DEST+'/Meshes/'+r['name'] for r in rows[:-1]}, 'Unexpected SiteComplete actor')
        lib = u.EditorAssetLibrary
        materials = {}
        for role in {role for row in rows for role in row['material_roles']} - {'MPRSC_Walkway','MPRSC_ParkingAsphalt'}:
            material = lib.load_asset(material_path(role))
            require(isinstance(material, u.MaterialInstanceConstant), 'Missing reviewed material: '+material_path(role))
            materials[role] = material
        walkway_sha = hashlib.sha256((sha(root/'Content/MPRWarehouse/SiteComplete/Materials/MI_SC_MPR3_Concrete.uasset')+
                                     json.dumps(plan['materials']['MPRSC_Walkway'], sort_keys=True)).encode()).hexdigest()
        walkway = owned_asset(u, material_path('MPRSC_Walkway'), walkway_sha)
        parking_sha = hashlib.sha256(json.dumps(plan['materials']['MPRSC_ParkingAsphalt'], sort_keys=True).encode()).hexdigest()
        parking = owned_asset(u, material_path('MPRSC_ParkingAsphalt'), parking_sha)
        if walkway is not None:
            require(isinstance(walkway, u.MaterialInstanceConstant), 'Owned walkway is not a material instance')
        for row in rows:
            existing = owned_asset(u, DEST+'/Meshes/'+row['name'], row['sha256'], refresh_owned)
            if existing:
                require(isinstance(existing, u.StaticMesh), 'Owned mesh destination is not a StaticMesh')
                require([package(s.material_interface) for s in existing.static_materials]
                        == [material_path(r) for r in row['material_roles']],
                        'Previously imported material slots changed: '+row['name'])
                check_bounds(existing, row)
        inventory_before = content_inventory(root, allowed)
        report.update(source_hashes=input_hashes, original_assets_count=len(inventory_before),
                      existing_actors=len(before['actors']), tree_groups=len(trees), tree_count=1282,
                      material_mapping={r: material_path(r) for row in rows for r in row['material_roles']},
                      allowed_content_packages=sorted(allowed),
                      planned_tree_relocations=moves, old_components=len(old),
                      preserved_instance_counts=plan['preserved_instance_counts'],
                      unsaved_content_before=before['dirty_content'], unsaved_maps_before=before['dirty_maps'])
        write(attempt/'before_scene.json', before)
        write(attempt/'original_content_hashes.json', inventory_before)
        if not apply:
            report.update(success=True, phase='preflight_complete', mutation_performed=False)
            return report
        report['phase'] = 'import_new_content'
        map_file = root/'Content/Maps/MPR_CAD_Warehouse_B50B57.umap'
        shutil.copy2(map_file, attempt/'map_before.umap')
        report['map_before_sha256'] = sha(map_file)
        if walkway is None:
            walkway = u.AssetToolsHelpers.get_asset_tools().duplicate_asset(
                'MI_SC_MPRSC_Walkway', DEST+'/Materials', materials['MPR3_Concrete'])
            require(isinstance(walkway, u.MaterialInstanceConstant), 'Walkway clone failed')
            definition = plan['materials']['MPRSC_Walkway']
            tint = style.linear(definition['source_srgb_hex'].lstrip('#'))
            u.MaterialEditingLibrary.set_material_instance_vector_parameter_value(walkway, 'Tint', u.LinearColor(*tint, 1))
            u.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(walkway, 'Roughness', definition['roughness'])
            actual_tint = u.MaterialEditingLibrary.get_material_instance_vector_parameter_value(walkway, 'Tint')
            require(max(abs(a-b) for a, b in zip((actual_tint.r, actual_tint.g, actual_tint.b), tint)) < 1e-5,
                    'Walkway tint did not apply')
            mark_owned(u, walkway, walkway_sha)
            require(lib.save_loaded_asset(walkway, only_if_is_dirty=False), 'Walkway save failed')
        materials['MPRSC_Walkway'] = walkway
        if parking is None:
            parking = u.AssetToolsHelpers.get_asset_tools().duplicate_asset(
                'MI_SC_MPRSC_ParkingAsphalt', DEST+'/Materials', lib.load_asset(DEST+'/Materials/MI_SC_MPR3_Asphalt'))
            require(isinstance(parking, u.MaterialInstanceConstant), 'Parking material clone failed')
            definition = plan['materials']['MPRSC_ParkingAsphalt']
            tint = style.linear(definition['source_srgb_hex'].lstrip('#'))
            u.MaterialEditingLibrary.set_material_instance_vector_parameter_value(parking, 'Tint', u.LinearColor(*tint, 1))
            u.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(parking, 'Roughness', definition['roughness'])
            mark_owned(u, parking, parking_sha)
            require(lib.save_loaded_asset(parking, only_if_is_dirty=False), 'Parking material save failed')
        materials['MPRSC_ParkingAsphalt'] = parking
        meshes = {}
        with legacy_fbx(u):
            for row in rows:
                mesh, result = import_mesh(u, root, row, materials, refresh_owned)
                meshes[row['name']] = mesh
                report['imports'].append(result)
                write(attempt/'apply_report.json', report)
        require(content_inventory(root, allowed) == inventory_before, 'Import modified original Content')
        report['phase'] = 'modify_current_level'
        expected = {row['path']: deepcopy(row) for row in before['actors']}
        expected_components = {(path, c['name']): c for path, row in expected.items() for c in row['components']}
        moved_keys, new_paths = {}, []
        # No property write on an existing Blueprint actor: only component APIs.
        with u.ScopedEditorTransaction('MPR 场地第二轮原位完善'):
            for row in rows[:-1]:
                path = DEST+'/Meshes/'+row['name']
                actor = existing_new.get(path)
                if actor is None:
                    actor = actors_sub.spawn_actor_from_class(u.StaticMeshActor, u.Vector(0, 0, 0))
                    require(actor is not None, 'Could not spawn site mesh actor')
                    actor.set_actor_label('MPRSC_'+row['material_roles'][0])
                    actor.set_folder_path('MPR/SiteComplete')
                    actor.set_editor_property('tags', [u.Name(OWNER)])
                    component = actor.get_component_by_class(u.StaticMeshComponent)
                    component.set_static_mesh(meshes[row['name']])
                    component.set_mobility(u.ComponentMobility.STATIC)
                    component.set_collision_profile_name('NoCollision')
                    new_paths.append(actor.get_path_name())
                else:
                    component = actor.get_component_by_class(u.StaticMeshComponent)
                rotation = actor.get_actor_rotation()
                require(xyz(actor.get_actor_location()) == [0, 0, 0]
                        and xyz(actor.get_actor_scale3d()) == [1, 1, 1]
                        and max(abs(rotation.pitch), abs(rotation.yaw), abs(rotation.roll)) < 1e-6,
                        'New site actor transform changed')
                require(component.visible and not component.hidden_in_game, 'New site actor is hidden')
                require(package(component.static_mesh) == path, 'New site actor mesh mismatch')
            for key, component in old.items():
                component.modify()
                component.set_visibility(False, False)
                component.set_hidden_in_game(True, False)
                expected_components[key].update(visible=False, hidden_in_game=True)
                report['hidden_components'].append(dict(actor=key[0], component=key[1], mesh=package(component.static_mesh)))
            tree_materials = [materials[role] for role in TREE_ROLES]
            for key, component in trees.items():
                component.modify()
                count = component.get_instance_count()
                component.set_static_mesh(meshes['SM_MPRSC_Tree_Canopy'])
                require(component.get_instance_count() == count, 'Tree mesh swap changed instance count')
                for index, material in enumerate(tree_materials):
                    component.set_material(index, material)
                expected_components[key].update(mesh=object_path(NEW_TREE),
                    materials=[m.get_path_name() for m in tree_materials],
                    override_materials=[m.get_path_name() for m in tree_materials])
            for move in moves:
                key = tuple(move['key'])
                component, index = trees[key], move['index']
                if not move['already_applied']:
                    transform = component.get_instance_transform(index, world_space=True)
                    target = u.Vector(*move['target_world_cm'])
                    transform.translation = target
                    local = u.MathLibrary.inverse_transform_location(component.get_world_transform(), target)
                    expected_components[key]['instance_transforms'][index]['translation_cm'] = xyz(local)
                    require(component.update_instance_transform(index, transform, world_space=True,
                            mark_render_state_dirty=True, teleport=True), 'Tree relocation failed')
                    moved_keys.setdefault(key, []).append(index)
                after_position = xyz(component.get_instance_transform(index, world_space=True).translation)
                require(math.dist(after_position, move['target_world_cm']) < .05, 'Tree destination verification failed')
                report['tree_changes'].append(dict(**move, after_world_cm=after_position))
            after = capture(u, guard, root)
            verify_preservation(before, after, expected, moved_keys, new_paths, guard)
            # Re-run coordinate matching and all vehicle/tree counts before saving.
            _, verified_trees, verified_sites, verified_moves = live_targets(u, plan, historical)
            require(len(verified_sites) == 7 and all(m['already_applied'] for m in verified_moves), 'Round2 incomplete')
            require(content_inventory(root, allowed) == inventory_before, 'Original Content changed before map save')
            require(world == u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world(), 'Editor world changed')
            require(levels.save_current_level(), 'Could not save the current B50B57 level')
            report['map_saved'] = True
        after_save = capture(u, guard, root)
        verify_preservation(before, after_save, expected, moved_keys, new_paths, guard)
        write(attempt/'after_scene.json', after_save)
        report.update(success=True, phase='complete', map_sha256=sha(map_file),
                      new_actors=len(new_paths), total_actors=len(after_save['actors']),
                      trees_moved=sum(not m['already_applied'] for m in moves),
                      trees_already_at_target=sum(m['already_applied'] for m in moves),
                      unchanged_tree_instances=1282-sum(not m['already_applied'] for m in moves),
                      all_other_existing_actor_state_preserved=True,
                      original_assets_unchanged=True, new_meshes=8, site_mesh_actors=7,
                      original_actor_tags_unchanged=True,
                      final_tree_count=sum(c.get_instance_count() for c in verified_trees.values()))
        return report
    except Exception as exc:
        report.update(success=False, error=str(exc), traceback=traceback.format_exc())
        raise
    finally:
        if inventory_before is not None:
            inventory_after = content_inventory(root, allowed)
            changes = {p: dict(before=inventory_before.get(p), after=inventory_after.get(p))
                       for p in sorted(set(inventory_before) | set(inventory_after))
                       if inventory_before.get(p) != inventory_after.get(p)}
            report['original_content_changes'] = changes
            if changes:
                report.update(success=False, original_assets_unchanged=False)
        write(attempt/'apply_report.json', report)
        write(root/OUTPUT/('round2_apply.json' if apply else 'round2_preflight.json'), report)
        u.log('MPR_SITE_ROUND2 '+json.dumps(dict(success=report['success'], phase=report['phase'],
                                               report=str(attempt/'apply_report.json'))))
        if report.get('original_content_changes'):
            raise RuntimeError('Original Content hashes changed; see detailed round2 report')


if __name__ == '__main__':
    run(apply=False)
