"""Apply the prepared Crossing_04 asphalt inlay without saving or opening a map."""
from pathlib import Path
from apply_mpr_site_round2 import legacy_fbx,check_bounds,package,require,sha,read

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'SourceAssets/MPR/crossing_surface_20261105'
MAP='/Game/Maps/MPR_CAD_Warehouse_B50B57'
DEST='/Game/MPRWarehouse/CrossingSurface20261105'
OWNER='mpr-crossing-surface-20261105'
TAG_OWNER='MPRCrossingSurface.Owner'
TAG_SHA='MPRCrossingSurface.SourceSHA256'
ROAD_ROLE='MPR4_TerminalAsphalt'

def source_inputs():
    manifest=read(SOURCE/'manifest.json');audit=read(SOURCE/'geometry_audit.json');validation=read(SOURCE/'geometry_validation.json')
    require(manifest['map']==MAP and manifest.get('crossing_surface')is True and manifest['crossing_id']=='Crossing_04','Wrong crossing manifest')
    require(validation['success']and validation['payload_sha256']==sha(SOURCE/'geometry_payload.json.gz'),'Crossing validation is stale')
    require(manifest['mesh_mappings']==audit['mesh_mappings']and not manifest['remove_mesh_names'],'Unreviewed crossing mapping/removal')
    require(len(manifest['meshes'])==len(manifest['mesh_mappings'])==8,'Unexpected crossing asset count')
    for row in manifest['meshes']:
        path=(ROOT/row['fbx']).resolve()
        require(path.is_relative_to(SOURCE.resolve())and path.suffix=='.fbx'and sha(path)==row['sha256'],'Invalid crossing FBX')
    if manifest.get('residual_material_cleanup'):
        residual=read(SOURCE/'residual_material_validation.json')
        rows=[r for r in manifest['meshes']if r['name']==residual['mesh_name']]
        require(residual['success']and residual['crossing_id']=='Crossing_04'and residual['road_id']=='TPX_ROADS_AXES_C08',
            'Wrong residual material scope')
        require(len(rows)==1 and rows[0]['sha256']==residual['final_fbx_sha256']and residual['positions_and_faces_exact']
            and residual['uv_exact']and residual['edge_fade_colors_exact']and not residual['other_crossings_changed'],
            'Residual material validation is stale')
    if manifest.get('corridor_residual_cleanup'):
        ballast=read(SOURCE/'residual_ballast_validation.json')
        rows=[r for r in manifest['meshes']if r['name']==ballast['mesh_name']]
        require(ballast['success']and ballast['crossing_id']=='Crossing_04'and ballast['road_id']=='TPX_ROADS_AXES_C08',
            'Wrong residual ballast scope')
        require(len(rows)==1 and rows[0]['sha256']==ballast['final_fbx_sha256']and ballast['remaining_ballast_in_mask_m2']<1e-8
            and ballast['outside_clip_difference_m2']<1e-8 and ballast['road_ramp_and_steel_files_unchanged']
            and ballast['other_crossings_unchanged'],'Residual ballast validation is stale')
    for p,digest in manifest['source_hashes'].items():
        source=(ROOT/p).resolve()
        require(source.is_relative_to((ROOT/'SourceAssets/MPR').resolve())and sha(source)==digest,'Existing source changed: '+p)
    return manifest

def plan_from_snapshot(snapshot,manifest):
    require(snapshot['map']==MAP,'Wrong open map')
    answer=[]
    for mapping in manifest['mesh_mappings']:
        matches=[(a,c)for a in snapshot['actors']for c in a['components']
            if (c.get('mesh')or '').split('.')[0]in{mapping['old_mesh'],mapping['new_mesh']}]
        require(len(matches)==1,'Missing/duplicate crossing component: '+mapping['name'])
        actor,component=matches[0]
        require(actor['class']=='/Script/Engine.StaticMeshActor'and component['class']=='/Script/Engine.StaticMeshComponent','Instanced/custom crossing target')
        answer.append(dict(**mapping,guid=actor['guid'],actor_path=actor['path'],component=component['name'],
            before_mesh=component['mesh'].split('.')[0]))
    states={item['before_mesh']==item['new_mesh']for item in answer}
    require(len(states)==1,'Partially applied crossing update requires explicit recovery')
    return answer

