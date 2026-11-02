"""Read-only UE snapshots and fail-closed checks for an exterior-only update.

No Unreal import or editor mutation occurs on import. The caller supplies the
Unreal module to capture_editor_snapshot(). Snapshots include all actors; only
the explicitly identified old exterior may disappear. Never use this module's
classification as a general-purpose deletion filter: retain the baseline GUID
list, and delete those exact actors only after the complete preflight succeeds.
"""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re

MAP = '/Game/Maps/MPR_CAD_Warehouse'
OLD_OWNER = 'mpr-cad-scene-v1'
NEW_OWNER = 'mpr-reference-exterior-v3'
EXTERIOR_OWNERS = {'mpr-reference-exterior-v3': 'MPR/ReferenceV3',
                   'mpr-reference-exterior-v4': 'MPR/ReferenceV4'}
SCHEMA = 1
INTERIOR_LABELS = {'MPR_Floor', 'MPR_OfficePartitions', 'MPR_OfficeGlazing'}
INTERIOR_FOLDERS = ('MPR/Architecture/Columns', 'MPR/Storage', 'MPR/Operations', 'MPR/Equipment')
LIGHT_LABELS = {'MPR_KeyLight', 'MPR_Ambient', 'MPR_GHS_Style', 'MPR_StudioSky'}
CAMERA_LABELS = {'MPR_WarehouseCamera', 'MPR_ReviewCamera'}


class PreservationError(RuntimeError):
    """The update changed an actor or asset outside its exterior boundary."""


def _under(folder, prefix):
    return folder == prefix or folder.startswith(prefix + '/')


def classify_actor(row):
    """Unknown/user-added actors are protected, including objects in MPR folders."""
    label, folder, tags = row['label'], row['folder'], set(row['tags'])
    if label in INTERIOR_LABELS or any(_under(folder, f) for f in INTERIOR_FOLDERS):
        return 'interior'
    # Preserve camera identity/controls while permitting its authored exterior
    # framing to change. They are never members of the deletion allowlist.
    if label in CAMERA_LABELS and folder == 'MPR/Cameras' and 'MPRWarehouse' in tags:
        return 'camera'
    if any(owner in tags and _under(folder, prefix) for owner, prefix in EXTERIOR_OWNERS.items()):
        return 'new_exterior'
    if {'MPRWarehouse', OLD_OWNER}.issubset(tags):
        if re.fullmatch(r'MPR_Exterior_\d{2}', label) and folder == 'MPR/Architecture':
            return 'old_exterior'
        if label in {'MPR_Roof', 'MPR_RoofEdge', 'MPR_RoofSolar', 'MPR_RoofPlant'} and folder == 'MPR/Architecture/RemovableRoof':
            return 'old_exterior'
        if re.fullmatch(r'MPR_DockDoors_-?\d+_-?\d+', label) and folder == 'MPR/Architecture/Docks':
            return 'old_exterior'
        if label in LIGHT_LABELS and folder == 'MPR/Lighting':
            return 'old_exterior'
        if _under(folder, 'MPR/Environment'):
            meshes = [c.get('mesh') for c in row.get('components', []) if c.get('mesh')]
            # Shared truck assets are external decoration; internal shared
            # conveyor/rack assets cannot enter this replacement list.
            if meshes and all(m.startswith('/Game/MPRWarehouse/Environment/Meshes/') or
                              m.startswith('/Game/GHSZcoolSmartFactory/Park/Meshes/SM_GHSPark_ClosedTruck.')
                              for m in meshes):
                return 'old_exterior'
    return 'protected_other'


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def _path(obj):
    return obj.get_path_name() if obj else None


def _v(value):
    return [float(value.x), float(value.y), float(value.z)]


def _transform(value):
    q = value.rotation
    values = {'translation_cm': _v(value.translation),
              'rotation_xyzw': [float(q.x), float(q.y), float(q.z), float(q.w)],
              'scale': _v(value.scale3d)}
    if not all(math.isfinite(v) for part in values.values() for v in part):
        raise PreservationError('Non-finite transform')
    return values


