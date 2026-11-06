"""Replace five current solar meshes with larger units; no map save or actors."""
from pathlib import Path
import math
import mpr_solar_hierarchy as base

ROOT = Path(__file__).resolve().parents[2]
SOURCE = 'SourceAssets/MPR/solar_units_20261106'
DEST = '/Game/MPRWarehouse/SolarUnits20261106'
OWNER = 'mpr-solar-units-20261106'
TAG_OWNER = 'MPRSolarUnits.Owner'
TAG_SHA = 'MPRSolarUnits.SourceSHA256'
require, read, sha, package = base.require, base.read, base.sha, base.package


def mesh_path(row):
    return DEST+'/Meshes/'+row['name']


def source_contract():
    manifest_path=ROOT/SOURCE/'manifest.json'
    manifest=read(manifest_path)
    validation=read(ROOT/SOURCE/'geometry_validation.json')
    previous, previous_report=base.source_contract()
    require(manifest['success'] and manifest['map']==base.MAP and manifest['namespace']==DEST,'wrong solar unit target')
    require(validation['success'] and validation['manifest_sha256']==sha(manifest_path),'unit geometry validation is stale')
    require(validation['all_lods_identical_top_masks'] and validation['old_assets_unchanged']
            and validation['all_original_cells_accounted_for']==5636 and validation['original_blocks_preserved']==59
            and validation['roof_devices_preserved']==195 and validation['minimum_device_clearance_m']>=.85,
            'unit geometry preservation failed')
    require(manifest['gap_m']==.08 and manifest['frame_width_m']==.015
            and manifest['standard_merge_cells']==[3,2] and manifest['visual_unit_count']==905,
            'visual-unit layout differs from reviewed 3x2 grouping')
    require(manifest['materials']==previous['materials'] and manifest['material_roles']==base.ROLES
            and manifest['material_paths']=={r:base.material_path(r) for r in base.ROLES},'existing final solar palette changed')
    require(manifest['preserved_blocks']==previous['preserved_blocks'],'59 original solar regions changed')
    for name,expected in manifest['source_hashes'].items():
        path=(ROOT/name).resolve()
        require(path.is_relative_to((ROOT/'SourceAssets/MPR').resolve()) and path.is_file() and sha(path)==expected,
                'previous solar source changed: '+name)
    require(sha(ROOT/SOURCE/'unit_layout.json')==manifest['unit_layout_sha256'],'unit layout changed')
    rows=manifest['meshes']
    require(len(rows)==5 and {r['bank']for r in rows}=={r['bank']for r in previous['meshes']},'unexpected solar banks')
    exports={r['name']:r for r in manifest['export_meshes']}
    require(len(exports)==15,'expected all 15 LOD FBXs')
    for row in rows:
        old=next(r for r in previous['meshes']if r['bank']==row['bank'])
        require(row['name']=='SM_MPRSU_SolarBank_'+row['bank'] and row['source_mesh']==base.mesh_path(old)
                and row['retained_actor_label']==old['retained_actor_label'],'solar identity changed')
        require(row['material_roles']==base.ROLES and row['lod_material_roles']==[base.ROLES]*3
                and row['all_lod_material_roles']==base.ROLES,'solar material order changed')
        require(len(row['lod_files'])==len(row['lod_sha256'])==2 and row['lod_screen_sizes']==old['lod_screen_sizes'],
                'solar LOD policy changed')
        require(row['collision'] is False and row['nanite'] is False and row['full_precision_uvs'] is True,
                'unit render policy changed')
        require(len(row['bounds_m'])==3 and all(len(p)==2 and p[0]<p[1] and all(math.isfinite(v)for v in p)
                for p in row['bounds_m']),'invalid bounds')
        for lod,(name,expected)in enumerate(zip([row['fbx'],*row['lod_files']],[row['sha256'],*row['lod_sha256']])):
            path=(ROOT/name).resolve()
            label=row['name']+(''if lod==0 else '_LOD'+str(lod))
            require(path.is_relative_to((ROOT/SOURCE).resolve()) and path.name==label+'.fbx' and sha(path)==expected,
                    'unit FBX/hash mismatch')
            require(exports[label]['sha256']==expected and exports[label]['triangles']==row['lod_triangles'][lod],
                    'LOD export/import rows differ')
    require([sum(r['lod_triangles'][i]for r in rows)for i in range(3)]==validation['triangle_counts']==[14086,5036,5036],
            'unit triangle budget changed')
    return manifest,dict(manifest_sha256=sha(manifest_path),geometry_validation_sha256=sha(ROOT/SOURCE/'geometry_validation.json'),
                         previous_source_contract=previous_report)


