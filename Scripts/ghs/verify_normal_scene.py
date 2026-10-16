"""Verify the saved normal warehouse in a fresh UE process without saving assets.

Only Saved/GHS_NormalVerification.json is written. Original mesh/material
assets are immutable. An explicit wall-height-sync report can authorize the
two saved maps and three registries, with before/after and backup SHA checks.
"""
import hashlib
import json
import math
import sys
import traceback
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import unreal

ROOT = Path(r'D:\UEPro\Test')
SOURCE = ROOT / 'SourceAssets/GHS_Normal'
ORIGINAL = ROOT / 'SourceAssets/GHS'
MAP = '/Game/Maps/GHS_CAD_NormalWarehouse'
OLD_MAP = '/Game/Maps/GHS_CAD_DigitalTwin'
MATERIAL_ROOT = '/Game/GHSNormalWarehouse/Materials/'
FX_ROOT = '/Game/GHSNormalWarehouse/FX/'
REPORT = ROOT / 'Saved/GHS_NormalVerification.json'
WALL_SYNC_REPORT = ROOT / 'Saved/GHS_WallHeightSync.json'
WALL_HEIGHT_PROFILE = ORIGINAL / 'wall_height_profile.json'
WALL_SYNC_FILES = {
    'Content/Maps/GHS_CAD_DigitalTwin.umap',
    'Content/Maps/GHS_CAD_NormalWarehouse.umap',
    'SourceAssets/GHS/ue_scene_registry.json',
    'SourceAssets/GHS_Normal/ue_scene_registry.json',
    'SourceAssets/GHS/Presentation/visual_layout.json',
}
sys.path.insert(0, str(ROOT / 'Scripts/ghs'))
import verify_ue_scene as common
import verify_clearance_scene as clearance
import verify_column_outlines as column

HIDDEN_ALLOWED = {'GHS_ContextGrid', 'GHS_ColumnOccupiedStorageOutlines'}
CARGO = {'GHS_CAD_PalletCargo', 'GHS_CAD_PalletCargoLow', 'GHS_CAD_PalletCargoHigh'}
KINDS = {label: 'cargo' for label in CARGO}
KINDS.update({'GHS_CAD_Racks': 'rack', 'GHS_CAD_DockRacks': 'dock_rack',
              'GHS_CAD_Columns': 'column', 'GHS_ColumnBases': 'column_base'})


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def prop(obj, name):
    return obj.get_editor_property(name)


def content_path(relative):
    value = str(relative).replace('\\', '/')
    path = ROOT / value if value.lower().startswith('content/') else ROOT / 'Content' / value
    path = path.resolve()
    assert path.is_relative_to((ROOT / 'Content').resolve()), 'Baseline path escapes Content: ' + value
    return path


def verify_authorized_wall_sync(baseline):
    """Accept only the exact authorized five-file change, backed by old bytes."""
    if not WALL_SYNC_REPORT.is_file():
        return None
    sync = read(WALL_SYNC_REPORT)
    assert sync.get('success') is True, 'Wall height synchronization is not complete'
    assert len(sync['maps']) == 2 and all(isinstance(row, dict) for row in sync['maps']), 'Invalid wall-sync map records'
    assert {row.get('map') for row in sync['maps']} == {OLD_MAP, MAP}, 'Unexpected wall-sync map set'
    assert all(isinstance(row.get('heights'), dict) and row['heights'] for row in sync['maps']), 'Wall-sync measurements missing'
    changes = sync['file_changes']
    assert isinstance(changes, dict) and len(changes) == len(WALL_SYNC_FILES)
    normalized = {str(key).replace('\\', '/'): value for key, value in changes.items()}
    assert set(normalized) == WALL_SYNC_FILES, 'Wall-sync file whitelist differs'
    backup_root = Path(sync['backup_root'])
    assert backup_root.is_absolute(), 'Wall-sync backup_root must be absolute'
    backup_root = backup_root.resolve()
    assert backup_root.is_dir(), 'Wall-sync backup root missing'
    checked = {}
    for relative, change in normalized.items():
        current = ROOT / relative
        backup = Path(change['backup_path'])
        assert backup.is_absolute(), relative + ' backup_path must be absolute'
        backup = backup.resolve()
        assert backup.is_relative_to(backup_root) and backup != current.resolve(), relative + ' invalid backup path'
        for key in ['before_sha256', 'after_sha256']:
            value = change[key]
            assert isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value), relative + ' invalid ' + key
        assert backup.is_file() and sha(backup) == change['before_sha256'], relative + ' backup does not prove before SHA'
        assert current.is_file() and sha(current) == change['after_sha256'], relative + ' current file differs from authorized after SHA'
        checked[relative] = dict(before_sha256=change['before_sha256'], after_sha256=change['after_sha256'], backup_path=str(backup))
    assert checked['Content/Maps/GHS_CAD_DigitalTwin.umap']['before_sha256'] == baseline['old_map_sha256'], 'Wall-sync old map before SHA differs from historical baseline'
    assert checked['SourceAssets/GHS/ue_scene_registry.json']['before_sha256'] == baseline['source_registry_sha256'], 'Wall-sync source registry before SHA differs from historical baseline'
    assert WALL_HEIGHT_PROFILE.is_file(), 'Wall height profile missing'
    profile = read(WALL_HEIGHT_PROFILE)
    assert isinstance(profile, dict) and profile, 'Empty wall height profile'
    assert sync.get('profile') == profile, 'Wall-sync report profile differs from shared profile'
    assert profile['source_wall_height_m'] == 2.8 and profile['wall_height_m'] == profile['column_height_m'] == 5.6
    assert profile['edge_offset_m'] == .0005 and set(profile['maps']) == {OLD_MAP, MAP}
    assert set(profile['wall_groups']) == {'GHS_CAD_WallFaces', 'GHS_CAD_WallSections', 'GHS_CAD_WallEdges'}
    for relative in sorted(WALL_SYNC_FILES):
        if relative.endswith('.json'):
            assert read(ROOT / relative).get('wall_height_profile') == profile, relative + ' wall height metadata differs from profile'
    return dict(report_path=str(WALL_SYNC_REPORT), backup_root=str(backup_root),
                file_changes=checked, wall_height_profile=profile, maps=sync['maps'],
                all_before_backup_and_current_after_hashes_verified=True)