def apply(u):
    from mpr_transport_cleanup import live_snapshot
    require(Path(u.Paths.convert_relative_path_to_full(u.Paths.project_dir())).resolve()==ROOT,'Wrong UE project')
    manifest=source_inputs();snapshot,actors=live_snapshot(u);plan=plan_from_snapshot(snapshot,manifest)
    if all(item['before_mesh']==item['new_mesh']for item in plan):
        return dict(success=True,already_applied=True,assets=[],changed_components=[],deleted_guids=[],map_saved=False)
    components={package(c.static_mesh):c for actor in actors.values()for c in actor.get_components_by_class(u.StaticMeshComponent)if c.static_mesh}
    rows={row['name']:row for row in manifest['meshes']};prepared={}
    for item in plan:
        component=components[item['before_mesh']];old_roles=item['old_material_roles'];new_roles=item['new_material_roles']
        slots=component.static_mesh.static_materials
        require([str(s.get_editor_property('imported_material_slot_name'))for s in slots]==old_roles,'Existing crossing material slots changed')
        static={role:slots[i].material_interface for i,role in enumerate(old_roles)}
        overrides=list(component.get_editor_property('override_materials'))
        effective={role:component.get_material(i)for i,role in enumerate(old_roles)}
        new_overrides=[]
        if item['material_reference_mesh']:
            reference=components.get(item['material_reference_mesh'])
            require(reference is not None and reference.get_num_materials()==1,'C08 road material reference is missing/ambiguous')
            road=reference.get_material(0);require(road is not None,'Missing C08 effective asphalt material')
            static[ROAD_ROLE]=road;effective[ROAD_ROLE]=road
            for role in new_roles:
                index=old_roles.index(role)if role in old_roles else None
                new_overrides.append(road if role==ROAD_ROLE else(overrides[index]if index is not None and index<len(overrides)else None))
        else:new_overrides=overrides
        materials=[static[role]for role in new_roles]
        require(all(materials),'Null crossing material reference')
        prepared[item['name']]=dict(component=component,materials=materials,overrides=new_overrides,
            old_overrides=[package(m)for m in overrides],old_materials=[package(component.get_material(i))for i in range(len(old_roles))],
            expected_materials=[package(effective[role])for role in new_roles])
    assets=[]
    with legacy_fbx(u):
        for item in plan:
            state=prepared[item['name']]
            state['mesh'],report=import_mesh(u,rows[item['name']],state['materials']);assets.append(report)
    changed=[]
    for item in plan:
        state=prepared[item['name']];component=state['component']
        require(component.set_static_mesh(state['mesh']),'Cannot replace crossing mesh')
        if item['material_reference_mesh']:component.set_editor_property('override_materials',state['overrides'])
        effective=[package(component.get_material(i))for i in range(len(item['new_material_roles']))]
        overrides=[package(m)for m in component.get_editor_property('override_materials')]
        require(effective==state['expected_materials'],'Effective crossing materials differ from reviewed references')
        require(overrides==[package(m)for m in state['overrides']],'Crossing overrides did not preserve/remap as planned')
        changed.append(dict(guid=item['guid'],actor_path=item['actor_path'],component=item['component'],name=item['name'],
            before_mesh=item['before_mesh'],after_mesh=package(state['mesh']),before_materials=state['old_materials'],after_materials=effective,
            before_overrides=state['old_overrides'],after_overrides=overrides))
    after,_=live_snapshot(u);verified=plan_from_snapshot(after,manifest)
    require(all(item['before_mesh']==item['new_mesh']for item in verified),'Crossing mesh verification failed')
    return dict(success=True,already_applied=False,map=MAP,map_saved=False,namespace=DEST,assets=assets,
        changed_components=changed,deleted_guids=[],deleted_actors=[],expected_actor_count_change=0,
        manifest_sha256=sha(SOURCE/'manifest.json'))

