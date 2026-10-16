"""Verify saved animated AGV decals in a fresh UE Python commandlet.

The attachment test moves the CBD50 parent temporarily and always restores its
transform. This script never saves the level or changes an asset.
"""
import json
import math
import re
import traceback
from pathlib import Path

import unreal

ROOT = Path(r'D:\UEPro\Test')
MAP = '/Game/Maps/VideoDigitalTwinWarehouse'
DEST = '/Game/VideoDigitalTwin/FX'
MANIFEST = ROOT / 'SourceAssets/VideoReference/animated_fx.json'
REPORT = ROOT / 'Saved/AGVFX_Verification.json'
ROBOTS = ['CDD14-1', 'CDD14-2', 'CDD14-3', 'CDD14-4', 'CBD50-1', 'HR-1', 'DN-1']
LEGACY = [name + '_StatusRing' for name in ROBOTS[:-1]] + ['ALARM_DN1_Ring', 'SCAN_AvoidanceFan']
result = dict(success=False, map=MAP, manifest=str(MANIFEST),
              verification_mode='Fresh process; reload saved map and assets; temporary parent motion; no save',
              details=dict(effects=[], materials=[], hidden_legacy=[], attachment_follow={}))


def xyz(value):
    return [float(value.x), float(value.y), float(value.z)]


def near(actual, expected, tolerance, message):
    assert len(actual) == len(expected) and all(
        math.isfinite(a) and abs(a - b) <= tolerance for a, b in zip(actual, expected)
    ), '%s: actual=%s expected=%s' % (message, actual, expected)


def snapshot(actor):
    return dict(location=xyz(actor.get_actor_location()),
                right=xyz(actor.get_actor_right_vector()),
                forward=xyz(actor.get_actor_forward_vector()),
                scale=xyz(actor.get_actor_scale3d()))


def rotate_z(vector, degrees):
    angle = math.radians(degrees)
    c, s = math.cos(angle), math.sin(angle)
    return [vector[0] * c - vector[1] * s, vector[0] * s + vector[1] * c, vector[2]]


def upstream_nodes(material, root):
    """Use the same saved-graph traversal as verify_video_warehouse.py."""
    assert root, 'Missing connected material graph root: ' + material.get_path_name()
    nodes, seen, pending = [], set(), [root]
    while pending:
        node = pending.pop()
        key = node.get_path_name()
        if key in seen:
            continue
        seen.add(key)
        nodes.append(node)
        pending.extend(value for value in unreal.MaterialEditingLibrary.get_inputs_for_material_expression(material, node) if value)
    return nodes


def verify_material(material):
    assert isinstance(material, unreal.Material), 'Missing master material'
    assert material.get_editor_property('material_domain') == unreal.MaterialDomain.MD_DEFERRED_DECAL
    assert material.get_editor_property('blend_mode') == unreal.BlendMode.BLEND_TRANSLUCENT
    ml = unreal.MaterialEditingLibrary
    assert hasattr(ml, 'get_material_property_input_node') and hasattr(ml, 'get_inputs_for_material_expression'), (
        'UE graph traversal API unavailable; cannot prove connected Time animation')
    detail = dict(path=material.get_path_name(), graph_api='MaterialEditingLibrary graph traversal', outputs={})
    for label, prop in [('emissive', unreal.MaterialProperty.MP_EMISSIVE_COLOR),
                        ('opacity', unreal.MaterialProperty.MP_OPACITY)]:
        nodes = upstream_nodes(material, ml.get_material_property_input_node(material, prop))
        customs = [node for node in nodes if isinstance(node, unreal.MaterialExpressionCustom)]
        assert customs, '%s has no connected Custom node for %s' % (material.get_name(), label)
        custom_details = []
        for custom in customs:
            code = str(custom.get_editor_property('code'))
            assert re.search(r'\bT\b', code), 'Custom HLSL does not use time input T'
            inputs = [str(item.get_editor_property('input_name')) for item in custom.get_editor_property('inputs')]
            assert {'UV', 'T', 'Tint', 'Phase'}.issubset(inputs), inputs
            custom_nodes = upstream_nodes(material, custom)
            times = [node for node in custom_nodes if isinstance(node, unreal.MaterialExpressionTime)]
            assert times, 'Custom HLSL has no connected Time expression'
            scalars = [str(node.get_editor_property('parameter_name')) for node in custom_nodes
                       if isinstance(node, unreal.MaterialExpressionScalarParameter)]
            assert 'Speed' in scalars and 'Phase' in scalars, scalars
            custom_details.append(dict(path=custom.get_path_name(), inputs=inputs,
                                       time_nodes=[node.get_path_name() for node in times],
                                       scalar_parameters=scalars, code_uses_T=True))
        detail['outputs'][label] = dict(reachable_node_count=len(nodes), custom_nodes=custom_details)
    return detail


