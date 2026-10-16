"""Import Blender wall union meshes and replace only the three wall groups."""
import copy,hashlib,json,shutil,traceback
from datetime import datetime
from pathlib import Path
import unreal

ROOT=Path(r'D:\UEPro\Test');SOURCE=ROOT/'SourceAssets/GHS'
MAP='/Game/Maps/GHS_CAD_DigitalTwin';DEST='/Game/GHSDigitalTwin'
REPORT=ROOT/'Saved/GHS_JoinedWallsApplied.json'
spec=json.loads((SOURCE/'joined_walls.json').read_text())
geometry=json.loads((SOURCE/'joined_walls_geometry.json').read_text())
assert geometry['verification']['edge_outside_wall_area_m2']==0
assert geometry['verification']['all_loops_closed'] and geometry['verification']['all_source_ids_retained']
registry_path=SOURCE/'ue_scene_registry.json'
registry=json.loads(registry_path.read_text());before_registry=copy.deepcopy(registry)
groups={g['actor']:g for g in registry['groups']}
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
assert editor.get_editor_world().get_path_name().split('.')[0]==MAP
by_label={a.get_actor_label():a for a in actors.get_all_level_actors()}
assets=unreal.EditorAssetLibrary;asset_tools=unreal.AssetToolsHelpers.get_asset_tools()
mapping={
 'GHS_CAD_WallFaces':('SM_GHS_JoinedWallFaces','M_GHS_WallVolume'),
 'GHS_CAD_WallSections':('SM_GHS_JoinedWallSections','M_GHS_WallSection'),
 'GHS_CAD_WallEdges':('SM_GHS_JoinedWallEdges','M_GHS_WallTrim'),
}
report=dict(success=False,map=MAP,meshes=[],changes=[],source_wall_ids=[r['id'] for r in geometry['source_mapping']])
source_map=ROOT/'Content/Maps/VideoDigitalTwinWarehouse.umap'
source_sha=hashlib.sha256(source_map.read_bytes()).hexdigest()
try:
    assert levels.save_current_level()
    backup=ROOT/'Saved/Backups'/('GHS_WallJoints_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
    backup.mkdir(parents=True,exist_ok=True)
    shutil.copy2(ROOT/'Content/Maps/GHS_CAD_DigitalTwin.umap',backup/'GHS_CAD_DigitalTwin.umap')
    shutil.copy2(registry_path,backup/'ue_scene_registry.json')
    for name in ['GHS_BuildReport','GHS_InstanceMaterials','GHS_ClearanceVerification']:
        previous=ROOT/'Saved'/(name+'.json')
        if previous.is_file():shutil.copy2(previous,backup/previous.name)
    report['backup']=str(backup)
    mesh_by_name={}
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
        task.options=options;asset_tools.import_asset_tasks([task])
        mesh=assets.load_asset(DEST+'/Meshes/'+item['name']);assert mesh
        mat_name=next(mat for name,mat in mapping.values() if name==item['name'])
        material=assets.load_asset(DEST+'/Materials/Instanced/'+mat_name);assert material
        slots=mesh.get_editor_property('static_materials');assert len(slots)==1
        slots[0].set_editor_property('material_interface',material)
        mesh.set_editor_property('static_materials',slots)
        assert assets.save_loaded_asset(mesh,only_if_is_dirty=False)
        mesh_by_name[item['name']]=mesh
        bounds=mesh.get_bounds()
        report['meshes'].append(dict(name=item['name'],path=mesh.get_path_name(),material=material.get_path_name(),bounds_origin_cm=[bounds.origin.x,bounds.origin.y,bounds.origin.z],bounds_extent_cm=[bounds.box_extent.x,bounds.box_extent.y,bounds.box_extent.z]))
    for label,(mesh_name,mat_name) in mapping.items():
        actor=by_label[label];component=actor.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
        old_count=component.get_instance_count()
        component.clear_instances();component.set_static_mesh(mesh_by_name[mesh_name])
        component.set_material(0,assets.load_asset(DEST+'/Materials/Instanced/'+mat_name))
        component.add_instance(unreal.Transform(location=unreal.Vector(0,0,0),rotation=unreal.Rotator(pitch=0,yaw=0,roll=0),scale=unreal.Vector(1,1,1)),world_space=True)
        assert component.get_instance_count()==1
        actor.set_editor_property('tags',['GHSDigitalTwin','HISMGroup','WallJointsCorrected','InstanceCount=1'])
        actor.set_is_temporarily_hidden_in_editor(False)
        source_handles=sorted({h for row in geometry['source_mapping'] for h in row['source_handles']})
        groups[label].update(mesh=mesh_name,count=1,material_override=mat_name.replace('M_GHS_','M_VR_'),instances=[dict(id=mesh_name,position_m=[0,0,0],rotation_deg=0,scale=[1,1,1],source_handles=source_handles,source_wall_ids=report['source_wall_ids'],geometry_source='joined_walls_geometry.json')])
        report['changes'].append(dict(actor=label,before_instances=old_count,after_instances=1))
    assert registry['individuals']==before_registry['individuals']
    assert all(g==next(old for old in before_registry['groups'] if old['actor']==g['actor']) for g in registry['groups'] if g['actor'] not in mapping)
    registry['joined_walls_geometry']='SourceAssets/GHS/joined_walls_geometry.json'
    registry['wall_joint_policy']='Union exact CAD wall rectangles; only exposed perimeter; inward 12mm edge band; no snapping or positive buffer'
    registry_path.write_text(json.dumps(registry,indent=2))
    material_path=ROOT/'Saved/GHS_InstanceMaterials.json';materials=json.loads(material_path.read_text())
    materials['groups']=[dict(actor=g['actor'],materials=[by_label[g['actor']].get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent).get_material(i).get_path_name() for i in range(by_label[g['actor']].get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent).get_num_materials())]) for g in registry['groups']]
    material_path.write_text(json.dumps(materials,indent=2))
    assert levels.save_current_level()
    assert hashlib.sha256(source_map.read_bytes()).hexdigest()==source_sha
    build_path=ROOT/'Saved/GHS_BuildReport.json';build=json.loads(build_path.read_text())
    build.update(wall_joined_corrected=True,instanced_count=sum(g['count'] for g in registry['groups']),groups=[dict(actor=g['actor'],count=g['count'],mesh=g['mesh']) for g in registry['groups']])
    build_path.write_text(json.dumps(build,indent=2))
    report.update(success=True,source_level_sha256=source_sha,actor_count=len(actors.get_all_level_actors()),hism_group_count=len(registry['groups']),instanced_count=build['instanced_count'],non_wall_groups_and_individuals_preserved=True,geometry_verification=geometry['verification'])
    REPORT.write_text(json.dumps(report,indent=2))
    unreal.log('GHS_JOINED_WALLS_SAVED')
except Exception:
    report['error']=traceback.format_exc();REPORT.write_text(json.dumps(report,indent=2));raise
