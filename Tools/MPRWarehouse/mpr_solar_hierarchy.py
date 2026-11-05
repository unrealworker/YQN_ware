"""Import five reviewed solar replacements into the active MPR map.

Call preflight(unreal) for a read-only check, or apply(unreal) from the owning
preservation executor. New assets are saved individually; this module never
opens/saves a map, creates actors, edits transforms, or invokes Git.
"""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = 'SourceAssets/MPR/hierarchy_20261105/solar'
MAP = '/Game/Maps/MPR_CAD_Warehouse_B50B57'
DEST = '/Game/MPRWarehouse/Hierarchy20261105'
OWNER = 'mpr-solar-hierarchy-20261105'
TAG_OWNER = 'MPRSolarHierarchy.Owner'
TAG_SHA = 'MPRSolarHierarchy.SourceSHA256'
ROLES = ['MPRH_SolarFrame', 'MPRH_SolarCells', 'MPRH_SolarCellsLight', 'MPRH_SolarCellsShade']
IDENTITIES = {
    'BC217E8B43B202CB7FE238B6F4B6556B': ('StaticMeshActor_41', '00_0'),
    'C7BD2BEB41095B0B59873AA3D64DD765': ('StaticMeshActor_42', '01_0'),
    '3D07E0584AE579B3F87A44B617CBFF87': ('StaticMeshActor_43', '01_1'),
    'CBE6448C453AE125A1FA0899147E45A5': ('StaticMeshActor_44', '02_0'),
    'B68AC22E4D4B120213C6FF93AEA28E06': ('StaticMeshActor_45', '02_1'),
}
OLD_MATERIALS = [
    '/Game/MPRWarehouse/ReferenceV4/Materials/MI_MPR4_SolarFrame',
    '/Game/MPRWarehouse/RebuildB50B57/Materials/MI_MPR4_SolarCells',
    '/Game/MPRWarehouse/RebuildB50B57/Materials/MI_MPR4_SolarMid',
    '/Game/MPRWarehouse/RebuildB50B57/Materials/MI_MPR4_SolarFar',
]