def verify_baseline(baseline):
    content = baseline['content']
    assert content, 'Empty original Content hash manifest'
    sync = verify_authorized_wall_sync(baseline)
    changes = sync['file_changes'] if sync else {}
    changed_content = []
    for relative, expected in content.items():
        path = content_path(relative)
        normalized = path.relative_to(ROOT).as_posix()
        if normalized in changes:
            assert normalized == 'Content/Maps/GHS_CAD_DigitalTwin.umap', 'Unexpected baseline Content exception'
            assert changes[normalized]['before_sha256'] == expected, 'Wall-sync before SHA differs from Content baseline'
            expected = changes[normalized]['after_sha256']
            if changes[normalized]['before_sha256'] != expected:
                changed_content.append(normalized)
        assert path.is_file() and sha(path) == expected, 'Original Content changed without authorization: ' + str(relative)
    registry_path = ORIGINAL / 'ue_scene_registry.json'
    registry_expected = changes.get('SourceAssets/GHS/ue_scene_registry.json', {}).get('after_sha256', baseline['source_registry_sha256'])
    map_expected = changes.get('Content/Maps/GHS_CAD_DigitalTwin.umap', {}).get('after_sha256', baseline['old_map_sha256'])
    assert sha(registry_path) == registry_expected, 'Original CAD registry changed without authorization'
    assert sha(ROOT / 'Content/Maps/GHS_CAD_DigitalTwin.umap') == map_expected, 'Original GHS map changed without authorization'
    return dict(original_content_files_checked=len(content),
                original_content_files_unchanged=len(content) - len(changed_content),
                authorized_changed_content_files=changed_content,
                old_content_hashes_preserved=not changed_content,
                immutable_assets_preserved_except_authorized_wall_height_sync=True,
                original_map_baseline_sha256=baseline['old_map_sha256'], original_map_current_sha256=map_expected,
                source_registry_baseline_sha256=baseline['source_registry_sha256'], source_registry_current_sha256=registry_expected,
                authorized_wall_height_sync=sync)


def actor_state(actor):
    return dict(actor_class=actor.get_class().get_path_name(),
                tags=sorted(str(tag) for tag in actor.tags),
                location=common.xyz(actor.get_actor_location()),
                scale=common.xyz(actor.get_actor_scale3d()),
                forward=common.xyz(actor.get_actor_forward_vector()),
                right=common.xyz(actor.get_actor_right_vector()),
                up=common.xyz(actor.get_actor_up_vector()))


def check_actor_state(actor, expected, label):
    actual = actor_state(actor)
    assert actual['actor_class'] == expected['actor_class'], label + ' actor class changed'
    assert set(expected['tags']).issubset(actual['tags']), label + ' source tags removed'
    for key in ['location', 'scale', 'forward', 'right', 'up']:
        common.compare(actual[key], expected[key], .05 if key == 'location' else .0002, label + ' ' + key)


def load_labels(path):
    assert unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).load_level(path), 'Could not load ' + path
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    assert world.get_path_name().split('.')[0] == path
    labels = {}
    for actor in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
        name = actor.get_actor_label()
        assert name not in labels, 'Duplicate actor label: ' + name
        labels[name] = actor
    return labels


