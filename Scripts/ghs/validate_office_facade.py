"""Read-only verification of the expanded warehouse glass facades.

The live editor path never reloads the level. A -run=pythonscript commandlet
reloads the saved map independently. Neither path changes or saves actors or
assets; only JSON evidence is written under Saved/FacadeExpansion.
"""
from datetime import datetime, timezone
from pathlib import Path
import copy
import hashlib
import json
import math
import re
import runpy
import traceback

import unreal


ROOT = Path('D:/UEPro/Test')
OUT = ROOT / 'Saved/FacadeExpansion'
MAP = '/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
MAP_FILE = ROOT / 'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'
SOURCE = ROOT / 'SourceAssets/GHS/OfficeFacade'
MANIFEST = SOURCE / 'facade_manifest.json'
LAYOUT = SOURCE / 'facade_layout.json'
ORIGINAL_MANIFEST = OUT / 'Before/facade_manifest.json'
DOCK_TEXT = OUT / 'Before/dock_text.json'
DOOR_MAPPING = ROOT / 'SourceAssets/GHS/RackSpecs/cad_plan_mapping.json'
BASELINE = OUT / 'Before/scene_state.json'
LABEL = 'GHS_OfficeGlassFacade'
ASSETS = '/Game/GHSZcoolSmartFactory/OfficeFacade'
MATINEE = '/Engine/EditorMeshes/MatineeCam_SM.MatineeCam_SM'
ROLES = {'Glass', 'Frame', 'Panel', 'Pier', 'Sill'}


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def xyz(value):
    return [float(value.x), float(value.y), float(value.z)]


def close(actual, expected, description, tolerance=1e-4):
    assert math.isfinite(float(actual)) and math.isfinite(float(expected)), description
    assert abs(float(actual) - float(expected)) < tolerance, (description, actual, expected)


def path_asset(path):
    """Canonical asset-object path, accepting manifest package paths."""
    return path if '.' in path.rsplit('/', 1)[-1] else path + '.' + path.rsplit('/', 1)[-1]


def serialized_property(obj, name):
    value = obj.get_editor_property(name)
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    if hasattr(value, 'r'):
        return [value.r, value.g, value.b, value.a]
    return str(value)


def compare_values(actual, expected, description):
    if isinstance(expected, float):
        close(actual, expected, description)
    elif isinstance(expected, list):
        assert len(actual) == len(expected), description
        for index, (a, b) in enumerate(zip(actual, expected)):
            compare_values(a, b, '{}[{}]'.format(description, index))
    else:
        assert actual == expected, (description, actual, expected)


def approved_dock_translation(layout):
    placement = layout['dock_label_placement']
    numbers = placement['numbers']
    expected = set(range(30, 34)) | set(range(51, 54)) | set(range(75, 79))
    assert set(numbers) == expected and len(numbers) == len(expected)
    delta = placement['translation_ue_cm']
    assert delta == [0, 20, 0], 'Only the approved 20 cm south-facing text offset is allowed'
    return {'GHS_DockNumber_' + str(number): delta for number in numbers}


def check_preserved_rows(before, after, nullrhi, layout):
    original = {row['label']: row for row in before}
    current = {row['label']: row for row in after}
    translations = approved_dock_translation(layout)
    assert len(original) == len(before) == 361, 'Expected the inspected 361-actor baseline'
    assert len(current) == len(after) == len(before), 'Actor count changed during facade expansion'
    assert set(current) == set(original), 'An actor was added or removed'
    assert LABEL in original, 'Expansion requires the original office facade actor'
    for label, old in original.items():
        expected = copy.deepcopy(old)
        actual = copy.deepcopy(current[label])
        if label in translations:
            assert old['actor_class'] == '/Script/Engine.TextRenderActor'
            delta = translations[label]
            expected['transform']['position'] = [round(value + offset, 4)
                for value, offset in zip(expected['transform']['position'], delta)]
            for component in expected['components']:
                component['transform']['position'] = [round(value + offset, 4)
                    for value, offset in zip(component['transform']['position'], delta)]
        if nullrhi and (old['actor_class'] == '/Script/Engine.CameraActor' or
                        label == 'GHS_WarehouseCamera'):
            present = {component['name'] for component in actual['components']}
            expected['components'] = [component for component in expected['components']
                if component['name'] in present or component['mesh'] != MATINEE]
        for row in (expected, actual):
            row['components'].sort(key=lambda component: component['name'])
        # Camera transforms receive the same strict comparison as every actor.
        # Bounds are not included: the shared snapshot records actual transforms.
        assert expected == actual, (label, 'Existing actor/component/instance state changed')
    return current


