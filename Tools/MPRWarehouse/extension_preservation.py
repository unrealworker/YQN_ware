"""Read-only guards for adding MPR surroundings without rebuilding the old scene.

Every baseline actor is immutable, regardless of ownership/classification. An
explicit, exact terminal-mesh replacement plan is the sole narrow exception:
only a named old road-terminal component's mesh reference may change. The
snapshot adds camera, lighting and post-process state to the existing geometry
snapshot, and hashes the transitive /Game package dependencies of the entire
map. It deliberately never loads a map, saves an asset, or changes an actor.

This proves recorded state and package preservation, not spatial non-overlap:
the extension builder must separately exclude the finished scene footprint,
including existing road-end fades. A huge background-grass plane is not that
footprint. Do not move, recolor, shrink or cover completed roads to join them.
"""
import hashlib
from copy import deepcopy
from pathlib import Path
import re

import mpr_interior_preservation as interior

MAP = interior.MAP
SCHEMA = interior.SCHEMA
SCOPE = 'all-existing-actors-and-game-dependencies-v1'
EXTENSION_NAMESPACE = '/Game/MPRWarehouse/ExtensionB50B57'
EXTENSION_FOLDER = 'MPR/ExtensionB50B57'
EXTENSION_TAG = 'mpr-extension-b50b57'
PreservationError = interior.PreservationError
canonical_digest = interior.canonical_digest
_PACKAGE = re.compile(r'/Game/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*')
_REFERENCES = re.compile(r'/Game/[A-Za-z0-9_/-]+(?:\.[A-Za-z0-9_]+)?')
_SUFFIXES = ('.uasset', '.umap', '.uexp', '.ubulk', '.uptnl')
TERMINAL_MESHES = frozenset(
    '/Game/MPRWarehouse/ReferenceV4/Site/Meshes/' + name + '.' + name
    for name in ('SM_MPR4_Site_RoadTerminalRoads', 'SM_MPR4_Site_RoadTerminalCurbs',
                 'SM_MPR4_Site_RoadTerminalEdges'))


def _under(value, prefix):
    return value == prefix or value.startswith(prefix + '/')


def _sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _package(value):
    package = str(value).split('.')[0]
    if not _PACKAGE.fullmatch(package):
        raise PreservationError('Invalid project dependency package: ' + str(value))
    return package


def _package_base(project_root, package):
    root = Path(project_root).resolve()
    base = root / 'Content' / _package(package)[len('/Game/'):]
    if not base.resolve().is_relative_to(root / 'Content'):
        raise PreservationError('Package resolves outside project Content: ' + package)
    return root, base


def package_hashes(project_root, package_paths):
    """Hash each /Game package and all sidecars, including non-active maps."""
    result = {}
    for package in sorted({_package(p) for p in package_paths}):
        root, base = _package_base(project_root, package)
        primary = [base.with_suffix(s) for s in ('.uasset', '.umap')
                   if base.with_suffix(s).is_file()]
        if len(primary) != 1:
            raise PreservationError('Missing or ambiguous dependency package: ' + package)
        paths = [base.with_suffix(s) for s in _SUFFIXES if base.with_suffix(s).is_file()]
        for path in paths:
            if not path.resolve().is_relative_to(root / 'Content'):
                raise PreservationError('Dependency file resolves outside Content: ' + str(path))
        result[package] = {p.relative_to(root).as_posix(): _sha(p) for p in paths}
    return result


def assert_new_package_destinations(project_root, planned_packages, *,
                                    extension_namespace=EXTENSION_NAMESPACE):
    """Preflight before any replace_existing import, including orphan sidecars."""
    namespace = _package(extension_namespace)
    planned = [_package(p) for p in planned_packages]
    if len({p.lower() for p in planned}) != len(planned):
        raise PreservationError('Duplicate planned package destinations')
    for package in planned:
        if package == namespace or not _under(package, namespace):
            raise PreservationError('New package is outside extension namespace: ' + package)
        _, base = _package_base(project_root, package)
        if any(base.with_suffix(s).exists() for s in _SUFFIXES):
            raise PreservationError('New package destination already exists: ' + package)
    return sorted(planned)


