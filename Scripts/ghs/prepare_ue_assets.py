"""Import only GHS assets and create LOD copies; never modify shared VR assets."""
import json
import traceback
from pathlib import Path
import unreal

ghs_root=Path(r'D:\UEPro\Test')
base=(ghs_root/'Scripts/build_video_warehouse.py').read_text(encoding='utf-8')
exec(compile(base.split('\ntry:main()')[0],'video_material_helpers.py','exec'),globals())
SOURCE=ROOT/'SourceAssets/GHS'
DEST='/Game/GHSDigitalTwin'
report_path=ROOT/'Saved/GHS_AssetImport.json'
report=dict(success=False,meshes=[],shared_materials_preserved=True)
unreal.load_module('StaticMeshEditor')
sm_editor=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)

def add_lods(mesh):
    assert mesh.get_path_name().startswith(DEST+'/')
    options=unreal.StaticMeshReductionOptions()
    options.set_editor_property('auto_compute_lod_screen_size',False)
    # The 5% cargo LOD folds the top faces and removes the pallet/seam sections.
    # Keep the validated 18% geometry for its final LOD as well.
    final_ratio=.18 if mesh.get_name()=='SM_GHS_Shared_PalletCargo' else .05
    options.set_editor_property('reduction_settings',[
        unreal.StaticMeshReductionSettings(percent_triangles=p,screen_size=s)
        for p,s in [(1,1),(.5,.4),(.18,.15),(final_ratio,.04)]])
    assert sm_editor.set_lods(mesh,options)==4
    assert sm_editor.get_lod_count(mesh)==4
    if mesh.get_name() in ['SM_GHS_KukaLowProfileAGV','SM_GHS_WallCharger']:
        assert sm_editor.set_lod_screen_sizes(mesh,[1,.12,.04,.012])
    save(mesh)

try:
    specs=[json.loads((SOURCE/(stem+'.json')).read_text(encoding='utf-8'))
           for stem in ['kuka_agv','charger','cad_architecture']]
    for spec in specs:
        for material in spec['materials']:
            name=material['name']
            if name in MATS:continue
            if name.startswith('M_VR_GHS_'):
                make_material(material)
            else:
                shared=lib.load_asset('/Game/VideoDigitalTwin/Materials/'+name)
                assert shared,'Missing existing style material '+name
                MATS[name]=shared
    for spec in specs:
        for item in spec['meshes']:
            task=unreal.AssetImportTask()
            task.filename=item['fbx'];task.destination_path=DEST+'/Meshes'
            task.destination_name=item['name'];task.automated=True;task.replace_existing=True;task.save=True
            options=unreal.FbxImportUI()
            options.import_mesh=True;options.import_as_skeletal=False
            options.mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH
            options.automated_import_should_detect_type=False
            options.import_materials=False;options.import_textures=False;options.import_animations=False
            options.static_mesh_import_data.combine_meshes=True
            options.static_mesh_import_data.generate_lightmap_u_vs=False
            options.static_mesh_import_data.auto_generate_collision=False
            options.static_mesh_import_data.normal_import_method=unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
            options.static_mesh_import_data.normal_generation_method=unreal.FBXNormalGenerationMethod.BUILT_IN
            task.options=options;assets.import_asset_tasks([task])
            mesh=lib.load_asset(DEST+'/Meshes/'+item['name']);assert mesh,item['name']
            slots=mesh.get_editor_property('static_materials')
            for i,slot in enumerate(slots):
                name=str(slot.get_editor_property('imported_material_slot_name'))
                if name not in MATS:name=str(slot.get_editor_property('material_slot_name'))
                assert name in MATS,name
                slot.set_editor_property('material_interface',MATS[name]);slots[i]=slot
            mesh.set_editor_property('static_materials',slots)
            if item['name'] in ['SM_GHS_KukaLowProfileAGV','SM_GHS_WallCharger']:add_lods(mesh)
            else:save(mesh)
            bounds=mesh.get_bounds()
            report['meshes'].append(dict(name=item['name'],path=mesh.get_path_name(),
                size_cm=[getattr(bounds.box_extent,a)*2 for a in ['x','y','z']],
                material_count=len(slots),lod_count=sm_editor.get_lod_count(mesh)))
    # Local copies preserve the approved model/material appearance while allowing
    # a 9000-instance scene to use progressively simpler geometry at distance.
    for original in ['SM_VR_RackBay','SM_VR_PalletCargo','SM_VR_Conveyor']:
        target=DEST+'/Meshes/'+original.replace('SM_VR_','SM_GHS_Shared_')
        mesh=lib.load_asset(target) if lib.does_asset_exist(target) else lib.duplicate_asset('/Game/VideoDigitalTwin/Meshes/'+original,target)
        assert mesh,target
        add_lods(mesh)
        report['meshes'].append(dict(name=mesh.get_name(),path=mesh.get_path_name(),
            reused_from='/Game/VideoDigitalTwin/Meshes/'+original,lod_count=sm_editor.get_lod_count(mesh)))
    report['success']=True
    report_path.write_text(json.dumps(report,indent=2),encoding='utf-8')
    unreal.log('GHS_ASSETS_IMPORTED '+str(len(report['meshes'])))
except Exception:
    report['error']=traceback.format_exc()
    report_path.write_text(json.dumps(report,indent=2),encoding='utf-8')
    raise