def material_check(role, spec):
    path = ASSETS + '/Materials/M_GHSFacade_' + role
    material = unreal.load_asset(path)
    assert isinstance(material, unreal.Material), path
    ml = unreal.MaterialEditingLibrary
    tint = ml.get_material_default_vector_parameter_value(material, 'SurfaceTint')
    for actual, expected in zip((tint.r, tint.g, tint.b), spec['color_linear']):
        close(actual, expected, path + ':SurfaceTint')
    scalars = {}
    for parameter, expected in [('Roughness', spec['roughness']),
                                ('Metallic', spec.get('metallic', 0.)),
                                ('Specular', spec.get('specular', .15))]:
        actual = ml.get_material_default_scalar_parameter_value(material, parameter)
        close(actual, expected, path + ':' + parameter)
        scalars[parameter] = actual
        prop = getattr(unreal.MaterialProperty, 'MP_' + parameter.upper())
        connected = ml.get_material_property_input_node(material, prop)
        assert isinstance(connected, unreal.MaterialExpressionScalarParameter), (path, parameter, 'Disconnected output')
        assert str(connected.get_editor_property('parameter_name')) == parameter
    assert material.get_editor_property('blend_mode') == unreal.BlendMode.BLEND_OPAQUE, path
    assert material.get_editor_property('shading_model') == unreal.MaterialShadingModel.MSM_DEFAULT_LIT, path
    # Glass may add a local gradient/Fresnel treatment beyond the four defaults.
    assert ml.get_num_material_expressions(material) >= 4, path
    base = ml.get_material_property_input_node(material, unreal.MaterialProperty.MP_BASE_COLOR)
    assert base, (path, 'BaseColor output is disconnected')
    pending = [base]
    seen = set()
    connected_parameters = set()
    fresnel_found = False
    while pending:
        expression = pending.pop()
        if not expression or expression.get_path_name() in seen:
            continue
        seen.add(expression.get_path_name())
        if isinstance(expression, unreal.MaterialExpressionVectorParameter):
            connected_parameters.add(str(expression.get_editor_property('parameter_name')))
        if isinstance(expression, unreal.MaterialExpressionFresnel):
            fresnel_found = True
            close(expression.get_editor_property('exponent'), 3., path + ':FresnelExponent')
            close(expression.get_editor_property('base_reflect_fraction'), .04, path + ':FresnelBase')
        pending.extend(ml.get_inputs_for_material_expression(material, expression))
    assert 'SurfaceTint' in connected_parameters, (path, 'SurfaceTint does not reach BaseColor')
    if role == 'Glass':
        assert fresnel_found and 'GrazingTint' in connected_parameters, 'Glass Fresnel tint is not connected'
        grazing = ml.get_material_default_vector_parameter_value(material, 'GrazingTint')
        for actual, expected in zip((grazing.r, grazing.g, grazing.b), (.085, .18, .275)):
            close(actual, expected, path + ':GrazingTint')
    return dict(role=role, path=material.get_path_name(),
                color_linear=[tint.r, tint.g, tint.b], scalars=scalars,
                expressions=ml.get_num_material_expressions(material),
                base_color_connected_parameters=sorted(connected_parameters),
                fresnel_connected=fresnel_found)


def part_bounds_ue_cm(part):
    """Convert the source prism's complete UV/Z extent to UE centimeters."""
    u0, v0, u1, v1 = part['bounds_uv_m']
    z0, z1 = part['z_range_m']
    assert all(math.isfinite(float(value)) for value in (u0, v0, u1, v1, z0, z1)), part['name']
    assert u0 < u1 and v0 < v1 and z0 < z1, part['name']
    return dict(min=[(u0 - 239.33385) * 100., (v0 - 60.24019) * 100., z0 * 100.],
                max=[(u1 - 239.33385) * 100., (v1 - 60.24019) * 100., z1 * 100.])


