"""Apply reviewed transport meshes to the already open MPR level, without saving it.

apply(unreal) imports into a new asset namespace, keeps each component's existing
material references/overrides, swaps only listed meshes and removes exact empty
transport actors. The caller owns map preservation, saving and screenshots.
"""
from pathlib import Path
from apply_mpr_site_round2 import legacy_fbx,check_bounds,package,require,sha,read

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'SourceAssets/MPR/transport_cleanup_20261105'
MAP='/Game/Maps/MPR_CAD_Warehouse_B50B57'
OLD='/Game/MPRWarehouse/RebuildB50B57/Site/Meshes/'
DEST='/Game/MPRWarehouse/TransportCleanup20261105'
OWNER='mpr-transport-cleanup-20261105'
TAG_OWNER='MPRTransportCleanup.Owner'
TAG_SHA='MPRTransportCleanup.SourceSHA256'

def source_inputs():
    manifest=read(SOURCE/'manifest.json');validation=read(SOURCE/'geometry_validation.json')
    audit=read(SOURCE/'geometry_audit.json')
    require(manifest.get('map')==MAP and manifest.get('transport_cleanup') is True,'Wrong transport map or manifest')
    require(validation['success'] and validation['payload_sha256']==sha(SOURCE/'geometry_payload.json.gz'),'Geometry validation is stale')
    rows=manifest['meshes'];names={r['name']for r in rows};removed=set(manifest['remove_mesh_names'])
    require(len(rows)==len(names)==23 and len(removed)==7 and not names&removed,'Unexpected reviewed transport set')
    require(names==set(audit['mesh_names'])and removed==set(audit['remove_mesh_names']),'Manifest and geometry audit disagree')
    for row in rows:
        path=(ROOT/row['fbx']).resolve()
        require(path.is_relative_to(SOURCE.resolve())and path.suffix=='.fbx','FBX escaped new cleanup source directory')
        require(path.is_file()and sha(path)==row['sha256'],'FBX hash mismatch: '+row['name'])
        require(row['category']=='Site'and row['full_precision_uvs']is True and not row.get('instance_only'),'Unexpected import mode')
    for path,digest in manifest['source_hashes'].items():
        source=(ROOT/path).resolve()
        require(source.is_relative_to((ROOT/'SourceAssets/MPR').resolve()),'Input hash path escaped MPR sources')
        require(source.is_file()and sha(source)==digest,'Old transport source changed: '+path)
    return manifest,rows,sorted(removed)

def plan_from_snapshot(snapshot,rows,removed):
    """Pure preflight, also tested against the saved live-scene snapshot."""
    require(snapshot['map']==MAP,'Snapshot belongs to another map')
    wanted={r['name']for r in rows};removed=set(removed)
    replacements={};deletions={};attached={a.get('attachment_parent')for a in snapshot['actors']if a.get('attachment_parent')}
    for actor in snapshot['actors']:
        for component in actor['components']:
            mesh=(component.get('mesh')or '').split('.')[0]
            name=mesh.rsplit('/',1)[-1]
            if mesh not in {OLD+name,DEST+'/Meshes/'+name}:continue
            if name not in wanted|removed:continue
            require(actor['class']=='/Script/Engine.StaticMeshActor','Target is not a plain StaticMeshActor: '+name)
            require(component['class']=='/Script/Engine.StaticMeshComponent','Target is an instanced/custom component: '+name)
            identity=dict(guid=actor['guid'],actor_path=actor['path'],component=component['name'],name=name,before_mesh=mesh)
            if name in wanted:
                require(name not in replacements,'Duplicate target mesh component: '+name)
                replacements[name]=identity
            else:
                require(mesh==OLD+name,'Removed mesh unexpectedly uses new namespace: '+name)
                require(name not in deletions and len(actor['components'])==1,'Cannot delete mixed/duplicate mesh actor: '+name)
                require(not actor.get('attachment_parent')and actor['path']not in attached,'Cannot delete attached transport actor: '+name)
                deletions[name]=identity
    require(set(replacements)==wanted,'Missing reviewed transport mesh components: '+str(sorted(wanted-set(replacements))))
    already=all(v['before_mesh'].startswith(DEST+'/Meshes/')for v in replacements.values())
    require(set(deletions)==removed or(already and not deletions),'Partial/unreviewed transport removal state')
    return dict(replacements=[replacements[n]for n in sorted(replacements)],deletions=[deletions[n]for n in sorted(deletions)],already_applied=already and not deletions)