def _references(value):
    if isinstance(value, str):
        return {_package(p) for p in _REFERENCES.findall(value)}
    if isinstance(value, dict):
        return set().union(*(_references(v) for v in value.values())) if value else set()
    if isinstance(value, (list, tuple)):
        return set().union(*(_references(v) for v in value)) if value else set()
    return set()


def dependency_packages(u, snapshot, additional_packages=()):
    """Include saved-map soft refs plus live actor/component/material refs.

    The active map itself changes when additions are saved and is excluded from
    immutable dependency hashes. Engine and /Script packages are not writable
    project content; /Game asset bytes (including parent materials/textures) are.
    additional_packages may reserve assets for read-only reuse before importing.
    Supply the same explicit roots for before/after captures.
    """
    roots = _references(snapshot['actors']) | {_package(snapshot['map'])}
    roots.update(_package(p) for p in additional_packages)
    registry = u.AssetRegistryHelpers.get_asset_registry()
    options = u.AssetRegistryDependencyOptions(include_soft_package_references=True,
        include_hard_package_references=True, include_searchable_names=False,
        include_soft_management_references=False, include_hard_management_references=False)
    pending, packages = list(roots), set()
    while pending:
        package = pending.pop()
        if package in packages:
            continue
        packages.add(package)
        dependencies = registry.get_dependencies(package, options)
        # UE 5.8 FAssetRegistryState::GetDependencies returns false when the
        # dependency node is absent. Python exposes this as None, whereas a
        # known leaf returns an empty array. Missing nodes must not erase part
        # of the protected transitive closure.
        if dependencies is None:
            raise PreservationError('Asset registry dependency node unavailable: ' + package +
                                    '; synchronously scan the saved package before taking a snapshot')
        pending.extend(_package(str(p)) for p in dependencies
                       if str(p).startswith('/Game/') and str(p) not in packages)
    return packages - {snapshot['map']}


def _value(value):
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if hasattr(value, 'export_text'):
        # StructBase.export_text includes every PP override, not a rounded repr.
        return value.export_text()
    if hasattr(value, 'get_path_name'):
        return value.get_path_name()
    # Known enum-valued editor properties have stable symbolic string forms.
    return str(value)


def _properties(obj, names):
    # Missing access is an error. Never silently omit a preservation property.
    return {name: _value(obj.get_editor_property(name)) for name in names}


def _is_a(u, obj, class_name):
    cls = getattr(u, class_name, None)
    return cls is not None and isinstance(obj, cls)


def _render_properties(u, actor, row):
    if _is_a(u, actor, 'PostProcessVolume'):
        row['render_settings'] = _properties(actor,
            ('settings', 'enabled', 'unbound', 'priority', 'blend_radius', 'blend_weight'))
    recorded = {c['name']: c for c in row['components']}
    if len(recorded) != len(row['components']):
        raise PreservationError('Duplicate component names: ' + row['path'])
    for component in actor.get_components_by_class(u.ActorComponent):
        names = []
        if _is_a(u, component, 'LightComponentBase'):
            names += ['intensity', 'light_color', 'cast_shadows',
                      'indirect_lighting_intensity', 'volumetric_scattering_intensity']
        if _is_a(u, component, 'LightComponent'):
            names += ['temperature', 'use_temperature', 'light_function_material',
                      'ies_texture', 'shadow_bias', 'shadow_slope_bias']
        if _is_a(u, component, 'DirectionalLightComponent'):
            names += ['light_source_angle', 'light_source_soft_angle']
        if _is_a(u, component, 'SkyLightComponent'):
            names += ['source_type', 'cubemap', 'source_cubemap_angle',
                      'real_time_capture', 'lower_hemisphere_is_black', 'lower_hemisphere_color']
        if _is_a(u, component, 'CameraComponent'):
            names += ['projection_mode', 'field_of_view', 'aspect_ratio',
                      'constrain_aspect_ratio', 'ortho_width',
                      'post_process_blend_weight', 'post_process_settings']
        if _is_a(u, component, 'CineCameraComponent'):
            names += ['current_focal_length', 'current_aperture',
                      'filmback', 'focus_settings', 'lens_settings']
        if names:
            recorded[component.get_name()]['render_settings'] = _properties(component, names)


