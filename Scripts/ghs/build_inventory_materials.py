"""Create inventory mask variants; never modify source materials or maps.

Run through UE5.8 PythonScript commandlet. The runtime fills four 18-bit words
once per instance. Unknown slots retain the authored capacity preview mask.
"""
import hashlib
import json
from pathlib import Path
import unreal

ROOT = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
SOURCE = '/Game/GHSZcoolSmartFactory/StorageCapacity/Materials'
DEST = '/Game/GHSZcoolSmartFactory/Inventory/Materials'
LIB = unreal.EditorAssetLibrary
ML = unreal.MaterialEditingLibrary
OWNER = 'ghs-real-inventory-20261125-v1'
MASK_CODE = '''float slot = floor(LocalSlot.x + 0.5);
if (slot < -0.5) return 1.0;
if (slot >= 36.0) return PreviousMask;
float bit = exp2(fmod(slot, 18.0));
// Perspective interpolation can move a constant packed integer just below its
// exact value. Restore the integer before bit decoding, otherwise floor() flips
// low bits per pixel and makes fully opaque boxes look like noisy transparency.
float known = floor((slot < 18.0 ? KnownLow : KnownHigh) + 0.5);
float occupied = floor((slot < 18.0 ? OccupiedLow : OccupiedHigh) + 0.5);
if (fmod(floor(known / bit), 2.0) < 0.5) return PreviousMask;
return fmod(floor(occupied / bit), 2.0);'''


def asset_file(package):
    return ROOT / 'Content' / (package.removeprefix('/Game/') + '.uasset')


def node(material, cls, **values):
    obj = ML.create_material_expression(material, cls)
    for key, value in values.items():
        obj.set_editor_property(key, value)
    return obj


def connect(source, destination, name):
    assert ML.connect_material_expressions(source, '', destination, name), name


def main():
    materials = {}
    for path in sorted(LIB.list_assets(SOURCE, recursive=False, include_folder=False)):
        source = LIB.load_asset(path)
        if not isinstance(source, unreal.Material):
            continue
        package = source.get_path_name().split('.')[0]
        before = hashlib.sha256(asset_file(package).read_bytes()).hexdigest()
        name = source.get_name().replace('M_Capacity_', 'M_Inventory_', 1)
        target = DEST + '/' + name
        if LIB.does_asset_exist(target):
            material = LIB.load_asset(target)
            assert LIB.get_metadata_tag(material, 'GHS.Inventory.Owner') == OWNER
            assert LIB.get_metadata_tag(material, 'GHS.Inventory.SourceHash') == before
        else:
            material = LIB.duplicate_asset(package, target)
            old_mask = ML.get_material_property_input_node(material, unreal.MaterialProperty.MP_OPACITY_MASK)
            assert old_mask, ('Missing original opacity mask', path)
            local = node(material, unreal.MaterialExpressionTextureCoordinate, coordinate_index=1) if '_Rack_' in name else node(material, unreal.MaterialExpressionConstant, r=0.)
            inputs = []
            for input_name in ('PreviousMask', 'LocalSlot', 'OccupiedLow', 'OccupiedHigh', 'KnownLow', 'KnownHigh'):
                entry = unreal.CustomInput()
                entry.set_editor_property('input_name', input_name)
                inputs.append(entry)
            mask = node(material, unreal.MaterialExpressionCustom, inputs=inputs,
                        output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT1,
                        description='Inventory occupancy: integer-restored 18-bit words; unknown keeps preview',
                        code=MASK_CODE)
            connect(old_mask, mask, 'PreviousMask')
            connect(local, mask, 'LocalSlot')
            for index, pin in enumerate(('OccupiedLow', 'OccupiedHigh', 'KnownLow', 'KnownHigh'), 1):
                custom = node(material, unreal.MaterialExpressionPerInstanceCustomData, data_index=index, const_default_value=0.)
                interp = node(material, unreal.MaterialExpressionVertexInterpolator)
                connect(custom, interp, 'VS')
                connect(interp, mask, pin)
            assert ML.connect_material_property(mask, '', unreal.MaterialProperty.MP_OPACITY_MASK)
            ML.recompile_material(material)
            LIB.set_metadata_tag(material, 'GHS.Inventory.Owner', OWNER)
            LIB.set_metadata_tag(material, 'GHS.Inventory.SourceHash', before)
            LIB.set_metadata_tag(material, 'GHS.Inventory.Source', source.get_path_name())
            assert LIB.save_loaded_asset(material, only_if_is_dirty=False)
        masks = [expression for expression in unreal.ObjectIterator(unreal.MaterialExpressionCustom)
                 if expression.get_outer() == material
                 and 'KnownLow' in expression.get_editor_property('code')]
        assert len(masks) == 1, ('Inventory mask expression must be unique', target, len(masks))
        masks[0].set_editor_property('code', MASK_CODE)
        masks[0].set_editor_property('description', 'Inventory occupancy: integer-restored 18-bit words; unknown keeps preview')
        ML.recompile_material(material)
        assert LIB.save_loaded_asset(material, only_if_is_dirty=False)
        if 'InventoryMaskVersion' not in [str(v) for v in ML.get_scalar_parameter_names(material)]:
            current_mask = ML.get_material_property_input_node(material, unreal.MaterialProperty.MP_OPACITY_MASK)
            version = node(material, unreal.MaterialExpressionScalarParameter, parameter_name='InventoryMaskVersion', default_value=1.)
            multiply = node(material, unreal.MaterialExpressionMultiply)
            connect(current_mask, multiply, 'A')
            connect(version, multiply, 'B')
            assert ML.connect_material_property(multiply, '', unreal.MaterialProperty.MP_OPACITY_MASK)
            ML.recompile_material(material)
            assert LIB.save_loaded_asset(material, only_if_is_dirty=False)
        assert hashlib.sha256(asset_file(package).read_bytes()).hexdigest() == before
        materials[source.get_path_name()] = material.get_path_name()
    assert len(materials) == 7, len(materials)
    output = ROOT / 'Content/GHSTwinUI/data/inventory-materials.json'
    output.write_text(json.dumps(dict(schemaVersion=1, owner=OWNER, materials=materials), ensure_ascii=False, indent=2), encoding='utf8')
    unreal.log('GHS_INVENTORY_MATERIALS_SUCCESS ' + str(len(materials)))


main()
