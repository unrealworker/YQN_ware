"""Add one removable roof and soften vegetation without rebuilding the park."""
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import traceback
import unreal

ROOT=Path('D:/UEPro/Test')
OUT=ROOT/'Saved/ParkRoofStyle'
MAP='/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
ROOF_DEST='/Game/GHSZcoolSmartFactory/Roof'
ROOF_LABEL='GHS_MainWarehouseRoof'
TREE_ROLES={'Trees','TreesDark','TreesLight'}
LIB=unreal.EditorAssetLibrary
ML=unreal.MaterialEditingLibrary
TOOLS=unreal.AssetToolsHelpers.get_asset_tools()
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def snapshot():
    fn=runpy.run_path(str(ROOT/'Scripts/ghs/validate_park_expansion.py'))['snapshot']
    return sorted([fn(a,unreal) for a in actors.get_all_level_actors() if a.get_actor_label()!=ROOF_LABEL],key=lambda r:r['label'])

def material(path,color,roughness,metallic=0.,specular=.15):
    folder,name=path.rsplit('/',1)
    LIB.make_directory(folder)
    mat=LIB.load_asset(path) if LIB.does_asset_exist(path) else TOOLS.create_asset(name,folder,unreal.Material,unreal.MaterialFactoryNew())
    # UE 5.4 can skip expressions while deleting from the same array. Remove
    # every old parameter so the saved cache cannot retain duplicate defaults.
    while ML.get_num_material_expressions(mat):
        previous=ML.get_num_material_expressions(mat)
        ML.delete_all_material_expressions(mat)
        assert ML.get_num_material_expressions(mat)<previous
    rgb=ML.create_material_expression(mat,unreal.MaterialExpressionVectorParameter)
    rgb.set_editor_property('parameter_name','SurfaceTint')
    rgb.set_editor_property('default_value',unreal.LinearColor(*color,1.))
    ML.connect_material_property(rgb,'',unreal.MaterialProperty.MP_BASE_COLOR)
    for label,value,prop in [('Roughness',roughness,unreal.MaterialProperty.MP_ROUGHNESS),
                             ('Metallic',metallic,unreal.MaterialProperty.MP_METALLIC),
                             ('Specular',specular,unreal.MaterialProperty.MP_SPECULAR)]:
        node=ML.create_material_expression(mat,unreal.MaterialExpressionScalarParameter)
        node.set_editor_property('parameter_name',label);node.set_editor_property('default_value',value)
        ML.connect_material_property(node,'',prop)
    ML.recompile_material(mat)
    assert ML.get_num_material_expressions(mat)==4
    for name,value in [('Roughness',roughness),('Metallic',metallic),('Specular',specular)]:
        assert abs(ML.get_material_default_scalar_parameter_value(mat,name)-value)<1e-5,(path,name)
    assert LIB.save_loaded_asset(mat,only_if_is_dirty=False)
    return mat

def import_roof(spec,materials):
    task=unreal.AssetImportTask()
    fbx=(ROOT/spec['fbx']).resolve()
    assert fbx.is_file() and fbx.is_relative_to(ROOT/'SourceAssets/GHS/MainRoof')
    task.filename=str(fbx);task.destination_path=ROOF_DEST+'/Meshes';task.destination_name=spec['name']
    task.automated=True;task.replace_existing=True;task.replace_existing_settings=True;task.save=False
    options=unreal.FbxImportUI()
    options.import_mesh=True;options.import_as_skeletal=False;options.import_materials=False;options.import_textures=False
    options.import_animations=False;options.automated_import_should_detect_type=False
    options.mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH
    data=options.static_mesh_import_data
    data.combine_meshes=True;data.generate_lightmap_u_vs=False;data.auto_generate_collision=False
    data.normal_import_method=unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
    task.options=options;TOOLS.import_asset_tasks([task])
    mesh=LIB.load_asset(ROOF_DEST+'/Meshes/'+spec['name'])
    assert isinstance(mesh,unreal.StaticMesh)
    slots=mesh.static_materials
    assert len(slots)==len(spec['material_roles'])
    for i,role in enumerate(spec['material_roles']):
        slot=slots[i]
        assert str(slot.material_slot_name)==spec['slot_names'][i],(i,str(slot.material_slot_name))
        slot.material_interface=materials[role];slots[i]=slot
    mesh.set_editor_property('static_materials',slots)
    bounds=mesh.get_bounds()
    for key,vec in [('min',bounds.origin-bounds.box_extent),('max',bounds.origin+bounds.box_extent)]:
        assert max(abs(float(a)-b) for a,b in zip((vec.x,vec.y,vec.z),spec['bounds_ue_cm'][key]))<2,(key,vec)
    assert LIB.save_loaded_asset(mesh,only_if_is_dirty=False)
    return mesh

