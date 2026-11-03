"""Independent saved-map audit and exactly eight UE screenshots.

Run only in a dedicated editor process, after the exterior import succeeds.
The script reloads the saved map, verifies the original interior snapshot,
audits manifests/materials/LODs and temporarily uses the existing review camera.
It NEVER saves the map or any asset. Pass -MPRReferenceCaptureQuit to exit.
"""
import hashlib
import gzip
import json
import math
from collections import defaultdict, deque
from itertools import product
from pathlib import Path
import sys
import time
import traceback
try:
    import unreal as u
except ModuleNotFoundError:
    u = None  # Pure-data matching tests run without loading Unreal.

ROOT = Path(u.Paths.convert_relative_path_to_full(u.Paths.project_dir())).resolve() if u else Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Tools/MPRWarehouse'))
from mpr_interior_preservation import MAP, NEW_OWNER, capture_editor_snapshot, assert_preserved
from mpr_scene_ownership import verify_owned_scene
from mpr_reference_catalog import load_catalog,material_name,DEST,TAG

OUT = ROOT / 'Saved/MPR/reference_v4'
SRC = ROOT / 'SourceAssets/MPR/reference_v4'
REPORT = OUT / 'validation.json'
A = L = E = SM = ML = USAGE = None

# Sub-centimetre tolerances accommodate serialized float precision without
# hiding wrong CAD/UE axes, tile offsets, rotations or model scaling.
POSITION_TOLERANCE_CM = .5
ROTATION_TOLERANCE_DEG = .05
SCALE_TOLERANCE = .0001


def _initialize_editor():
    global A, L, E, SM, ML, USAGE
    if u is None:
        raise RuntimeError('UE editor required; use --self-test for pure matching tests')
    OUT.mkdir(parents=True, exist_ok=True)
    A = u.get_editor_subsystem(u.EditorActorSubsystem)
    L = u.get_editor_subsystem(u.LevelEditorSubsystem)
    E = u.get_editor_subsystem(u.UnrealEditorSubsystem)
    SM = u.get_editor_subsystem(u.StaticMeshEditorSubsystem)
    ML = u.MaterialEditingLibrary
    USAGE = u.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES


def source_world_transform(row):
    """Catalog CAD metres/+Y to UE world centimetres/-Y, matching the importer."""
    x, y, z = row['position_m']
    half_yaw = math.radians(-float(row.get('rotation_deg', 0))) / 2
    return dict(translation_cm=[100*x, -100*y, 100*z],
                rotation_xyzw=[0., 0., math.sin(half_yaw), math.cos(half_yaw)],
                scale=list(row.get('scale', [1., 1., 1.])))


def _finite_transform(row):
    result = {}
    for key, length in [('translation_cm', 3), ('rotation_xyzw', 4), ('scale', 3)]:
        values = list(row[key])
        assert len(values) == length and all(math.isfinite(v) for v in values), ('Invalid transform', key, values)
        result[key] = values
    q = result['rotation_xyzw']
    norm = math.sqrt(sum(v*v for v in q))
    assert norm > 1e-12, 'Invalid zero quaternion'
    result['rotation_xyzw'] = [v/norm for v in q]
    return result


def transform_error(expected, actual):
    """Quaternion sign and Euler wrapping do not change the represented pose."""
    a, b = _finite_transform(expected), _finite_transform(actual)
    dot = min(1., abs(sum(x*y for x, y in zip(a['rotation_xyzw'], b['rotation_xyzw']))))
    return dict(position_cm=math.dist(a['translation_cm'], b['translation_cm']),
                rotation_deg=math.degrees(2*math.acos(dot)),
                scale=max(abs(x-y) for x, y in zip(a['scale'], b['scale'])))


def assert_transform_matches(expected, actual, *, label,
                             position_cm=POSITION_TOLERANCE_CM,
                             rotation_deg=ROTATION_TOLERANCE_DEG,
                             scale=SCALE_TOLERANCE):
    errors = transform_error(expected, actual)
    assert errors['position_cm'] <= position_cm and errors['rotation_deg'] <= rotation_deg and errors['scale'] <= scale, (
        'World transform mismatch', label, errors, actual)
    return errors


