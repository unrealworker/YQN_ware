"""New-namespace material graphs for the independent MPR rebuild.

This module imports no editor and performs no work on import. The caller owns
the Unreal session, the instance clones, and the destination-only save policy.
"""


def make_solar_parent(u, core, dest, save_new, source_material=None):
    """Create and return a solar parent; never rebuild any existing material.

    Cache the returned parent and assign it to the three cloned solar MIs. Read
    each original MI's effective ``Albedo``/``Normal`` textures *before* changing
    its clone's parent, then explicitly copy those texture overrides onto that
    clone. Set ``AlbedoLuminanceReference`` to the original PNG's mean luminance
    after sRGB decoding; the shader texture sampler likewise outputs linear RGB.

    ``core`` supplies LIB, TOOLS, MATLIB, USAGE and load, as in the existing MPR
    importer. ``save_new`` must reject saves outside the destination namespace.
    """
    dest = dest.rstrip('/')
    if not dest.startswith('/Game/MPRWarehouse/Rebuild') or '..' in dest:
        raise ValueError('Solar parent must use the independent MPR rebuild namespace')
    name = 'M_MPRR_SolarSurface'
    folder = dest+'/Materials'
    path = folder+'/'+name
    if core.LIB.does_asset_exist(path):
        raise RuntimeError('Refusing to edit an existing solar parent: '+path)
    if source_material is None:
        source_material = core.load('/Game/MPRWarehouse/ReferenceV4/Materials/MI_MPR4_SolarCells')
    if source_material is None:
        raise RuntimeError('A read-only source solar MI is required for valid texture defaults')
    ml = core.MATLIB
    albedo_texture = ml.get_material_instance_texture_parameter_value(source_material, 'Albedo')
    normal_texture = ml.get_material_instance_texture_parameter_value(source_material, 'Normal')
    if albedo_texture is None:
        albedo_texture = core.load('/Engine/EngineResources/DefaultTexture')
    if albedo_texture is None or normal_texture is None:
        raise RuntimeError('Solar texture defaults are incomplete; refusing a colour texture as a normal map')
    material = core.TOOLS.create_asset(name, folder, u.Material, u.MaterialFactoryNew())
    if material is None:
        raise RuntimeError('Could not create '+path)
    if material.get_path_name().split('.')[0] != path:
        raise RuntimeError('Created solar parent outside its requested package')

    def expression(klass, **props):
        node = ml.create_material_expression(material, klass)
        if node is None:
            raise RuntimeError('Could not create solar expression '+str(klass))
        for key, value in props.items():
            node.set_editor_property(key, value)
        return node

    def connect(source, output, target, input_name):
        if not ml.connect_material_expressions(source, output, target, input_name):
            raise RuntimeError('Solar expression connection failed: '+str(input_name))

    def property_input(node, prop, output=''):
        if not ml.connect_material_property(node, output, prop):
            raise RuntimeError('Solar material property connection failed: '+str(prop))

    def scalar(name, value):
        return expression(u.MaterialExpressionScalarParameter, parameter_name=name, default_value=value)

    def constant(value):
        return expression(u.MaterialExpressionConstant, r=value)

    material.set_editor_property('blend_mode', u.BlendMode.BLEND_OPAQUE)
    material.set_editor_property('shading_model', u.MaterialShadingModel.MSM_DEFAULT_LIT)
    tint = expression(u.MaterialExpressionVectorParameter, parameter_name='Tint',
                      default_value=u.LinearColor(.007499032043226175, .042311410620809675,
                                                  .11697066775851084, 1.))
    albedo = expression(u.MaterialExpressionTextureSampleParameter2D,
                        parameter_name='Albedo', texture=albedo_texture)
    weights = expression(u.MaterialExpressionConstant3Vector,
                         constant=u.LinearColor(.2126, .7152, .0722, 1.))
    luminance = expression(u.MaterialExpressionDotProduct)
    connect(albedo, 'RGB', luminance, 'A')
    connect(weights, '', luminance, 'B')
    reference = scalar('AlbedoLuminanceReference', .05)
    safe_reference = expression(u.MaterialExpressionMax)
    connect(reference, '', safe_reference, 'A')
    connect(constant(.0001), '', safe_reference, 'B')
    normalized = expression(u.MaterialExpressionDivide)
    connect(luminance, '', normalized, 'A')
    connect(safe_reference, '', normalized, 'B')
    detail = expression(u.MaterialExpressionClamp, min_default=.65, max_default=1.25)
    # UE 5.8 GetShortenPinName maps "Input" to NAME_None; the editing library
    # selects expression input 0 when its input name is empty.
    connect(normalized, '', detail, '')
    base_color = expression(u.MaterialExpressionMultiply)
    connect(detail, '', base_color, 'A')
    connect(tint, 'RGB', base_color, 'B')
    property_input(base_color, u.MaterialProperty.MP_BASE_COLOR)

    # The same filtered low-amplitude luminance gives a restrained variation;
    # no extra procedural/high-frequency noise is introduced.
    centered = expression(u.MaterialExpressionSubtract)
    connect(detail, '', centered, 'A')
    connect(constant(1.), '', centered, 'B')
    variation = expression(u.MaterialExpressionMultiply)
    connect(centered, '', variation, 'A')
    connect(constant(.035), '', variation, 'B')
    roughness = expression(u.MaterialExpressionAdd)
    connect(scalar('Roughness', .35), '', roughness, 'A')
    connect(variation, '', roughness, 'B')
    bounded_roughness = expression(u.MaterialExpressionClamp, min_default=.25, max_default=.45)
    connect(roughness, '', bounded_roughness, '')
    property_input(bounded_roughness, u.MaterialProperty.MP_ROUGHNESS)

    flat = expression(u.MaterialExpressionConstant3Vector, constant=u.LinearColor(0., 0., 1., 1.))
    normal = expression(u.MaterialExpressionTextureSampleParameter2D, parameter_name='Normal',
                        texture=normal_texture, sampler_type=u.MaterialSamplerType.SAMPLERTYPE_NORMAL)
    normal_lerp = expression(u.MaterialExpressionLinearInterpolate)
    connect(flat, '', normal_lerp, 'A')
    connect(normal, 'RGB', normal_lerp, 'B')
    connect(scalar('NormalStrength', .015), '', normal_lerp, 'Alpha')
    property_input(normal_lerp, u.MaterialProperty.MP_NORMAL)
    for parameter, default, prop in (
        ('Metallic', 0., u.MaterialProperty.MP_METALLIC),
        ('Specular', .5, u.MaterialProperty.MP_SPECULAR),
        ('Emission', 0., u.MaterialProperty.MP_EMISSIVE_COLOR),
    ):
        property_input(scalar(parameter, default), prop)
    ml.set_material_usage(material, core.USAGE)
    material.set_editor_property('used_with_nanite', True)
    ml.recompile_material(material)
    save_new(material)
    return material
