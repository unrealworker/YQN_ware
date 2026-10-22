"""Read-only verification of the additive southwest office glass facade.

The live editor path never reloads the level. A -run=pythonscript commandlet
reloads the saved map independently. Neither path changes or saves actors or
assets; only JSON evidence is written under Saved/OfficeFacade.
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
OUT = ROOT / 'Saved/OfficeFacade'
MAP = '/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
MAP_FILE = ROOT / 'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'
SOURCE = ROOT / 'SourceAssets/GHS/OfficeFacade'
MANIFEST = SOURCE / 'facade_manifest.json'
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


def check_preserved_rows(before, after, nullrhi):
    original = {row['label']: row for row in before}
    current = {row['label']: row for row in after}
    assert len(original) == len(before) == 360, 'Expected the inspected 360-actor baseline'
    assert len(current) == len(after) == 361, 'Expected precisely one additional actor'
    assert set(current) - set(original) == {LABEL}, 'Unexpected added actor'
    assert not set(original) - set(current), 'An existing actor was removed'
    for label, old in original.items():
        expected = copy.deepcopy(old)
        actual = copy.deepcopy(current[label])
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
        for actual, expected in zip((grazing.r, grazing.g, grazing.b), (.065, .15, .24)):
            close(actual, expected, path + ':GrazingTint')
    return dict(role=role, path=material.get_path_name(),
                color_linear=[tint.r, tint.g, tint.b], scalars=scalars,
                expressions=ml.get_num_material_expressions(material),
                base_color_connected_parameters=sorted(connected_parameters),
                fresnel_connected=fresnel_found)


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
        spec = manifest['mesh']
        levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        if commandlet:
            # UE 5.4's PIE query dereferences GUnrealEd without a null guard.
            # Commandlets need not initialize that interactive editor global.
            assert levels.load_level(MAP), 'Could not independently load the saved map'
        else:
            assert not levels.is_in_play_in_editor(), 'Validation requires an editor world'
        assert editor.get_editor_world().get_path_name().split('.')[0] == MAP
        actor_list = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
        by = {actor.get_actor_label(): actor for actor in actor_list}
        helper = runpy.run_path(str(ROOT / 'Scripts/ghs/validate_park_expansion.py'))
        rows = [helper['snapshot'](actor, unreal) for actor in actor_list]
        report['stage'] = 'preserve original actors'
        current = check_preserved_rows(baseline['actors'], rows, nullrhi)
        report.update(actor_count=len(actor_list), preserved_existing_actors=len(baseline['actors']),
                      ground_transform_preserved=current['GHSPark_Ground']['transform'])

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
        assert 0 < spec['triangles'] < 12000, 'Facade exceeds the agreed triangle budget'
        assert 0 < spec['vertices']
        roof = by['GHS_MainWarehouseRoof']
        assert roof is not facade and roof.actor_has_tag('RemovableRoof')
        assert not roof.get_editor_property('hidden'), 'Roof should remain visible after capture'
        assert roof.get_component_by_class(unreal.StaticMeshComponent).static_mesh != mesh
        report.update(facade_label=LABEL, facade_asset=mesh.get_path_name(),
                      bounds_ue_cm=actual_bounds, facade_triangles=spec['triangles'],
                      independent_from_roof=True, no_business_identity=True)

        report['stage'] = 'material parameters'
        report['materials_checked'] = [material_check(role, manifest['materials'][role])
                                       for role in spec['material_roles']]
        report['stage'] = 'source artifact integrity'
        fbx = (ROOT / spec['fbx']).resolve()
        assert fbx.is_relative_to(SOURCE.resolve()) and fbx.is_file() and fbx.stat().st_size > 1024
        assert sha(fbx) == spec['sha256'], 'FBX differs from the checked geometry manifest'
        blends = sorted(SOURCE.glob('*.blend'))
        assert blends and all(path.stat().st_size > 1024 for path in blends), 'Editable Blender source is missing'
        report['source_hashes'] = {str(path.relative_to(ROOT)): sha(path) for path in [MANIFEST, fbx] + blends}
        assert manifest['bay_count'] == len(manifest['bays']) == 8
        assert manifest['pane_count'] == sum(bay['pane_count'] for bay in manifest['bays']) == 96
        assert {facade['id']: facade['bay_count'] for facade in manifest['facades']} == {'West': 3, 'Front': 5}
        checks = manifest['checks']
        for key in ('all_parts_closed', 'all_faces_valid', 'positive_volume_parts',
                    'all_geometry_below_roof', 'existing_shared_sources_unchanged'):
            assert checks[key], ('Source geometry check failed', key)
        assert checks['glass_back_clearance_m'] > 0.
        assert checks['loading_door_overlap_area_m2'] == 0.
        assert checks['minimum_door_clearance_m'] > 0.
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