def mesh_state(mesh, editor):
    count = editor.get_lod_count(mesh)
    bounds = mesh.get_bounds()
    return dict(path=mesh.get_path_name(), lod_count=count,
                screen_sizes=list(editor.get_lod_screen_sizes(mesh)),
                triangles=[mesh.get_num_triangles(i) for i in range(count)],
                sections=[mesh.get_num_sections(i) for i in range(count)],
                bounds_origin_cm=common.xyz(bounds.origin), bounds_extent_cm=common.xyz(bounds.box_extent),
                default_materials=[slot.get_editor_property('material_interface').get_path_name()
                                   for slot in mesh.get_editor_property('static_materials')])


def material_master(material):
    seen = set()
    while isinstance(material, unreal.MaterialInstanceConstant):
        path = material.get_path_name()
        assert path not in seen, 'Material parent cycle: ' + path
        seen.add(path)
        material = prop(material, 'parent')
        assert material, 'Material instance has no parent'
    assert isinstance(material, unreal.Material), 'Expected a Material master'
    return material


def component_materials(component, label, expected_count=None):
    count = component.get_num_materials()
    assert count > 0 and (expected_count is None or count == expected_count), label + ' material slot count changed'
    materials = []
    for slot in range(count):
        material = component.get_material(slot)
        assert material, '%s null material slot %d' % (label, slot)
        path = material.get_path_name()
        assert 'WorldGrid' not in path and 'DefaultMaterial' not in path, label + ' fallback material: ' + path
        if isinstance(component, unreal.HierarchicalInstancedStaticMeshComponent):
            assert prop(material_master(material), 'used_with_instanced_static_meshes'), path + ' instancing usage not saved'
        materials.append(path)
    return materials


def upstream_nodes(material, output):
    ml = unreal.MaterialEditingLibrary
    root = ml.get_material_property_input_node(material, output)
    assert root, material.get_name() + ' missing connected graph for ' + str(output)
    seen, nodes, pending = set(), [], [root]
    while pending:
        node = pending.pop()
        path = node.get_path_name()
        if path in seen:
            continue
        seen.add(path)
        nodes.append(node)
        pending.extend(n for n in ml.get_inputs_for_material_expression(material, node) if n)
    return nodes


def verify_scalar(material, name, expected, output=None):
    ml = unreal.MaterialEditingLibrary
    actual = float(ml.get_material_default_scalar_parameter_value(material, name))
    common.compare([actual], [float(expected)], 1e-5, material.get_name() + ' ' + name)
    if output is not None:
        node = ml.get_material_property_input_node(material, output)
        assert isinstance(node, unreal.MaterialExpressionScalarParameter) and str(prop(node, 'parameter_name')) == name, (
            material.get_name() + ' ' + name + ' is not connected directly to its surface output')
    return actual


def verify_vector(material, name, expected):
    value = unreal.MaterialEditingLibrary.get_material_default_vector_parameter_value(material, name)
    actual = [float(value.r), float(value.g), float(value.b)]
    common.compare(actual, expected, 1e-5, material.get_name() + ' ' + name)
    return actual


def verify_surface_material(material, name, item):
    assert prop(material, 'material_domain') == unreal.MaterialDomain.MD_SURFACE
    assert prop(material, 'used_with_instanced_static_meshes'), material.get_name() + ' usage flag not saved'
    assert prop(material, 'shading_model') == (unreal.MaterialShadingModel.MSM_UNLIT if item.get('unlit') else
                                             unreal.MaterialShadingModel.MSM_DEFAULT_LIT), name + ' shading model differs'
    assert prop(material, 'blend_mode') == (unreal.BlendMode.BLEND_MASKED if item.get('masked') else
                                          unreal.BlendMode.BLEND_OPAQUE), name + ' blend mode differs'
    assert bool(prop(material, 'two_sided')) == bool(item.get('two_sided', False)), name + ' two-sided flag differs'
    detail = dict(path=material.get_path_name(), SurfaceTint=verify_vector(material, 'SurfaceTint', item['base_color']))
    for parameter, value, output in [
        ('Roughness', item['roughness'], unreal.MaterialProperty.MP_ROUGHNESS),
        ('Metallic', item['metallic'], unreal.MaterialProperty.MP_METALLIC),
        ('Specular', .30, unreal.MaterialProperty.MP_SPECULAR),
    ]:
        detail[parameter] = verify_scalar(material, parameter, value, output)
    target = unreal.MaterialProperty.MP_EMISSIVE_COLOR if item.get('unlit') else unreal.MaterialProperty.MP_BASE_COLOR
    nodes = upstream_nodes(material, target)
    vector_names = {str(prop(n, 'parameter_name')) for n in nodes if isinstance(n, unreal.MaterialExpressionVectorParameter)}
    scalar_names = {str(prop(n, 'parameter_name')) for n in nodes if isinstance(n, unreal.MaterialExpressionScalarParameter)}
    assert 'SurfaceTint' in vector_names, name + ' SurfaceTint is disconnected'
    if 'tier_period_cm' in item:
        assert any(isinstance(n, unreal.MaterialExpressionCustom) for n in nodes), name + ' shelf color Custom graph missing'
        assert any(isinstance(n, unreal.MaterialExpressionWorldPosition) for n in nodes), name + ' shelf world position missing'
        assert 'ShelfBlue' in vector_names and {'Origin', 'Period', 'HalfWidth'}.issubset(scalar_names)
        detail['ShelfBlue'] = verify_vector(material, 'ShelfBlue', item['tier_color'])
        for parameter, key in [('Origin', 'tier_origin_cm'), ('Period', 'tier_period_cm'), ('HalfWidth', 'tier_halfwidth_cm')]:
            detail[parameter] = verify_scalar(material, parameter, item[key])
    if 'instance_variation' in item:
        assert any(isinstance(n, unreal.MaterialExpressionCustom) for n in nodes), name + ' instance color Custom graph missing'
        assert any(isinstance(n, unreal.MaterialExpressionPerInstanceRandom) for n in nodes), name + ' PerInstanceRandom missing'
        assert 'Variation' in scalar_names
        detail['Variation'] = verify_scalar(material, 'Variation', item['instance_variation'])
    if item.get('masked'):
        detail['EnvelopeOpacity'] = verify_scalar(material, 'EnvelopeOpacity', item['opacity'], unreal.MaterialProperty.MP_OPACITY_MASK)
    if name == 'GhostDisabled':
        assert item.get('masked') and item['opacity'] == 0.0, 'Ghost envelope must be fully masked out'
    if name == 'Sky':
        assert item.get('unlit'), 'Studio sky must use unlit shading'
    else:
        assert not item.get('unlit'), name + ' unexpectedly uses unlit shading'
    detail['surface_graph_nodes'] = len(nodes)
    return detail