def owned_mesh(u,row):
    path=mesh_path(row)
    lib=u.EditorAssetLibrary
    if not lib.does_asset_exist(path):return None
    mesh=lib.load_asset(path)
    require(isinstance(mesh,u.StaticMesh) and lib.get_metadata_tag(mesh,TAG_OWNER)==OWNER
            and lib.get_metadata_tag(mesh,TAG_SHA)==base.digest(row),'unknown destination ownership/source: '+path)
    base.audit_mesh(u,mesh,row)
    return mesh


def _preflight(u):
    require(Path(u.Paths.convert_relative_path_to_full(u.Paths.project_dir())).resolve()==ROOT.resolve(),'wrong project')
    require(not u.get_editor_subsystem(u.LevelEditorSubsystem).is_in_play_in_editor(),'stop PIE first')
    world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    require(package(world)==base.MAP,'must use existing MPR map')
    manifest,source=source_contract()
    previous,_=base.source_contract()
    materials={}
    for role in base.ROLES:
        mat=base.owned_asset(u,base.material_path(role),base.digest(manifest['materials'][role]),u.Material)
        require(mat is not None,'missing current final solar material')
        base.material_audit(u,mat,manifest['materials'][role])
        materials[role]=mat
    actors=list(u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors())
    lookup={u.GuidLibrary.conv_guid_to_string(a.get_editor_property('actor_guid')):a for a in actors}
    require(len(lookup)==len(actors),'duplicate Actor GUID')
    targets=[]
    for guid,(name,bank)in base.IDENTITIES.items():
        actor=lookup.get(guid)
        row=next(r for r in manifest['meshes']if r['bank']==bank)
        require(actor is not None and actor.get_name()==name and actor.get_actor_label()==row['retained_actor_label']
                and isinstance(actor,u.StaticMeshActor),'original solar Actor identity changed')
        components=list(actor.get_components_by_class(u.StaticMeshComponent))
        require(len(components)==1 and components[0].get_name()=='StaticMeshComponent0'
                and not isinstance(components[0],u.InstancedStaticMeshComponent),'unexpected solar component')
        c=components[0]
        state=base.actor_state(u,actor,c)
        require(state['mesh']in(row['source_mesh'],mesh_path(row)),'solar source mesh changed')
        require(state['materials']==[base.material_path(r)for r in base.ROLES] and state['forced_lod_model']==0,
                'solar materials or LOD override changed')
        if state['mesh']==row['source_mesh']:
            old=next(r for r in previous['meshes']if r['bank']==bank)
            require(base.owned_asset(u,base.mesh_path(old),base.mesh_digest(old,previous['materials']),u.StaticMesh)
                    is not None,'current hierarchy mesh has no saved ownership')
            base.audit_mesh(u,c.static_mesh,old)
        existing=owned_mesh(u,row)
        if state['mesh']==mesh_path(row):require(existing is not None,'current unit mesh missing ownership')
        targets.append(dict(actor=actor,component=c,row=row,before=state))
    return manifest,materials,targets,dict(success=True,map=base.MAP,namespace=DEST,source=source,
        targets=[r['before']for r in targets],actor_guids_before=sorted(lookup))


def preflight(u):return _preflight(u)[3]


