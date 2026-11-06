"""Create only the globe's surface-glow decal material; never load or save a level.

Run with Unreal Python. The material is included by the existing
/Game/GlobeNavigation cook directory. Re-running regenerates this generated asset.
"""
import unreal as u

DEST = '/Game/GlobeNavigation/Materials'
NAME = 'M_WarehouseSurfaceGlow'
assets = u.EditorAssetLibrary
ml = u.MaterialEditingLibrary
assets.make_directory(DEST)
material = assets.load_asset(DEST + '/' + NAME)
if material is None:
    material = u.AssetToolsHelpers.get_asset_tools().create_asset(NAME, DEST, u.Material, u.MaterialFactoryNew())
if not isinstance(material, u.Material):
    raise RuntimeError('Expected a Material at ' + DEST + '/' + NAME)
ml.delete_all_material_expressions(material)
material.set_editor_property('material_domain', u.MaterialDomain.MD_DEFERRED_DECAL)
material.set_editor_property('blend_mode', u.BlendMode.BLEND_TRANSLUCENT)
material.set_editor_property('shading_model', u.MaterialShadingModel.MSM_UNLIT)

uv = ml.create_material_expression(material, u.MaterialExpressionTextureCoordinate, -600, -120)
tint = ml.create_material_expression(material, u.MaterialExpressionDecalColor, -600, 100)
profile = ml.create_material_expression(material, u.MaterialExpressionCustom, -300, -100)
profile.set_editor_property('description', 'Surface-locked warehouse core, ring and soft halo')
profile.set_editor_property('output_type', u.CustomMaterialOutputType.CMOT_FLOAT3)
custom_inputs = []
for input_name in ('UV', 'Tint'):
    custom_input = u.CustomInput()
    custom_input.set_editor_property('input_name', input_name)
    custom_inputs.append(custom_input)
profile.set_editor_property('inputs', custom_inputs)
profile.set_editor_property('code', '''
float radius = length((UV - 0.5) * 2.0);
float core = 1.0 - smoothstep(0.18, 0.26, radius);
float ring = 1.0 - smoothstep(0.025, 0.06, abs(radius - 0.40));
float halo = pow(saturate(1.0 - radius), 3.0);
return Tint * (core * 3.5 + ring * 1.8 + halo * 0.65)
    + float3(0.35, 0.5, 0.75) * core;
''')
assert ml.connect_material_expressions(uv, '', profile, 'UV')
assert ml.connect_material_expressions(tint, 'RGB', profile, 'Tint')
assert ml.connect_material_property(profile, '', u.MaterialProperty.MP_EMISSIVE_COLOR)
# Emissive-only decals are additive. Outside the circular profile emissive is
# zero; leave base color / normal / roughness unconnected to preserve the map.
opacity = ml.create_material_expression(material, u.MaterialExpressionConstant, -300, 180)
opacity.set_editor_property('r', 1.0)
assert ml.connect_material_property(opacity, '', u.MaterialProperty.MP_OPACITY)
ml.layout_material_expressions(material)
ml.recompile_material(material)
if not assets.save_loaded_asset(material):
    raise RuntimeError('Could not save warehouse surface-glow material')
u.log('GHS_WAREHOUSE_SURFACE_GLOW_CREATED ' + material.get_path_name())
