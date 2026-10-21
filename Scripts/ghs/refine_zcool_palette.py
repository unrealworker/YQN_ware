"""Match the Zcool scene's ground labels and animated decals to its rack blue.

Call apply_palette(by_label) from an editor-side scene transaction. This helper
saves only private Zcool material instances; the caller owns map save/rollback.
"""
import math

import unreal


MAP = '/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
ROOT = '/Game/GHSZcoolSmartFactory/'
COBALT = ROOT + 'Materials/M_Zcool_Cobalt.M_Zcool_Cobalt'
LABELS = ('GHS_SiteTitle', 'GHS_RackZone', 'GHS_PalletZone')
PRESERVED_SCALARS = ('Speed', 'Phase', 'OpacityScale', 'EmissionScale')


def _rgba(color):
    return [float(color.r), float(color.g), float(color.b), float(color.a)]


def _path(obj):
    return obj.get_path_name() if obj else None


def _fx_state(material):
    library = unreal.MaterialEditingLibrary
    return dict(parent=_path(material.get_editor_property('parent')),
                tint=_rgba(library.get_material_instance_vector_parameter_value(material, 'Tint')),
                scalars={name: float(library.get_material_instance_scalar_parameter_value(material, name))
                         for name in PRESERVED_SCALARS})


def apply_palette(by):
    """Apply the current rack tint after checking all targets; do not save the map."""
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    assert world and world.get_path_name().split('.')[0] == MAP, 'Palette changes require the Zcool map'
    library = unreal.MaterialEditingLibrary
    assets = unreal.EditorAssetLibrary

    # Read the material actually used by the rack actors, so later palette edits
    # are inherited rather than overwritten by an old hard-coded color.
    rack_materials = {}
    for label, actor in by.items():
        if not label.startswith('GHS_V2_Rack_'):
            continue
        for component in actor.get_components_by_class(unreal.StaticMeshComponent):
            for index in range(component.get_num_materials()):
                material = component.get_material(index)
                if _path(material) == COBALT:
                    rack_materials[COBALT] = material
    assert COBALT in rack_materials, 'No rack component uses the expected private Cobalt material'
    source = rack_materials[COBALT]
    assert isinstance(source, unreal.Material), COBALT
    tint = library.get_material_default_vector_parameter_value(source, 'SurfaceTint')
    rgb = _rgba(tint)[:3]
    assert all(math.isfinite(v) and 0 <= v <= 1 for v in rgb), rgb
    assert rgb[2] > max(rgb[:2]), 'Rack SurfaceTint is not the expected blue palette'

    # TextRenderComponent sends FColor straight to an UNORM vertex color buffer.
    # It is already interpreted as linear in the material; sRGB encoding here
    # would make the ground text pale again. Keep keyword fields (UE uses BGRA).
    byte_rgb = [int(math.floor(v * 255 + .5)) for v in rgb]
    text_color = unreal.Color(r=byte_rgb[0], g=byte_rgb[1], b=byte_rgb[2], a=255)
    labels = []
    for label in LABELS:
        assert label in by, 'Missing ground label: ' + label
        component = by[label].get_component_by_class(unreal.TextRenderComponent)
        assert component, 'Missing TextRenderComponent: ' + label
        labels.append((label, component, dict(
            color=[int(v) for v in _rgba(component.get_editor_property('text_render_color'))],
            material=_path(component.get_material(0)))))

    # Deduplicate actual live references: AGV and stacker decals may intentionally
    # share one MIC. No source-map material or master shader is changed.
    effects = {}
    for label, actor in by.items():
        for component in actor.get_components_by_class(unreal.DecalComponent):
            material = component.get_decal_material()
            path = _path(material)
            if label.startswith(('FX_GHS_AGV_', 'FX_GHN_FloorStacker_')):
                assert path and path.startswith(ROOT + 'FX/'), ('Unexpected shared FX material', label, path)
            if not path or not path.startswith(ROOT + 'FX/'):
                continue
            assert isinstance(material, unreal.MaterialInstanceConstant), path
            if path not in effects:
                before = _fx_state(material)
                assert before['parent'] and before['parent'].startswith(ROOT + 'FX/'), before
                effects[path] = dict(material=material, before=before, actors=[])
            effects[path]['actors'].append(label)
    assert effects, 'No private Zcool FX instances were found'

    report = dict(map=MAP, source_material=COBALT, source_parameter='SurfaceTint',
                  tint_linear=rgb, text_color_bytes=byte_rgb + [255],
                  text_quantization_error=max(abs(v - b / 255) for v, b in zip(rgb, byte_rgb)),
                  labels=[], fx=[], map_saved=False)
    for label, component, before in labels:
        component.set_text_render_color(text_color)
        after = [int(v) for v in _rgba(component.get_editor_property('text_render_color'))]
        assert after == byte_rgb + [255], (label, after)
        assert _path(component.get_material(0)) == before['material'], label
        report['labels'].append(dict(actor=label, before=before, after_color=after))

    target = unreal.LinearColor(r=rgb[0], g=rgb[1], b=rgb[2], a=1.0)
    for path, record in sorted(effects.items()):
        material, before = record['material'], record['before']
        library.set_material_instance_vector_parameter_value(material, 'Tint', target)
        library.update_material_instance(material)
        after = _fx_state(material)
        assert max(abs(a - b) for a, b in zip(after['tint'], rgb + [1.0])) < 1e-6, (path, after)
        assert after['parent'] == before['parent'] and after['scalars'] == before['scalars'], path
        assert assets.save_loaded_asset(material, only_if_is_dirty=False), path
        report['fx'].append(dict(material=path, actors=sorted(record['actors']), before=before, after=after))
    report.update(success=True, private_materials_saved=len(effects),
                  decal_components=sum(len(record['actors']) for record in effects.values()),
                  animation_parameters_preserved=True)
    return report
