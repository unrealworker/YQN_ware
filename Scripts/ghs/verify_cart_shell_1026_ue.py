"""Read-only verification of the saved CAD cart import and current six actors."""
import hashlib
import json
from pathlib import Path
import unreal

ROOT = Path('D:/UEPro/Test')
OUT = ROOT / 'SourceAssets/CartShell_1026/20k'
report = json.loads((OUT/'ue-import-verification.json').read_text(encoding='utf8'))
lib = unreal.EditorAssetLibrary
mesh = lib.load_asset(report['mesh'])
sm = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
build = sm.get_lod_build_settings(mesh, 0)
assert sm.get_num_uv_channels(mesh, 0) >= 1
assert not build.get_editor_property('use_mikk_t_space')
assert not build.get_editor_property('recompute_normals')
assert build.get_editor_property('recompute_tangents')
assert mesh.get_num_triangles(0) == 19965
actors = {a.get_actor_label(): a for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()}
for row in report['actors']:
    actor = actors[row['label']]
    c = actor.get_component_by_class(unreal.StaticMeshComponent)
    assert c.static_mesh == mesh, row['label']
    assert [str(t) for t in actor.tags] == row['tags'], row['label']
    assert [c.get_material(i).get_path_name() for i in range(5)] == report['materials']
assert sum(a.get_actor_label().startswith('GHS_AGV_') for a in actors.values()) == 32
fbx = OUT / 'SM_CartShell_1026.fbx'
assert hashlib.sha256(fbx.read_bytes()).hexdigest() == report['fbx_sha256']
map_file = ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'
assert hashlib.sha256(map_file.read_bytes()).hexdigest() == report['map_sha256']
report.update(uv_channels=sm.get_num_uv_channels(mesh, 0), ue_tangent_basis='BuiltIn',
              imported_normals_preserved=True, repeated_scene_check_passed=True,
              other_low_profile_agvs_unchanged=32,
              dirty_maps_at_verification=[p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()])
(OUT/'ue-import-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
unreal.log('CART_SHELL_FINAL_READONLY_CHECK_PASSED')