def check_layout_and_preservation(manifest, layout, original, baseline, dock_text, door_mapping):
    assert manifest['version'] == layout['version'] == 2
    assert layout['preserve_original_office_bays']
    assert manifest['additional_groups'] == layout['groups'], 'Generated geometry uses a stale window layout'
    assert manifest.get('corner_piers', []) == layout.get('corner_piers', [])
    assert manifest['dock_label_placement'] == layout['dock_label_placement']
    translations = approved_dock_translation(layout)
    text_by = {row['label']: row for row in dock_text}
    assert set(text_by) == set(translations)
    groups = {group['id']: group for group in layout['groups']}
    assert len(groups) == len(layout['groups']), 'Duplicate window group identifier'
    old_bays = {bay['id']: bay for bay in original['bays']}
    bays = {bay['id']: bay for bay in manifest['bays']}
    assert len(old_bays) == len(original['bays'])
    assert len(bays) == len(manifest['bays']) == manifest['bay_count']
    for key, old in old_bays.items():
        assert bays.get(key) == old, (key, 'Original corner window bay changed')
    added_bays = [bay for key, bay in bays.items() if key not in old_bays]
    assert len(added_bays) == sum(group['bay_count'] for group in groups.values())
    assert {bay['facade'] for bay in added_bays} == set(groups), 'Generated window group is missing or unexpected'
    for key, group in groups.items():
        generated = [bay for bay in added_bays if bay['facade'] == key]
        assert len(generated) == group['bay_count'], key
        generated.sort(key=lambda bay: bay['id'])
        for index, bay in enumerate(generated):
            assert bay['kind'] == group['kind']
            assert bay['window_z_ranges'] == group['window_z_ranges'], (key, 'Window elevation differs from layout')
            assert bay['columns'] == group['columns']
            expected_rows = group['rows']
            if not isinstance(expected_rows, list):
                expected_rows = [expected_rows] * len(group['window_z_ranges'])
            assert bay['rows'] == expected_rows, (key, 'Window pane rows differ from layout')
            assert bay['pane_count'] == group['columns'] * sum(expected_rows)
            if group['kind'] == 'dock_portal':
                assert bay['structural_bay_edges_m'] == group['bay_edges_m'][index:index + 2]
                assert bay['dock_numbers'] == group['dock_numbers_by_bay'][index]
    assert manifest['pane_count'] == sum(bay['pane_count'] for bay in bays.values())

    original_parts = {part['name']: part for part in original['parts']}
    parts = {part['name']: part for part in manifest['parts']}
    assert len(original_parts) == len(original['parts'])
    assert len(parts) == len(manifest['parts']) == manifest['editable_part_count']
    for name, old in original_parts.items():
        assert name in parts, (name, 'Original corner part was removed')
        for key, value in old.items():
            assert parts[name].get(key) == value, (name, key, 'Original corner geometry changed')
    checks = manifest['checks']
    assert checks['original_corner_geometry_preserved']
    assert checks['original_corner_part_count'] == len(original_parts)
    added_parts = [part for name, part in parts.items() if name not in original_parts]
    assert added_parts, 'No facade extension geometry was generated'
    labels = baseline['dock_labels']
    assert labels and len({label['label'] for label in labels}) == len(labels)
    overlaps = []
    text_clearances = []
    for part in added_parts:
        bounds = part_bounds_ue_cm(part)
        for label in labels:
            if label['label'] in translations:
                delta = translations[label['label']]
                text_bounds = text_by[label['label']]['text_bounds']
                shifted = {key: [value + offset for value, offset in zip(text_bounds[key], delta)]
                           for key in ('min', 'max')}
                xz_overlap = all(min(bounds['max'][axis], shifted['max'][axis]) -
                                 max(bounds['min'][axis], shifted['min'][axis]) > .01 for axis in (0, 2))
                if xz_overlap:
                    clearance = shifted['min'][1] - bounds['max'][1]
                    assert clearance >= 2., (label['label'], part['name'], 'Text is not in front of cladding by 2 cm', clearance)
                    text_clearances.append(clearance)
                continue
            depths = [min(bounds['max'][axis], label['max'][axis]) -
                      max(bounds['min'][axis], label['min'][axis]) for axis in range(3)]
            if all(depth > .01 for depth in depths):
                overlaps.append(dict(part=part['name'], dock_label=label['label'],
                                     overlap_extent_cm=depths))
    assert not overlaps, ('New facade geometry overlaps existing dock number bounds', overlaps[:12])
    assert text_clearances, 'Portal text did not overlap any facade panel in elevation'
    # The generated south portals must be based on the actual door identities,
    # not just visually plausible spacing or the sequential display numbers.
    actors_by = {row['label']: row for row in baseline['actors']}
    doors_by = {row['instance_id']: row for row in door_mapping['loading_doors']}
    portal_numbers = []
    portal_door_clearances = []
    for group in groups.values():
        if group['kind'] != 'dock_portal':
            continue
        assert group['outward_uv'] == [0, 1]
        close(group['start_uv_m'][1], 118.872, group['id'] + ':south wall')
        close(group['end_uv_m'][1], 118.872, group['id'] + ':south wall')
        edges = group['bay_edges_m']
        close(edges[0], 0., group['id'] + ':first bay edge')
        close(edges[-1], group['end_uv_m'][0] - group['start_uv_m'][0], group['id'] + ':last bay edge')
        assert len(edges) == group['bay_count'] + 1
        assert group['pier_z_range'] == [.04, 9.56]
        assert group['lower_panel_z_range'][0] >= 4.25
        assert len(group['dock_numbers_by_bay']) == group['bay_count']
        centers_by_bay = []
        for index, numbers in enumerate(group['dock_numbers_by_bay']):
            assert numbers
            centers = []
            left = group['start_uv_m'][0] + edges[index] + group['pier_width_m'] / 2
            right = group['start_uv_m'][0] + edges[index + 1] - group['pier_width_m'] / 2
            for number in numbers:
                portal_numbers.append(number)
                row = actors_by['GHS_DockNumber_' + str(number)]
                identities = [tag.split('=', 1)[1] for tag in row['tags'] if tag.startswith('DoorInstance=')]
                assert len(identities) == 1
                door = doors_by[identities[0]]
                center = door['physical_center_m'][0] + 239.33385
                width = door['physical_size_m'][0]
                assert abs(math.sin(math.radians(door['rotation_deg']))) < 1e-6
                clearances = [center - width / 2 - left, right - center - width / 2]
                assert min(clearances) > 0., (group['id'], number, 'Full-height pier covers a loading door', clearances)
                portal_door_clearances.extend(clearances)
                centers.append(center)
            assert centers == sorted(centers), (group['id'], 'Dock order does not match the wall direction')
            centers_by_bay.append(centers)
        for index in range(1, group['bay_count']):
            expected_edge = (centers_by_bay[index - 1][-1] + centers_by_bay[index][0]) / 2
            close(group['start_uv_m'][0] + edges[index], expected_edge, group['id'] + ':pier between door centers')
        portal_parts = [part for part in added_parts if part['name'].startswith(group['id'] + '_')]
        panels = [part for part in portal_parts if part['name'].endswith('_DockSpandrel')]
        assert len(panels) == group['bay_count']
        assert all(part['z_range_m'] == group['lower_panel_z_range'] for part in panels)
    assert set(portal_numbers) == set(layout['dock_label_placement']['numbers'])
    assert len(portal_numbers) == len(set(portal_numbers))
    return dict(window_groups=len(groups), bay_count=manifest['bay_count'],
                pane_count=manifest['pane_count'], preserved_corner_parts=len(original_parts),
                added_parts=len(added_parts), dock_labels_checked=len(labels), dock_number_overlaps=[],
                moved_dock_text_count=len(translations), minimum_text_front_clearance_cm=min(text_clearances),
                portal_dock_count=len(portal_numbers), minimum_pier_to_door_clearance_m=min(portal_door_clearances))