def import_mesh(u,row,materials):
    mesh=owned_mesh(u,row)
    reused=mesh is not None
    if not reused:
        path=mesh_path(row)
        task=u.AssetImportTask()
        for key,value in dict(filename=str(ROOT/row['fbx']),destination_path=path.rsplit('/',1)[0],destination_name=row['name'],
                              automated=True,replace_existing=False,replace_existing_settings=False,save=False).items():
            task.set_editor_property(key,value)
        options=u.FbxImportUI()
        for key,value in dict(import_mesh=True,import_as_skeletal=False,import_materials=False,import_textures=False,
            import_animations=False,mesh_type_to_import=u.FBXImportType.FBXIT_STATIC_MESH,
            automated_import_should_detect_type=False,reset_to_fbx_on_material_conflict=True).items():
            options.set_editor_property(key,value)
        for key,value in dict(combine_meshes=True,auto_generate_collision=False,generate_lightmap_u_vs=False,
            convert_scene=True,convert_scene_unit=True,force_front_x_axis=False,
            normal_import_method=u.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS,
            normal_generation_method=u.FBXNormalGenerationMethod.BUILT_IN).items():
            options.static_mesh_import_data.set_editor_property(key,value)
        task.options=options
        task.factory=u.FbxFactory()
        u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        require({str(p).split('.')[0]for p in task.imported_object_paths}=={path},'unexpected imported objects')
        mesh=u.EditorAssetLibrary.load_asset(path)
        require(isinstance(mesh,u.StaticMesh),'FBX failed to import')
        sm=u.get_editor_subsystem(u.StaticMeshEditorSubsystem)
        for lod,filename in enumerate(row['lod_files'],1):
            require(sm.import_lod(mesh,lod,str(ROOT/filename))==lod,'explicit LOD failed')
        for lod in range(sm.get_lod_count(mesh)):
            settings=sm.get_lod_build_settings(mesh,lod)
            settings.set_editor_property('use_full_precision_u_vs',True)
            settings.set_editor_property('recompute_tangents',True)
            settings.set_editor_property('generate_lightmap_u_vs',False)
            sm.set_lod_build_settings(mesh,lod,settings)
        nanite=sm.get_nanite_settings(mesh)
        if nanite.enabled:
            nanite.enabled=False
            sm.set_nanite_settings(mesh,nanite,True)
        if sm.get_simple_collision_count(mesh)or sm.get_convex_collision_count(mesh):
            require(sm.remove_collisions(mesh),'cannot remove collision')
        base.bind_lod_materials(u,mesh,row,materials)
        base.audit_mesh(u,mesh,row)
        u.EditorAssetLibrary.set_metadata_tag(mesh,TAG_OWNER,OWNER)
        u.EditorAssetLibrary.set_metadata_tag(mesh,TAG_SHA,base.digest(row))
        require(u.EditorAssetLibrary.save_loaded_asset(mesh,only_if_is_dirty=False),'cannot save new unit mesh')
    return mesh,dict(reused=reused,**base.audit_mesh(u,mesh,row))


def apply(u):
    manifest,materials,targets,report=_preflight(u)
    report.update(success=False,map_saved=False,meshes=[],changed_components=[],added_actor_guids=[],removed_actor_guids=[])
    map_file=ROOT/('Content/'+base.MAP.removeprefix('/Game/')+'.umap')
    map_sha=sha(map_file)
    meshes={}
    with base.legacy_fbx(u):
        for row in manifest['meshes']:
            meshes[row['name']],audit=import_mesh(u,row,materials)
            report['meshes'].append(audit)
    for target in targets:
        require(base.actor_state(u,target['actor'],target['component'])==target['before'],
                'solar Actor changed during import')
    edited=[]
    try:
        for target in targets:
            c=target['component']
            edited.append((c,c.static_mesh))
            replacement=meshes[target['row']['name']]
            if c.static_mesh!=replacement:require(c.set_static_mesh(replacement),'mesh assignment failed')
            after=base.actor_state(u,target['actor'],c)
            require(after==dict(target['before'],mesh=mesh_path(target['row'])),
                    'mesh replacement changed Actor/component/material state')
            report['changed_components'].append(dict(actor_guid=after['guid'],actor_name=after['name'],
                component_name=after['component_name'],before=target['before'],after=after,
                mesh_before=target['before']['mesh'],mesh_after=after['mesh']))
        actors=u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors()
        current=sorted(u.GuidLibrary.conv_guid_to_string(a.get_editor_property('actor_guid'))for a in actors)
        require(current==report['actor_guids_before'],'Actor set changed')
        require(sha(map_file)==map_sha,'apply saved or changed map bytes')
    except Exception:
        for c,mesh in reversed(edited):c.set_static_mesh(mesh)
        raise
    report.update(success=True,actor_guids_after=current,preserved_transform_and_guid_count=5,
        materials_unchanged=True,old_assets_unchanged=True,map_file_unchanged=True,
        new_packages_saved=[r['package']for r in report['meshes']if not r['reused']])
    return report