def assert_instance_world_transforms(source_rows, actual_rows, *, label,
                                    position_cm=POSITION_TOLERANCE_CM,
                                    rotation_deg=ROTATION_TOLERANCE_DEG,
                                    scale=SCALE_TOLERANCE):
    """One-to-one pose matching, independent of HISM actor/tile/instance order.

    Spatial buckets keep normal scenes linear. Augmenting paths handle nearby
    or duplicate placements without the false failures of greedy matching.
    """
    assert position_cm > 0 and rotation_deg >= 0 and scale >= 0, 'Invalid tolerances'
    expected = [_finite_transform(source_world_transform(r)) for r in source_rows]
    actual = [_finite_transform(r) for r in actual_rows]
    assert len(expected) == len(actual), ('Instance count mismatch', label, len(expected), len(actual))
    bucket = lambda p: tuple(math.floor(v/position_cm) for v in p)
    spatial = defaultdict(list)
    for i, row in enumerate(actual):
        spatial[bucket(row['translation_cm'])].append(i)
    candidates = []
    for ei, row in enumerate(expected):
        origin = bucket(row['translation_cm']);matches = []
        for offset in product((-1, 0, 1), repeat=3):
            for ai in spatial.get(tuple(a+b for a, b in zip(origin, offset)), ()):
                errors = transform_error(row, actual[ai])
                if errors['position_cm'] <= position_cm and errors['rotation_deg'] <= rotation_deg and errors['scale'] <= scale:
                    matches.append((errors['position_cm'], ai))
        assert matches, ('No matching world transform', label, 'catalog_index', ei, row)
        candidates.append([ai for _, ai in sorted(matches)])
    owned_actual, owned_expected = {}, {}
    for root in range(len(expected)):
        queue = deque([root]);seen = {root};parent = {};free = None
        while queue and free is None:
            ei = queue.popleft()
            for ai in candidates[ei]:
                if ai in parent:
                    continue
                parent[ai] = ei
                if ai not in owned_actual:
                    free = ai
                    break
                previous = owned_actual[ai]
                if previous not in seen:
                    seen.add(previous);queue.append(previous)
        assert free is not None, ('Duplicate/missing world placement', label, 'catalog_index', root)
        while free is not None:
            ei = parent[free];previous = owned_expected.get(ei)
            owned_expected[ei] = free;owned_actual[free] = ei;free = previous
    maxima = dict(position_cm=0., rotation_deg=0., scale=0.)
    for ei, ai in owned_expected.items():
        for key, value in transform_error(expected[ei], actual[ai]).items():
            maxima[key] = max(maxima[key], value)
    return dict(count=len(expected),maximum_error=maxima)


def unreal_transform_data(value):
    q, t, s = value.rotation, value.translation, value.scale3d
    return dict(translation_cm=[float(t.x), float(t.y), float(t.z)],
                rotation_xyzw=[float(q.x), float(q.y), float(q.z), float(q.w)],
                scale=[float(s.x), float(s.y), float(s.z)])

# Targets are source CAD-local metres; camera yaw is UE space, negative CAD Y.
VIEWS = [
    ('01-overall', [0, 0, 8], 75000, -52, -90, False),
    ('02-yard-corner', [-125, -90, 5], 28000, -26, -55, False),
    ('03-roof', [65, 0, 14], 32000, -66, -90, False),
    ('04-docks', [-130, -82, 3.5], 4500, -15, -90, False),
    ('05-yard', [-60, -120, 0], 22000, -50, -90, False),
    ('06-pond', [-217, -184, -1.2], 10500, -45, -60, False),
    ('07-railway', [210, -125, 0], 24000, -48, -65, False),
    ('08-interior-preserved', [0, 0, 4], 49000, -60, -90, True),
]


def read(path):
    if path.suffix == '.gz':
        return json.loads(gzip.decompress(path.read_bytes()).decode('utf-8-sig'))
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def material_path(role):
    return DEST + '/Materials/' + material_name(role)


