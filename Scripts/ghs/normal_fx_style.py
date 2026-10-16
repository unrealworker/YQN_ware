"""Update the private normal-scene FX parameters without replacing animation."""
import unreal


def connected_nodes(material):
    ml=unreal.MaterialEditingLibrary
    pending=[ml.get_material_property_input_node(material,p) for p in
             [unreal.MaterialProperty.MP_BASE_COLOR,unreal.MaterialProperty.MP_EMISSIVE_COLOR,unreal.MaterialProperty.MP_OPACITY]]
    seen=set();result=[]
    while pending:
        node=pending.pop()
        if node is None or node.get_path_name() in seen:continue
        seen.add(node.get_path_name());result.append(node)
        pending.extend(n for n in ml.get_inputs_for_material_expression(material,node) if n)
    return result


def update_master(material,style):
    assert material.get_path_name().startswith('/Game/GHSNormalWarehouse/FX/')
    values={'OpacityScale':style['fx_opacity_scale'],'EmissionScale':style['fx_emissive_scale']}
    found=set()
    for node in connected_nodes(material):
        if isinstance(node,unreal.MaterialExpressionScalarParameter):
            name=str(node.get_editor_property('parameter_name'))
            if name in values:
                node.set_editor_property('default_value',float(values[name]));found.add(name)
    assert found==set(values),found
    unreal.MaterialEditingLibrary.recompile_material(material)
    for name,value in values.items():
        assert abs(unreal.MaterialEditingLibrary.get_material_default_scalar_parameter_value(material,name)-value)<1e-5

