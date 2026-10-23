"""Import only new replay assets/materials; preserve the current map verbatim."""
import sys,json,hashlib
from pathlib import Path
import unreal
ROOT=Path('D:/UEPro/Test');sys.path.insert(0,str(ROOT/'Scripts/ghs'))
import import_manned_forklift as u
from sync_wall_heights import snapshot
SRC=ROOT/'SourceAssets/GHS/OrderReplay';DEST='/Game/GHSOrderReplay'
manifest=json.loads((SRC/'replay_assets.json').read_text());assert manifest['success']
by=u.labels();before=snapshot(by)
original={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in manifest['source_hashes']};assert original==manifest['source_hashes']
ML=unreal.MaterialEditingLibrary;LIB=unreal.EditorAssetLibrary;TOOLS=unreal.AssetToolsHelpers.get_asset_tools()
slot_materials={}
for label in ['GHN_MannedForklift_01','GHS_DockTruck_020','GHS_CAD_PalletCargo','GHS_CAD_PalletCargoLow','GHS_CAD_PalletCargoHigh','GHS_CAD_DockDoors']:
    c=by[label].get_component_by_class(unreal.StaticMeshComponent)
    for n,slot in enumerate(c.static_mesh.get_editor_property('static_materials')):
        slot_materials[str(slot.get_editor_property('imported_material_slot_name'))]=c.get_material(n)
unreal.load_module('StaticMeshEditor');SM=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
results=[]
for spec in manifest['meshes']:
    name=spec['name'];path=DEST+'/Meshes/'+name
    task=unreal.AssetImportTask();task.filename=spec['fbx'];task.destination_path=DEST+'/Meshes';task.destination_name=name
    task.automated=True;task.replace_existing=True;task.replace_existing_settings=True;task.save=False
    opt=unreal.FbxImportUI();opt.import_mesh=True;opt.import_as_skeletal=False;opt.mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH
    opt.automated_import_should_detect_type=False;opt.import_materials=False;opt.import_textures=False;opt.import_animations=False
    d=opt.static_mesh_import_data;d.combine_meshes=True;d.generate_lightmap_u_vs=False;d.auto_generate_collision=False
    d.normal_import_method=unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS;d.normal_generation_method=unreal.FBXNormalGenerationMethod.BUILT_IN
    task.options=opt;TOOLS.import_asset_tasks([task]);mesh=LIB.load_asset(path);assert mesh,path
    slots=mesh.get_editor_property('static_materials')
    for i,s in enumerate(slots):
        key=str(s.get_editor_property('imported_material_slot_name'));assert key in slot_materials,(name,key,list(slot_materials))
        s.set_editor_property('material_interface',slot_materials[key]);slots[i]=s
    mesh.set_editor_property('static_materials',slots)
    if spec['triangles']>1000:
        reduction=unreal.StaticMeshReductionOptions();reduction.auto_compute_lod_screen_size=False
        reduction.reduction_settings=[unreal.StaticMeshReductionSettings(percent_triangles=p,screen_size=s) for p,s in [(1.,1.),(.5,.25),(.2,.07),(.08,.02)]]
        SM.set_lods(mesh,reduction)
    assert LIB.save_loaded_asset(mesh,only_if_is_dirty=False)
    results.append(dict(name=name,path=path,triangles=mesh.get_num_triangles(0),bounds_cm=u.mesh_box(mesh,unreal.Transform())))

from replay_repair_trail_material import build_trail_material
path=DEST+'/Materials/M_ReplayTrail';build_trail_material()
assert before==snapshot(u.labels()),'Replay import changed original scene'
assert original=={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in original}
report=dict(success=True,meshes=results,original_scene_unchanged=True,source_hashes_unchanged=True,trail_material=path)
(ROOT/'Saved/OrderReplay/asset_import.json').write_text(json.dumps(report,indent=2),encoding='utf8')
unreal.log('ORDER_REPLAY_ASSETS_IMPORTED '+str(len(results)))
