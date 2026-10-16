"""Import CAD-derived rack geometry without changing saved levels or old assets."""
import json,traceback,hashlib
from pathlib import Path
import unreal
ROOT=Path(r'D:\UEPro\Test');DEST='/Game/GHSDigitalTwin/Meshes'
lib=unreal.EditorAssetLibrary;assets=unreal.AssetToolsHelpers.get_asset_tools()
unreal.load_module('StaticMeshEditor');editor=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
SLOTS={'Upright':'StorageSteel','Beam':'StorageSteelLight','Braces':'StorageSteelLight',
       'Pallet':'StoragePalletBlue','Cargo':'StorageCargoBlue','CargoEdges':'StorageCargoGrid','Detail':'StorageCharcoal',
       'Panel':'StorageSteel','Frame':'StorageSteelLight','Dark':'StorageCharcoal'}
NORMAL={'Upright':'RackSilver','Beam':'BluePallet','Braces':'RackSilver','Pallet':'BluePallet',
        'Cargo':'Cardboard','CargoEdges':'CardboardSeam','Detail':'Charcoal',
        'Panel':'RackSilver','Frame':'WallTrim','Dark':'Charcoal'}

def read(p):return json.loads(p.read_text(encoding='utf-8'))

def run():
    source=read(ROOT/'SourceAssets/GHS/RackSpecs/Models/cad_rack_models.json')
    door=read(ROOT/'SourceAssets/GHS/RackSpecs/Doors/cad_dock_door.json')
    specs=source['meshes']+door['meshes'];report=dict(success=False,meshes=[])
    try:
        for spec in specs:
            name=spec['name'];assert name.startswith(('SM_GHS_CADRack','SM_GHS_CADDock'))
            task=unreal.AssetImportTask();task.filename=spec['fbx'];task.destination_path=DEST
            task.destination_name=name;task.automated=True;task.replace_existing=True;task.save=True
            options=unreal.FbxImportUI();options.import_mesh=True;options.import_as_skeletal=False
            options.mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH;options.automated_import_should_detect_type=False
            options.import_materials=False;options.import_textures=False;options.import_animations=False
            data=options.static_mesh_import_data;data.combine_meshes=True;data.generate_lightmap_u_vs=False;data.auto_generate_collision=False
            data.normal_import_method=unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
            data.normal_generation_method=unreal.FBXNormalGenerationMethod.BUILT_IN
            task.options=options;assets.import_asset_tasks([task])
            mesh=lib.load_asset(DEST+'/'+name);assert isinstance(mesh,unreal.StaticMesh)
            slots=mesh.get_editor_property('static_materials');roles=[]
            for i,slot in enumerate(slots):
                role=str(slot.get_editor_property('imported_material_slot_name')).rsplit('_',1)[-1];assert role in SLOTS
                material=lib.load_asset('/Game/GHSDigitalTwin/Materials/Instanced/M_GHS_'+SLOTS[role]);assert material
                slot.set_editor_property('material_interface',material);slots[i]=slot;roles.append(role)
            mesh.set_editor_property('static_materials',slots)
            reduction=unreal.StaticMeshReductionOptions();reduction.auto_compute_lod_screen_size=False
            reduction.reduction_settings=[unreal.StaticMeshReductionSettings(percent_triangles=p,screen_size=s)
                for p,s in [(1.,1.),(.55,.25),(.30,.08),(.18,.025)]]
            assert editor.set_lods(mesh,reduction)==4
            b=mesh.get_bounds();bounds=spec['bounds_m']
            expected_center=[(a+b)*50 for a,b in bounds];expected_center[1]*=-1
            expected_extent=[(b-a)*50 for a,b in bounds]
            # Generated reductions must not introduce visible scale changes.
            assert max(abs(getattr(b.origin,k)-v) for k,v in zip('xyz',expected_center))<.15,name
            assert max(abs(getattr(b.box_extent,k)-v) for k,v in zip('xyz',expected_extent))<.15,name
            assert lib.save_loaded_asset(mesh,only_if_is_dirty=False)
            report['meshes'].append(dict(name=name,path=mesh.get_path_name(),roles=roles,
                normal_materials=['/Game/GHSNormalWarehouse/Materials/M_GHN_'+NORMAL[r] for r in roles],
                blue_materials=[mesh.get_material(i).get_path_name() for i in range(len(slots))],
                size_cm=[getattr(b.box_extent,k)*2 for k in 'xyz'],origin_cm=[getattr(b.origin,k) for k in 'xyz'],
                lod_triangles=[mesh.get_num_triangles(i) for i in range(4)]))
        report.update(success=True,model_manifest_sha256=hashlib.sha256((ROOT/'SourceAssets/GHS/RackSpecs/Models/cad_rack_models.json').read_bytes()).hexdigest())
        unreal.log('GHS_CAD_RACK_IMPORT_COMPLETE '+str(len(specs)))
    except Exception:
        report['error']=traceback.format_exc();raise
    finally:(ROOT/'Saved/GHS_CADRackImport.json').write_text(json.dumps(report,indent=2),encoding='utf-8')

if __name__=='__main__':run()
