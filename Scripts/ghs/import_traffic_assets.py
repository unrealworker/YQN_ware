"""Import standalone traffic cars; source Park assets and level stay untouched."""
from pathlib import Path
import json
import unreal
ROOT=Path('D:/UEPro/Test')
DEST='/Game/GHSZcoolSmartFactory/Traffic'
PARK='/Game/GHSZcoolSmartFactory/Park'
LIB=unreal.EditorAssetLibrary
TOOLS=unreal.AssetToolsHelpers.get_asset_tools()
ML=unreal.MaterialEditingLibrary
report={'success':False,'meshes':[]}
try:
    data=json.loads((ROOT/'SourceAssets/GHS/Traffic/cars.json').read_text(encoding='utf8'))
    mats={}
    for role in {r for row in data['meshes'] for r in row['material_roles']}:
        path=DEST+'/Materials/M_GHSTraffic_'+role
        mat=LIB.load_asset(path)
        if mat is None:mat=LIB.duplicate_asset(PARK+'/Materials/M_GHSPark_'+role,path)
        assert isinstance(mat,unreal.Material),role
        mat.set_editor_property('used_with_instanced_static_meshes',True)
        ML.recompile_material(mat)
        assert LIB.save_loaded_asset(mat,only_if_is_dirty=False)
        mats[role]=mat
    for row in data['meshes']:
        task=unreal.AssetImportTask()
        task.filename=row['fbx'];task.destination_path=DEST+'/Meshes';task.destination_name=row['name']
        task.automated=True;task.replace_existing=True;task.replace_existing_settings=True;task.save=False
        options=unreal.FbxImportUI();options.import_mesh=True;options.import_as_skeletal=False
        options.mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH
        options.automated_import_should_detect_type=False
        options.import_materials=False;options.import_textures=False;options.import_animations=False
        options.static_mesh_import_data.combine_meshes=True
        options.static_mesh_import_data.generate_lightmap_u_vs=False
        options.static_mesh_import_data.auto_generate_collision=False
        options.static_mesh_import_data.normal_import_method=unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
        task.options=options;TOOLS.import_asset_tasks([task])
        mesh=LIB.load_asset(DEST+'/Meshes/'+row['name'])
        assert isinstance(mesh,unreal.StaticMesh)
        slots=mesh.static_materials
        assert len(slots)==len(row['material_roles'])
        for i,role in enumerate(row['material_roles']):
            assert str(slots[i].material_slot_name)==row['slot_names'][i]
            slot=slots[i];slot.material_interface=mats[role];slots[i]=slot
        mesh.set_editor_property('static_materials',slots)
        bound=mesh.get_bounds()
        for side,vector in [('min',bound.origin-bound.box_extent),('max',bound.origin+bound.box_extent)]:
            assert max(abs(a-b) for a,b in zip([vector.x,vector.y,vector.z],row['bounds_ue_cm'][side]))<1.
        assert LIB.save_loaded_asset(mesh,only_if_is_dirty=False)
        report['meshes'].append({'path':mesh.get_path_name(),'triangles':row['triangles'],'slots':len(slots)})
    truck=LIB.load_asset(PARK+'/Meshes/SM_GHSPark_ClosedTruck')
    assert isinstance(truck,unreal.StaticMesh)
    assert all(truck.get_material(i).get_editor_property('used_with_instanced_static_meshes') for i in range(len(truck.static_materials)))
    report['success']=True
finally:
    out=ROOT/'Saved/RoofTraffic';out.mkdir(parents=True,exist_ok=True)
    (out/'traffic-import.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print('GHS_TRAFFIC_IMPORT '+json.dumps(report))