def audit_scene():
    _initialize_editor()
    assert not L.is_in_play_in_editor(), 'Dedicated editor world required'
    dirty = u.EditorLoadingAndSavingUtils.get_dirty_map_packages() + u.EditorLoadingAndSavingUtils.get_dirty_content_packages()
    assert not dirty, ('Do not discard unsaved work', [p.get_path_name() for p in dirty])
    verify_owned_scene(ROOT)
    build_path = ROOT / 'Saved/MPR/reference_v4_build.json'
    if not build_path.is_file():
        build_path = SRC / 'validation/import_report.json'
    build = read(build_path)
    assert build.get('success') and build.get('map') == MAP, 'Successful import report required'
    baseline_path = Path(build.get('before_snapshot', ROOT / 'Saved/MPR/reference_v3_interior_before.json'))
    if not baseline_path.is_file():
        baseline_path = ROOT / 'SourceAssets/MPR/reference_v3/validation/interior_before.json.gz'
    baseline = read(baseline_path)
    # Force deserialization from disk in this separate process; no caller's
    # in-memory scene or transient instances are accepted as saved-map proof.
    assert L.load_level('/Engine/Maps/Entry')
    assert L.load_level(MAP)
    snapshot = capture_editor_snapshot(u, project_root=ROOT)
    preserved = assert_preserved(baseline, snapshot, require_old_exterior_removed=True)
    (OUT / 'interior_after_reload.json').write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding='utf-8')
    catalog=load_catalog(ROOT)
    manifests=catalog['manifests']
    expected_counts={name:len(rows) for name,rows in catalog['instances'].items()}
    meshes, specs, mesh_paths, static_expected = {}, {}, {}, set()
    pv_material_audit,pv_texture_audit,terminal_material_audit={},{},{}
    for category, data in manifests:
        specs.update(data['materials'])
        for row in data['meshes']:
            if row.get('lod', 0):
                continue
            mesh = u.EditorAssetLibrary.load_asset(DEST + '/' + category + '/Meshes/' + row['name'])
            assert isinstance(mesh, u.StaticMesh), ('Missing imported mesh', row['name'])
            mesh_paths[row['name']] = mesh.get_path_name()
            if not row.get('instance_only'):
                static_expected.add(row['name'])
            if category=='Props' and 'Tree' in row['name']:
                nanite=SM.get_nanite_settings(mesh)
                assert nanite.enabled and nanite.shape_preservation==u.NaniteShapePreservation.PRESERVE_AREA, ('Foliage detail preservation',row['name'])
                assert abs(nanite.max_edge_length_factor)<1e-6,('Foliage area preservation without edge constraint',row['name'])
            if 'SolarBank' in row['name']:
                assert not SM.get_nanite_settings(mesh).enabled,('Solar topology preservation',row['name'])
            slots = mesh.static_materials
            if row.get('vertex_color_fade'):
                assert mesh.get_editor_property('asset_import_data').get_editor_property('vertex_color_import_option')==u.VertexColorImportOption.REPLACE, (row['name'],'Road terminal vertex colors')
            explicit_lods=bool(row.get('lod_material_roles'))
            roles=row['all_lod_material_roles'] if explicit_lods else row['material_roles']
            assert len(slots) == len(roles), ('Material slot count', row['name'],len(slots),roles)
            expected_mats = {material_path(role) for role in roles}
            for slot in slots:
                assert slot.material_interface
                assert slot.material_interface.get_path_name().split('.')[0] in expected_mats, ('Unexpected slot material', row['name'])
            lod_count = SM.get_lod_count(mesh)
            expected_lods = 1 + len(row.get('lod_files', []))
            if 'Tree' not in row['name'] and not row.get('lod_files') and row.get('instance_only') and row.get('triangles', 0) > 1000:
                expected_lods = max(expected_lods, 3)
            assert lod_count >= expected_lods, ('Missing LODs', row['name'], lod_count, expected_lods)
            explicit_audit=None
            if explicit_lods:
                assert lod_count==len(row['lod_material_roles'])==3,('Exact PV LOD count',row['name'],lod_count)
                actual_names=[str(s.get_editor_property('imported_material_slot_name'))for s in slots]
                assert actual_names==roles,('PV slot union mismatch',row['name'],actual_names,roles)
                screen=list(SM.get_lod_screen_sizes(mesh));wanted_screen=row['lod_screen_sizes']
                assert len(screen)==3 and max(abs(a-b)for a,b in zip(screen,wanted_screen))<1e-5
                levels=[]
                for lod,wanted in enumerate(row['lod_material_roles']):
                    sections=[];used=[]
                    for section in range(mesh.get_num_sections(lod)):
                        slot_index=SM.get_lod_material_slot(mesh,lod,section)
                        assert 0<=slot_index<len(slots)
                        role=actual_names[slot_index];used.append(role)
                        assert role in wanted,('PV wrong LOD section',row['name'],lod,section,role,wanted)
                        assert slots[slot_index].material_interface.get_path_name().split('.')[0]==material_path(role)
                        sections.append(dict(section=section,slot_index=slot_index,role=role,material=material_path(role)))
                    assert set(used)==set(wanted),('PV missing LOD role',row['name'],lod,used,wanted)
                    settings=SM.get_lod_build_settings(mesh,lod)
                    assert settings.get_editor_property('use_full_precision_u_vs')
                    levels.append(dict(lod=lod,screen_size=screen[lod],full_precision_uvs=True,sections=sections))
                explicit_audit=dict(slot_roles=actual_names,lods=levels)
            bounds = mesh.get_bounds()
            actual = [[bounds.origin.x - bounds.box_extent.x, bounds.origin.x + bounds.box_extent.x],
                      [bounds.origin.y - bounds.box_extent.y, bounds.origin.y + bounds.box_extent.y],
                      [bounds.origin.z - bounds.box_extent.z, bounds.origin.z + bounds.box_extent.z]]
            b = row['bounds_m']
            expected = [[v * 100 for v in b[0]], [-b[1][1] * 100, -b[1][0] * 100], [v * 100 for v in b[2]]]
            assert max(abs(x - y) for aa, bb in zip(actual, expected) for x, y in zip(aa, bb)) < (20 if explicit_lods else 2), ('Axis/scale mismatch', row['name'])
            nanite = SM.get_nanite_settings(mesh)
            meshes[row['name']] = {'lods': lod_count, 'slots': len(slots), 'source_triangles': row.get('triangles'),
                                  'category': category, 'nanite_enabled': bool(nanite.enabled),
                                  'nanite_max_edge_length_factor': float(nanite.max_edge_length_factor)}
            if explicit_audit is not None:meshes[row['name']]['explicit_lod_audit']=explicit_audit
    for role, spec in specs.items():
        mi = u.EditorAssetLibrary.load_asset(material_path(role))
        assert isinstance(mi, u.MaterialInstanceConstant), ('Missing material instance', role)
        overrides=mi.get_editor_property('base_property_overrides')
        assert bool(overrides.get_editor_property('override_two_sided'))
        assert bool(overrides.get_editor_property('two_sided'))==bool(spec.get('two_sided',False)), (role,'Two-sided leaves')
        if role.startswith('MPR4_Solar'):
            assert overrides.get_editor_property('override_dithered_lod_transition') and overrides.get_editor_property('dithered_lod_transition'),(role,'PV dithered LOD transition')
            pv_material_audit[role]=dict(override_dithered_lod_transition=True,dithered_lod_transition=True)
        for param, expected in [('Roughness', spec.get('roughness', .8)), ('Metallic', spec.get('metallic', 0))]:
            assert abs(ML.get_material_instance_scalar_parameter_value(mi, param) - expected) < 1e-5, (role, param)
        color = list(spec.get('color', spec.get('base_color')))[:3]
        actual = ML.get_material_instance_vector_parameter_value(mi, 'Tint')
        assert max(abs(x - y) for x, y in zip(color, [actual.r, actual.g, actual.b])) < 1e-5, (role, 'Tint')
        if spec.get('vertex_color_fade'):
            fade=spec['vertex_color_fade'];ground=specs[fade['ground_role']]
            parent=mi.get_editor_property('parent')
            expected_parent='M_MPR4_PBRTexturedTerminal' if spec.get('textures') else 'M_MPR4_PBRSolidTerminal'
            assert parent.get_name()==expected_parent and parent.get_editor_property('blend_mode')==u.BlendMode.BLEND_OPAQUE,(role,'Opaque terminal parent')
            ground_color=list(ground.get('color',ground.get('base_color')))[:3]
            actual_ground=ML.get_material_instance_vector_parameter_value(mi,'GroundTint')
            assert max(abs(a-b) for a,b in zip(ground_color,[actual_ground.r,actual_ground.g,actual_ground.b]))<1e-5
            actual_uv=ML.get_material_instance_vector_parameter_value(mi,'GroundUVScale')
            assert max(abs(a-b) for a,b in zip([1/600,-1/600,0],[actual_uv.r,actual_uv.g,actual_uv.b]))<1e-7
            for key,expected in [('GroundRoughness',ground.get('roughness',.98)),('GroundMetallic',ground.get('metallic',0)),('GroundNormalStrength',ground.get('normal_strength',.06))]:
                assert abs(ML.get_material_instance_scalar_parameter_value(mi,key)-expected)<1e-5,(role,key)
            for channel,filename in ground['textures'].items():
                tex=ML.get_material_instance_texture_parameter_value(mi,'GroundNormal' if channel=='normal' else 'GroundAlbedo')
                assert tex and tex.get_path_name().split('.')[0]==DEST+'/Textures/'+Path(filename).stem,(role,'ground texture',channel)
            terminal_material_audit[role]=dict(parent=parent.get_path_name(),ground_role=fade['ground_role'],opaque=True,ground_tint=ground_color,ground_uv_scale_cm=[actual_uv.r,actual_uv.g,actual_uv.b])
        for channel, filename in spec.get('textures', {}).items():
            tex = ML.get_material_instance_texture_parameter_value(mi, 'Normal' if channel == 'normal' else 'Albedo')
            assert tex and tex.get_path_name().split('.')[0] == DEST + '/Textures/' + Path(filename).stem, (role, channel)
            assert bool(tex.get_editor_property('srgb')) == (channel != 'normal'), (role, 'sRGB')
            if channel == 'normal':
                assert tex.get_editor_property('compression_settings') == u.TextureCompressionSettings.TC_NORMALMAP, role
            if role.startswith('MPR4_Solar'):
                assert tex.get_editor_property('mip_gen_settings')==u.TextureMipGenSettings.TMGS_SIMPLE_AVERAGE,(role,'PV mip policy')
                assert tex.get_editor_property('filter')==u.TextureFilter.TF_DEFAULT,(role,'PV filter policy')
                assert tex.get_editor_property('lod_bias')==0,(role,'PV mip bias')
                assert not tex.get_editor_property('never_stream') and not tex.get_editor_property('virtual_texture_streaming'),(role,'PV streaming policy')
                pv_texture_audit[tex.get_path_name()]=dict(mip_gen_settings=str(tex.get_editor_property('mip_gen_settings')),
                    filter=str(tex.get_editor_property('filter')),lod_bias=int(tex.get_editor_property('lod_bias')),
                    never_stream=False,virtual_texture_streaming=False,max_texture_size=int(tex.get_editor_property('max_texture_size')),
                    note='Saved configuration readback; resident mip count and temporal behavior require runtime validation.')
    actors = list(A.get_all_level_actors())
    counts, static_counts = {}, defaultdict(int)
    world_instances = defaultdict(list)
    identity = source_world_transform(dict(position_m=[0, 0, 0]))
    for actor in actors:
        if not actor.actor_has_tag(TAG):
            continue
        assert not actor.is_actor_tick_enabled() and not actor.get_actor_enable_collision(), actor.get_actor_label()
        for component in actor.get_components_by_class(u.StaticMeshComponent):
            assert component.static_mesh and str(component.get_collision_profile_name()) == 'NoCollision', actor.get_actor_label()
            name = component.static_mesh.get_name()
            if name in mesh_paths:
                assert component.static_mesh.get_path_name() == mesh_paths[name], ('Wrong mesh package', actor.get_actor_label(), name)
            if isinstance(component, u.InstancedStaticMeshComponent):
                assert name in expected_counts, ('Unexpected instanced mesh', name)
                counts[name] = counts.get(name, 0) + component.get_instance_count()
                world_instances[name].extend(unreal_transform_data(component.get_instance_transform(i, world_space=True))
                                             for i in range(component.get_instance_count()))
                for index in range(component.get_num_materials()):
                    assert ML.has_material_usage(component.get_material(index), USAGE), (name, 'Missing HISM shader usage')
            elif name in mesh_paths:
                assert name in static_expected, ('Instance-only mesh also spawned as static actor', name)
                assert actor.get_attach_parent_actor() is None, ('World mesh unexpectedly attached', actor.get_actor_label())
                assert_transform_matches(identity, unreal_transform_data(actor.get_actor_transform()), label=actor.get_actor_label())
                assert_transform_matches(identity, unreal_transform_data(component.get_relative_transform()), label=component.get_path_name())
                static_counts[name] += 1
    assert counts == expected_counts, ('Instance coverage mismatch', counts, expected_counts)
    assert dict(static_counts) == {name:1 for name in static_expected}, ('Static world-mesh coverage mismatch', dict(static_counts), sorted(static_expected))
    transform_audit = {name:assert_instance_world_transforms(rows, world_instances[name], label=name)
                       for name, rows in catalog['instances'].items()}
    registry=u.AssetRegistryHelpers.get_asset_registry()
    registry.search_all_assets(synchronous_search=True)
    options=u.AssetRegistryDependencyOptions(include_soft_package_references=True,
        include_hard_package_references=True,include_searchable_names=False,
        include_soft_management_references=True,include_hard_management_references=True)
    dependencies=set();pending_packages=[MAP]
    while pending_packages:
        name=pending_packages.pop()
        if name in dependencies:continue
        dependencies.add(name)
        pending_packages.extend(str(p) for p in registry.get_dependencies(name,options)
                                if str(p).startswith('/Game/') and str(p) not in dependencies)
    assert not any(p.startswith('/Game/MPRWarehouse/ReferenceV3/') for p in dependencies)
    dependency_report=dict(success=True,map_sha256=sha(ROOT/'Content/Maps/MPR_CAD_Warehouse.umap'),
        recursive_map_dependencies=sorted(dependencies),v3_dependencies=0,assets_modified=False)
    (SRC/'validation/package_dependencies.json').write_text(json.dumps(dependency_report,indent=2),encoding='utf8')
    by_label = {a.get_actor_label(): a for a in actors}
    return dict(success=False, map=MAP, reload_verified=True, preservation=preserved,
                map_sha256=dependency_report['map_sha256'],
                source_manifest_hashes={category:sha(path) for category,path in catalog['paths']},
                mesh_count=len(meshes), mesh_audit=meshes, exterior_instances=sum(counts.values()),
                pv_material_audit=pv_material_audit,pv_texture_audit=pv_texture_audit,terminal_material_audit=terminal_material_audit,
                instance_world_transform_audit=transform_audit, static_identity_actors=sum(static_counts.values()),
                transform_tolerances=dict(position_cm=POSITION_TOLERANCE_CM,rotation_deg=ROTATION_TOLERANCE_DEG,scale=SCALE_TOLERANCE),
                captures=[]), baseline, by_label['MPR_ReviewCamera'], [a for a in actors if a.actor_has_tag('MPR_Roof')]


