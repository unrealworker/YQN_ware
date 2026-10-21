"""Add the satellite-referenced campus to the current Zcool map only.

Generate SourceAssets/GHS/Park first. Run from the live editor dispatcher.
All new content is private to the Park folder and can be rebuilt in place.
"""
import hashlib
import json
import math
import shutil
import traceback
from pathlib import Path
import unreal

ROOT = Path('D:/UEPro/Test')
OUT = ROOT/'Saved/ParkExpansion'
DEST = '/Game/GHSZcoolSmartFactory/Park'
MAP = '/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
TAG = 'GHS_ParkContext'
PREFIX = 'GHSPark_'
EDITOR = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
ACTORS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
LEVELS = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
LIB = unreal.EditorAssetLibrary
TOOLS = unreal.AssetToolsHelpers.get_asset_tools()
ML = unreal.MaterialEditingLibrary

def read(path): return json.loads(path.read_text(encoding='utf-8-sig'))
def write(path, value): path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def xyz(v): return [float(v.x),float(v.y),float(v.z)]

def material(role, rgb):
    name='M_GHSPark_'+role
    path=DEST+'/Materials/'+name
    mat=LIB.load_asset(path) if LIB.does_asset_exist(path) else TOOLS.create_asset(name,DEST+'/Materials',unreal.Material,unreal.MaterialFactoryNew())
    while ML.get_num_material_expressions(mat):
        count=ML.get_num_material_expressions(mat)
        ML.delete_all_material_expressions(mat)
        assert ML.get_num_material_expressions(mat)<count
    color=ML.create_material_expression(mat,unreal.MaterialExpressionVectorParameter)
    color.set_editor_property('parameter_name','SurfaceTint')
    color.set_editor_property('default_value',unreal.LinearColor(*rgb,1))
    ML.connect_material_property(color,'',unreal.MaterialProperty.MP_BASE_COLOR)
    for name,value,prop in [('Roughness',.88,unreal.MaterialProperty.MP_ROUGHNESS),('Specular',.20,unreal.MaterialProperty.MP_SPECULAR)]:
        node=ML.create_material_expression(mat,unreal.MaterialExpressionScalarParameter)
        node.set_editor_property('parameter_name',name)
        node.set_editor_property('default_value',value)
        ML.connect_material_property(node,'',prop)
    mat.set_editor_property('two_sided',False)
    ML.layout_material_expressions(mat)
    ML.recompile_material(mat)
    assert LIB.save_loaded_asset(mat,only_if_is_dirty=False)
    return mat

def import_mesh(row, mats):
    name=row['name']
    assert name.startswith('SM_GHSPark_')
    fbx=(ROOT/row['fbx']).resolve()
    assert fbx.is_relative_to(ROOT/'SourceAssets/GHS/Park') and fbx.is_file()
    task=unreal.AssetImportTask()
    task.filename=str(fbx); task.destination_path=DEST+'/Meshes'; task.destination_name=name
    task.automated=True; task.replace_existing=True; task.replace_existing_settings=True; task.save=False
    options=unreal.FbxImportUI()
    options.import_mesh=True; options.import_as_skeletal=False
    options.mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH
    options.automated_import_should_detect_type=False
    options.import_materials=False; options.import_textures=False; options.import_animations=False
    data=options.static_mesh_import_data
    data.combine_meshes=True; data.generate_lightmap_u_vs=False; data.auto_generate_collision=False
    data.normal_import_method=unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
    task.options=options
    TOOLS.import_asset_tasks([task])
    mesh=LIB.load_asset(DEST+'/Meshes/'+name)
    assert isinstance(mesh,unreal.StaticMesh),name
    slots=mesh.static_materials
    assert len(slots)==1,(name,len(slots))
    slot=slots[0]
    slot.material_interface=mats[row['role']]
    slots[0]=slot
    mesh.set_editor_property('static_materials',slots)
    assert mesh.get_material(0)==mats[row['role']], (name,'Material slot assignment did not persist')
    bounds=mesh.get_bounds()
    actual_min=xyz(bounds.origin-bounds.box_extent)
    actual_max=xyz(bounds.origin+bounds.box_extent)
    expected=row['bounds_ue_cm']
    assert max(abs(actual_min[i]-expected['min'][i]) for i in range(3))<2.0,(name,'minimum',actual_min,expected)
    assert max(abs(actual_max[i]-expected['max'][i]) for i in range(3))<2.0,(name,'maximum',actual_max,expected)
    assert LIB.save_loaded_asset(mesh,only_if_is_dirty=False)
    return mesh