def refine_owned_meshes(u):
    """Reimport verified owned ramp/corridor assets; no actor or map edits."""
    require(Path(u.Paths.convert_relative_path_to_full(u.Paths.project_dir())).resolve()==ROOT,'Wrong UE project')
    manifest=source_inputs();validation=read(SOURCE/'ramp_normals_validation.json')
    require(validation['success'],'Ramp normals have not passed source validation')
    ramps={'SM_MPRR_CrossingRamp_-1_-3','SM_MPRR_CrossingRamp_0_-3'}
    corridor={r['name']for r in manifest['meshes']if r.get('corridor_residual_cleanup')}
    require(corridor in(set(),{'SM_MPRR_RailCorridor_0_-3'}),'Unexpected residual ballast scope')
    names=ramps|corridor
    # Source topology is checked exactly by the FBX verifier. UE rebuilds its
    # render buffers after a normal-only reimport, so audit native counts
    # separately from the unchanged source polygons.
    previous_native={'SM_MPRR_CrossingRamp_-1_-3':108,'SM_MPRR_CrossingRamp_0_-3':1205}
    native_triangles={'SM_MPRR_CrossingRamp_-1_-3':108,'SM_MPRR_CrossingRamp_0_-3':1199}
    rows=[r for r in manifest['meshes']if r['name']in names]
    require(len(rows)==len(names) and set(validation['meshes'])==ramps,'Unexpected refinement scope')
    lib=u.EditorAssetLibrary;subsystem=u.get_editor_subsystem(u.StaticMeshEditorSubsystem);assets=[]
    with legacy_fbx(u):
        for row in rows:
            target=DEST+'/Meshes/'+row['name'];mesh=lib.load_asset(target)
            require(isinstance(mesh,u.StaticMesh)and lib.get_metadata_tag(mesh,TAG_OWNER)==OWNER,'Unowned ramp refinement target')
            previous=lib.get_metadata_tag(mesh,TAG_SHA)
            require(previous in{row['sha256'],row['approved_previous_sha256']},'Unexpected ramp source version')
            before_triangles=mesh.get_num_triangles(0)
            if row['name']in ramps:
                require(before_triangles in {previous_native[row['name']],native_triangles[row['name']]},'Existing ramp render count differs')
            before_materials=[s.material_interface for s in mesh.static_materials]
            before_slots=[str(s.get_editor_property('imported_material_slot_name'))for s in mesh.static_materials]
            require(before_slots==row['material_roles'],'Existing ramp slots changed')
            if previous==row['sha256']:
                if row['name']in ramps:require(mesh.get_num_triangles(0)==native_triangles[row['name']],'Refined ramp render count differs')
                assets.append(dict(package=target,reused=True,source_sha256=previous,
                    triangles=mesh.get_num_triangles(0),previous_native_triangles=previous_native.get(row['name'],before_triangles),
                    source_triangles=row['triangles'],local_ballast_clipping=row['name']in corridor,
                    vertices_moved=False,**check_bounds(mesh,row)));continue
            data=mesh.get_editor_property('asset_import_data')
            require(isinstance(data,u.FbxStaticMeshImportData),'Expected owned legacy FBX ramp')
            for key,value in dict(combine_meshes=True,auto_generate_collision=False,generate_lightmap_u_vs=False,
                convert_scene=True,convert_scene_unit=True,force_front_x_axis=False,
                vertex_color_import_option=u.VertexColorImportOption.REPLACE,
                normal_import_method=u.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS,
                normal_generation_method=u.FBXNormalGenerationMethod.BUILT_IN).items():data.set_editor_property(key,value)
            options=u.FbxImportUI()
            for key,value in dict(import_mesh=True,import_as_skeletal=False,import_materials=False,import_textures=False,
                import_animations=False,mesh_type_to_import=u.FBXImportType.FBXIT_STATIC_MESH,
                automated_import_should_detect_type=False).items():options.set_editor_property(key,value)
            for key,value in dict(combine_meshes=True,auto_generate_collision=False,generate_lightmap_u_vs=False,
                convert_scene=True,convert_scene_unit=True,force_front_x_axis=False,
                vertex_color_import_option=u.VertexColorImportOption.REPLACE,
                normal_import_method=u.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS,
                normal_generation_method=u.FBXNormalGenerationMethod.BUILT_IN).items():options.static_mesh_import_data.set_editor_property(key,value)
            task=u.AssetImportTask()
            for key,value in dict(filename=str(ROOT/row['fbx']),destination_path=DEST+'/Meshes',destination_name=row['name'],
                automated=True,replace_existing=True,replace_existing_settings=False,save=False).items():task.set_editor_property(key,value)
            task.options=options;task.factory=u.FbxFactory()
            u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
            require({str(p).split('.')[0]for p in task.imported_object_paths}=={target},'Unexpected ramp reimport output')
            mesh=lib.load_asset(target);slots=mesh.static_materials
            require([str(s.get_editor_property('imported_material_slot_name'))for s in slots]==before_slots,'Reimport changed ramp slot names')
            for i,slot in enumerate(slots):slot.material_interface=before_materials[i];slots[i]=slot
            mesh.set_editor_property('static_materials',slots)
            for lod in range(subsystem.get_lod_count(mesh)):
                settings=subsystem.get_lod_build_settings(mesh,lod)
                settings.recompute_normals=False;settings.recompute_tangents=True;settings.use_full_precision_u_vs=True;settings.generate_lightmap_u_vs=False
                subsystem.set_lod_build_settings(mesh,lod,settings)
            if row['name']in ramps:require(mesh.get_num_triangles(0)==native_triangles[row['name']],'Ramp triangle count changed')
            else:require(0<mesh.get_num_triangles(0)<=row['triangles'],'Invalid clipped ballast render count')
            require([package(s.material_interface)for s in mesh.static_materials]==[package(m)for m in before_materials],'Ramp materials changed')
            bounds=check_bounds(mesh,row)
            lib.set_metadata_tag(mesh,TAG_SHA,row['sha256'])
            require(lib.save_loaded_asset(mesh,only_if_is_dirty=False),'Could not save refined ramp')
            assets.append(dict(package=target,reused=False,before_sha256=previous,after_sha256=row['sha256'],
                triangles=mesh.get_num_triangles(0),previous_native_triangles=previous_native.get(row['name'],before_triangles),
                source_triangles=row['triangles'],material_slots=before_slots,vertices_moved=False,
                local_ballast_clipping=row['name']in corridor,**bounds))
    return dict(success=True,assets=assets,map_saved=False,actor_changes=[],road_ramp_rail_positions_unchanged=True,
        geometry_unchanged=not corridor,clipped_ballast_meshes=sorted(corridor))


