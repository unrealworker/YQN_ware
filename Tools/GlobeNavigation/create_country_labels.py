"""Build the north-up country-label atlas and its Earth-surface decal material.

Run with a Pillow-enabled Python and --atlas-only to regenerate the source PNG.
Then run this script with Unreal Python to import only the texture/material.
Neither mode loads or saves a level. Atlas cell order matches GHSGlobeCountryLabels.cpp.
"""
from pathlib import Path

NAMES = ('加拿大', '美国', '墨西哥', '哥伦比亚', '委内瑞拉', '秘鲁', '巴西',
         '智利', '阿根廷', '中国', '澳大利亚', '印度', '俄罗斯', '南非')


def build_atlas(root):
    from PIL import Image, ImageDraw, ImageFont
    target = root / 'SourceAssets/GlobeNavigation/country-labels-atlas.png'
    font_path = root / 'Content/GHSTwinUI/web/assets/DroidSansFallback.ttf'
    # Four 512x128 cells per row. Transparent gutters keep all generated mips
    # within each label; every glyph has the same physical size before Size scaling.
    image = Image.new('RGBA', (2048, 512), (0, 0, 0, 0))
    font = ImageFont.truetype(str(font_path), 88)
    draw = ImageDraw.Draw(image)
    for index, name in enumerate(NAMES):
        bounds = draw.textbbox((0, 0), name, font=font, stroke_width=6)
        x = (index % 4) * 512 + (512 - bounds[2] + bounds[0]) / 2 - bounds[0]
        y = (index // 4) * 128 + (128 - bounds[3] + bounds[1]) / 2 - bounds[1]
        draw.text((x, y), name, font=font, fill=(8, 34, 77, 255), stroke_width=6, stroke_fill=(255, 255, 255, 255))
    image.save(target)
    print('Country label atlas:', target)


def import_assets(u):
    root = Path(u.Paths.project_dir()).resolve()
    source = root / 'SourceAssets/GlobeNavigation/country-labels-atlas.png'
    if not source.is_file():
        raise RuntimeError('Generate the country label atlas first with --atlas-only')
    assets = u.EditorAssetLibrary
    tools = u.AssetToolsHelpers.get_asset_tools()
    ml = u.MaterialEditingLibrary
    texture_dir = '/Game/GlobeNavigation/Textures'
    material_dir = '/Game/GlobeNavigation/Materials'
    assets.make_directory(texture_dir)
    assets.make_directory(material_dir)
    task = u.AssetImportTask()
    task.filename = str(source)
    task.destination_path = texture_dir
    task.destination_name = 'T_CountryLabels'
    task.automated = True
    task.replace_existing = True
    task.save = True
    tools.import_asset_tasks([task])
    texture = assets.load_asset(texture_dir + '/T_CountryLabels')
    if not isinstance(texture, u.Texture2D):
        raise RuntimeError('Could not import country label atlas')
    texture.set_editor_property('srgb', True)
    texture.set_editor_property('compression_settings', u.TextureCompressionSettings.TC_EDITOR_ICON)
    texture.set_editor_property('mip_gen_settings', u.TextureMipGenSettings.TMGS_SIMPLE_AVERAGE)
    texture.set_editor_property('address_x', u.TextureAddress.TA_CLAMP)
    texture.set_editor_property('address_y', u.TextureAddress.TA_CLAMP)
    texture.set_editor_property('max_texture_size', 2048)
    assets.save_loaded_asset(texture)

    material_path = material_dir + '/M_CountrySurfaceLabel'
    material = assets.load_asset(material_path) if assets.does_asset_exist(material_path) else None
    if material is None:
        material = tools.create_asset('M_CountrySurfaceLabel', material_dir, u.Material, u.MaterialFactoryNew())
    if not isinstance(material, u.Material):
        raise RuntimeError('Expected country surface-label material')
    ml.delete_all_material_expressions(material)
    material.set_editor_property('material_domain', u.MaterialDomain.MD_DEFERRED_DECAL)
    material.set_editor_property('blend_mode', u.BlendMode.BLEND_TRANSLUCENT)
    material.set_editor_property('shading_model', u.MaterialShadingModel.MSM_UNLIT)
    uv = ml.create_material_expression(material, u.MaterialExpressionTextureCoordinate, -800, 0)
    rect = ml.create_material_expression(material, u.MaterialExpressionVectorParameter, -800, 160)
    rect.set_editor_property('parameter_name', 'AtlasRect')
    rect.set_editor_property('default_value', u.LinearColor(.25, .25, 0, 0))
    transform = ml.create_material_expression(material, u.MaterialExpressionCustom, -550, 0)
    transform.set_editor_property('output_type', u.CustomMaterialOutputType.CMOT_FLOAT2)
    inputs = []
    for name in ('UV', 'Rect'):
        item = u.CustomInput()
        item.set_editor_property('input_name', name)
        inputs.append(item)
    transform.set_editor_property('inputs', inputs)
    transform.set_editor_property('code', 'return UV * Rect.xy + Rect.zw;')
    assert ml.connect_material_expressions(uv, '', transform, 'UV')
    # MaterialEditingLibrary exposes the vector parameter's RGB/A pins even on
    # engine builds whose reflection does not expose its combined RGBA output.
    rect_rgba = ml.create_material_expression(material, u.MaterialExpressionAppendVector, -680, 180)
    assert ml.connect_material_expressions(rect, 'RGB', rect_rgba, 'A')
    assert ml.connect_material_expressions(rect, 'A', rect_rgba, 'B')
    assert ml.connect_material_expressions(rect_rgba, '', transform, 'Rect')
    sample = ml.create_material_expression(material, u.MaterialExpressionTextureSample, -300, 0)
    sample.texture = texture
    sample.sampler_type = u.MaterialSamplerType.SAMPLERTYPE_COLOR
    assert ml.connect_material_expressions(transform, '', sample, 'UVs')
    assert ml.connect_material_property(sample, 'RGB', u.MaterialProperty.MP_BASE_COLOR)
    assert ml.connect_material_property(sample, 'A', u.MaterialProperty.MP_OPACITY)
    ambient = ml.create_material_expression(material, u.MaterialExpressionMultiply, -80, 240)
    ambient.set_editor_property('const_b', .12)
    assert ml.connect_material_expressions(sample, 'RGB', ambient, 'A')
    assert ml.connect_material_property(ambient, '', u.MaterialProperty.MP_EMISSIVE_COLOR)
    ml.layout_material_expressions(material)
    ml.recompile_material(material)
    if not assets.save_loaded_asset(material):
        raise RuntimeError('Could not save country surface-label material')
    u.log('GHS_COUNTRY_SURFACE_LABELS_CREATED ' + material.get_path_name())


try:
    import unreal as _unreal
except ImportError:
    import sys
    if '--atlas-only' not in sys.argv:
        raise SystemExit('Use --atlas-only outside Unreal, then run the script in Unreal to import assets')
    build_atlas(Path(__file__).resolve().parents[2])
else:
    import_assets(_unreal)