def connected_fx_graph(master, light):
    ml = unreal.MaterialEditingLibrary
    detail = {}
    assert prop(master, 'material_domain') == unreal.MaterialDomain.MD_DEFERRED_DECAL
    assert prop(master, 'blend_mode') == unreal.BlendMode.BLEND_TRANSLUCENT
    for label, output in [('emissive', unreal.MaterialProperty.MP_EMISSIVE_COLOR),
                          ('opacity', unreal.MaterialProperty.MP_OPACITY)]:
        nodes = upstream_nodes(master, output)
        times = [n.get_path_name() for n in nodes if isinstance(n, unreal.MaterialExpressionTime)]
        scalars = {str(prop(n, 'parameter_name')) for n in nodes if isinstance(n, unreal.MaterialExpressionScalarParameter)}
        assert times and {'Speed', 'Phase'}.issubset(scalars), master.get_name() + ' has no connected Time/Speed/Phase'
        parameter, expected = ('EmissionScale', light['fx_emissive_scale']) if label == 'emissive' else ('OpacityScale', light['fx_opacity_scale'])
        assert parameter in scalars, master.get_name() + ' missing connected ' + parameter
        assert isinstance(nodes[0], unreal.MaterialExpressionMultiply), master.get_name() + ' FX output is not multiplied by scale'
        actual = verify_scalar(master, parameter, expected)
        detail[label] = dict(connected_time_nodes=times, connected_scalar_parameters=sorted(scalars), scale_parameter=parameter, scale=actual)
    base = ml.get_material_property_input_node(master, unreal.MaterialProperty.MP_BASE_COLOR)
    assert isinstance(base, unreal.MaterialExpressionVectorParameter) and str(prop(base, 'parameter_name')) == 'Tint', (
        master.get_name() + ' BaseColor must connect to Tint')
    detail['base_color_parameter'] = 'Tint'
    return detail


