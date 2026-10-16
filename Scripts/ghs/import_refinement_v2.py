"""Import only versioned V2 meshes and truck materials, preserving previous assets."""
from pathlib import Path
import json,hashlib,traceback
import unreal
ROOT=Path(r'D:\UEPro\Test');SRC=ROOT/'SourceAssets/GHS/RefinementV2';DEST='/Game/GHSRefinementV2'
lib=unreal.EditorAssetLibrary;ml=unreal.MaterialEditingLibrary;assets=unreal.AssetToolsHelpers.get_asset_tools()
unreal.load_module('StaticMeshEditor');editor=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
BLUE={'Upright':'StorageSteel','Beam':'StorageSteelLight','Braces':'StorageSteelLight','Pallet':'StoragePalletBlue',
    'Cargo':'StorageCargoBlue','CargoEdges':'StorageCargoGrid','Detail':'StorageCharcoal',
    'Panel':'StorageSteel','Frame':'StorageSteelLight','Dark':'StorageCharcoal','Faces':'WallVolume','Sections':'WallSection','Edges':'WallTrim'}
NORMAL={'Upright':'RackSilver','Beam':'BluePallet','Braces':'RackSilver','Pallet':'BluePallet',
    'Cargo':'Cardboard','CargoEdges':'CardboardSeam','Detail':'Charcoal','Panel':'RackSilver','Frame':'WallTrim','Dark':'Charcoal',
    'Faces':'Wall','Sections':'WallSection','Edges':'WallTrim'}
TRUCK={
    'Normal':{'Body':(.57,.62,.68),'Trim':(.29,.36,.44),'Accent':(.018,.055,.31),'Glass':(.018,.048,.065),'Rubber':(.019,.025,.032),'Headlight':(.46,.66,.79),'TailLight':(.36,.028,.014)},
    'Blue':{'Body':(.025,.095,.205),'Trim':(.052,.16,.27),'Accent':(.015,.28,.36),'Glass':(.006,.016,.032),'Rubber':(.008,.014,.024),'Headlight':(.08,.37,.43),'TailLight':(.19,.025,.016)}}
def truck_material(style,role):
    name='M_V2Truck_'+style+'_'+role;path=DEST+'/Materials/'+name
    assert not lib.does_asset_exist(path),'Preserve imported V2 asset; inspect before reimport '+path
    mat=assets.create_asset(name,DEST+'/Materials',unreal.Material,unreal.MaterialFactoryNew())
    mat.set_editor_property('used_with_instanced_static_meshes',True)
    color=ml.create_material_expression(mat,unreal.MaterialExpressionConstant3Vector)
    color.set_editor_property('constant',unreal.LinearColor(*TRUCK[style][role],1))
    ml.connect_material_property(color,'',unreal.MaterialProperty.MP_BASE_COLOR)
    for prop,value in [(unreal.MaterialProperty.MP_ROUGHNESS,.22 if role=='Glass' else .78 if role=='Rubber' else .55),
                       (unreal.MaterialProperty.MP_METALLIC,.18 if role in {'Body','Trim'} else .03)]:
        n=ml.create_material_expression(mat,unreal.MaterialExpressionConstant);n.set_editor_property('r',value);ml.connect_material_property(n,'',prop)
    ml.recompile_material(mat);assert lib.save_loaded_asset(mat,only_if_is_dirty=False)
    return path
def run():
    manifests=['Racks/refined_rack_cargo.json','Envelope/envelope_v2.json','Trucks/dock_truck_v2.json']
    report=dict(success=False,manifests={p:sha(SRC/p) for p in manifests},meshes=[])
    try:
        truck_mats={style:{role:truck_material(style,role) for role in palette} for style,palette in TRUCK.items()}
        for relative in manifests:
            for spec in read(SRC/relative)['meshes']:
                name=spec['name'];assert name.startswith('SM_GHS_V2')
                assert not lib.does_asset_exist(DEST+'/Meshes/'+name),name+' already exists'
                task=unreal.AssetImportTask();task.filename=spec['fbx'];task.destination_path=DEST+'/Meshes'
                task.destination_name=name;task.automated=True;task.replace_existing=False;task.save=True
                options=unreal.FbxImportUI();options.import_mesh=True;options.import_as_skeletal=False
                options.mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH;options.automated_import_should_detect_type=False
                options.import_materials=False;options.import_textures=False;options.import_animations=False
                data=options.static_mesh_import_data;data.combine_meshes=True;data.generate_lightmap_u_vs=False;data.auto_generate_collision=False
                data.normal_import_method=(unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS_AND_TANGENTS if relative.startswith('Envelope') else unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
                data.normal_generation_method=unreal.FBXNormalGenerationMethod.BUILT_IN
                task.options=options;assets.import_asset_tasks([task]);mesh=lib.load_asset(DEST+'/Meshes/'+name);assert mesh
                slots=mesh.get_editor_property('static_materials');roles=[];palettes={'Blue':[],'Normal':[]}
                for i,s in enumerate(slots):
                    role=str(s.get_editor_property('imported_material_slot_name')).rsplit('_',1)[-1]
                    role={'WallVolume':'Faces','WallSection':'Sections','WallTrim':'Edges'}.get(role,role)
                    assert role in spec['slot_roles'],(name,role,spec['slot_roles'])
                    roles.append(role)
                    for style in palettes:
                        path=truck_mats[style][role] if relative.startswith('Trucks') else ('/Game/GHSDigitalTwin/Materials/Instanced/M_GHS_'+BLUE[role] if style=='Blue' else '/Game/GHSNormalWarehouse/Materials/M_GHN_'+NORMAL[role])
                        palettes[style].append(path);assert lib.does_asset_exist(path),path
                    s.set_editor_property('material_interface',lib.load_asset(palettes['Blue'][-1]));slots[i]=s
                mesh.set_editor_property('static_materials',slots)
                if 'Exterior' not in name:
                    reduction=unreal.StaticMeshReductionOptions();reduction.auto_compute_lod_screen_size=False
                    reduction.reduction_settings=[unreal.StaticMeshReductionSettings(percent_triangles=p,screen_size=s) for p,s in [(1.,1.),(.55,.25),(.30,.08),(.18,.025)]]
                    assert editor.set_lods(mesh,reduction)==4
                b=mesh.get_bounds();expected=spec['bounds_m'];center=[(a+b)*50 for a,b in expected];center[1]*=-1;extent=[(b-a)*50 for a,b in expected]
                assert max(abs(getattr(b.origin,k)-v) for k,v in zip('xyz',center))<.15,name
                assert max(abs(getattr(b.box_extent,k)-v) for k,v in zip('xyz',extent))<.15,name
                assert lib.save_loaded_asset(mesh,only_if_is_dirty=False)
                report['meshes'].append(dict(name=name,path=mesh.get_path_name(),roles=roles,palettes=palettes,fbx_sha256=sha(Path(spec['fbx'])),
                    bounds_m=expected,lod_triangles=[mesh.get_num_triangles(i) for i in range(editor.get_lod_count(mesh))]))
        report['success']=True;unreal.log('GHS_V2_IMPORT_SUCCESS '+str(len(report['meshes'])))
    except Exception:report['error']=traceback.format_exc();raise
    finally:(ROOT/'Saved/GHS_RefinementV2Import.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
if __name__=='__main__':run()
