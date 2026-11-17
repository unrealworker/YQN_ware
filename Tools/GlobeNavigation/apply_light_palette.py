"""Apply the pale atlas palette to M_Earth without loading or saving a level.

Run with UnrealEditor -ExecutePythonScript, or call apply_palette(material)
after creating the original texture nodes in import_globe.py. The helper only
edits the material graph; its caller owns compilation and saving.
"""
import json

import unreal as u


MATERIAL_PATH = '/Game/GlobeNavigation/M_Earth'
COLOR_TEXTURE_PATH = '/Game/GlobeNavigation/T_Earth_BaseColor.T_Earth_BaseColor'
NODE_PREFIX = 'GHS Earth light palette: '
PARAMETER_GROUP = 'Earth palette'
DEFAULTS = {
    'EarthMidtoneExponent': .65,
    'EarthDesaturation': .15,
    'EarthCoolTint': (.94, 1.02, 1.08),
    'EarthAmbientStrength': .65,
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def apply_palette(material):
    """Update only the reviewed colour/emissive paths, reusing named nodes."""
    require(isinstance(material, u.Material), 'Expected an editable earth material')
    ml = u.MaterialEditingLibrary
    expressions = list(ml.get_material_expressions(material))
    samples = [node for node in expressions
               if isinstance(node, u.MaterialExpressionTextureSample)
               and node.get_editor_property('texture')
               and node.get_editor_property('texture').get_path_name() == COLOR_TEXTURE_PATH]
    def marker(role):
        return NODE_PREFIX + role

    # Refuse unfamiliar graph endpoints before changing any node. The original
    # texture sample, normal and roughness paths are retained exactly as authored.
    base_property = u.MaterialProperty.MP_BASE_COLOR
    emissive_property = u.MaterialProperty.MP_EMISSIVE_COLOR
    original_base = ml.get_material_property_input_node(material, base_property)
    if original_base in samples:
        # The existing asset also contains disconnected historical samples.
        # Select the sample that actually supplies the colour output.
        source = original_base
    else:
        require(original_base is not None and
                original_base.get_editor_property('desc') == marker('Tinted colour'),
                'Earth base-colour graph changed; review it before applying the palette')
        lifts = [node for node in expressions
                 if node.get_editor_property('desc') == marker('Midtone lift')]
        require(len(lifts) == 1, 'Missing or duplicate earth midtone node')
        inputs = ml.get_inputs_for_material_expression(material, lifts[0])
        connected_samples = [node for node in inputs if node in samples]
        require(len(connected_samples) == 1, 'Earth midtone source texture changed')
        source = connected_samples[0]
    ambient = ml.get_material_property_input_node(material, emissive_property)
    require(isinstance(ambient, u.MaterialExpressionMultiply),
            'Earth emissive output must be the existing ambient multiply node')
    require(ambient.get_editor_property('desc') in ('', marker('Ambient fill')),
            'Earth emissive graph changed; review it before applying the palette')

    preserved = {}
    for prop in (u.MaterialProperty.MP_NORMAL, u.MaterialProperty.MP_ROUGHNESS):
        preserved[prop] = (ml.get_material_property_input_node(material, prop),
                           ml.get_material_property_input_node_output_name(material, prop))
    require(all(node is not None for node, _ in preserved.values()),
            'Earth normal and roughness must remain connected')

    def node_for(role, expression_class, x, y):
        matches = [node for node in expressions
                   if node.get_editor_property('desc') == marker(role)]
        require(len(matches) <= 1, 'Duplicate earth palette node: ' + role)
        if matches:
            result = matches[0]
            require(isinstance(result, expression_class),
                    'Earth palette node type changed: ' + role)
        else:
            result = ml.create_material_expression(material, expression_class, x, y)
            require(result is not None, 'Could not create earth palette node: ' + role)
            result.set_editor_property('desc', marker(role))
            expressions.append(result)
        return result

    def scalar(name, x, y):
        parameter = node_for(name, u.MaterialExpressionScalarParameter, x, y)
        parameter.set_editor_property('parameter_name', name)
        parameter.set_editor_property('group', PARAMETER_GROUP)
        parameter.set_editor_property('default_value', DEFAULTS[name])
        return parameter

    exponent = scalar('EarthMidtoneExponent', -1150, -350)
    power = node_for('Midtone lift', u.MaterialExpressionPower, -900, -100)
    desaturation = scalar('EarthDesaturation', -900, -350)
    desaturate = node_for('Softened colour', u.MaterialExpressionDesaturation, -650, -100)
    tint = node_for('EarthCoolTint', u.MaterialExpressionVectorParameter, -650, -350)
    tint.set_editor_property('parameter_name', 'EarthCoolTint')
    tint.set_editor_property('group', PARAMETER_GROUP)
    tint.set_editor_property('default_value', u.LinearColor(*DEFAULTS['EarthCoolTint'], 1.))
    tinted = node_for('Tinted colour', u.MaterialExpressionMultiply, -350, -100)
    strength = scalar('EarthAmbientStrength', -350, -350)
    ambient.set_editor_property('desc', marker('Ambient fill'))

    # Power raises dark ocean midtones more than bright terrain. Gentle
    # desaturation and a cool tint match the pale blue UI while retaining relief.
    for a, output_name, b, input_name in (
            (source, 'RGB', power, 'Base'),
            (exponent, '', power, 'Exp'),
            (power, '', desaturate, ''),
            (desaturation, '', desaturate, 'Fraction'),
            (desaturate, '', tinted, 'A'),
            (tint, 'RGB', tinted, 'B'),
            (tinted, '', ambient, 'A'),
            (strength, '', ambient, 'B')):
        require(ml.connect_material_expressions(a, output_name, b, input_name),
                'Could not connect earth palette input: ' + input_name)
    require(ml.connect_material_property(tinted, '', base_property),
            'Could not connect earth palette to base colour')
    require(ml.connect_material_property(ambient, '', emissive_property),
            'Could not connect earth palette to emissive colour')

    for prop, original in preserved.items():
        require((ml.get_material_property_input_node(material, prop),
                 ml.get_material_property_input_node_output_name(material, prop)) == original,
                'Earth normal or roughness connection changed')
    final_expressions = list(ml.get_material_expressions(material))
    palette_nodes = [node for node in final_expressions
                     if node.get_editor_property('desc').startswith(NODE_PREFIX)]
    require(len(palette_nodes) == 8, 'Unexpected earth palette node count')
    return {
        'material': material.get_path_name(),
        'sourceTexture': source.get_editor_property('texture').get_path_name(),
        'parameters': DEFAULTS,
        'paletteNodeCount': len(palette_nodes),
        'materialNodeCount': len(final_expressions),
        'normalAndRoughnessPreserved': True,
        'levelLoadedOrSaved': False,
        'texturesReimported': False,
    }


def main():
    material = u.EditorAssetLibrary.load_asset(MATERIAL_PATH)
    require(material is not None, 'Missing earth material: ' + MATERIAL_PATH)
    report = apply_palette(material)
    u.MaterialEditingLibrary.recompile_material(material)
    require(u.EditorAssetLibrary.save_loaded_asset(material, only_if_is_dirty=False),
            'Failed to save earth palette material')
    u.log('GHS_EARTH_LIGHT_PALETTE ' + json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