def verify_lighting(labels, style):
    directions = [a for a in labels.values() if isinstance(a, unreal.DirectionalLight)]
    skies = [a for a in labels.values() if isinstance(a, unreal.SkyLight)]
    volumes = [a for a in labels.values() if isinstance(a, unreal.PostProcessVolume)]
    assert len(directions) == len(skies) == len(volumes) == 1, 'Expected one directional, one sky, and one PP volume'
    assert not any(isinstance(a, (unreal.PointLight, unreal.RectLight, unreal.SpotLight)) for a in labels.values()), 'Unexpected local fill light'
    directional = directions[0].get_component_by_class(unreal.DirectionalLightComponent)
    sky = skies[0].get_component_by_class(unreal.SkyLightComponent)
    for component, prefix in [(directional, 'directional'), (sky, 'skylight')]:
        assert prop(component, 'mobility') == unreal.ComponentMobility.MOVABLE
        common.compare([float(prop(component, 'intensity'))], [style[prefix + '_intensity']], 1e-5, prefix + ' intensity')
        color = component.get_light_color()
        common.compare([color.r, color.g, color.b], style[prefix + '_color'], .01, prefix + ' color')
    assert prop(directional, 'cast_shadows') and not prop(sky, 'cast_shadows')
    common.compare([float(prop(directional, 'light_source_angle'))], [style['directional_source_angle']], 1e-5, 'directional source angle')
    rotation = directions[0].get_actor_rotation()
    actual_rotation = [float(rotation.pitch), float(rotation.yaw), float(rotation.roll)]
    assert all(abs((a - b + 180) % 360 - 180) < .02 for a, b in zip(actual_rotation, style['directional_rotation'])), 'Directional rotation differs'
    assert not prop(sky, 'real_time_capture') and not prop(sky, 'lower_hemisphere_is_black')
    assert prop(sky, 'source_type') == unreal.SkyLightSourceType.SLS_SPECIFIED_CUBEMAP
    assert prop(sky, 'cubemap_resolution') == 64 and prop(sky, 'cubemap').get_path_name() == style['skylight_cubemap']
    volume = volumes[0]
    assert prop(volume, 'unbound'), 'Studio PP volume is not unbound'
    settings = prop(volume, 'settings')
    values = dict(vignette_intensity=0.0, bloom_intensity=style['bloom_intensity'],
                  ambient_occlusion_intensity=style['ambient_occlusion_intensity'],
                  ambient_occlusion_radius=style['ambient_occlusion_radius_cm'],
                  ambient_occlusion_quality=style['ambient_occlusion_quality'],
                  auto_exposure_min_brightness=style['exposure_ev100'],
                  auto_exposure_max_brightness=style['exposure_ev100'], auto_exposure_bias=0.0)
    for name, expected in values.items():
        assert prop(settings, 'override_' + name), 'PP override disabled: ' + name
        common.compare([float(prop(settings, name))], [float(expected)], 1e-5, 'PP ' + name)
    for name, expected in [('dynamic_global_illumination_method', unreal.DynamicGlobalIlluminationMethod.NONE),
                           ('reflection_method', unreal.ReflectionMethod.NONE)]:
        assert prop(settings, 'override_' + name) and prop(settings, name) == expected, 'PP ' + name + ' differs'
    return dict(style=style, directional_count=1, skylight_count=1, local_fill_count=0,
                directional_cast_shadows=True, skylight_cast_shadows=False, cubemap_resolution=64,
                real_time_capture=False, post_process=values, no_lumen=True)


def check_column_closure(groups, components, boxes):
    grouped = defaultdict(list)
    component = components['GHS_ColumnEdgeOutlines']
    bounds = prop(component, 'static_mesh').get_bounds()
    for index, row in enumerate(groups['GHS_ColumnEdgeOutlines']['instances']):
        grouped[row['parent_column_id']].append(clearance.actual_box(component.get_instance_transform(index, world_space=True), bounds))
    assert len(grouped) == 170
    for identity, outlines in grouped.items():
        body = boxes[identity]
        size = (body.hx * 2, body.hy * 2, body.zmax - body.zmin)
        expected = column.expected_edges(*size)
        remaining, local = set(range(12)), []
        assert len(outlines) == 12, identity + ' does not have twelve edges'
        for box in outlines:
            center, half, points = column.box_in_column_frame(box, body)
            assert max(abs(p[k]) - size[k] / 2 for p in points for k in range(3)) <= column.TOLERANCE_M
            error = lambda j: max([abs(center[k] - expected[j][0][k]) for k in range(3)] +
                                  [abs(half[k] - expected[j][1][k]) for k in range(3)])
            best = min(remaining, key=error)
            assert error(best) <= column.TOLERANCE_M, identity + ' incorrect column edge'
            remaining.remove(best)
            local.append((center, half))
        assert not remaining and not any(column.local_positive_overlap(a, b) for i, a in enumerate(local) for b in local[i + 1:])