def check_dock_text(by, layout, baseline_text):
    translations = approved_dock_translation(layout)
    assert {row['label'] for row in baseline_text} == set(translations)
    checked = []
    for row in baseline_text:
        component = by[row['label']].get_component_by_class(unreal.TextRenderComponent)
        assert component, row['label']
        color = component.text_render_color
        actual = dict(text=str(component.text), world_size=component.world_size,
                      material=component.text_material.get_path_name(),
                      font=component.font.get_path_name() if component.font else None,
                      color=[color.r, color.g, color.b, color.a],
                      horizontal_alignment=str(component.horizontal_alignment),
                      vertical_alignment=str(component.vertical_alignment))
        for key, expected in row.items():
            if key not in ('label', 'text_bounds'):
                compare_values(actual[key], expected, row['label'] + ':' + key)
        origin, extent, radius = unreal.SystemLibrary.get_component_bounds(component)
        bounds = dict(min=xyz(origin - extent), max=xyz(origin + extent))
        for key in ('min', 'max'):
            expected = [value + offset for value, offset in zip(row['text_bounds'][key], translations[row['label']])]
            for a, b in zip(bounds[key], expected):
                close(a, b, row['label'] + ':' + key, tolerance=.02)
        checked.append(dict(label=row['label'], bounds_ue_cm=bounds, attributes_preserved=True))
    return checked