def run():
    global report, baseline, camera, roofs, camera_transform, old_view, old_hidden
    global map_sha, map_file, start, index, pending, task, done, busy, handle, old_delay
    report, baseline, camera, roofs = audit_scene()
    assert len(VIEWS) == 8 and roofs
    map_file = ROOT / 'Content/Maps/MPR_CAD_Warehouse.umap'
    map_sha = sha(map_file)
    camera_transform = camera.get_actor_transform()
    old_view = E.get_level_viewport_camera_info()
    old_hidden = [(a, bool(a.get_editor_property('hidden')), a.is_temporarily_hidden_in_editor()) for a in roofs]
    old_delay = u.SystemLibrary.get_console_variable_int_value('r.HighResScreenshotDelay')
    u.SystemLibrary.execute_console_command(E.get_editor_world(), 'r.HighResScreenshotDelay 16')
    A.set_selected_level_actors([])
    L.editor_set_game_view(True)
    start, index, pending, task, done, busy, handle = time.monotonic(), 0, None, None, False, False, None
    write()
    handle = u.register_slate_post_tick_callback(tick)
    print('MPR_REFERENCE_VALIDATION_CAPTURE_STARTED', len(VIEWS))


def write():
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


def finish(error=None):
    global done
    if done:
        return
    done = True
    if handle:
        u.unregister_slate_post_tick_callback(handle)
    try:
        for actor, hidden, editor_hidden in old_hidden:
            actor.set_actor_hidden_in_game(hidden)
            actor.set_is_temporarily_hidden_in_editor(editor_hidden)
        camera.set_actor_transform(camera_transform, False, True)
        E.set_level_viewport_camera_info(*old_view)
        u.SystemLibrary.execute_console_command(E.get_editor_world(), 'r.HighResScreenshotDelay ' + str(old_delay))
        report['preservation_after_capture'] = assert_preserved(baseline, capture_editor_snapshot(u, project_root=ROOT), require_old_exterior_removed=True)
        assert sha(map_file) == map_sha, 'Capture unexpectedly changed the saved map'
        assert len(report['captures']) == 8 or error, 'Incomplete eight-view evidence'
    except Exception:
        error = (error or '') + '\nRESTORE/VERIFY: ' + traceback.format_exc()
    report.update(success=error is None, error=error, elapsed_seconds=time.monotonic() - start,
                  map_saved_by_validator=False)
    write()
    if '-MPRReferenceCaptureQuit' in u.SystemLibrary.get_command_line():
        # No map/content save is requested by this tool or on this exit path.
        u.SystemLibrary.quit_editor()


