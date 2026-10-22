"""Import the independent office glazing without touching existing geometry."""
import hashlib
import json
from pathlib import Path
import runpy
import traceback
import unreal

ROOT=Path('D:/UEPro/Test');OUT=ROOT/'Saved/OfficeFacade'
MAP='/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
DEST='/Game/GHSZcoolSmartFactory/OfficeFacade'
LABEL='GHS_OfficeGlassFacade'
LIB=unreal.EditorAssetLibrary;ML=unreal.MaterialEditingLibrary
TOOLS=unreal.AssetToolsHelpers.get_asset_tools()
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def snapshot():
    fn=runpy.run_path(str(ROOT/'Scripts/ghs/validate_park_expansion.py'))['snapshot']
    return sorted([fn(a,unreal) for a in actors.get_all_level_actors() if a.get_actor_label()!=LABEL],key=lambda r:r['label'])

def material(role,spec):
    folder=DEST+'/Materials';name='M_GHSFacade_'+role;path=folder+'/'+name
    LIB.make_directory(folder)
    mat=LIB.load_asset(path) if LIB.does_asset_exist(path) else TOOLS.create_asset(name,folder,unreal.Material,unreal.MaterialFactoryNew())
    while ML.get_num_material_expressions(mat):
        previous=ML.get_num_material_expressions(mat)
        ML.delete_all_material_expressions(mat)
        assert ML.get_num_material_expressions(mat)<previous
    tint=ML.create_material_expression(mat,unreal.MaterialExpressionVectorParameter)
    tint.set_editor_property('parameter_name','SurfaceTint')
    tint.set_editor_property('default_value',unreal.LinearColor(*spec['color_linear'],1.))
    ML.connect_material_property(tint,'',unreal.MaterialProperty.MP_BASE_COLOR)
    # Restrained view-dependent blue reflection: opaque glazing keeps the
    # original CAD walls intact and works with this scene's reflection method.
    if role=='Glass':
        edge=ML.create_material_expression(mat,unreal.MaterialExpressionVectorParameter)
        edge.set_editor_property('parameter_name','GrazingTint')
        edge.set_editor_property('default_value',unreal.LinearColor(.065,.15,.24,1.))
        fresnel=ML.create_material_expression(mat,unreal.MaterialExpressionFresnel)
        fresnel.set_editor_property('exponent',3.)
        fresnel.set_editor_property('base_reflect_fraction',.04)
        mix=ML.create_material_expression(mat,unreal.MaterialExpressionLinearInterpolate)
        ML.connect_material_expressions(tint,'',mix,'A')
        ML.connect_material_expressions(edge,'',mix,'B')
        ML.connect_material_expressions(fresnel,'',mix,'Alpha')
        ML.connect_material_property(mix,'',unreal.MaterialProperty.MP_BASE_COLOR)
    for name,value,prop in [('Roughness',spec['roughness'],unreal.MaterialProperty.MP_ROUGHNESS),
                            ('Metallic',spec['metallic'],unreal.MaterialProperty.MP_METALLIC),
                            ('Specular',spec.get('specular',.15),unreal.MaterialProperty.MP_SPECULAR)]:
        node=ML.create_material_expression(mat,unreal.MaterialExpressionScalarParameter)
        node.set_editor_property('parameter_name',name);node.set_editor_property('default_value',value)
        ML.connect_material_property(node,'',prop)
    ML.recompile_material(mat)
    assert abs(ML.get_material_default_scalar_parameter_value(mat,'Roughness')-spec['roughness'])<1e-5
    assert LIB.save_loaded_asset(mat,only_if_is_dirty=False)
    return mat