def _sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def referenced_package_hashes(project_root, package_paths):
    """Hash project packages and companions. Engine packages stay path-stable."""
    root = Path(project_root).resolve()
    result = {}
    for package in sorted(set(p.split('.')[0] for p in package_paths if p and p.startswith('/Game/'))):
        if not re.fullmatch(r'/Game/[A-Za-z0-9_/]+', package):
            raise PreservationError('Invalid dependency package: ' + package)
        primary = root / ('Content/' + package[len('/Game/'):] + '.uasset')
        if not primary.is_file():
            raise PreservationError('Referenced project package is missing: ' + str(primary))
        paths = [primary] + [primary.with_suffix(s) for s in ('.uexp', '.ubulk', '.uptnl') if primary.with_suffix(s).is_file()]
        result[package] = {p.relative_to(root).as_posix(): _sha(p) for p in paths}
    return result


def capture_editor_snapshot(u, *, project_root, expected_map=MAP, hash_assets=True):
    """Inspect the active editor world; never load/save, hide, select, or modify.

    Component transforms use local space and retain instance order. All raw
    IEEE float values are serialized without rounding; an altered or recreated
    actor cannot pass by merely preserving its visible name or instance count.
    """
    actor_sub = u.get_editor_subsystem(u.EditorActorSubsystem)
    level_sub = u.get_editor_subsystem(u.LevelEditorSubsystem)
    editor_sub = u.get_editor_subsystem(u.UnrealEditorSubsystem)
    if level_sub.is_in_play_in_editor():
        raise PreservationError('Snapshot requires the non-PIE editor world')
    world = editor_sub.get_editor_world()
    current_map = world.get_path_name().split('.')[0]
    if current_map != expected_map:
        raise PreservationError('Refusing to switch map: ' + current_map)
    rows, dependencies = [], set()
    for actor in actor_sub.get_all_level_actors():
        guid = u.GuidLibrary.conv_guid_to_string(actor.get_editor_property('actor_guid'))
        if not u.GuidLibrary.is_valid_guid(actor.get_editor_property('actor_guid')):
            raise PreservationError('Actor has no persistent GUID: ' + actor.get_path_name())
        row = {'guid': guid, 'path': actor.get_path_name(), 'name': actor.get_name(),
               'class': actor.get_class().get_path_name(), 'label': actor.get_actor_label(),
               'folder': str(actor.get_folder_path()), 'tags': [str(t) for t in actor.tags],
               'transform': _transform(actor.get_actor_transform()),
               'attachment_parent': _path(actor.get_attach_parent_actor()),
               'hidden': bool(actor.get_editor_property('hidden')),
               'tick_enabled': actor.is_actor_tick_enabled(),
               'collision_enabled': actor.get_actor_enable_collision(), 'components': []}
        for component in actor.get_components_by_class(u.ActorComponent):
            c = {'name': component.get_name(), 'class': component.get_class().get_path_name(),
                 'tags': [str(t) for t in component.component_tags]}
            if isinstance(component, u.SceneComponent):
                c.update(transform=_transform(component.get_relative_transform()),
                         attach_parent=_path(component.get_attach_parent()),
                         mobility=str(component.mobility), visible=bool(component.visible),
                         hidden_in_game=bool(component.hidden_in_game))
            if isinstance(component, u.StaticMeshComponent):
                c.update(mesh=_path(component.static_mesh),
                         materials=[_path(component.get_material(i)) for i in range(component.get_num_materials())],
                         collision_profile=str(component.get_collision_profile_name()),
                         cast_shadow=bool(component.cast_shadow))
            if isinstance(component, u.InstancedStaticMeshComponent):
                count = component.get_instance_count()
                c.update(instance_count=count,
                         instance_transforms=[_transform(component.get_instance_transform(i, world_space=False)) for i in range(count)],
                         num_custom_data_floats=int(component.get_editor_property('num_custom_data_floats')),
                         custom_data=[float(v) for v in component.get_editor_property('per_instance_sm_custom_data')])
            row['components'].append(c)
        row['components'].sort(key=lambda c: c['name'])
        row['classification'] = classify_actor(row)
        if row['classification'] in ('interior', 'protected_other'):
            dependencies.add(row['class'])
            for c in row['components']:
                dependencies.update([c.get('mesh'), *c.get('materials', [])])
        rows.append(row)
    rows.sort(key=lambda r: r['guid'])
    if len({r['guid'] for r in rows}) != len(rows):
        raise PreservationError('Duplicate actor GUIDs')
    # Material inheritance/default mesh material references must also remain
    # byte-identical. AssetRegistry reads metadata and does not save packages.
    if hash_assets:
        registry = u.AssetRegistryHelpers.get_asset_registry()
        opts = u.AssetRegistryDependencyOptions(include_soft_package_references=True,
                  include_hard_package_references=True, include_searchable_names=False,
                  include_soft_management_references=False, include_hard_management_references=False)
        pending = [p.split('.')[0] for p in dependencies if p and p.startswith('/Game/')]
        packages = set()
        while pending:
            package = pending.pop()
            if package in packages:
                continue
            packages.add(package)
            pending.extend(str(p) for p in registry.get_dependencies(package, opts)
                           if str(p).startswith('/Game/') and str(p) not in packages)
        assets = referenced_package_hashes(project_root, packages)
    else:
        assets = {}
    answer = {'schema_version': SCHEMA, 'map': current_map, 'actors': rows, 'asset_hashes': assets,
              'counts': dict(Counter(r['classification'] for r in rows)),
              'dirty_maps': sorted(p.get_path_name() for p in u.EditorLoadingAndSavingUtils.get_dirty_map_packages()),
              'dirty_content': sorted(p.get_path_name() for p in u.EditorLoadingAndSavingUtils.get_dirty_content_packages())}
    answer['protected_digest'] = canonical_digest([r for r in rows if r['classification'] in ('interior', 'protected_other')])
    return answer


