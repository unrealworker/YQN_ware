"""Reimport an explicitly listed MPR-private mesh; never edit shared materials."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]


def import_mesh(u,row,destination,*,replace=False,reference_slots=None,materials=None):
    assert destination.startswith('/Game/MPRWarehouse/')
    path=destination+'/'+row['name'];source=ROOT/row['fbx']
    assert source.resolve().is_relative_to((ROOT/'SourceAssets/MPR').resolve()) and source.is_file()
    exists=u.EditorAssetLibrary.does_asset_exist(path)
    assert exists==replace,(path,'unexpected asset presence')
    t=u.AssetImportTask();t.filename=str(source);t.destination_path=destination;t.destination_name=row['name']
    t.automated=True;t.replace_existing=replace;t.replace_existing_settings=True;t.save=False
    o=u.FbxImportUI();o.import_mesh=True;o.import_as_skeletal=False;o.import_materials=False;o.import_textures=False;o.import_animations=False
    o.mesh_type_to_import=u.FBXImportType.FBXIT_STATIC_MESH;o.automated_import_should_detect_type=False
    d=o.static_mesh_import_data;d.combine_meshes=True;d.auto_generate_collision=False;d.generate_lightmap_u_vs=False
    d.convert_scene=True;d.convert_scene_unit=True;d.force_front_x_axis=False;d.vertex_color_import_option=u.VertexColorImportOption.IGNORE
    d.normal_import_method=u.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS;d.normal_generation_method=u.FBXNormalGenerationMethod.BUILT_IN
    t.options=o;t.factory=u.FbxFactory();u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([t])
    mesh=u.EditorAssetLibrary.load_asset(path);assert isinstance(mesh,u.StaticMesh)
    sm=u.get_editor_subsystem(u.StaticMeshEditorSubsystem)
    for index,filename in enumerate(row.get('lod_files',[]),1):
        assert sm and sm.import_lod(mesh,index,str(ROOT/filename))==index
    slots=list(mesh.get_editor_property('static_materials'))
    roles=[str(s.get_editor_property('imported_material_slot_name')).removeprefix('M_Zcool_').split('.')[0] for s in slots]
    assert set(roles)<=set(row['material_roles']),(roles,row['material_roles'])
    if reference_slots is not None:
        assert sm and materials
        sections=[[roles[sm.get_lod_material_slot(mesh,lod,i)] for i in range(mesh.get_num_sections(lod))] for lod in range(sm.get_lod_count(mesh))]
        expected_roles=list(materials)
        mesh.set_editor_property('static_materials',list(reference_slots))
        for i,role in enumerate(expected_roles):mesh.set_material(i,materials[role])
        for lod,section in enumerate(sections):
            for i,role in enumerate(section):sm.set_lod_material_slot(mesh,expected_roles.index(role),lod,i)
        assert sm.set_lod_screen_sizes(mesh,[1.,.22,.065] if row.get('lod_files') else [1.])
    else:
        for i,(slot,role) in enumerate(zip(slots,roles)):
            mat=None
            for candidate in (f'/Game/MPRWarehouse/Materials/MI_MPR_HISM_M_Zcool_{role}',f'/Game/GHSZcoolSmartFactory/Materials/M_Zcool_{role}'):
                value=u.EditorAssetLibrary.load_asset(candidate)
                if value and u.MaterialEditingLibrary.has_material_usage(value,u.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES):mat=value;break
            assert mat,role
            slot.material_interface=mat;slots[i]=slot
        mesh.set_editor_property('static_materials',slots)
    b=mesh.get_bounds();actual=[[b.origin.x-b.box_extent.x,b.origin.x+b.box_extent.x],[b.origin.y-b.box_extent.y,b.origin.y+b.box_extent.y],[b.origin.z-b.box_extent.z,b.origin.z+b.box_extent.z]]
    src=row['bounds_m'];expected=[[src[0][0]*100,src[0][1]*100],[-src[1][1]*100,-src[1][0]*100],[src[2][0]*100,src[2][1]*100]]
    assert max(abs(a-b) for aa,bb in zip(actual,expected) for a,b in zip(aa,bb))<.1,(row['name'],actual,expected)
    return mesh