def verify_follow(parent, children):
    """Check both translation and yaw, restoring even if an assertion fails."""
    detail = result['details']['attachment_follow']
    original = parent.get_actor_transform()
    parent_before = snapshot(parent)
    before = {child.get_actor_label(): snapshot(child) for child in children}
    rotation = parent.get_actor_rotation()
    detail.update(parent=parent.get_actor_label(), translation_cm=[100, 0, 0], yaw_degrees=30,
                  before=before, restored=False)
    try:
        assert abs(rotation.pitch) < .01 and abs(rotation.roll) < .01, 'Expected an upright CBD50 robot'
        moved = [parent_before['location'][0] + 100, parent_before['location'][1], parent_before['location'][2]]
        parent.set_actor_location(unreal.Vector(*moved), False, True)
        near(xyz(parent.get_actor_location()), moved, .01, 'Parent translation was not applied')
        translated = {}
        for child in children:
            name = child.get_actor_label()
            state = snapshot(child)
            expected = list(before[name]['location'])
            expected[0] += 100
            near(state['location'], expected, .05, name + ' failed to follow translation')
            near(state['right'], before[name]['right'], .0001, name + ' orientation changed on translation')
            translated[name] = state
        detail['after_translation'] = translated
        parent.set_actor_rotation(unreal.Rotator(pitch=rotation.pitch, yaw=rotation.yaw + 30, roll=rotation.roll), True)
        near(xyz(parent.get_actor_right_vector()), rotate_z(parent_before['right'], 30), .0001,
             'Parent rotation was not applied')
        rotated = {}
        for child in children:
            name = child.get_actor_label()
            state = snapshot(child)
            offset = [a - b for a, b in zip(before[name]['location'], parent_before['location'])]
            expected = [a + b for a, b in zip(moved, rotate_z(offset, 30))]
            near(state['location'], expected, .05, name + ' failed to follow rotation position')
            near(state['right'], rotate_z(before[name]['right'], 30), .0001, name + ' failed to follow yaw')
            near(state['forward'], rotate_z(before[name]['forward'], 30), .0001, name + ' forward basis mismatch')
            rotated[name] = state
        detail.update(after_rotation=rotated, translation_passed=True, yaw_passed=True)
    finally:
        parent.set_actor_transform(original, False, True)
        restored = {'parent': snapshot(parent), 'children': {child.get_actor_label(): snapshot(child) for child in children}}
        detail['after_restore'] = restored
        for key, expected in parent_before.items():
            near(restored['parent'][key], expected, .05 if key == 'location' else .0001, 'Parent restore ' + key)
        for name, expected_state in before.items():
            for key, expected in expected_state.items():
                near(restored['children'][name][key], expected, .05 if key == 'location' else .0001,
                     name + ' restore ' + key)
        detail['restored'] = True


