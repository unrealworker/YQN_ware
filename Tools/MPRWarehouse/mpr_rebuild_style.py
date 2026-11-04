"""Explicit, repeatable material and lighting style for the independent MPR map.

Pure Python: no file access and no Unreal/Blender imports. Colour specifications
are sRGB swatches; every engine parameter emitted here is scene-linear RGB.
Retained warehouse materials are overridden through new-namespace clones only.
"""
from copy import deepcopy


def srgb_hex_to_linear(value):
    """Convert a six-digit sRGB swatch using the IEC 61966-2-1 transfer curve."""
    value = value.lstrip('#')
    if len(value) != 6:
        raise ValueError('Expected a six-digit sRGB colour')
    channels = [int(value[index:index+2], 16)/255. for index in (0, 2, 4)]
    return [channel/12.92 if channel <= .04045 else ((channel+.055)/1.055)**2.4
            for channel in channels]


_RETAINED = {
    'MPR4_RoofMembrane': ('DDE3E8', .74, .025),
    'MPR4_FacadeWhite': ('D1D7DB', .78, .025),
    'MPR4_IndustrialBlue': ('174C78', .52, .025),
    'MPR4_SolarCells': ('153A60', .35, .015),
    'MPR4_SolarMid': ('153A60', .35, 0.),
    'MPR4_SolarFar': ('153A60', .35, 0.),
}


def _material(materials, role, swatch, roughness, normal_strength=None):
    spec = materials.setdefault(role, {})
    linear = srgb_hex_to_linear(swatch)
    spec.update(base_color=linear, roughness=roughness, metallic=0., specular=.5,
                emission=0., source_srgb_hex='#'+swatch.upper(),
                color_space='linear RGB tint converted from IEC sRGB; existing textures preserved')
    if 'color' in spec:
        # The retained-material importer prefers `color` over `base_color`.
        spec['color'] = list(linear)
    if normal_strength is not None:
        spec['normal_strength'] = normal_strength


def _merge_lighting(existing, additions):
    """Replace explicit fields, preserving unrelated reviewed lighting settings."""
    rows = deepcopy(existing)
    by_key = {(row['actor_label'], row.get('component_name'), row['property']): index
              for index, row in enumerate(rows)}
    if len(by_key) != len(rows):
        raise ValueError('Duplicate lighting override identity')
    for addition in additions:
        key = addition['actor_label'], addition.get('component_name'), addition['property']
        if key not in by_key:
            by_key[key] = len(rows)
            rows.append(deepcopy(addition))
        else:
            index = by_key[key]
            old = rows[index].get('value')
            if addition['property'] == 'settings' and isinstance(old, dict):
                row = deepcopy(addition)
                row['value'] = {**old, **row['value']}
                rows[index] = row
            else:
                rows[index] = deepcopy(addition)
    return rows


def _lighting():
    settings = {
        # Config/DefaultEngine.ini enables extended luminance range. Therefore
        # these legacy API field names represent EV100, not luminance values.
        'override_auto_exposure_method': True,
        'auto_exposure_method': {'enum': 'AutoExposureMethod.AEM_HISTOGRAM'},
        'override_auto_exposure_min_brightness': True,
        'override_auto_exposure_max_brightness': True,
        'auto_exposure_min_brightness': .3,
        'auto_exposure_max_brightness': .3,
        'override_auto_exposure_bias': True,
        'auto_exposure_bias': 0.,
        'override_bloom_intensity': True,
        'bloom_intensity': 0.,
        'override_color_grading_intensity': True,
        'color_grading_intensity': 0.,
        'override_color_grading_lut': True,
        'color_grading_lut': None,
        'override_local_exposure_highlight_contrast_scale': True,
        'local_exposure_highlight_contrast_scale': 1.,
        'override_local_exposure_shadow_contrast_scale': True,
        'local_exposure_shadow_contrast_scale': 1.,
        'override_local_exposure_detail_strength': True,
        'local_exposure_detail_strength': 1.,
        'override_local_exposure_middle_grey_bias': True,
        'local_exposure_middle_grey_bias': 0.,
        # Typed enum tokens must be resolved by the Unreal importer. They are
        # deliberately not numeric constants whose meaning may change.
        'override_dynamic_global_illumination_method': True,
        'dynamic_global_illumination_method': {'enum': 'DynamicGlobalIlluminationMethod.LUMEN'},
        'override_reflection_method': True,
        'reflection_method': {'enum': 'ReflectionMethod.LUMEN'},
        'override_lumen_scene_view_distance': True,
        'lumen_scene_view_distance': 200000.,
        'override_lumen_scene_detail': True,
        'lumen_scene_detail': 4.,
        'override_lumen_max_trace_distance': True,
        'lumen_max_trace_distance': 100000.,
    }
    for name in ('color_saturation', 'color_contrast', 'color_gamma', 'color_gain', 'color_offset'):
        for region in ('', '_shadows', '_midtones', '_highlights'):
            settings['override_'+name+region] = False
    for name in ('white_temp', 'white_tint', 'scene_color_tint', 'film_slope', 'film_toe',
                 'film_shoulder', 'film_black_clip', 'film_white_clip'):
        settings['override_'+name] = False
    lights = []
    for label, component, values in (
        ('MPR4_KeyLight', 'LightComponent0', {
            'intensity': 3.8, 'light_source_angle': 3.,
            'light_color': [255, 255, 255, 255], 'use_temperature': False,
            'indirect_lighting_intensity': 1., 'cast_shadows': True}),
        ('MPR4_Ambient', 'SkyLightComponent0', {
            'intensity': 1., 'light_color': [255, 255, 255, 255],
            'cast_shadows': True}),
    ):
        lights.extend(dict(actor_label=label, component_name=component, property=key, value=value)
                      for key, value in values.items())
    lights.append(dict(actor_label='MPR4_ReferenceStyle', property='settings', value=settings))
    return lights


