"""Run in the active UE editor to replace only the GHS cargo's collapsed LOD3."""
import json
import traceback
from pathlib import Path

import unreal


ASSET_PATH = '/Game/GHSDigitalTwin/Meshes/SM_GHS_Shared_PalletCargo'
REPORT_PATH = Path(r'D:\UEPro\Test\Saved\GHS_StorageLODRefinement.json')
RATIOS = [1.0, 0.5, 0.18, 0.18]
SCREEN_SIZES = [1.0, 0.4, 0.15, 0.04]
report = dict(success=False, asset_path=ASSET_PATH, ratios=RATIOS,
              screen_sizes=SCREEN_SIZES, meshes=[], source_vr_assets_modified=False)


def snapshot(mesh, subsystem):
    count = subsystem.get_lod_count(mesh)
    return dict(lod_count=count,
                triangles=[mesh.get_num_triangles(i) for i in range(count)],
                sections=[mesh.get_num_sections(i) for i in range(count)],
                screen_sizes=list(subsystem.get_lod_screen_sizes(mesh)))


try:
    unreal.load_module('StaticMeshEditor')
    subsystem = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    mesh = unreal.EditorAssetLibrary.load_asset(ASSET_PATH)
    assert isinstance(mesh, unreal.StaticMesh), 'Missing GHS cargo mesh'
    assert mesh.get_path_name().split('.')[0] == ASSET_PATH
    before = snapshot(mesh, subsystem)
    original_materials = [mesh.get_material(i).get_path_name()
                          for i in range(len(mesh.get_editor_property('static_materials')))]
    options = unreal.StaticMeshReductionOptions()
    options.set_editor_property('auto_compute_lod_screen_size', False)
    options.set_editor_property('reduction_settings', [
        unreal.StaticMeshReductionSettings(percent_triangles=ratio, screen_size=screen)
        for ratio, screen in zip(RATIOS, SCREEN_SIZES)])
    assert subsystem.set_lods(mesh, options) == 4
    after = snapshot(mesh, subsystem)
    assert after['lod_count'] == 4
    assert all(abs(actual - wanted) < 1e-6
               for actual, wanted in zip(after['screen_sizes'], SCREEN_SIZES))
    assert after['triangles'][3] >= after['triangles'][0] * 0.15, after
    assert after['sections'][3] >= 3, 'Cargo, pallet and seam sections must survive'
    assert original_materials == [mesh.get_material(i).get_path_name()
                                  for i in range(len(mesh.get_editor_property('static_materials')))]
    assert unreal.EditorAssetLibrary.save_loaded_asset(mesh, only_if_is_dirty=False)
    report['meshes'].append(dict(mesh=mesh.get_name(), before=before, after=after))
    report['success'] = True
    unreal.log('GHS_STORAGE_LOD_REFINED ' + mesh.get_name())
except Exception:
    report['error'] = traceback.format_exc()
    raise
finally:
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding='utf-8')