def import_mesh(spec,materials):
    fbx=(ROOT/spec['fbx']).resolve()
    assert fbx.is_file() and fbx.is_relative_to(ROOT/'SourceAssets/GHS/OfficeFacade')
    task=unreal.AssetImportTask()
    task.filename=str(fbx);task.destination_path=DEST+'/Meshes';task.destination_name=spec['name']
    task.automated=True;task.replace_existing=True;task.replace_existing_settings=True;task.save=False
    options=unreal.FbxImportUI()
    options.import_mesh=True;options.import_as_skeletal=False
    options.import_materials=False;options.import_textures=False;options.import_animations=False
    options.automated_import_should_detect_type=False
    options.mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH
    data=options.static_mesh_import_data
    data.combine_meshes=True;data.generate_lightmap_u_vs=False;data.auto_generate_collision=False
    data.normal_import_method=unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
    task.options=options;TOOLS.import_asset_tasks([task])
    mesh=LIB.load_asset(DEST+'/Meshes/'+spec['name'])
    assert isinstance(mesh,unreal.StaticMesh)
    slots=mesh.static_materials
    assert len(slots)==len(spec['material_roles'])==5
    for i,role in enumerate(spec['material_roles']):
        slot=slots[i];assert str(slot.material_slot_name)==spec['slot_names'][i]
        slot.material_interface=materials[role];slots[i]=slot
    mesh.set_editor_property('static_materials',slots)
    bounds=mesh.get_bounds()
    for key,vec in [('min',bounds.origin-bounds.box_extent),('max',bounds.origin+bounds.box_extent)]:
        assert max(abs(float(a)-b) for a,b in zip((vec.x,vec.y,vec.z),spec['bounds_ue_cm'][key]))<2.,(key,vec)
    assert LIB.save_loaded_asset(mesh,only_if_is_dirty=False)
    return mesh

report=dict(success=False,map=MAP)
try:
    assert not levels.is_in_play_in_editor()
    assert editor.get_editor_world().get_path_name().split('.')[0]==MAP
    assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages(), 'Save existing scene edits before applying the facade'
    dirty={p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()}
    assert not any(p.startswith(DEST+'/') for p in dirty),'Target facade assets have unsaved edits'
    before=snapshot();baseline=read(OUT/'Before/scene_state.json')
    assert before==baseline['actors'],'Existing actors changed since baseline'
    spec=read(ROOT/'SourceAssets/GHS/OfficeFacade/facade_manifest.json')
    materials={role:material(role,values) for role,values in spec['materials'].items()}
    mesh=import_mesh(spec['mesh'],materials)
    existing=[a for a in actors.get_all_level_actors() if a.get_actor_label()==LABEL]
    assert len(existing)<=1
    if existing:
        actor=existing[0];assert actor.actor_has_tag('GHS_OfficeFacade')
    else:
        actor=actors.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector())
        actor.set_actor_label(LABEL)
    actor.set_folder_path('GHS/Architecture/OfficeFacade')
    actor.tags=['GHS_OfficeFacade','GHS_ArchitecturalContext']
    actor.set_actor_enable_collision(False);actor.set_actor_tick_enabled(False)
    actor.set_actor_hidden_in_game(False);actor.set_is_temporarily_hidden_in_editor(False)
    component=actor.get_component_by_class(unreal.StaticMeshComponent)
    component.set_static_mesh(mesh);component.set_mobility(unreal.ComponentMobility.STATIC)
    component.set_collision_profile_name('NoCollision')
    component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    component.set_editor_property('cast_shadow',True)
    assert snapshot()==before,'Unrelated actors changed during import'
    assert {p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()}==dirty
    assert levels.save_current_level()
    report.update(success=True,saved=True,preserved_existing_actors=len(before),
        actor_count=len(actors.get_all_level_actors()),facade_asset=mesh.get_path_name(),
        triangles=spec['mesh']['triangles'],manifest_sha256=sha(ROOT/'SourceAssets/GHS/OfficeFacade/facade_manifest.json'),
        map_sha256=sha(ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'))
except Exception:
    report['error']=traceback.format_exc();unreal.log_error(report['error'])
(OUT/'apply_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
assert report['success'],report.get('error')
unreal.log('GHS_OFFICE_FACADE_APPLIED')