def import_mesh(u,row,materials):
    lib=u.EditorAssetLibrary;target=DEST+'/Meshes/'+row['name']
    if lib.does_asset_exist(target):
        mesh=lib.load_asset(target)
        require(isinstance(mesh,u.StaticMesh),'Destination is not a StaticMesh: '+target)
        require(lib.get_metadata_tag(mesh,TAG_OWNER)==OWNER and lib.get_metadata_tag(mesh,TAG_SHA)==row['sha256'],'Unowned or changed destination asset: '+target)
        require([package(s.material_interface)for s in mesh.static_materials]==[package(m)for m in materials],'Reused mesh materials differ from current references')
        return mesh,dict(package=target,reused=True,fbx_sha256=row['sha256'],**check_bounds(mesh,row))
    task=u.AssetImportTask()
    for key,value in dict(filename=str(ROOT/row['fbx']),destination_path=DEST+'/Meshes',destination_name=row['name'],
                          automated=True,replace_existing=False,replace_existing_settings=False,save=False).items():task.set_editor_property(key,value)
    options=u.FbxImportUI()
    for key,value in dict(import_mesh=True,import_as_skeletal=False,import_materials=False,import_textures=False,import_animations=False,
                          mesh_type_to_import=u.FBXImportType.FBXIT_STATIC_MESH,automated_import_should_detect_type=False).items():options.set_editor_property(key,value)
    data=options.static_mesh_import_data
    for key,value in dict(combine_meshes=True,auto_generate_collision=False,generate_lightmap_u_vs=False,convert_scene=True,
                          convert_scene_unit=True,force_front_x_axis=False,vertex_color_import_option=u.VertexColorImportOption.REPLACE,
                          normal_import_method=u.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS,
                          normal_generation_method=u.FBXNormalGenerationMethod.BUILT_IN).items():data.set_editor_property(key,value)
    task.options=options;task.factory=u.FbxFactory()
    u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    require({str(p).split('.')[0]for p in task.imported_object_paths}=={target},'Import produced unexpected objects')
    mesh=lib.load_asset(target);require(isinstance(mesh,u.StaticMesh),'Expected mesh was not imported')
    bounds=check_bounds(mesh,row);slots=mesh.static_materials
    require(len(slots)==len(row['material_roles'])==len(materials),'Material slot count changed')
    require([str(s.get_editor_property('imported_material_slot_name'))for s in slots]==row['material_roles'],'Imported material slot order changed')
    for i,slot in enumerate(slots):slot.material_interface=materials[i];slots[i]=slot
    mesh.set_editor_property('static_materials',slots)
    subsystem=u.get_editor_subsystem(u.StaticMeshEditorSubsystem)
    for lod in range(subsystem.get_lod_count(mesh)):
        settings=subsystem.get_lod_build_settings(mesh,lod)
        settings.use_full_precision_u_vs=True;settings.recompute_tangents=True;settings.generate_lightmap_u_vs=False
        subsystem.set_lod_build_settings(mesh,lod,settings)
    require(subsystem.get_simple_collision_count(mesh)==0 and subsystem.get_convex_collision_count(mesh)==0,'Unexpected generated collision')
    lib.set_metadata_tag(mesh,TAG_OWNER,OWNER);lib.set_metadata_tag(mesh,TAG_SHA,row['sha256'])
    require(lib.save_loaded_asset(mesh,only_if_is_dirty=False),'Could not save new transport mesh')
    return mesh,dict(package=target,reused=False,fbx_sha256=row['sha256'],material_references=[package(m)for m in materials],
        lod_triangles=[mesh.get_num_triangles(i)for i in range(subsystem.get_lod_count(mesh))],**bounds)