def replacement_guids(snapshot):
    return [r['guid'] for r in snapshot['actors'] if r['classification'] == 'old_exterior']


def assert_preserved(before, after, *, require_old_exterior_removed=False):
    """Compare identity plus complete recorded state; raise with concise errors."""
    errors = []
    if before.get('schema_version') != SCHEMA or after.get('schema_version') != SCHEMA:
        raise PreservationError('Snapshot schema mismatch')
    if before['map'] != after['map']:
        errors.append('Map identity changed')
    old = {r['guid']: r for r in before['actors']}
    new = {r['guid']: r for r in after['actors']}
    if len(old) != len(before['actors']) or len(new) != len(after['actors']):
        errors.append('Duplicate actor GUIDs')
    protected = 0
    for guid, row in old.items():
        current = new.get(guid)
        if row['classification'] in ('interior', 'protected_other'):
            protected += 1
            if current is None:
                errors.append('Protected actor disappeared/recreated: ' + row['label'])
            elif current != row:
                fields = [k for k in sorted(set(current) | set(row)) if current.get(k) != row.get(k)]
                errors.append('Protected actor changed: ' + row['label'] + ' [' + ', '.join(fields) + ']')
        elif row['classification'] == 'camera':
            if current is None or any(row[k] != current.get(k) for k in ('path', 'name', 'class', 'label')):
                errors.append('Existing camera identity changed: ' + row['label'])
        elif require_old_exterior_removed and row['classification'] == 'old_exterior' and current:
            errors.append('Old exterior actor remains: ' + row['label'])
    for guid, row in new.items():
        if guid not in old and row['classification'] != 'new_exterior':
            errors.append('Unexpected new non-exterior actor: ' + row['label'])
    if before['asset_hashes'] != after['asset_hashes']:
        for package in sorted(set(before['asset_hashes']) | set(after['asset_hashes'])):
            if before['asset_hashes'].get(package) != after['asset_hashes'].get(package):
                errors.append('Protected dependency package changed: ' + package)
    if errors:
        raise PreservationError('\n'.join(errors[:40]) + ('\n... additional failures' if len(errors) > 40 else ''))
    return {'success': True, 'protected_actors': protected,
            'interior_actors': sum(r['classification'] == 'interior' for r in old.values()),
            'protected_digest': before['protected_digest'], 'protected_assets': len(before['asset_hashes']),
            'new_exterior_actors': sum(r['classification'] == 'new_exterior' for r in new.values())}