def live_snapshot(u):
    levels=u.get_editor_subsystem(u.LevelEditorSubsystem)
    world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    require(not levels.is_in_play_in_editor()and package(world)==MAP,'Open the existing MPR editor level outside PIE before applying transport cleanup')
    actors=list(u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors())
    rows=[]
    for actor in actors:
        rows.append(dict(guid=u.GuidLibrary.conv_guid_to_string(actor.get_editor_property('actor_guid')),
            path=actor.get_path_name(),class_=actor.get_class().get_path_name(),
            attachment_parent=actor.get_attach_parent_actor().get_path_name()if actor.get_attach_parent_actor()else None,
            components=[dict(name=c.get_name(),class_=c.get_class().get_path_name(),mesh=package(c.static_mesh))
                for c in actor.get_components_by_class(u.StaticMeshComponent)]))
    for actor in rows:
        actor['class']=actor.pop('class_')
        for component in actor['components']:component['class']=component.pop('class_')
    return dict(map=MAP,actors=rows),{a.get_path_name():a for a in actors}

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

def apply(u):
    """Return the exact allowed changes; deliberately does not save the level."""
    root=Path(u.Paths.convert_relative_path_to_full(u.Paths.project_dir())).resolve()
    require(root==ROOT,'Transport cleanup is running in another project')
    manifest,rows,removed=source_inputs();snapshot,actors=live_snapshot(u)
    plan=plan_from_snapshot(snapshot,rows,removed)
    targets={r['name']:r for r in plan['replacements']};prepared={};assets=[];changed=[]
    row_by_name={r['name']:r for r in rows}
    # Resolve every material and component before importing or changing actors.
    for name,item in targets.items():
        actor=actors[item['actor_path']]
        component=next(c for c in actor.get_components_by_class(u.StaticMeshComponent)if c.get_name()==item['component'])
        slots=component.static_mesh.static_materials
        require(len(slots)==len(row_by_name[name]['material_roles']),'Existing material slot count changed: '+name)
        require([str(s.get_editor_property('imported_material_slot_name'))for s in slots]==row_by_name[name]['material_roles'],'Existing slot order changed: '+name)
        materials=[s.material_interface for s in slots]
        require(all(materials),'Missing original material reference: '+name)
        overrides=list(component.get_editor_property('override_materials'))
        effective=[package(component.get_material(i))for i in range(len(slots))]
        prepared[name]=(component,materials,overrides,effective)
    with legacy_fbx(u):
        for row in rows:
            component,materials,overrides,effective=prepared[row['name']]
            mesh,asset_report=import_mesh(u,row,materials);assets.append(asset_report)
            prepared[row['name']]=(*prepared[row['name']],mesh)
    for name,item in targets.items():
        component,materials,overrides,effective,mesh=prepared[name]
        if component.static_mesh!=mesh:
            require(component.set_static_mesh(mesh),'Cannot replace mesh on '+name)
            # set_static_mesh preserves overrides in UE; explicitly verify both
            # the override array and effective materials, without clearing it.
            require([package(m)for m in component.get_editor_property('override_materials')]==[package(m)for m in overrides],'Component material overrides changed')
            require([package(component.get_material(i))for i in range(len(materials))]==effective,'Effective component materials changed')
            changed.append(dict(**item,after_mesh=package(mesh),materials=effective))
    deleted=[];subsystem=u.get_editor_subsystem(u.EditorActorSubsystem)
    for item in plan['deletions']:
        actor=actors[item['actor_path']]
        require(subsystem.destroy_actor(actor),'Could not remove exact empty transport actor: '+item['name'])
        deleted.append(item)
    after,_=live_snapshot(u);after_plan=plan_from_snapshot(after,rows,removed)
    require(after_plan['already_applied'],'Transport component replacement verification failed')
    return dict(success=True,map=MAP,map_saved=False,namespace=DEST,manifest_sha256=sha(SOURCE/'manifest.json'),
        assets=assets,changed_components=changed,deleted_actors=deleted,deleted_guids=[v['guid']for v in deleted],
        replaced_mesh_names=sorted(targets),removed_mesh_names=removed,already_applied=plan['already_applied'])