def main(report):
    baseline = read(SOURCE / 'baseline_hashes.json')
    baseline_integrity = verify_baseline(baseline)
    report.update(baseline_integrity)
    build = read(ROOT / 'Saved/GHS_NormalBuild.json')
    assert build['success'] and build['map'] == MAP, 'Normal build is not complete'
    registry = read(SOURCE / 'ue_scene_registry.json')
    original = read(ORIGINAL / 'ue_scene_registry.json')
    assert registry.get('map') in {MAP, OLD_MAP}
    for key, value in original.items():
        if key != 'map':
            assert registry.get(key) == value, 'CAD registry differs from source: ' + key
    style = read(SOURCE / 'material_style.json')
    light_style = read(SOURCE / 'lighting_style.json')
    assert len(style) == 20 and set(build['materials']) == set(style), 'Expected exactly 20 declared normal materials'
    # Read usage flags before loading HISM actors, which can auto-enable flags.
    report['normal_materials'] = []
    report['material_parameter_readback'] = {}
    for name, item in style.items():
        path = MATERIAL_ROOT + 'M_GHN_' + name
        material = unreal.EditorAssetLibrary.load_asset(path)
        assert isinstance(material, unreal.Material), 'Missing normal material: ' + path
        assert material.get_path_name() == build['materials'][name], name + ' material differs from build report'
        report['material_parameter_readback'][name] = verify_surface_material(material, name, item)
        report['normal_materials'].append(material.get_path_name())
    new_map_file = ROOT / 'Content/Maps/GHS_CAD_NormalWarehouse.umap'
    immutable_paths = [new_map_file, SOURCE / 'ue_scene_registry.json', SOURCE / 'material_style.json',
                       SOURCE / 'lighting_style.json', SOURCE / 'baseline_hashes.json', ROOT / 'Saved/GHS_NormalBuild.json']
    if baseline_integrity['authorized_wall_height_sync']:
        immutable_paths.extend([WALL_SYNC_REPORT, WALL_HEIGHT_PROFILE, ORIGINAL / 'Presentation/visual_layout.json'])
    immutable_paths.extend(p for p in (ROOT / 'Saved').glob('GHS_*Verification.json') if p != REPORT)
    before_files = {str(path): sha(path) for path in immutable_paths}
    unreal.load_module('StaticMeshEditor')
    mesh_editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    groups = {g['actor']: g for g in registry['groups']}
    assert len(groups) == len(registry['groups']) == 18
    assert sum(g['count'] for g in groups.values()) == 14116
    old_labels = load_labels(OLD_MAP)
    assert len(old_labels) == 227, 'Source scene is not the verified presentation map'
    old_states = {name: actor_state(actor) for name, actor in old_labels.items()
                  if not isinstance(actor, (unreal.Light, unreal.SkyLight, unreal.PostProcessVolume))}
    old_slots = {}
    old_meshes = {}
    for label in list(groups) + [r['id'] for r in registry['individuals']]:
        component = old_labels[label].get_component_by_class(unreal.StaticMeshComponent)
        assert component, label + ' missing source mesh component'
        old_slots[label] = component.get_num_materials()
        mesh = prop(component, 'static_mesh')
        old_meshes[mesh.get_path_name()] = mesh_state(mesh, mesh_editor)
    old_camera_fovs = {name: actor.get_component_by_class(unreal.CameraComponent).field_of_view
                       for name, actor in old_labels.items() if actor.get_component_by_class(unreal.CameraComponent)}
    old_labels = None
    labels = load_labels(MAP)
    for name, state in old_states.items():
        assert name in labels, 'Original scene actor missing: ' + name
        check_actor_state(labels[name], state, name)
    added = [name for name in labels if name not in old_states and
             not isinstance(labels[name], (unreal.Light, unreal.SkyLight, unreal.PostProcessVolume))]
    assert set(added) == {'GHN_StudioGround', 'GHN_StudioSky'} == set(build['added_environment']), 'Unexpected added environment actor set'
    for label in added:
        actor = labels[label]
        assert not any(str(tag).startswith(('CAD=', 'TwinId=', 'FXOwner=')) for tag in actor.tags), label + ' additional actor claims a CAD identity'
        assert not actor.get_components_by_class(unreal.HierarchicalInstancedStaticMeshComponent), label + ' unexpected added HISM'
        for component in actor.get_components_by_class(unreal.PrimitiveComponent):
            assert component.get_collision_enabled() == unreal.CollisionEnabled.NO_COLLISION, label + ' additional environment collision'
            assert not prop(component, 'cast_shadow') and not prop(component, 'receives_decals'), label + ' studio backdrop affects scene shadows/decals'
        component = actor.get_component_by_class(unreal.StaticMeshComponent)
        expected_material = 'Sky' if label == 'GHN_StudioSky' else 'Surround'
        expected_mesh = '/Engine/BasicShapes/Sphere.Sphere' if label == 'GHN_StudioSky' else '/Engine/BasicShapes/Plane.Plane'
        assert component and prop(component, 'static_mesh').get_path_name() == expected_mesh
        assert component_materials(component, label, 1) == [build['materials'][expected_material]]
    report['added_environment_actors'] = added
    assert len(labels) == build['actor_count'] == 229
    overrides = build['component_overrides']
    assert set(overrides) == set(groups) | {'GHS_CAD_ExactFootprint', 'GHS_DarkSurround'}, 'Build override actor set incomplete'
    report['component_overrides_readback'] = {}
    for label, keys in overrides.items():
        assert all(key in build['materials'] for key in keys), label + ' unknown normal material key'
        component = labels[label].get_component_by_class(unreal.StaticMeshComponent)
        assert component, label + ' override component missing'
        actual = component_materials(component, label, len(keys))
        expected = [build['materials'][key] for key in keys]
        assert actual == expected, label + ' saved component material overrides differ from build'
        report['component_overrides_readback'][label] = actual
    hism_labels = {name for name, actor in labels.items() if actor.get_components_by_class(unreal.HierarchicalInstancedStaticMeshComponent)}
    assert hism_labels == set(groups), 'HISM groups differ from CAD source'
    components, objects, boxes, new_material_uses = {}, [], {}, 0
    for label, group in groups.items():
        actor = labels[label]
        found = actor.get_components_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
        assert len(found) == 1
        component = components[label] = found[0]
        if label not in HIDDEN_ALLOWED:
            assert prop(component, 'visible') and not prop(component, 'hidden_in_game'), label + ' hidden CAD geometry'
            # UE 5.4 exposes bHidden as a reflected property; IsHidden() is
            # native-only (not a UFUNCTION), so Python has no is_hidden().
            assert not prop(actor, 'hidden'), label + ' actor hidden in game'
        count = component.get_instance_count()
        assert count == group['count'] == len(group['instances']), label + ' instance count changed'
        mesh = prop(component, 'static_mesh')
        assert mesh.get_path_name() == common.expected_mesh_path(group['mesh']), label + ' mesh changed'
        materials = component_materials(component, label, old_slots[label])
        new_material_uses += sum(path.startswith(MATERIAL_ROOT) for path in materials)
        maximum = dict(position_cm=0.0, scale=0.0, yaw_deg=0.0)
        for index, row in enumerate(group['instances']):
            transform = component.get_instance_transform(index, world_space=True)
            errors = common.check_transform(transform, row, '%s[%d]' % (label, index))
            for key, value in errors.items():
                maximum[key] = max(maximum[key], value)
            if label in KINDS:
                box = clearance.actual_box(transform, mesh.get_bounds())
                boxes[row['id']] = box
                objects.append(dict(actor=label, kind=KINDS[label], id=row['id'], box=box))
        report['groups'].append(dict(actor=label, count=count, mesh=mesh.get_path_name(), materials=materials,
                                     maximum_error=maximum, all_world_transforms_verified=True,
                                     hidden_in_game=bool(prop(component, 'hidden_in_game')) or bool(prop(actor, 'hidden'))))
    assert new_material_uses > 0, 'New HISM appearance has no independent normal materials'
    individuals = registry['individuals']
    assert len(individuals) == 92
    expected_ids = {r['id'] for r in individuals}
    twin_ids = [str(tag)[7:] for actor in labels.values() for tag in actor.tags if str(tag).startswith('TwinId=')]
    assert sorted(twin_ids) == sorted(expected_ids), 'TwinId identity set changed'
    for row in individuals:
        label, actor = row['id'], labels[row['id']]
        common.check_transform(actor.get_actor_transform(), row, label)
        component = actor.get_component_by_class(unreal.StaticMeshComponent)
        assert component and not isinstance(component, unreal.InstancedStaticMeshComponent)
        mesh = prop(component, 'static_mesh')
        assert mesh.get_path_name() == common.expected_mesh_path(row['mesh']), label + ' individual mesh changed'
        assert str(actor.get_folder_path()) == 'GHS/' + row['folder'], label + ' source folder changed'
        materials = component_materials(component, label, old_slots[label])
        if row['folder'] == 'Equipment/AGVs':
            assert prop(component, 'mobility') == unreal.ComponentMobility.MOVABLE
        report['individuals'].append(dict(id=label, mesh=mesh.get_path_name(), materials=materials))
    for path, expected in old_meshes.items():
        mesh = unreal.EditorAssetLibrary.load_asset(path)
        actual = mesh_state(mesh, mesh_editor)
        assert actual == expected, 'Source mesh geometry/LOD/default materials changed: ' + path
        report['meshes'].append(actual)
    report['source_meshes_geometry_lod_unchanged'] = True
    expected_fx = {'FX_GHS_AGV_%02d_Diffusion' % i: ('GHS_AGV_%02d' % i, 'Diffusion', 115) for i in range(1, 35)}
    expected_fx.update({'FX_GHS_AGV_%02d_Radar' % i: ('GHS_AGV_%02d' % i, 'Radar', 300) for i in range(29, 35)})
    actual_fx = {name for name, actor in labels.items() if actor.get_component_by_class(unreal.DecalComponent)}
    assert actual_fx == set(expected_fx), '40 original AGV Decals were not preserved'
    built_fx = {row['actor']: row for row in build['fx']}
    assert len(built_fx) == len(build['fx']) == 40 and set(built_fx) == set(expected_fx), 'Build FX set incomplete'
    checked_masters = {}
    for label, (owner, kind, radius) in expected_fx.items():
        actor = labels[label]
        assert isinstance(actor, unreal.DecalActor) and actor.get_attach_parent_actor() == labels[owner], label + ' wrong owner'
        assert not actor.get_components_by_class(unreal.StaticMeshComponent), label + ' effect contains a mesh'
        component = actor.get_component_by_class(unreal.DecalComponent)
        assert prop(component, 'mobility') == unreal.ComponentMobility.MOVABLE
        assert prop(component, 'visible') and not prop(component, 'hidden_in_game') and not prop(actor, 'hidden')
        common.compare(common.xyz(prop(component, 'decal_size')), [3, radius, radius], .01, label + ' decal size')
        material = component.get_decal_material()
        assert isinstance(material, unreal.MaterialInstanceConstant)
        assert material.get_path_name() == built_fx[label]['material'] and material.get_path_name().startswith(FX_ROOT), label + ' FX material differs from build'
        assert built_fx[label]['kind'] == kind
        master = material_master(material)
        expected_master = FX_ROOT + 'M_GHN_FX_' + kind
        assert master.get_path_name().split('.')[0] == expected_master and prop(material, 'parent') == master, label + ' FX master is not independent'
        speed = float(unreal.MaterialEditingLibrary.get_material_instance_scalar_parameter_value(material, 'Speed'))
        assert math.isfinite(speed) and speed > 0, label + ' invalid animation speed'
        tint = unreal.MaterialEditingLibrary.get_material_instance_vector_parameter_value(material, 'Tint')
        common.compare([tint.r, tint.g, tint.b], light_style['fx_tint'], 1e-5, label + ' configured FX Tint')
        for name, key in [('EmissionScale', 'fx_emissive_scale'), ('OpacityScale', 'fx_opacity_scale')]:
            actual = unreal.MaterialEditingLibrary.get_material_instance_scalar_parameter_value(material, name)
            common.compare([float(actual)], [light_style[key]], 1e-5, label + ' inherited ' + name)
        if master.get_path_name() not in checked_masters:
            checked_masters[master.get_path_name()] = connected_fx_graph(master, light_style)
        report['effects'].append(dict(actor=label, parent=owner, kind=kind, material=material.get_path_name(), speed=speed,
                                     tint=[tint.r, tint.g, tint.b], master=master.get_path_name()))
    report['connected_time_animation'] = checked_masters
    report['lighting_readback'] = verify_lighting(labels, light_style)
    cameras = {name: actor for name, actor in labels.items() if actor.get_component_by_class(unreal.CameraComponent)}
    assert set(cameras) == set(old_camera_fovs) == common.CAMERAS
    for name, actor in cameras.items():
        common.compare([actor.get_component_by_class(unreal.CameraComponent).field_of_view],
                       [old_camera_fovs[name]], .0001, name + ' camera FOV')
    layout = read(ORIGINAL / 'clearance_layout.json')
    cad = read(ORIGINAL / 'cad_layout.json')
    report['lineage'] = clearance.lineage_checks(layout, registry, cad)
    blocked = {row['id'] for row in registry['blocked_storage']}
    cargo_ids = {row['id'] for label in CARGO for row in groups[label]['instances']}
    assert len(blocked) == 122 and len(cargo_ids) == 7408 and not blocked & cargo_ids
    assert cargo_ids == {row['id'] for row in layout['storage']}, 'Active cargo source IDs changed'
    report['intersections'] = clearance.check_intersections(objects)
    assert report['intersections']['overlap_count'] == 0, 'Saved CAD objects overlap: ' + str(report['intersections']['overlaps'][:10])
    check_column_closure(groups, components, boxes)
    assert verify_baseline(baseline) == baseline_integrity, 'Baseline or wall-height-sync evidence changed during verification'
    for path, digest in before_files.items():
        assert sha(Path(path)) == digest, 'Read-only verification modified file: ' + path
    report.update(success=True, actor_count=len(labels), hism_group_count=18, instanced_count=14116,
                  rack_count=1617, pallet_count=7408, column_count=170, dock_rack_count=87,
                  charger_count=56, agv_count=34, fx_count=40, camera_count=6,
                  blocked_slots_preserved=122, all_column_frames_closed=True,
                  all_hism_world_transforms_verified=True,
                  new_map_sha256=before_files[str(new_map_file)], historical_reports_unchanged=True,
                  level_saved=False, assets_saved=False)


def run():
    report = dict(success=False, map=MAP, source_map=OLD_MAP,
                  created_utc=datetime.now(timezone.utc).isoformat(),
                  verification_mode='Fresh UE process; reload source and new saved maps; read-only assets; actual-transform OBB SAT',
                  groups=[], individuals=[], effects=[], meshes=[])
    try:
        main(report)
    except Exception:
        report['success'] = False
        report['error'] = traceback.format_exc()
        raise
    finally:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(report, indent=2), encoding='utf-8')
    unreal.log('GHS_NORMAL_VERIFIED ' + json.dumps({key: report[key] for key in
               ['success', 'actor_count', 'hism_group_count', 'instanced_count', 'fx_count']}))


if __name__ == '__main__':
    run()