def editor_actors_during_pie(editor_world):
    """Read only the editor world while leaving its separate PIE world alone.

    UE 5.4 EditorActorSubsystem::GetAllLevelActors uses this world, but its
    CheckIfInEditorAndPIE guard rejects active PIE. GameplayStatics performs
    the same world-scoped TActorIterator without that editing guard. Apply
    the reflected EAS predicates here and fail on unknown additional actors.
    Python exposes no RF_Transient flag accessor, so unrecognized transient
    actors are deliberately not silently dropped from the strict comparison.
    """
    result, excluded = [], []
    all_actors = unreal.GameplayStatics.get_all_actors_of_class(editor_world, unreal.Actor)
    for actor in all_actors:
        assert unreal.SystemLibrary.is_valid(actor), 'Invalid actor in editor-world enumeration'
        assert actor.get_world() == editor_world, 'PIE actor leaked into editor-world validation'
        reason = None
        if actor == unreal.get_default_object(actor.get_class()):
            reason = 'class default object'
        elif actor.get_outermost().get_path_name() == '/Engine/Transient':
            reason = 'transient package'
        elif not actor.is_editable():
            reason = 'not editable'
        elif not actor.get_editor_property('listed_in_scene_outliner'):
            reason = 'not listed in scene outliner'
        elif isinstance(actor, unreal.WorldSettings):
            reason = 'world settings'
        elif (actor.get_class().get_path_name() == '/Script/Engine.Brush' and
              actor.get_name() == 'Brush_0' and actor.get_editor_property('brush_builder')):
            # The default builder brush is not a user level placement. Other
            # Brush actors stay in the collection and must match the baseline.
            reason = 'default builder brush'
        if reason:
            excluded.append(dict(path=actor.get_path_name(), actor_class=actor.get_class().get_path_name(), reason=reason))
        else:
            result.append(actor)
    return result, excluded


