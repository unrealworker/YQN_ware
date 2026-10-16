"""Import four GHS-only Blender storage meshes with retained material mapping and LODs."""
import json,traceback
from pathlib import Path
import unreal
ROOT=Path(r'D:\UEPro\Test');DEST='/Game/GHSDigitalTwin/Meshes'
spec=json.loads((ROOT/'SourceAssets/GHS/Presentation/presentation_storage.json').read_text())
assets=unreal.AssetToolsHelpers.get_asset_tools();lib=unreal.EditorAssetLibrary
unreal.load_module('StaticMeshEditor');sm=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
report=dict(success=False,meshes=[])
try:
    for item in spec['meshes']:
        task=unreal.AssetImportTask();task.filename=item['fbx'];task.destination_path=DEST
        task.destination_name=item['name'];task.automated=True;task.replace_existing=True;task.save=True
        options=unreal.FbxImportUI();options.import_mesh=True;options.import_as_skeletal=False
        options.mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH
        options.automated_import_should_detect_type=False
        options.import_materials=False;options.import_textures=False;options.import_animations=False
        data=options.static_mesh_import_data;data.combine_meshes=True;data.generate_lightmap_u_vs=False;data.auto_generate_collision=False
        data.normal_import_method=unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
        data.normal_generation_method=unreal.FBXNormalGenerationMethod.BUILT_IN
        task.options=options;assets.import_asset_tasks([task])
        mesh=lib.load_asset(DEST+'/'+item['name']);assert mesh
        slots=mesh.get_editor_property('static_materials')
        for i,slot in enumerate(slots):
            name=str(slot.get_editor_property('imported_material_slot_name'))
            assert name in item['slots'],name
            material=lib.load_asset('/Game/GHSDigitalTwin/Materials/Instanced/'+name.replace('M_VR_','M_GHS_'))
            assert material
            slot.set_editor_property('material_interface',material);slots[i]=slot
        mesh.set_editor_property('static_materials',slots)
        opts=unreal.StaticMeshReductionOptions();opts.set_editor_property('auto_compute_lod_screen_size',False)
        ratios=[1.,.5,.18,.12] if 'Rack' in item['name'] else [1.,.5,.22,.16]
        opts.set_editor_property('reduction_settings',[unreal.StaticMeshReductionSettings(percent_triangles=p,screen_size=s) for p,s in zip(ratios,[1.,.35,.12,.03])])
        assert sm.set_lods(mesh,opts)==4
        old=lib.load_asset(DEST+('/SM_GHS_Shared_RackBay' if 'Rack' in item['name'] else '/SM_GHS_Shared_PalletCargo'))
        a,b=mesh.get_bounds(),old.get_bounds()
        for axis in ['x','y']:
            # Previous decimated LOD bounds contain small outliers. A new mesh
            # must fit inside that approved footprint, never inherit outliers.
            assert getattr(a.origin,axis)-getattr(a.box_extent,axis)>=getattr(b.origin,axis)-getattr(b.box_extent,axis)-.02
            assert getattr(a.origin,axis)+getattr(a.box_extent,axis)<=getattr(b.origin,axis)+getattr(b.box_extent,axis)+.02
        assert abs(a.origin.z-a.box_extent.z)<.02
        assert lib.save_loaded_asset(mesh,only_if_is_dirty=False)
        report['meshes'].append(dict(name=item['name'],path=mesh.get_path_name(),size_cm=[getattr(a.box_extent,k)*2 for k in ['x','y','z']],
            origin_cm=[getattr(a.origin,k) for k in ['x','y','z']],triangles=[mesh.get_num_triangles(i) for i in range(4)],
            materials=[mesh.get_material(i).get_path_name() for i in range(len(slots))],xy_bounds_contained=True))
    report['success']=True
except Exception:
    report['error']=traceback.format_exc();raise
finally:(ROOT/'Saved/GHS_PresentationImport.json').write_text(json.dumps(report,indent=2))