def require(condition, message):
    if not condition:
        raise RuntimeError('Solar hierarchy: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def package(obj):
    return obj.get_path_name().split('.')[0] if obj is not None else None


def material_path(role):
    require(role in ROLES, 'unknown material role')
    return DEST + '/Materials/M_' + role


def mesh_path(row):
    return DEST + '/Meshes/' + row['name']


def mesh_digest(row, materials):
    return digest(dict(row=row, materials=materials))


def source_contract(root=ROOT):
    """Validate every reviewed input before creating any UE asset."""
    root = Path(root).resolve()
    base = (root / SOURCE).resolve()
    manifest_path = base / 'manifest.json'
    manifest = read(manifest_path)
    require(manifest.get('success') is True and manifest['map'] == MAP and manifest['namespace'] == DEST,
            'manifest targets another map or namespace')
    require(manifest['material_roles'] == ROLES and set(manifest['materials']) == set(ROLES),
            'exactly four reviewed material roles are required')
    require(manifest['module_count'] == 5636 and manifest['preserved_device_count'] == 195,
            'reviewed module/device count changed')
    require(all(manifest[k] is True for k in ('module_centres_unchanged', 'blocks_unchanged',
                                              'per_lod_identical_module_silhouettes')),
            'source does not preserve the reviewed solar layout')
    geometry = read(base / 'geometry_validation.json')
    silhouette = read(base / 'silhouette_validation.json')
    require(geometry.get('success') is True and geometry['manifest_sha256'] == sha(manifest_path),
            'geometry validation does not match this manifest')
    require(silhouette.get('success') is True and silhouette['actual_fbx_identical_top_geometry_all_lods']
            and silhouette['source_module_centres_unchanged'] and silhouette['outside_original_block_count'] == 0
            and silhouette['minimum_device_clearance_m'] >= silhouette['required_device_clearance_m'] >= .85,
            'module silhouette or equipment-clearance validation failed')
    for name, expected in manifest['source_hashes'].items():
        source = (root / name).resolve()
        require(source.is_relative_to((root / 'SourceAssets/MPR/rebuild_b50b57/solar').resolve())
                and source.is_file() and sha(source) == expected, 'old solar input changed: ' + name)
    old = read(root / manifest['layout_source'])
    require(old['blocks'] == manifest['preserved_blocks'] and sum(map(len, old['blocks'].values())) == 59,
            'original 59 block regions changed')
    modules = read(base / 'module_layout.json')
    require(hashlib.sha256(json.dumps(modules, sort_keys=True).encode()).hexdigest()
            == manifest['module_silhouettes_sha256'], 'module layout hash changed')
    rows = manifest['meshes']
    banks = {value[1] for value in IDENTITIES.values()}
    require(len(rows) == 5 and {r['bank'] for r in rows} == banks, 'expected exactly five bank meshes')
    checked = {str(manifest_path.relative_to(root)).replace('\\', '/'): sha(manifest_path)}
    exports = {r['name']: r for r in manifest['export_meshes']}
    require(len(exports) == 15, 'expected 15 exported LOD sources')
    for row in rows:
        bank = row['bank']
        require(row['name'] == 'SM_MPRH_SolarBank_' + bank
                and row['retained_actor_label'] == 'MPR4_SolarBank_' + bank
                and row['source_mesh'] == '/Game/MPRWarehouse/RebuildB50B57/Architecture/Meshes/SM_MPRR_SolarBank_' + bank,
                'mesh/actor identity mismatch')
        require(row['material_roles'] == ROLES and row['all_lod_material_roles'] == ROLES
                and row['lod_material_roles'] == [ROLES] * 3, 'LOD material role contract changed')
        require(row['nanite'] is False and row['collision'] is False and row['full_precision_uvs'] is True,
                'unexpected Nanite/collision/UV policy')
        require(len(row['lod_files']) == len(row['lod_sha256']) == 2, 'missing explicit LOD files')
        sizes = row['lod_screen_sizes']
        require(len(sizes) == 3 and all(math.isfinite(x) for x in sizes)
                and 1 == sizes[0] > sizes[1] > sizes[2] > 0, 'invalid LOD screens')
        require(len(row['bounds_m']) == 3 and all(len(pair) == 2 and all(math.isfinite(v) for v in pair)
                and pair[0] < pair[1] for pair in row['bounds_m']), 'invalid mesh bounds')
        require(len(row['lod_triangles']) == 3 and all(type(n) is int and n > 0 for n in row['lod_triangles']),
                'invalid triangle budget')
        for lod, (name, expected) in enumerate(zip([row['fbx'], *row['lod_files']], [row['sha256'], *row['lod_sha256']])):
            path = (root / name).resolve()
            basename = row['name'] + ('' if lod == 0 else '_LOD' + str(lod))
            require(path.is_relative_to(base) and path.name == basename + '.fbx'
                    and path.is_file() and sha(path) == expected, 'FBX source/hash mismatch: ' + name)
            require(exports[basename]['sha256'] == expected
                    and exports[basename]['triangles'] == row['lod_triangles'][lod], 'export row differs from import row')
            checked[name] = expected
    require(sum(r['lod_triangles'][0] for r in rows) <= 150000, 'LOD0 exceeds reviewed 150k budget')
    require(geometry['triangles_per_lod'] == [sum(r['lod_triangles'][i] for r in rows) for i in range(3)],
            'triangle validation no longer matches the sources')
    for role, spec in manifest['materials'].items():
        require(len(spec['base_color']) == 3 and all(math.isfinite(v) and 0 <= v <= 1 for v in spec['base_color'])
                and .55 <= spec['roughness'] <= 1 and spec['metallic'] == 0 and 0 <= spec['specular'] <= .25
                and spec['emission'] == 0 and spec['normal_strength'] == 0, 'unexpected material definition: ' + role)
    # Finish color is independently reviewed; the original manifest and its
    # geometry validation stay byte-identical. Repeated calls always derive
    # from the raw source, never multiply an already-darkened value again.
    palette_path = base / 'final_palette.json'
    palette = read(palette_path)
    require(palette == dict(schema_version=1, owner=OWNER, map=MAP, namespace=DEST,
                           original_manifest_sha256=sha(manifest_path),
                           original_materials_sha256=digest(manifest['materials']),
                           cell_roles=ROLES[1:], cell_linear_multiplier=.70,
                           frame_policy='unchanged', preserve_geometry=True),
            'final palette differs from the reviewed three-cell 0.70 finish')
    manifest['materials'] = deepcopy(manifest['materials'])
    for role in palette['cell_roles']:
        manifest['materials'][role]['base_color'] = [v * palette['cell_linear_multiplier']
                                                   for v in manifest['materials'][role]['base_color']]
    return manifest, dict(manifest_sha256=sha(manifest_path), checked_source_files=checked,
                          geometry_validation_sha256=sha(base / 'geometry_validation.json'),
                          silhouette_validation_sha256=sha(base / 'silhouette_validation.json'),
                          final_palette_sha256=sha(palette_path), final_palette=palette)


def transform(value):
    q = value.rotation
    return dict(translation=[float(value.translation.x), float(value.translation.y), float(value.translation.z)],
                rotation=[float(q.x), float(q.y), float(q.z), float(q.w)],
                scale=[float(value.scale3d.x), float(value.scale3d.y), float(value.scale3d.z)])


def actor_state(u, actor, component):
    return dict(guid=u.GuidLibrary.conv_guid_to_string(actor.get_editor_property('actor_guid')),
                name=actor.get_name(), path=actor.get_path_name(), label=actor.get_actor_label(),
                folder=str(actor.get_folder_path()), tags=[str(v) for v in actor.tags],
                actor_transform=transform(actor.get_actor_transform()),
                component_name=component.get_name(), component_transform=transform(component.get_relative_transform()),
                component_tags=[str(v) for v in component.component_tags],
                attachment=actor.get_attach_parent_actor().get_path_name() if actor.get_attach_parent_actor() else None,
                hidden=bool(actor.get_editor_property('hidden')), visible=bool(component.visible),
                hidden_in_game=bool(component.hidden_in_game), mobility=str(component.mobility),
                collision_profile=str(component.get_collision_profile_name()), cast_shadow=bool(component.cast_shadow),
                forced_lod_model=int(component.get_editor_property('forced_lod_model')),
                mesh=package(component.static_mesh),
                materials=[package(component.get_material(i)) for i in range(component.get_num_materials())],
                override_materials=[package(m) for m in component.get_editor_property('override_materials')])


def owned_asset(u, path, expected_digest, cls):
    lib = u.EditorAssetLibrary
    if not lib.does_asset_exist(path):
        return None
    asset = lib.load_asset(path)
    require(isinstance(asset, cls) and lib.get_metadata_tag(asset, TAG_OWNER) == OWNER
            and lib.get_metadata_tag(asset, TAG_SHA) == expected_digest,
            'existing destination has unreviewed ownership/source; refusing overwrite: ' + path)
    return asset


def transition_asset(u, path, old_digest, new_digest, cls):
    """Accept only this owned asset at one of two exact palette revisions."""
    lib = u.EditorAssetLibrary
    require(lib.does_asset_exist(path), 'palette finish requires an existing owned asset: ' + path)
    asset = lib.load_asset(path)
    current_digest = lib.get_metadata_tag(asset, TAG_SHA) if asset is not None else None
    require(isinstance(asset, cls) and lib.get_metadata_tag(asset, TAG_OWNER) == OWNER
            and current_digest in (old_digest, new_digest),
            'palette finish encountered unknown asset ownership/source: ' + path)
    return asset, current_digest


def _preflight(u, *, allow_palette_transition=False):
    require(Path(u.Paths.convert_relative_path_to_full(u.Paths.project_dir())).resolve() == ROOT.resolve(),
            'wrong UE project')
    require(not u.get_editor_subsystem(u.LevelEditorSubsystem).is_in_play_in_editor(), 'stop PIE before import')
    world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    require(package(world) == MAP, 'active map must be the existing MPR map; refusing to switch')
    manifest, source_report = source_contract()
    original_materials = read(ROOT / SOURCE / 'manifest.json')['materials'] if allow_palette_transition else None
    actors = list(u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors())
    by_guid = {}
    for actor in actors:
        guid = u.GuidLibrary.conv_guid_to_string(actor.get_editor_property('actor_guid'))
        require(guid not in by_guid, 'duplicate Actor GUID')
        by_guid[guid] = actor
    rows = {r['bank']: r for r in manifest['meshes']}
    targets = []
    for guid, (name, bank) in IDENTITIES.items():
        actor = by_guid.get(guid)
        require(actor is not None and actor.get_name() == name and isinstance(actor, u.StaticMeshActor)
                and actor.get_actor_label() == rows[bank]['retained_actor_label'], 'retained Actor identity changed: ' + bank)
        components = list(actor.get_components_by_class(u.StaticMeshComponent))
        require(len(components) == 1 and components[0].get_name() == 'StaticMeshComponent0'
                and not isinstance(components[0], u.InstancedStaticMeshComponent), 'unexpected solar component: ' + bank)
        component = components[0]
        state = actor_state(u, actor, component)
        require(state['mesh'] in (rows[bank]['source_mesh'], mesh_path(rows[bank])), 'solar mesh changed manually: ' + bank)
        if allow_palette_transition:
            require(state['mesh'] == mesh_path(rows[bank]), 'palette finish requires the already imported hierarchy mesh')
        expected = OLD_MATERIALS if state['mesh'] == rows[bank]['source_mesh'] else [material_path(r) for r in ROLES]
        require(state['materials'] == expected, 'solar effective materials changed manually: ' + bank)
        require(state['forced_lod_model'] == 0, 'solar component forces a fixed LOD: ' + bank)
        targets.append(dict(actor=actor, component=component, row=rows[bank], before=state))
    require(sum(1 for a in actors if a.get_actor_label().startswith('MPR4_SolarBank_')) == 5,
            'unexpected duplicate/additional solar Actor labels')
    destinations = []
    for role in ROLES:
        path = material_path(role)
        audit_spec = manifest['materials'][role]
        if allow_palette_transition:
            existing, current_digest = transition_asset(u, path, digest(original_materials[role]), digest(audit_spec), u.Material)
            if current_digest == digest(original_materials[role]):
                audit_spec = original_materials[role]
        else:
            existing = owned_asset(u, path, digest(audit_spec), u.Material)
        if existing is not None:
            material_audit(u, existing, audit_spec)
        destinations.append(dict(package=path, exists=existing is not None, kind='material'))
    for row in manifest['meshes']:
        path = mesh_path(row)
        if allow_palette_transition:
            existing, _ = transition_asset(u, path, mesh_digest(row, original_materials),
                                            mesh_digest(row, manifest['materials']), u.StaticMesh)
        else:
            existing = owned_asset(u, path, mesh_digest(row, manifest['materials']), u.StaticMesh)
        if existing is not None:
            audit_mesh(u, existing, row)
        destinations.append(dict(package=path, exists=existing is not None, kind='mesh'))
    return manifest, targets, dict(success=True, map=MAP, namespace=DEST, source=source_report,
                                    targets=[t['before'] for t in targets], destinations=destinations,
                                    actor_guids_before=sorted(by_guid))


def preflight(u):
    return _preflight(u)[2]


def mark_owned(u, asset, source_digest):
    u.EditorAssetLibrary.set_metadata_tag(asset, TAG_OWNER, OWNER)
    u.EditorAssetLibrary.set_metadata_tag(asset, TAG_SHA, source_digest)


def material_audit(u, material, spec):
    ml = u.MaterialEditingLibrary
    require(material.get_editor_property('blend_mode') == u.BlendMode.BLEND_OPAQUE
            and material.get_editor_property('shading_model') == u.MaterialShadingModel.MSM_DEFAULT_LIT
            and ml.get_num_material_expressions(material) == 4, 'material must remain a simple opaque four-input surface')
    color = ml.get_material_default_vector_parameter_value(material, 'BaseColor')
    require(max(abs(a-b) for a, b in zip([color.r, color.g, color.b], spec['base_color'])) < 1e-6,
            'material base color readback mismatch')
    for parameter, key in [('Roughness', 'roughness'), ('Metallic', 'metallic'), ('Specular', 'specular')]:
        require(abs(ml.get_material_default_scalar_parameter_value(material, parameter) - spec[key]) < 1e-6,
                'material scalar readback mismatch: ' + parameter)
    return dict(package=package(material), parameters=spec, expression_count=4, opaque=True, default_lit=True)


def create_material(u, role, spec):
    path = material_path(role)
    material = owned_asset(u, path, digest(spec), u.Material)
    reused = material is not None
    if not reused:
        material = u.AssetToolsHelpers.get_asset_tools().create_asset(
            path.rsplit('/', 1)[-1], path.rsplit('/', 1)[0], u.Material, u.MaterialFactoryNew())
        require(isinstance(material, u.Material), 'material creation failed: ' + path)
        material.set_editor_property('blend_mode', u.BlendMode.BLEND_OPAQUE)
        material.set_editor_property('shading_model', u.MaterialShadingModel.MSM_DEFAULT_LIT)
        ml = u.MaterialEditingLibrary
        tint = ml.create_material_expression(material, u.MaterialExpressionVectorParameter)
        tint.set_editor_property('parameter_name', 'BaseColor')
        tint.set_editor_property('default_value', u.LinearColor(*spec['base_color'], 1.))
        require(ml.connect_material_property(tint, '', u.MaterialProperty.MP_BASE_COLOR), 'cannot connect BaseColor')
        for parameter, key, prop in [('Roughness', 'roughness', u.MaterialProperty.MP_ROUGHNESS),
                                     ('Metallic', 'metallic', u.MaterialProperty.MP_METALLIC),
                                     ('Specular', 'specular', u.MaterialProperty.MP_SPECULAR)]:
            scalar = ml.create_material_expression(material, u.MaterialExpressionScalarParameter)
            scalar.set_editor_property('parameter_name', parameter)
            scalar.set_editor_property('default_value', spec[key])
            require(ml.connect_material_property(scalar, '', prop), 'cannot connect ' + parameter)
        ml.recompile_material(material)
        material_audit(u, material, spec)
        mark_owned(u, material, digest(spec))
        require(u.EditorAssetLibrary.save_loaded_asset(material, only_if_is_dirty=False), 'cannot save new material')
    return material, dict(reused=reused, **material_audit(u, material, spec))


@contextmanager
def legacy_fbx(u):
    name = 'Interchange.FeatureFlags.Import.FBX'
    before = u.SystemLibrary.get_console_variable_int_value(name)
    try:
        u.SystemLibrary.execute_console_command(None, name + ' 0')
        require(u.SystemLibrary.get_console_variable_int_value(name) == 0, 'cannot select legacy FBX importer')
        yield
    finally:
        u.SystemLibrary.execute_console_command(None, name + ' ' + str(before))
        require(u.SystemLibrary.get_console_variable_int_value(name) == before, 'FBX flag failed to restore')


def bind_lod_materials(u, mesh, row, materials):
    """Name-addressed remap from import_mpr_scene.bind_explicit_lod_materials.

    Standalone to avoid importing that module's unrelated scene globals/files.
    Preserve each imported section role before compacting duplicated LOD slots.
    """
    sm = u.get_editor_subsystem(u.StaticMeshEditorSubsystem)
    require(sm.get_lod_count(mesh) == 3, 'explicit LOD import count differs')
    slots = list(mesh.static_materials)
    names = [str(s.get_editor_property('imported_material_slot_name')) for s in slots]
    per_lod = []
    for lod in range(3):
        current = []
        for section in range(mesh.get_num_sections(lod)):
            index = sm.get_lod_material_slot(mesh, lod, section)
            require(0 <= index < len(slots), 'invalid imported LOD slot index')
            current.append(names[index])
        require(len(current) == len(ROLES) and set(current) == set(ROLES), 'missing/unexpected LOD section roles')
        per_lod.append(current)
    compact = []
    for role in ROLES:
        slot = slots[names.index(role)]
        slot.material_interface = materials[role]
        slot.set_editor_property('material_slot_name', role)
        compact.append(slot)
    mesh.set_editor_property('static_materials', compact)
    for lod, roles in enumerate(per_lod):
        for section, role in enumerate(roles):
            sm.set_lod_material_slot(mesh, ROLES.index(role), lod, section)
    require(sm.set_lod_screen_sizes(mesh, row['lod_screen_sizes']), 'failed setting explicit LOD screens')
    return dict(imported_roles_before=names, compact_roles=ROLES,
                removed_unused_or_duplicate_slots=len(slots) - len(compact))


def audit_mesh(u, mesh, row):
    sm = u.get_editor_subsystem(u.StaticMeshEditorSubsystem)
    require(sm.get_lod_count(mesh) == 3 and not sm.get_nanite_settings(mesh).enabled,
            'mesh must use three authored non-Nanite LODs')
    slots = list(mesh.static_materials)
    require([str(s.get_editor_property('imported_material_slot_name')) for s in slots] == ROLES,
            'compacted material slot order differs')
    require([package(s.material_interface) for s in slots] == [material_path(role) for role in ROLES],
            'mesh material bindings differ')
    screens = list(sm.get_lod_screen_sizes(mesh))
    require(len(screens) == 3 and max(abs(a-b) for a, b in zip(screens, row['lod_screen_sizes'])) < 1e-5,
            'LOD screen-size readback differs')
    lods = []
    for lod in range(3):
        triangles = mesh.get_num_triangles(lod)
        require(triangles == row['lod_triangles'][lod], 'imported LOD triangle count differs')
        roles = []
        for section in range(mesh.get_num_sections(lod)):
            index = sm.get_lod_material_slot(mesh, lod, section)
            require(0 <= index < len(ROLES), 'readback invalid section index')
            roles.append(ROLES[index])
        require(len(roles) == 4 and set(roles) == set(ROLES), 'LOD section remap differs')
        settings = sm.get_lod_build_settings(mesh, lod)
        require(settings.get_editor_property('use_full_precision_u_vs')
                and not settings.get_editor_property('generate_lightmap_u_vs'), 'unexpected LOD build settings')
        lods.append(dict(lod=lod, triangles=triangles, section_roles=roles, screen_size=screens[lod]))
    require(sm.get_simple_collision_count(mesh) == 0 and sm.get_convex_collision_count(mesh) == 0,
            'unexpected generated collision')
    b = mesh.get_bounds()
    actual = [[b.origin.x-b.box_extent.x, b.origin.x+b.box_extent.x],
              [b.origin.y-b.box_extent.y, b.origin.y+b.box_extent.y],
              [b.origin.z-b.box_extent.z, b.origin.z+b.box_extent.z]]
    x, y, z = row['bounds_m']
    expected = [[x[0]*100, x[1]*100], [-y[1]*100, -y[0]*100], [z[0]*100, z[1]*100]]
    error = max(abs(a-b) for aa, bb in zip(actual, expected) for a, b in zip(aa, bb))
    require(error < 2, 'FBX units/axis/bounds mismatch: ' + row['name'])
    return dict(package=package(mesh), bounds_cm=actual, bounds_error_cm=error, lods=lods,
                material_roles=ROLES, nanite=False, collision=False)


def import_mesh(u, row, materials, specs):
    path = mesh_path(row)
    source_digest = mesh_digest(row, specs)
    mesh = owned_asset(u, path, source_digest, u.StaticMesh)
    reused = mesh is not None
    remap = None
    if not reused:
        task = u.AssetImportTask()
        for key, value in dict(filename=str(ROOT / row['fbx']), destination_path=path.rsplit('/', 1)[0],
                               destination_name=row['name'], automated=True, replace_existing=False,
                               replace_existing_settings=False, save=False).items():
            task.set_editor_property(key, value)
        options = u.FbxImportUI()
        for key, value in dict(import_mesh=True, import_as_skeletal=False, import_materials=False,
                               import_textures=False, import_animations=False,
                               mesh_type_to_import=u.FBXImportType.FBXIT_STATIC_MESH,
                               automated_import_should_detect_type=False,
                               reset_to_fbx_on_material_conflict=True).items():
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
        require({str(p).split('.')[0] for p in task.imported_object_paths} == {path}, 'unexpected imported objects')
        mesh = u.EditorAssetLibrary.load_asset(path)
        require(isinstance(mesh, u.StaticMesh), 'FBX failed to import the expected mesh')
        sm = u.get_editor_subsystem(u.StaticMeshEditorSubsystem)
        for lod, filename in enumerate(row['lod_files'], 1):
            require(sm.import_lod(mesh, lod, str(ROOT / filename)) == lod, 'explicit LOD import failed')
        for lod in range(sm.get_lod_count(mesh)):
            settings = sm.get_lod_build_settings(mesh, lod)
            settings.set_editor_property('use_full_precision_u_vs', True)
            settings.set_editor_property('recompute_tangents', True)
            settings.set_editor_property('generate_lightmap_u_vs', False)
            sm.set_lod_build_settings(mesh, lod, settings)
        nanite = sm.get_nanite_settings(mesh)
        if nanite.enabled:
            nanite.enabled = False
            sm.set_nanite_settings(mesh, nanite, True)
        if sm.get_simple_collision_count(mesh) or sm.get_convex_collision_count(mesh):
            require(sm.remove_collisions(mesh), 'cannot remove generated collision')
        remap = bind_lod_materials(u, mesh, row, materials)
        audit_mesh(u, mesh, row)
        mark_owned(u, mesh, source_digest)
        require(u.EditorAssetLibrary.save_loaded_asset(mesh, only_if_is_dirty=False), 'cannot save new solar mesh')
    return mesh, dict(reused=reused, material_remap=remap, **audit_mesh(u, mesh, row))


def apply(u):
    """Import assets, then replace only five mesh/material bindings; no map save."""
    manifest, targets, report = _preflight(u)
    report.update(success=False, materials=[], meshes=[], changed_components=[], map_saved=False,
                  added_actor_guids=[], removed_actor_guids=[])
    materials, meshes = {}, {}
    for role in ROLES:
        materials[role], record = create_material(u, role, manifest['materials'][role])
        report['materials'].append(record)
    with legacy_fbx(u):
        for row in manifest['meshes']:
            meshes[row['name']], record = import_mesh(u, row, materials, manifest['materials'])
            report['meshes'].append(record)
    # The world is untouched until every new asset has passed readback.
    for target in targets:
        require(actor_state(u, target['actor'], target['component']) == target['before'],
                'solar component changed while importing; abort before assignment')
    edited = []
    try:
        for target in targets:
            component = target['component']
            original_mesh = component.static_mesh
            original_overrides = list(component.get_editor_property('override_materials'))
            edited.append((component, original_mesh, original_overrides))
            replacement = meshes[target['row']['name']]
            if component.static_mesh != replacement:
                require(component.set_static_mesh(replacement), 'failed replacing solar mesh')
            component.set_editor_property('override_materials', [materials[role] for role in ROLES])
            after = actor_state(u, target['actor'], component)
            expected = dict(target['before'], mesh=mesh_path(target['row']),
                            materials=[material_path(r) for r in ROLES],
                            override_materials=[material_path(r) for r in ROLES])
            require(after == expected, 'assignment changed something beyond mesh/material references')
            report['changed_components'].append(dict(actor_guid=after['guid'], actor_name=after['name'],
                component_name=after['component_name'], before=target['before'], after=after,
                mesh_before=target['before']['mesh'], mesh_after=after['mesh'],
                override_materials_before=target['before']['override_materials'],
                override_materials_after=after['override_materials']))
        actors = u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors()
        current_guids = sorted(u.GuidLibrary.conv_guid_to_string(a.get_editor_property('actor_guid')) for a in actors)
        require(current_guids == report['actor_guids_before'], 'world Actor set changed during import')
    except Exception:
        for component, mesh, overrides in reversed(edited):
            component.set_static_mesh(mesh)
            component.set_editor_property('override_materials', overrides)
        raise
    report.update(success=True, actor_guids_after=current_guids,
                  new_packages_saved=[r['package'] for r in report['materials'] + report['meshes'] if not r['reused']],
                  reused_packages=[r['package'] for r in report['materials'] + report['meshes'] if r['reused']],
                  preserved_transform_and_guid_count=5)
    return report


def _base_color_node(u, material):
    """Find the exact native BaseColor VectorParameter owned by this material."""
    matches = []
    for node in u.ObjectIterator(u.MaterialExpressionVectorParameter):
        outer = node.get_outer()
        while outer is not None and outer != material:
            outer = outer.get_outer()
        if outer == material and str(node.get_editor_property('parameter_name')) == 'BaseColor':
            matches.append(node)
    require(len(matches) == 1, 'expected exactly one owned native BaseColor VectorParameter: ' + package(material))
    return matches[0]


def finish_palette(u):
    """Darken only three owned Cell materials; update five mesh source tags.

    All nine existing assets pass old-or-final provenance and native readback
    checks before mutation. Actor references/transforms and geometry are not
    changed. The map is never saved; an already finished call is a no-op.
    """
    manifest, targets, preflight_report = _preflight(u, allow_palette_transition=True)
    original = read(ROOT / SOURCE / 'manifest.json')['materials']
    map_file = ROOT / ('Content/' + MAP.removeprefix('/Game/') + '.umap')
    map_hash = sha(map_file)
    plans = []
    mesh_plans = []
    lib = u.EditorAssetLibrary
    for role in ROLES:
        before_spec, after_spec = original[role], manifest['materials'][role]
        material, before_digest = transition_asset(u, material_path(role), digest(before_spec), digest(after_spec), u.Material)
        node = _base_color_node(u, material)
        value = node.get_editor_property('default_value')
        observed = [float(value.r), float(value.g), float(value.b)]
        expected = before_spec if before_digest == digest(before_spec) else after_spec
        require(max(abs(a-b) for a, b in zip(observed, expected['base_color'])) < 1e-6,
                'native BaseColor differs from tagged palette: ' + role)
        plans.append(dict(role=role, material=material, node=node, before_digest=before_digest,
                          after_digest=digest(after_spec), before_color=observed, after_spec=after_spec))
    for row in manifest['meshes']:
        mesh, before_digest = transition_asset(u, mesh_path(row), mesh_digest(row, original),
                                               mesh_digest(row, manifest['materials']), u.StaticMesh)
        mesh_plans.append(dict(mesh=mesh, row=row, before_digest=before_digest,
                               after_digest=mesh_digest(row, manifest['materials']), before_audit=audit_mesh(u, mesh, row)))
    report = dict(success=False, map=MAP, map_saved=False, source=preflight_report['source'],
                  materials=[], meshes=[], new_assets_created=[], packages_saved=[])
    for plan in plans:
        changed = plan['before_digest'] != plan['after_digest']
        if changed:
            require(plan['role'] in ROLES[1:], 'frame material must not change')
            plan['node'].set_editor_property('default_value', u.LinearColor(*plan['after_spec']['base_color'], 1.))
            u.MaterialEditingLibrary.recompile_material(plan['material'])
            value = plan['node'].get_editor_property('default_value')
            require(max(abs(a-b) for a, b in zip([value.r, value.g, value.b], plan['after_spec']['base_color'])) < 1e-6,
                    'native BaseColor did not persist')
            material_audit(u, plan['material'], plan['after_spec'])
            mark_owned(u, plan['material'], plan['after_digest'])
            require(lib.save_loaded_asset(plan['material'], only_if_is_dirty=False), 'cannot save final palette material')
            report['packages_saved'].append(package(plan['material']))
        report['materials'].append(dict(role=plan['role'], changed=changed, before_base_color=plan['before_color'],
            after_base_color=plan['after_spec']['base_color'], before_source_digest=plan['before_digest'],
            after_source_digest=plan['after_digest'], **material_audit(u, plan['material'], plan['after_spec'])))
    for plan in mesh_plans:
        changed = plan['before_digest'] != plan['after_digest']
        if changed:
            mark_owned(u, plan['mesh'], plan['after_digest'])
            require(lib.save_loaded_asset(plan['mesh'], only_if_is_dirty=False), 'cannot save mesh palette source metadata')
            report['packages_saved'].append(package(plan['mesh']))
        after_audit = audit_mesh(u, plan['mesh'], plan['row'])
        require(after_audit == plan['before_audit'], 'palette metadata update changed mesh geometry/settings')
        report['meshes'].append(dict(metadata_changed=changed, before_source_digest=plan['before_digest'],
            after_source_digest=plan['after_digest'], geometry_unchanged=True, **after_audit))
    for target in targets:
        require(actor_state(u, target['actor'], target['component']) == target['before'],
                'palette finishing changed Actor/component state')
    final = preflight(u)
    require(final['actor_guids_before'] == preflight_report['actor_guids_before'], 'palette finishing changed Actor set')
    require(sha(map_file) == map_hash, 'palette finishing changed saved map bytes')
    report.update(success=True, map_unchanged=True, frame_unchanged=True, geometry_unchanged=True,
                  material_change_count=sum(p['changed'] for p in report['materials']),
                  actor_references_unchanged=True, final_preflight_success=final['success'])
    return report