def main():
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    assert manifest.get('effect_meshes') is False, 'Manifest must declare no effect meshes'
    records = manifest['effects']
    expected_labels = {'FX_' + name + '_Diffusion' for name in ROBOTS} | {'FX_CBD50-1_Radar'}
    assert len(records) == 8 and {item['actor'] for item in records} == expected_labels
    assert {item['parent'] for item in records} == set(ROBOTS)
    assert len(manifest['hidden_legacy_actors']) == 8 and set(manifest['hidden_legacy_actors']) == set(LEGACY)
    assert unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).load_level(MAP), 'Could not reload saved map'
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
    labels = {}
    for actor in actors:
        labels.setdefault(actor.get_actor_label(), []).append(actor)

    def single(label):
        found = labels.get(label, [])
        assert len(found) == 1, 'Expected one %s, got %d' % (label, len(found))
        return found[0]

    placed_fx = [actor for actor in actors if 'AGVAnimatedFX' in [str(tag) for tag in actor.tags]
                 or str(actor.get_folder_path()) == 'VideoTwin/FX/AnimatedDecals']
    assert len(placed_fx) == 8 and {actor.get_actor_label() for actor in placed_fx} == expected_labels
    masters = {kind: unreal.EditorAssetLibrary.load_asset(DEST + '/M_VR_FX_' + kind)
               for kind in ['Diffusion', 'Radar']}
    assert all(masters.values()), 'Missing saved master materials'
    assert set(manifest['master_materials']) == {material.get_path_name() for material in masters.values()}
    for material in masters.values():
        result['details']['materials'].append(verify_material(material))
    for item in records:
        actor, parent = single(item['actor']), single(item['parent'])
        assert isinstance(actor, unreal.DecalActor), item['actor'] + ' is not a native DecalActor'
        assert not actor.get_components_by_class(unreal.StaticMeshComponent), item['actor'] + ' contains effect geometry'
        components = actor.get_components_by_class(unreal.DecalComponent)
        assert len(components) == 1, item['actor'] + ' must have one DecalComponent'
        component = components[0]
        assert component.get_editor_property('visible') and not component.get_editor_property('hidden_in_game')
        assert component.get_editor_property('mobility') == unreal.ComponentMobility.MOVABLE
        near(xyz(component.get_editor_property('decal_size')),
             [float(item['projection_depth_cm']) / 2, float(item['radius_cm']), float(item['radius_cm'])],
             .01, item['actor'] + ' decal size')
        assert actor.get_attach_parent_actor() == parent, item['actor'] + ' has wrong parent'
        material = component.get_decal_material()
        assert isinstance(material, unreal.MaterialInstanceConstant) and material.get_path_name() == item['material']
        kind = 'Radar' if item['actor'].endswith('_Radar') else 'Diffusion'
        assert item['type'] == kind and material.get_editor_property('parent') == masters[kind]
        speed = float(unreal.MaterialEditingLibrary.get_material_instance_scalar_parameter_value(material, 'Speed'))
        phase = float(unreal.MaterialEditingLibrary.get_material_instance_scalar_parameter_value(material, 'Phase'))
        tint = unreal.MaterialEditingLibrary.get_material_instance_vector_parameter_value(material, 'Tint')
        rgb = [float(tint.r), float(tint.g), float(tint.b)]
        assert math.isfinite(speed) and speed > 0, item['actor'] + ' has no positive animation speed'
        assert math.isfinite(phase) and all(math.isfinite(value) and value >= 0 for value in rgb) and max(rgb) > 0
        assert rgb[0] > rgb[1] > rgb[2] if item['parent'] == 'DN-1' else rgb[1] > rgb[0] and rgb[1] > rgb[2]
        result['details']['effects'].append(dict(actor=item['actor'], parent=item['parent'], type=kind,
                                                 material=material.get_path_name(), native_decal=True,
                                                 static_mesh_components=0, visible=True, hidden_in_game=False,
                                                 mobility='MOVABLE', decal_size_cm=xyz(component.get_editor_property('decal_size')),
                                                 speed=speed, phase=phase, tint_rgb=rgb))
    for label in LEGACY:
        components = single(label).get_components_by_class(unreal.StaticMeshComponent)
        assert components, 'Legacy actor lost its mesh: ' + label
        for component in components:
            assert not component.get_editor_property('visible'), 'Legacy effect remains visible: ' + label
            assert component.get_editor_property('hidden_in_game'), 'Legacy effect visible in game: ' + label
        result['details']['hidden_legacy'].append(label)
    verify_follow(single('CBD50-1'), [single('FX_CBD50-1_Diffusion'), single('FX_CBD50-1_Radar')])
    result.update(success=True, effect_count=8, robot_count=7, master_material_count=2,
                  disabled_legacy_effect_count=8, connected_time_animation_verified=True,
                  attachment_follow_verified=True, effect_mesh_count=0, level_saved=False)


REPORT.parent.mkdir(parents=True, exist_ok=True)
try:
    main()
except Exception:
    result['error'] = traceback.format_exc()
    REPORT.write_text(json.dumps(result, indent=2), encoding='utf-8')
    raise
else:
    REPORT.write_text(json.dumps(result, indent=2), encoding='utf-8')
    unreal.log('AGV_ANIMATED_FX_VERIFIED ' + json.dumps({key: result[key] for key in
               ['success', 'effect_count', 'robot_count', 'effect_mesh_count', 'attachment_follow_verified']}))
