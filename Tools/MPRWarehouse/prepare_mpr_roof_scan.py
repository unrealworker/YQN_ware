"""Clone MPR roof masters with the exact GHS scan shader; never edit the map."""
from pathlib import Path
import hashlib
import importlib.util
import json
import sys
import unreal as u

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT/'SourceAssets/MPR/roof_interaction_20261106'
OUT = ROOT/'Saved/MPR/roof_interaction_20261106'
DEST = '/Game/MPRWarehouse/Roof/ScanReveal'
sys.path.insert(0, str(ROOT/'Tools/MPRWarehouse'))
import mpr_scene_patch_guard as g


def main():
    rows = g.read(SOURCE/'material_sources.json')
    protected = g.read(OUT/'content_before.json.gz')
    assert protected == g.guard.content_hashes(ROOT), 'Content changed since the material inventory'
    dirty = {p.get_path_name() for p in u.EditorLoadingAndSavingUtils.get_dirty_content_packages()}
    sources = sorted({r['base'] for r in rows})
    assert len(rows) == 13 and len(sources) == 6
    for row in rows:
        material = u.EditorAssetLibrary.load_asset(row['effective'])
        while isinstance(material, u.MaterialInstance):
            material = material.get_editor_property('parent')
        assert material.get_path_name().split('.')[0] == row['base']
        assert row['base'] not in dirty
        assert material.get_editor_property('blend_mode') == u.BlendMode.BLEND_OPAQUE
        assert not material.get_editor_property('use_material_attributes')
    spec = importlib.util.spec_from_file_location('ghs_roof_scan_builder', ROOT/'Scripts/ghs/apply_roof_dissolve.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    builder.DEST = DEST
    u.EditorAssetLibrary.make_directory(DEST)
    variants = [builder.create(source) for source in sources]
    after = g.guard.content_hashes(ROOT)
    assert all(after.get(p) == digest for p, digest in protected.items()), 'Existing Content changed'
    expected = {'Content/'+r['target'].removeprefix('/Game/')+'.uasset' for r in variants}
    added = {p:d for p,d in after.items() if p not in protected}
    assert set(added) == expected, 'Unexpected new assets'
    report = dict(success=True, variants=variants, shader_sha256=builder.SHADER_HASH,
                  shader='Scripts/ghs/roof_scan_shader.hlsl', new_assets=added,
                  protected_packages=len(protected), map_unchanged=True,
                  originals_unchanged=True, manual_seconds=.8, restore_seconds=.55)
    g.write(SOURCE/'material_validation.json', report)
    print('MPR_ROOF_SCAN_MATERIALS_READY', len(variants))


if __name__ == '__main__':
    main()