def _frozen_file_hashes(project_root, paths):
    root = Path(project_root).resolve()
    result = {}
    for name in paths:
        path = Path(name)
        path = (path if path.is_absolute() else root / path).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise PreservationError('Frozen file is missing/outside project: ' + str(name))
        result[path.relative_to(root).as_posix()] = _sha(path)
    return result


def capture_editor_snapshot(u, *, project_root, expected_map=MAP, hash_assets=True,
                            additional_packages=(), frozen_paths=()):
    """Capture the active editor world without saving/loading/mutating anything.

    hash_assets=False is useful for inspection only: assert_preserved rejects
    it. A dirty baseline must be resolved by the caller before starting imports;
    this function never saves user work on the caller's behalf.
    """
    snapshot = interior.capture_editor_snapshot(u, project_root=project_root,
        expected_map=expected_map, hash_assets=False)
    actors = u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors()
    by_guid = {u.GuidLibrary.conv_guid_to_string(a.get_editor_property('actor_guid')): a
               for a in actors}
    if len(by_guid) != len(actors) or set(by_guid) != {row['guid'] for row in snapshot['actors']}:
        raise PreservationError('Actor set changed during snapshot capture')
    for row in snapshot['actors']:
        _render_properties(u, by_guid[row['guid']], row)
    snapshot.update(preservation_scope=SCOPE, assets_hashed=bool(hash_assets),
                    additional_packages=sorted({_package(p) for p in additional_packages}))
    snapshot['asset_hashes'] = package_hashes(project_root,
        dependency_packages(u, snapshot, additional_packages)) if hash_assets else {}
    snapshot['frozen_files'] = _frozen_file_hashes(project_root, frozen_paths)
    _, map_base = _package_base(project_root, expected_map)
    snapshot['map_file_sha256'] = _sha(map_base.with_suffix('.umap'))
    snapshot['protected_digest'] = canonical_digest(snapshot['actors'])
    return snapshot


def verify_protected_files(snapshot, *, project_root):
    """Re-read all baseline dependencies; detect added/deleted sidecars too."""
    actual = package_hashes(project_root, snapshot['asset_hashes'])
    if actual != snapshot['asset_hashes']:
        changed = sorted(p for p in actual if actual[p] != snapshot['asset_hashes'][p])
        raise PreservationError('Protected dependency package bytes changed: ' + ', '.join(changed[:10]))
    frozen = _frozen_file_hashes(project_root, snapshot.get('frozen_files', {}))
    if frozen != snapshot.get('frozen_files', {}):
        raise PreservationError('Protected source/file bytes changed')
    return {'protected_asset_packages': len(actual), 'protected_files': len(frozen)}


def assert_clean_baseline(snapshot):
    if snapshot.get('dirty_maps') or snapshot.get('dirty_content'):
        raise PreservationError('Baseline has unsaved editor work; do not overwrite/reload it')


def _mesh_object_path(value):
    package = _package(value)
    if value != package + '.' + package.rsplit('/', 1)[-1]:
        raise PreservationError('Expected exact static-mesh object path: ' + str(value))
    return package