def apply_style(manifest):
    """Update and return *manifest*; safe to call both before and after export.

    Existing texture paths, texture blends, UV periods and parent metadata stay
    intact. `retained_material_overrides` is a declarative request to clone each
    original warehouse MI and override its slots only in the independent map.
    """
    materials = manifest.setdefault('materials', {})
    for role in ('MPRR_ContextWall', 'MPRR_ContextRoof'):
        _material(materials, role, 'B9BEC5', .88, 0.)
    for role in ('MPR3_Concrete', 'MPR4_TerminalCurb'):
        _material(materials, role, 'B7BAB8', .88, .025)
    for role in ('MPR3_Asphalt', 'MPR4_TerminalAsphalt'):
        _material(materials, role, '7F8891', .90, .035)
    _material(materials, 'MPR3_Grass', 'AEBBA3', .98, .02)
    for role, swatch in (('MPRR_LeafMid', '94A58B'), ('MPRR_LeafLight', 'A4B29B'),
                         ('MPRR_LeafShade', '84977A')):
        _material(materials, role, swatch, .82, 0.)
        materials[role]['two_sided'] = True
    for role, (swatch, roughness, normal) in _RETAINED.items():
        _material(materials, role, swatch, roughness, normal)
        materials[role]['color'] = list(materials[role]['base_color'])
    for role, luminance in [('MPR4_SolarCells',.03639439175161885),
                            ('MPR4_SolarMid',.06304834068066972),
                            ('MPR4_SolarFar',.06401825442443115)]:
        materials[role]['albedo_luminance_reference']=luminance
        materials[role]['solar_surface']=True
    for spec in materials.values():
        if spec.get('vertex_color_fade'):
            spec['vertex_color_fade']['ground_base_color'] = list(materials['MPR3_Grass']['base_color'])
            spec['vertex_color_fade']['ground_roughness'] = materials['MPR3_Grass']['roughness']
    manifest['retained_material_overrides'] = [
        dict(source='/Game/MPRWarehouse/ReferenceV4/Materials/MI_'+role, role=role)
        for role in _RETAINED]
    manifest['lighting_overrides'] = _merge_lighting(manifest.get('lighting_overrides', []), _lighting())
    manifest['style_contract'] = dict(
        version=1, colour_input='sRGB hex', colour_output='linear RGB',
        transfer_function='IEC 61966-2-1', original_assets_modified=False,
        retained_material_policy='Clone original MI parent chain and textures into new namespace',
        exposure_units='EV100', requires_extended_luminance_range=True,
        locked_ev100=.3, exposure_bias=0., directional_light_lux=3.8,
        sky_source='Existing neutral GrayLightTextureCube preserved',
        lumen_policy='Enable GI/reflections; measure actual runtime before judging performance',
        reference_srgb=dict(context='B9BEC5', concrete='B7BAB8', asphalt='7F8891', grass='AEBBA3',
                            leaf='94A58B', roof='DDE3E8', facade='D1D7DB', blue='174C78', solar='153A60'))
    manifest['render_profile'] = dict(lumen_clipmap_extent=5000.)
    return manifest
