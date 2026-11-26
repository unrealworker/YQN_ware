"""Import only new replay assets/materials; preserve the current map verbatim."""
import sys,json,hashlib
from pathlib import Path
import unreal
ROOT=Path('D:/UEPro/Test');sys.path.insert(0,str(ROOT/'Scripts/ghs'))
import import_manned_forklift as u
from sync_wall_heights import snapshot
SRC=ROOT/'SourceAssets/GHS/OrderReplay';DEST='/Game/GHSOrderReplay'
manifest=json.loads((SRC/'replay_assets.json').read_text());assert manifest['success']
rack_only='-ghsrackcargoonly' in unreal.SystemLibrary.get_command_line().lower().split()
specs=manifest['meshes']
if rack_only:
    specs=[s for s in specs if s['name'].startswith('SM_Replay_CargoRack_')]
    assert {s['name'] for s in specs}=={'SM_Replay_CargoRack_A1_L2_C2','SM_Replay_CargoRack_A1_L1_C2','SM_Replay_CargoRack_A1_L1_C3'}
    assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
    selected_files={s['name']+'.uasset' for s in specs}
    packages=[p for p in (ROOT/'Content/GHSOrderReplay').rglob('*.uasset') if p.name not in selected_files]
    packages.extend([ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap',
                     ROOT/'Content/GHSZcoolSmartFactory/StorageCapacity/Meshes/SM_GHS_V2Rack_CAD24_A1_Capacity.uasset'])
    protected={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in packages}
by=u.labels();before=snapshot(by)
original={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in manifest['source_hashes']};assert original==manifest['source_hashes']
ML=unreal.MaterialEditingLibrary;LIB=unreal.EditorAssetLibrary;TOOLS=unreal.AssetToolsHelpers.get_asset_tools()
slot_materials={}
source_labels=[] if rack_only else ['GHN_MannedForklift_01','GHS_DockTruck_020','GHS_CAD_PalletCargo','GHS_CAD_PalletCargoLow','GHS_CAD_PalletCargoHigh','GHS_CAD_DockDoors']
for label in source_labels:
    if label in ('GHS_CAD_PalletCargoLow','GHS_CAD_PalletCargoHigh') and label not in by:
        continue
    c=by[label].get_component_by_class(unreal.StaticMeshComponent)
    for n,slot in enumerate(c.static_mesh.get_editor_property('static_materials')):
        slot_materials[str(slot.get_editor_property('imported_material_slot_name'))]=c.get_material(n)
for role,finish in [('Pallet','Cobalt'),('Cargo','Cargo'),('CargoEdges','CargoSeam'),('Detail','Charcoal')]:
    material=LIB.load_asset('/Game/GHSZcoolSmartFactory/Materials/M_Zcool_'+finish)
    assert material,finish
    slot_materials['M_GHS_CADRack_'+role]=material
unreal.load_module('StaticMeshEditor');SM=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
results=[]
for spec in specs:
    name=spec['name'];path=DEST+'/Meshes/'+name
    fbx=SRC/(name+'.fbx')
    assert hashlib.sha256(fbx.read_bytes()).hexdigest()==spec['sha256'],name
    task=unreal.AssetImportTask();task.filename=str(fbx);task.destination_path=DEST+'/Meshes';task.destination_name=name
    task.automated=True;task.replace_existing=True;task.replace_existing_settings=True;task.save=False
    opt=unreal.FbxImportUI();opt.import_mesh=True;opt.import_as_skeletal=False;opt.mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH
    opt.automated_import_should_detect_type=False;opt.import_materials=False;opt.import_textures=False;opt.import_animations=False
    d=opt.static_mesh_import_data;d.combine_meshes=True;d.generate_lightmap_u_vs=False;d.auto_generate_collision=False
    d.normal_import_method=unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS;d.normal_generation_method=unreal.FBXNormalGenerationMethod.BUILT_IN
    task.options=opt;TOOLS.import_asset_tasks([task]);mesh=LIB.load_asset(path);assert mesh,path
    slots=mesh.get_editor_property('static_materials')
    if name.startswith('SM_Replay_CargoRack_'):
        assert {str(s.get_editor_property('imported_material_slot_name')) for s in slots}==set(spec['slots'])
    for i,s in enumerate(slots):
        key=str(s.get_editor_property('imported_material_slot_name'));assert key in slot_materials,(name,key,list(slot_materials))
        s.set_editor_property('material_interface',slot_materials[key]);slots[i]=s
    mesh.set_editor_property('static_materials',slots)
    if name.startswith('SM_Replay_CargoRack_'):
        SM.remove_lods(mesh)
        assert mesh.get_num_triangles(0)==spec['triangles'] and SM.get_lod_count(mesh)==1,name
    elif spec['triangles']>1000:
        reduction=unreal.StaticMeshReductionOptions();reduction.auto_compute_lod_screen_size=False
        reduction.reduction_settings=[unreal.StaticMeshReductionSettings(percent_triangles=p,screen_size=s) for p,s in [(1.,1.),(.5,.25),(.2,.07),(.08,.02)]]
        SM.set_lods(mesh,reduction)
    assert LIB.save_loaded_asset(mesh,only_if_is_dirty=False)
    results.append(dict(name=name,path=path,triangles=mesh.get_num_triangles(0),bounds_cm=u.mesh_box(mesh,unreal.Transform()),
                        materials=[m.get_editor_property('material_interface').get_path_name() for m in mesh.get_editor_property('static_materials')]))

if rack_only:
    assert protected=={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
else:
    from replay_repair_trail_material import build_trail_material,build_ripple_material
    build_trail_material();build_ripple_material()
assert before==snapshot(u.labels()),'Replay import changed original scene'
assert original=={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in original}
report=dict(success=True,meshes=results,original_scene_unchanged=True,source_hashes_unchanged=True)
if not rack_only:report['trail_material']=DEST+'/Materials/M_ReplayTrail'
report_name='rack_cargo_import.json' if rack_only else 'asset_import.json'
(ROOT/'Saved/OrderReplay'/report_name).write_text(json.dumps(report,indent=2),encoding='utf8')
unreal.log('ORDER_REPLAY_ASSETS_IMPORTED '+str(len(results)))