def main():
    cli = unreal.SystemLibrary.get_command_line().lower()
    commandlet = '-run=pythonscript' in cli
    nullrhi = bool(re.search(r'(?:^|\s)-nullrhi(?=\s|$)', cli))
    report = dict(success=False, stage='initialization', map=MAP,
                  started_utc=datetime.now(timezone.utc).isoformat(),
                  mode='saved_commandlet' if commandlet else 'live_editor',
                  writes_scene=False, errors=[])
    OUT.mkdir(parents=True, exist_ok=True)
    report_path = OUT / ('saved_validation.json' if commandlet else 'live_validation.json')
    before_hash = None
    try:
        before_hash = sha(MAP_FILE)
        baseline = read(BASELINE)
        manifest = read(MANIFEST)
        layout = read(LAYOUT)
        original_manifest = read(ORIGINAL_MANIFEST)
        dock_text = read(DOCK_TEXT)
        door_mapping = read(DOOR_MAPPING)
        spec = manifest['mesh']
        levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        if commandlet:
            # UE 5.4's PIE query dereferences GUnrealEd without a null guard.
            # Commandlets need not initialize that interactive editor global.
            assert levels.load_level(MAP), 'Could not independently load the saved map'
            pie_active = False
        else:
            pie_active = levels.is_in_play_in_editor()
        editor_world = editor.get_editor_world()
        assert editor_world.get_path_name().split('.')[0] == MAP
        if pie_active:
            actor_list, excluded = editor_actors_during_pie(editor_world)
        else:
            actor_list = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
            excluded = []
        assert all(actor.get_world() == editor_world for actor in actor_list)
        report.update(pie_active=pie_active, validated_world=editor_world.get_path_name(),
                      editor_internal_actors_excluded=excluded)
        by = {actor.get_actor_label(): actor for actor in actor_list}
        helper = runpy.run_path(str(ROOT / 'Scripts/ghs/validate_park_expansion.py'))
        rows = [helper['snapshot'](actor, unreal) for actor in actor_list]
        report['stage'] = 'preserve original actors'
        current = check_preserved_rows(baseline['actors'], rows, nullrhi, layout)
        report.update(actor_count=len(actor_list), preserved_existing_actors=len(baseline['actors']),
                      ground_transform_preserved=current['GHSPark_Ground']['transform'])
        report['dock_text_preservation'] = check_dock_text(by, layout, dock_text)
        report['actor_preservation_scope'] = dict(unchanged_actors=350,
            dock_text_offset_only_actors=11, dock_translation_ue_cm=layout['dock_label_placement']['translation_ue_cm'])

        report['stage'] = 'preserve lighting and post process'
        for row in baseline.get('lights', []):
            actor = by[row['label']]
            component_class = unreal.DirectionalLightComponent if row['kind'] == 'directional' else unreal.SkyLightComponent
            component = actor.get_component_by_class(component_class)
            assert component, row['label']
            for name, expected in row.get('values', {}).items():
                if isinstance(expected, dict) and 'unavailable' in expected:
                    continue
                compare_values(serialized_property(component, name), expected, row['label'] + ':' + name)
        for row in baseline.get('post_process', []):
            settings = by[row['label']].get_editor_property('settings')
            for name, expected in row.get('values', {}).items():
                if isinstance(expected, dict) and 'unavailable' in expected:
                    continue
                compare_values(serialized_property(settings, name), expected, row['label'] + ':' + name)
        report['lighting_and_post_process_checked'] = dict(
            lights=len(baseline.get('lights', [])),
            post_process_volumes=len(baseline.get('post_process', [])))

        report['stage'] = 'facade actor and imported geometry'
        facade = by[LABEL]
        assert isinstance(facade, unreal.StaticMeshActor)
        assert set(str(tag) for tag in facade.tags) == {'GHS_OfficeFacade', 'GHS_ArchitecturalContext'}
        assert str(facade.get_folder_path()) == 'GHS/Architecture/OfficeFacade'
        assert not facade.get_actor_enable_collision() and not facade.is_actor_tick_enabled()
        assert not facade.get_editor_property('hidden')
        assert facade.get_attach_parent_actor() is None, 'Facade must not hide with the independent roof'
        transform = current[LABEL]['transform']
        assert transform == dict(position=[0., 0., 0.], scale=[1., 1., 1.], rotation=[0., 0., 0., 1.]), transform
        components = facade.get_components_by_class(unreal.StaticMeshComponent)
        assert len(components) == 1
        component = components[0]
        assert component.get_editor_property('visible') and not component.get_editor_property('hidden_in_game')
        assert component.get_editor_property('mobility') == unreal.ComponentMobility.STATIC
        assert component.get_collision_enabled() == unreal.CollisionEnabled.NO_COLLISION
        mesh = component.static_mesh
        assert isinstance(mesh, unreal.StaticMesh)
        assert mesh.get_path_name() == path_asset(ASSETS + '/Meshes/' + spec['name'])
        assert mesh.get_name() == 'SM_GHS_OfficeGlassFacade'
        assert set(spec['material_roles']) == set(manifest['materials']) == ROLES
        assert len(spec['material_roles']) == len(spec['slot_names']) == component.get_num_materials() == 5
        assert len(mesh.static_materials) == 5
        for index, role in enumerate(spec['material_roles']):
            expected = path_asset(ASSETS + '/Materials/M_GHSFacade_' + role)
            assert component.get_material(index).get_path_name() == expected
            assert str(mesh.static_materials[index].material_slot_name) == spec['slot_names'][index]
        bounds = mesh.get_bounds()
        actual_bounds = dict(min=xyz(bounds.origin - bounds.box_extent), max=xyz(bounds.origin + bounds.box_extent))
        for key in ('min', 'max'):
            for actual, expected in zip(actual_bounds[key], spec['bounds_ue_cm'][key]):
                close(actual, expected, 'mesh bounds ' + key, tolerance=2.)
        assert 0 < spec['triangles'] <= manifest['checks']['triangle_budget'] <= 30000, 'Facade exceeds the agreed triangle budget'
        assert 0 < spec['vertices']
        roof = by['GHS_MainWarehouseRoof']
        assert roof is not facade and roof.actor_has_tag('RemovableRoof')
        assert not roof.get_editor_property('hidden'), 'Roof should remain visible after capture'
        assert roof.get_component_by_class(unreal.StaticMeshComponent).static_mesh != mesh
        roof_components = roof.get_components_by_class(unreal.StaticMeshComponent)
        assert len(roof_components) == 1
        roof_materials = [roof_components[0].get_material(index).get_path_name()
                          for index in range(roof_components[0].get_num_materials())]
        assert path_asset(ASSETS + '/Materials/M_GHSFacade_Glass') in roof_materials, 'User roof glass binding was lost'
        report.update(facade_label=LABEL, facade_asset=mesh.get_path_name(),
                      bounds_ue_cm=actual_bounds, facade_triangles=spec['triangles'],
                      independent_from_roof=True, no_business_identity=True,
                      preserved_roof_material_bindings=roof_materials)

        report['stage'] = 'material parameters'
        report['materials_checked'] = [material_check(role, manifest['materials'][role])
                                       for role in spec['material_roles']]
        report['stage'] = 'source artifact integrity'
        fbx = (ROOT / spec['fbx']).resolve()
        assert fbx.is_relative_to(SOURCE.resolve()) and fbx.is_file() and fbx.stat().st_size > 1024
        assert sha(fbx) == spec['sha256'], 'FBX differs from the checked geometry manifest'
        blends = sorted(SOURCE.glob('*.blend'))
        assert blends and all(path.stat().st_size > 1024 for path in blends), 'Editable Blender source is missing'
        report['source_hashes'] = {str(path.relative_to(ROOT)): sha(path) for path in [MANIFEST, LAYOUT, fbx] + blends}
        facade_assets = sorted((ROOT / 'Content/GHSZcoolSmartFactory/OfficeFacade').rglob('*.uasset'))
        assert len(facade_assets) == 6, 'Expected exactly five facade materials and one facade mesh'
        report['facade_asset_hashes'] = {str(path.relative_to(ROOT)): sha(path) for path in facade_assets}
        report['layout_validation'] = check_layout_and_preservation(manifest, layout, original_manifest, baseline, dock_text, door_mapping)
        checks = manifest['checks']
        for key in ('all_parts_closed', 'all_faces_valid', 'positive_volume_parts',
                    'all_geometry_below_roof', 'existing_shared_sources_unchanged'):
            assert checks[key], ('Source geometry check failed', key)
        assert checks['glass_back_clearance_m'] > 0.
        assert checks['door_overlap_volume_m3'] == 0., 'Facade solids overlap loading door openings'
        protected_hashes = {}
        for relative, expected in checks['source_hashes'].items():
            source = (ROOT / relative).resolve()
            assert source.is_relative_to(ROOT) and source.is_file(), relative
            assert sha(source) == expected, ('Shared source changed after geometry validation', relative)
            protected_hashes[relative] = expected
        report.update(bay_count=manifest['bay_count'], pane_count=manifest['pane_count'],
                      protected_source_hashes=protected_hashes)
        dirty = sorted(package.get_path_name() for package in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
        assert not any(path.startswith(ASSETS + '/') for path in dirty), 'Facade assets are not saved'
        report['dirty_assets'] = dirty
        report['success'] = True
        report['stage'] = 'complete'
    except Exception:
        report['errors'].append(traceback.format_exc())
        unreal.log_error(report['errors'][-1])
    finally:
        try:
            after_hash = sha(MAP_FILE)
            report.update(map_sha256=after_hash, map_unchanged_during_validation=before_hash == after_hash)
            if before_hash != after_hash:
                report['success'] = False
                report['errors'].append('Map bytes changed during read-only validation')
        except Exception:
            report['success'] = False
            report['errors'].append(traceback.format_exc())
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    assert report['success'], '\n'.join(report['errors'])
    unreal.log('GHS_OFFICE_FACADE_VALIDATED ' + str(report_path))


if __name__ == '__main__':
    main()