def _validated_mesh_replacements(before, replacements, extension_namespace):
    """Validate the narrow authorization against the actual baseline identity."""
    rows = {r['guid']: r for r in before['actors']}
    if len(rows) != len(before['actors']):
        raise PreservationError('Duplicate actor GUIDs in replacement baseline')
    required = {'actor_guid', 'component_name', 'old_mesh', 'new_mesh'}
    approved, seen = [], set()
    for replacement in replacements:
        if not isinstance(replacement, dict) or set(replacement) != required:
            raise PreservationError('Mesh replacement requires exactly: ' + ', '.join(sorted(required)))
        guid, component_name = replacement['actor_guid'], replacement['component_name']
        identity = (guid, component_name)
        if identity in seen:
            raise PreservationError('Duplicate terminal component replacement: ' + str(identity))
        seen.add(identity)
        old_mesh, new_mesh = replacement['old_mesh'], replacement['new_mesh']
        if old_mesh not in TERMINAL_MESHES:
            raise PreservationError('Only the three authored road-terminal meshes may be replaced: ' + str(old_mesh))
        new_package = _mesh_object_path(new_mesh)
        if new_package == extension_namespace or not _under(new_package, extension_namespace):
            raise PreservationError('Terminal replacement target is outside extension namespace: ' + new_mesh)
        if new_package in before['asset_hashes']:
            raise PreservationError('Terminal replacement must use a new asset package: ' + new_package)
        old_package = _mesh_object_path(old_mesh)
        if old_package not in before['asset_hashes']:
            raise PreservationError('Original terminal package has no protected baseline hash: ' + old_package)
        row = rows.get(guid)
        expected_label = old_package.rsplit('/', 1)[-1].removeprefix('SM_')
        if row is None or row.get('class') != '/Script/Engine.StaticMeshActor' or \
                row.get('label') != expected_label or row.get('folder') != 'MPR/ReferenceV4/Site' or \
                'mpr-reference-exterior-v4' not in row.get('tags', []):
            raise PreservationError('Replacement GUID does not identify the expected existing terminal actor: ' + str(guid))
        components = [c for c in row['components'] if c['name'] == component_name]
        if len(components) != 1 or components[0].get('mesh') != old_mesh:
            raise PreservationError('Terminal replacement component/old mesh does not match baseline: ' + str(identity))
        if components[0].get('class') != '/Script/Engine.StaticMeshComponent' or 'instance_count' in components[0]:
            raise PreservationError('Terminal replacement requires one ordinary StaticMeshComponent')
        approved.append(dict(replacement))
    return sorted(approved, key=lambda r: (r['actor_guid'], r['component_name']))


def terminal_mesh_replacement_plan(before, mesh_targets, *, extension_namespace=EXTENSION_NAMESPACE):
    """Resolve exact old-mesh -> new-mesh targets into baseline GUID/component IDs.

    The caller chooses the targets; this function never changes Unreal objects.
    Persist the returned list as the audit allowlist and pass it unchanged to
    assert_preserved before save and after reload. The three old terminal meshes
    batch 29 road endings: spatial review must still constrain the *contents* of
    replacement assets to approved joining strips, retaining unmatched endings.
    """
    plan = []
    for old_mesh, new_mesh in mesh_targets.items():
        matches = [(row, component) for row in before['actors'] for component in row['components']
                   if component.get('mesh') == old_mesh]
        if len(matches) != 1:
            raise PreservationError('Expected exactly one baseline terminal-mesh component: ' + str(old_mesh))
        row, component = matches[0]
        plan.append({'actor_guid': row['guid'], 'component_name': component['name'],
                     'old_mesh': old_mesh, 'new_mesh': new_mesh})
    return _validated_mesh_replacements(before, plan, _package(extension_namespace))