def tick(dt):
    global busy, index, task, pending
    if busy or done:
        return
    busy = True
    try:
        assert time.monotonic() - start < 300, 'Screenshot deadline'
        if time.monotonic() - start < 15:
            return
        if task:
            if not task.is_task_done() or not pending['path'].is_file() or pending['path'].stat().st_mtime_ns == pending['old']:
                return
            path = pending['path']
            assert path.read_bytes()[:8] == b'\x89PNG\r\n\x1a\n' and path.stat().st_size > 10000, 'Invalid screenshot'
            report['captures'].append({'name': pending['name'], 'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)})
            task, pending = None, None
            write()
        if index == len(VIEWS):
            finish()
            return
        name, xyz, distance, pitch, yaw, hide_roof = VIEWS[index]
        index += 1
        for actor in roofs:
            actor.set_actor_hidden_in_game(hide_roof)
            actor.set_is_temporarily_hidden_in_editor(hide_roof)
        target = u.Vector(xyz[0] * 100, -xyz[1] * 100, xyz[2] * 100)
        rotation = u.Rotator(pitch=pitch, yaw=yaw)
        eye = target - u.MathLibrary.get_forward_vector(rotation) * distance
        camera.set_actor_location_and_rotation(eye, rotation, False, True)
        E.set_level_viewport_camera_info(eye, rotation)
        path = OUT / (name + '.png')
        pending = {'name': name, 'path': path, 'old': path.stat().st_mtime_ns if path.exists() else 0}
        task = u.AutomationLibrary.take_high_res_screenshot(1920, 1080, str(path), camera=camera, delay=2.)
        assert task, 'Screenshot task was not created'
    except Exception:
        finish(traceback.format_exc())
    finally:
        busy = False


def _run_self_tests():
    """Meaningful fault-injection checks; no UE import or filesystem writes."""
    import copy
    import unittest

    class TransformReadbackTests(unittest.TestCase):
        def setUp(self):
            self.source = [dict(position_m=[12., -3., 1.4], rotation_deg=90., scale=[1.5, 2., .8]),
                           dict(position_m=[-8., 6., 0.], rotation_deg=-45.)]
            self.actual = [source_world_transform(r) for r in self.source]

        def test_cad_to_ue_axes_units_and_yaw(self):
            expected = dict(translation_cm=[1200., 300., 140.],
                            rotation_xyzw=[0., 0., -math.sqrt(.5), math.sqrt(.5)],scale=[1.5, 2., .8])
            assert_transform_matches(expected, self.actual[0], label='axis contract')

        def test_reordered_instances_and_quaternion_sign(self):
            self.actual.reverse()
            self.actual[0]['rotation_xyzw'] = [-v for v in self.actual[0]['rotation_xyzw']]
            self.assertEqual(assert_instance_world_transforms(self.source, self.actual, label='unordered')['count'], 2)

        def test_small_serialization_error_is_allowed(self):
            self.actual[0]['translation_cm'][0] += .2
            self.actual[0]['scale'][1] += .00005
            errors = assert_instance_world_transforms(self.source, self.actual, label='float roundtrip')
            self.assertAlmostEqual(errors['maximum_error']['position_cm'], .2)

        def test_wrong_translation_rotation_or_scale_fails(self):
            for mutation in ('position', 'rotation', 'scale'):
                with self.subTest(mutation=mutation):
                    actual = copy.deepcopy(self.actual)
                    if mutation == 'position':actual[0]['translation_cm'][1] += 5.
                    elif mutation == 'rotation':actual[0]['rotation_xyzw'] = source_world_transform(dict(position_m=[0,0,0],rotation_deg=91.))['rotation_xyzw']
                    else:actual[0]['scale'][2] += .01
                    with self.assertRaises(AssertionError):
                        assert_instance_world_transforms(self.source, actual, label=mutation)

        def test_duplicate_cannot_hide_missing_instance_with_same_count(self):
            with self.assertRaises(AssertionError):
                assert_instance_world_transforms(self.source, [self.actual[0], self.actual[0]], label='duplicate')

        def test_one_to_one_augmenting_match_handles_nearby_instances(self):
            source = [dict(position_m=[0.,0.,0.]), dict(position_m=[.004,0.,0.])]
            actual = [source_world_transform(dict(position_m=[.002,0.,0.])),
                      source_world_transform(dict(position_m=[-.004,0.,0.]))]
            self.assertEqual(assert_instance_world_transforms(source, actual, label='ambiguous')['count'], 2)
            with self.assertRaises(AssertionError):
                assert_instance_world_transforms(source, [actual[1], actual[1]], label='no bijection')

        def test_identity_mesh_rejects_actor_and_component_offset(self):
            identity = source_world_transform(dict(position_m=[0.,0.,0.]))
            for field, index in [('translation_cm', 0), ('scale', 2)]:
                bad = copy.deepcopy(identity);bad[field][index] += 1.
                with self.assertRaises(AssertionError):
                    assert_transform_matches(identity, bad, label='static mesh')

        def test_invalid_numeric_values_fail(self):
            for value in (float('nan'), float('inf')):
                bad = copy.deepcopy(self.actual);bad[0]['translation_cm'][0] = value
                with self.assertRaises(AssertionError):
                    assert_instance_world_transforms(self.source, bad, label='nonfinite')
            bad = copy.deepcopy(self.actual);bad[0]['rotation_xyzw'] = [0.,0.,0.,0.]
            with self.assertRaises(AssertionError):
                assert_instance_world_transforms(self.source, bad, label='zero quaternion')

    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TransformReadbackTests))
    if not result.wasSuccessful():
        raise SystemExit(1)


if __name__ == '__main__' and '--self-test' in sys.argv:
    _run_self_tests()
elif __name__ == '__main__':
    if u is None:
        raise RuntimeError('UE editor required; use --self-test for pure matching tests')
    try:
        run()
    except Exception:
        REPORT.write_text(json.dumps({'success': False, 'stage': 'reload_and_audit', 'error': traceback.format_exc()}, indent=2), encoding='utf-8')
        if '-MPRReferenceCaptureQuit' in u.SystemLibrary.get_command_line():
            u.SystemLibrary.quit_editor()
        raise