def decorate(actor,label,folder):
    actor.set_actor_label(label)
    actor.set_folder_path('GHS/Park/'+folder)
    actor.tags=[TAG]
    actor.set_actor_enable_collision(False)
    actor.set_actor_tick_enabled(False)
    for component in actor.get_components_by_class(unreal.PrimitiveComponent):
        component.set_collision_profile_name('NoCollision')
        component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)

def capture_camera(label,center,distance,pitch,yaw):
    rotation=unreal.Rotator(pitch=pitch,yaw=yaw)
    eye=unreal.Vector(*center)-unreal.MathLibrary.get_forward_vector(rotation)*distance
    actor=ACTORS.spawn_actor_from_class(unreal.CameraActor,eye,rotation)
    decorate(actor,PREFIX+label,'Views')
    camera=actor.get_component_by_class(unreal.CameraComponent)
    camera.set_field_of_view(58.)
    camera.set_editor_property('constrain_aspect_ratio',False)
    return actor

def main():
    result=dict(success=False,map=MAP,new_actors=[],meshes=[])
    try:
        assert not LEVELS.is_in_play_in_editor(), 'Stop Play before importing the campus'
        assert EDITOR.get_editor_world().get_path_name().split('.')[0]==MAP
        assert (OUT/'scene_inspection.json').is_file() and (OUT/'map_before.umap').is_file()
        # Retry only our own packages after a failed import.
        assert all(p.get_path_name()==MAP for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())
        assert all(p.get_path_name().startswith(DEST+'/') for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
        baseline=read(OUT/'source_map_baseline.json')
        assert sha(Path(baseline['path']))==baseline['sha256']
        manifest=read(ROOT/'SourceAssets/GHS/Park/park_manifest.json')
        LIB.make_directory(DEST+'/Materials'); LIB.make_directory(DEST+'/Meshes')
        mats={role:material(role,rgb) for role,rgb in manifest['materials'].items()}
        meshes=[(row,import_mesh(row,mats)) for row in manifest['meshes']]
        # Only delete our explicitly tagged previous generated context.
        for actor in ACTORS.get_all_level_actors():
            if actor.get_actor_label().startswith(PREFIX):
                assert TAG in [str(t) for t in actor.tags]
                ACTORS.destroy_actor(actor)
        for row,mesh in meshes:
            actor=ACTORS.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector())
            label=PREFIX+row['name'].removeprefix('SM_GHSPark_')
            decorate(actor,label,'Geometry')
            component=actor.get_component_by_class(unreal.StaticMeshComponent)
            component.set_static_mesh(mesh)
            component.set_mobility(unreal.ComponentMobility.STATIC)
            component.set_editor_property('cast_shadow',row['role'] not in ('Hardstand','Roads','ContextRoads','Markings','Landscape'))
            result['new_actors'].append(label)
            result['meshes'].append(dict(name=row['name'],triangles=row['triangles'],bounds=xyz(mesh.get_bounds().box_extent)))
        by={a.get_actor_label():a for a in ACTORS.get_all_level_actors()}
        pawn=by['GHS_WarehouseCamera']
        center=(3000.,6000.,0.)
        # MaximumZoom is defaults-only in UniversalCamera. Keep its existing
        # 95,000 cm cap; the panel-adjusted overview remains below that cap.
        for key,value in dict(overview_center=unreal.Vector(*center),overview_distance=65000.,overview_pitch=-48.,overview_yaw=-110.,maximum_pan=unreal.Vector2D(55000,40000)).items():
            pawn.set_editor_property(key,value)
        overview=capture_camera('Overview',center,73000.,-53.,-105.)
        capture_camera('Yard',(-9000.,10200.,0.),40000.,-52.,-110.)
        capture_camera('SitePlan',center,72000.,-89.9,-90.)
        ACTORS.set_selected_level_actors([])
        EDITOR.set_level_viewport_camera_info(overview.get_actor_location(),overview.get_actor_rotation())
        assert LEVELS.save_current_level()
        assert sha(Path(baseline['path']))==baseline['sha256']
        result.update(success=True,saved=True,source_map_preserved=True,triangle_total=sum(r['triangles'] for r in manifest['meshes']),
            camera=dict(center=center,distance=65000,pitch=-48,yaw=-110),reference_accuracy='Satellite-referenced visual approximation; not cadastral survey')
    except Exception:
        result['error']=traceback.format_exc()
        unreal.log_error(result['error'])
    write(OUT/'apply_report.json',result)
    assert result['success'],result.get('error')
    unreal.log('GHS_PARK_APPLIED')

if __name__=='__main__': main()