def assert_preserved(before, after, *, extension_namespace=EXTENSION_NAMESPACE,
                     extension_folder=EXTENSION_FOLDER, extension_tag=EXTENSION_TAG,
                     expected_new_guids=None, allowed_mesh_replacements=()):
    """Require exact baseline records/bytes; only namespaced additions may differ.

    The active map's byte hash is deliberately not equal after a valid append.
    Capture a fresh clean baseline and keep its disk/map backup before import.
    Run this comparison before saving and again after a saved-map reload.
    allowed_mesh_replacements permits only exact planned mesh-reference swaps
    on the three existing terminal actors. Transforms, GUIDs, labels, materials,
    shadow flags, components and original asset bytes remain fully protected.
    After capture must include additional_packages=before['asset_hashes'] so
    old meshes no longer referenced by the saved map remain byte-protected.
    """
    for snapshot in (before, after):
        if snapshot.get('schema_version') != SCHEMA or snapshot.get('preservation_scope') != SCOPE:
            raise PreservationError('Snapshot schema/scope mismatch; capture all-existing snapshot')
        if not snapshot.get('assets_hashed'):
            raise PreservationError('Unhashed inspection snapshot cannot verify preservation')
    assert_clean_baseline(before)
    namespace = _package(extension_namespace)
    approved = _validated_mesh_replacements(before, allowed_mesh_replacements, namespace)
    expected_rows = {r['guid']: deepcopy(r) for r in before['actors']}
    for replacement in approved:
        component = next(c for c in expected_rows[replacement['actor_guid']]['components']
                         if c['name'] == replacement['component_name'])
        component['mesh'] = replacement['new_mesh']
    errors = []
    if before['map'] != after['map']:
        errors.append('Map identity changed')
    old = {r['guid']: r for r in before['actors']}
    new = {r['guid']: r for r in after['actors']}
    if len(old) != len(before['actors']) or len(new) != len(after['actors']):
        errors.append('Duplicate actor GUIDs')
    for guid, row in old.items():
        current = new.get(guid)
        if current is None:
            errors.append('Existing actor disappeared/recreated: ' + row['label'])
        elif current != expected_rows[guid]:
            fields = [k for k in sorted(set(current) | set(row))
                      if current.get(k) != expected_rows[guid].get(k)]
            errors.append('Existing actor changed: ' + row['label'] + ' [' + ', '.join(fields) + ']')
    for replacement in approved:
        row = new.get(replacement['actor_guid'])
        component = next((c for c in row['components'] if c['name'] == replacement['component_name']), None) if row else None
        if component is None or component.get('mesh') != replacement['new_mesh']:
            errors.append('Planned terminal mesh replacement was not applied: ' + replacement['actor_guid'])
        if _package(replacement['new_mesh']) not in after['asset_hashes']:
            errors.append('Replacement mesh package is missing from after hashes: ' + replacement['new_mesh'])
    old_paths = {row['path'] for row in old.values()}
    added = sorted(set(new) - set(old))
    for guid in added:
        row = new[guid]
        if extension_tag not in row['tags'] or not _under(row['folder'], extension_folder):
            errors.append('Unexpected new actor outside extension ownership: ' + row['label'])
        if row.get('attachment_parent') in old_paths:
            errors.append('New actor attached to existing actor: ' + row['label'])
        if any(c.get('attach_parent') and any(c['attach_parent'].startswith(p + '.') for p in old_paths)
               for c in row['components']):
            errors.append('New component attached to existing actor: ' + row['label'])
        if row.get('render_settings') or any(c.get('render_settings') for c in row['components']):
            errors.append('New scene-wide render controller is forbidden: ' + row['label'])
    if expected_new_guids is not None and added != sorted(expected_new_guids):
        errors.append('Expected new actor GUIDs do not match saved/reloaded additions')
    for package, hashes in before['asset_hashes'].items():
        if after['asset_hashes'].get(package) != hashes:
            errors.append('Protected dependency package changed/missing: ' + package)
    for package in set(after['asset_hashes']) - set(before['asset_hashes']):
        if not _under(package, namespace):
            errors.append('New dependency outside extension namespace: ' + package)
    if before.get('frozen_files', {}) != after.get('frozen_files', {}):
        errors.append('Protected source/file bytes changed')
    for package in after.get('dirty_content', []):
        if not _under(package.split('.')[0], namespace):
            errors.append('Protected/unknown dirty content package: ' + package)
    if any(p.split('.')[0] != before['map'] for p in after.get('dirty_maps', [])):
        errors.append('An unrelated map became dirty')
    if errors:
        raise PreservationError('\n'.join(errors[:24]))
    return {'protected_actors': len(old),
            'protected_instances': sum(c.get('instance_count', 0) for row in old.values()
                                       for c in row['components']),
            'protected_asset_packages': len(before['asset_hashes']),
            'protected_digest': canonical_digest(before['actors']),
            'unchanged_actor_count': len(old) - len({r['actor_guid'] for r in approved}),
            'approved_mesh_replacements': approved,
            'new_actor_count': len(added), 'new_actor_guids': added}