report=dict(success=False,map=MAP,updated_meshes=[],created_roof=False)
try:
    assert not levels.is_in_play_in_editor()
    assert editor.get_editor_world().get_path_name().split('.')[0]==MAP
    dirty={p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()}
    target_tree_paths={f'/Game/GHSZcoolSmartFactory/Park/{kind}/{prefix}{role}'
        for role in TREE_ROLES for kind,prefix in [('Meshes','SM_GHSPark_'),('Materials','M_GHSPark_')]}
    assert not dirty.intersection(target_tree_paths), 'Target tree assets have unsaved edits'
    assert not any(p.startswith(ROOF_DEST+'/') for p in dirty), 'Roof assets have unsaved edits'
    before=snapshot()
    baseline=read(OUT/'Before/scene_state.json')
    assert before==baseline['actors'], 'Scene changed since the inspected baseline'
    manifest=read(ROOT/'SourceAssets/GHS/Park/park_manifest.json')
    original=read(OUT/'Before/park_manifest.json')
    assert read(ROOT/'SourceAssets/GHS/Park/site_geometry_report.json')==read(OUT/'Before/site_geometry_report.json')
    assert manifest['counts']==original['counts'] and manifest['triangles_total']==original['triangles_total']
    for old,new in zip(original['meshes'],manifest['meshes']):
        for key in ['name','vertices','triangles','bounds_ue_cm','instances','component_material_overrides']:
            assert old.get(key)==new.get(key),(old['name'],key)
    style=read(ROOT/'SourceAssets/GHS/Park/presentation_style.json')
    roof=read(ROOT/'SourceAssets/GHS/MainRoof/roof_manifest.json')
    backups=OUT/'Before/Assets';backups.mkdir(exist_ok=True)
    for path in target_tree_paths:
        src=ROOT/'Content'/(path.removeprefix('/Game/')+'.uasset')
        dst=backups/src.name
        if src.exists() and not dst.exists():shutil.copy2(src,dst)
    mats={role:material('/Game/GHSZcoolSmartFactory/Park/Materials/M_GHSPark_'+role,
                        manifest['materials'][role],style['tree_roughness'],specular=style['tree_specular']) for role in TREE_ROLES}
    importer=runpy.run_path(str(ROOT/'Scripts/ghs/apply_park_expansion.py'))
    for row in manifest['meshes']:
        if row['role'] in TREE_ROLES:
            importer['import_mesh'](row,mats);report['updated_meshes'].append(row['name'])
    roof_materials={role:material(ROOF_DEST+'/Materials/M_GHSRoof_'+role,spec['color_linear'],spec['roughness'],spec['metallic'])
                    for role,spec in roof['materials'].items()}
    mesh=import_roof(roof['mesh'],roof_materials)
    existing=[a for a in actors.get_all_level_actors() if a.get_actor_label()==ROOF_LABEL]
    assert len(existing)<=1
    if existing:
        actor=existing[0];assert actor.actor_has_tag('GHS_WarehouseRoof')
    else:
        actor=actors.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector())
        actor.set_actor_label(ROOF_LABEL);report['created_roof']=True
    actor.set_folder_path('GHS/Architecture/RemovableRoof')
    actor.tags=['GHS_WarehouseRoof','RemovableRoof','GHS_ArchitecturalContext']
    actor.set_actor_enable_collision(False);actor.set_actor_tick_enabled(False)
    actor.set_actor_hidden_in_game(False);actor.set_is_temporarily_hidden_in_editor(False)
    component=actor.get_component_by_class(unreal.StaticMeshComponent)
    component.set_static_mesh(mesh);component.set_mobility(unreal.ComponentMobility.STATIC)
    component.set_collision_profile_name('NoCollision');component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    component.set_editor_property('cast_shadow',True)
    for obj in actors.get_all_level_actors():
        light=obj.get_component_by_class(unreal.DirectionalLightComponent)
        if light:light.set_editor_property('light_source_angle',style['directional_source_angle'])
        if isinstance(obj,unreal.PostProcessVolume):
            settings=obj.get_editor_property('settings')
            for key,value in [('ambient_occlusion_intensity',style['ambient_occlusion_intensity']),
                              ('ambient_occlusion_radius',style['ambient_occlusion_radius_cm'])]:
                settings.set_editor_property('override_'+key,True);settings.set_editor_property(key,value)
            obj.set_editor_property('settings',settings)
    assert snapshot()==before, 'Unrelated actor transform, material or instance changed'
    assert {p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()}==dirty
    assert levels.save_current_level()
    report.update(success=True,saved=True,preserved_existing_actors=len(before),
                  actor_count=len(actors.get_all_level_actors()),roof_label=ROOF_LABEL,
                  roof_asset=mesh.get_path_name(),roof_triangles=roof['mesh']['triangles'],
                  roof_manifest_sha256=sha(ROOT/'SourceAssets/GHS/MainRoof/roof_manifest.json'),
                  park_manifest_sha256=sha(ROOT/'SourceAssets/GHS/Park/park_manifest.json'),
                  map_sha256=sha(ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'),
                  style=style,unsaved_unrelated_assets_preserved=sorted(dirty))
except Exception:
    report['error']=traceback.format_exc();unreal.log_error(report['error'])
(OUT/'apply_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
assert report['success'],report.get('error')
unreal.log('GHS_ROOF_STYLE_APPLIED')
