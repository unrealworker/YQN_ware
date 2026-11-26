"""Import the replay pallet derivative only; preserve source storage and the map."""
import hashlib
import json
import shutil
from pathlib import Path
import unreal

ROOT=Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
OUT=ROOT/'Saved/OrderReplay'
OUT.mkdir(parents=True,exist_ok=True)
NAME='SM_Replay_CargoMid'
ASSET='/Game/GHSOrderReplay/Meshes/'+NAME
PACKAGE=ROOT/'Content/GHSOrderReplay/Meshes'/f'{NAME}.uasset'
MANIFEST=ROOT/'SourceAssets/GHS/OrderReplay/replay_assets.json'
protected=[ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap',
           ROOT/'Content/GHSZcoolSmartFactory/DoublePallet/Meshes/SM_GHS_Presentation_CargoMid.uasset',
           ROOT/'SourceAssets/GHS/DoublePallet/double_pallet_storage.blend']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
before={str(p):sha(p) for p in protected}
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
spec=next(m for m in json.loads(MANIFEST.read_text(encoding='utf8'))['meshes'] if m['name']==NAME)
fbx=ROOT/'SourceAssets/GHS/OrderReplay'/f'{NAME}.fbx'
lib=unreal.EditorAssetLibrary
mesh=lib.load_asset(ASSET)
assert mesh

def bounds(m):
    b=m.get_bounds()
    return [getattr(b.origin,k)+sign*getattr(b.box_extent,k) for sign in (-1,1) for k in 'xyz']

old_bounds=bounds(mesh)
materials={str(s.get_editor_property('imported_material_slot_name')):s.get_editor_property('material_interface')
           for s in mesh.get_editor_property('static_materials')}
assert all(materials.values())
backup=OUT/'cargo-mid-before-side-fork-slots.uasset'
if not backup.exists():shutil.copy2(PACKAGE,backup)
task=unreal.AssetImportTask()
task.filename=fbx.as_posix()
task.destination_path='/Game/GHSOrderReplay/Meshes'
task.destination_name=NAME
task.automated=True
task.replace_existing=True
task.replace_existing_settings=True
task.save=False
options=unreal.FbxImportUI()
options.import_mesh=True
options.import_as_skeletal=False
options.mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH
options.automated_import_should_detect_type=False
options.import_materials=False
options.import_textures=False
options.import_animations=False
options.static_mesh_import_data.combine_meshes=True
options.static_mesh_import_data.generate_lightmap_u_vs=False
options.static_mesh_import_data.auto_generate_collision=False
options.static_mesh_import_data.normal_import_method=unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
options.static_mesh_import_data.normal_generation_method=unreal.FBXNormalGenerationMethod.BUILT_IN
task.options=options
unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
mesh=lib.load_asset(ASSET)
slots=mesh.get_editor_property('static_materials')
assert {str(s.get_editor_property('imported_material_slot_name')) for s in slots}==set(materials)
for s in slots:s.set_editor_property('material_interface',materials[str(s.get_editor_property('imported_material_slot_name'))])
mesh.set_editor_property('static_materials',slots)
assert max(abs(a-b) for a,b in zip(bounds(mesh),old_bounds))<.02,'Pallet exterior changed'
unreal.load_module('StaticMeshEditor')
editor=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
# Only ten replay pallets exist. Preserve the fork openings at every distance;
# an aggressive reduced LOD could bridge the newly opened pockets again.
reduction=unreal.StaticMeshReductionOptions()
reduction.auto_compute_lod_screen_size=False
reduction.reduction_settings=[unreal.StaticMeshReductionSettings(percent_triangles=1.,screen_size=1.)]
editor.set_lods(mesh,reduction)
assert mesh.get_num_triangles(0)==spec['triangles']
assert lib.save_loaded_asset(mesh,only_if_is_dirty=False)
assert before=={str(p):sha(p) for p in protected}
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
report=dict(success=True,asset=ASSET,asset_sha256=sha(PACKAGE),fbx_sha256=sha(fbx),
            bounds_cm=bounds(mesh),triangles=mesh.get_num_triangles(0),
            materials={k:v.get_path_name() for k,v in materials.items()},protected_unchanged=before)
(OUT/'cargo_mid_import.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
unreal.log('GHS_REPLAY_CARGO_MID_IMPORTED '+json.dumps(report,ensure_ascii=False))
