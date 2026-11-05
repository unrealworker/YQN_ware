"""Read-only import metadata/vertex-color inspection; no automatic retry."""
from pathlib import Path
import json
import math
import shutil
import sys
import traceback

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).parent))
import apply_mpr_transport_revision as transport

TARGET='SM_MPRR_Roads_-2_-3'


def original_fade(position_cm, frame):
    """The exporter's original 24m perimeter fade, in the same CAD XY frame."""
    x,y=position_cm[0]/100.,-position_cm[1]/100.;best=math.inf
    for ring in frame['coordinates']:
        for a,b in zip(ring,ring[1:]):
            dx,dy=b[0]-a[0],b[1]-a[1];den=dx*dx+dy*dy
            t=max(0.,min(1.,((x-a[0])*dx+(y-a[1])*dy)/den)) if den else 0.
            best=min(best,math.hypot(x-a[0]-t*dx,y-a[1]-t*dy))
    value=max(0.,min(1.,1-best/24.))
    return value*value*(3-2*value)


def legacy_color(value):
    # FbxStaticMeshImport.cpp constructs uint8(255*FBXColor), then
    # FLinearColor(FColor). MeshDescriptionToDynamicMesh converts that linear
    # value back to sRGB by default, so the readback is the quantized input.
    return int(max(0.,min(1.,value))*255.)/255.


def vertex_color_audit(u, mesh, frame):
    assets=u.GeometryScript_AssetUtils;queries=u.GeometryScript_MeshQueries
    dynamic=u.DynamicMesh()
    options=u.GeometryScriptCopyMeshFromAssetOptions()
    options.set_editor_property('apply_build_settings',False)
    lod=u.GeometryScriptMeshReadLOD(lod_type=u.GeometryScriptLODType.SOURCE_MODEL,lod_index=0)
    copied=assets.copy_mesh_from_static_mesh(mesh,dynamic,options,lod)
    values=copied if isinstance(copied,tuple) else (copied,)
    transport.require(any(str(v).endswith('SUCCESS>') or 'SUCCESS' in str(v) for v in values),
                      'Static mesh color copy did not report success: '+str(copied))
    transport.require(queries.get_has_vertex_colors(dynamic),'Mesh has no color attribute')
    count=queries.get_num_triangle_i_ds(dynamic) if hasattr(queries,'get_num_triangle_i_ds') else queries.get_num_triangle_ids(dynamic)
    samples=[];histogram={};maximum_error=0.;worst=None;cache={};invalid=0
    for triangle in range(count):
        positions=queries.get_triangle_positions(dynamic,triangle)
        colors=queries.get_triangle_vertex_colors(dynamic,triangle)
        pvalues=positions if isinstance(positions,tuple) else (positions,)
        cvalues=colors if isinstance(colors,tuple) else (colors,)
        pv=[v for v in pvalues if isinstance(v,u.Vector)]
        cv=[v for v in cvalues if isinstance(v,u.LinearColor)]
        if not any(v is True for v in pvalues) or not any(v is True for v in cvalues):
            invalid+=1;continue
        transport.require(len(pv)==len(cv)==3,'Unexpected GeometryScript triangle query shape')
        for p,c in zip(pv,cv):
            key=(round(p.x,4),round(p.y,4),round(p.z,4))
            if key not in cache:cache[key]=legacy_color(original_fade(key,frame))
            expected=cache[key];actual=[c.r,c.g,c.b,c.a]
            error=max(abs(c.r-expected),abs(c.g-expected),abs(c.b-expected),abs(c.a-1))
            if error>maximum_error:
                maximum_error=error;worst=dict(position_cm=list(key),expected=expected,actual=actual)
            bucket=str(round(c.r,5));histogram[bucket]=histogram.get(bucket,0)+1
            samples.append([*key,*[round(v,7) for v in actual]])
    transport.require(samples and not invalid,'Missing/invalid triangle colors')
    reds=[r[3] for r in samples]
    return dict(valid=True,triangle_count=count,corner_count=len(samples),red_min=min(reds),red_max=max(reds),
        distinct_red_values=len(histogram),red_histogram=histogram,positions_and_colors_sha256=transport.guard.digest(samples),
        export_mapping='uint8(255*linearFBX), FLinearColor sRGB decode, DynamicMesh default linear-to-sRGB',
        maximum_expected_error=maximum_error,worst_mismatch=worst,
        matches_original_fade=maximum_error<.015,comparison_tolerance=.015)


def metadata(u, mesh):
    data=mesh.get_editor_property('asset_import_data')
    result=dict(import_data_class=data.get_class().get_path_name(),import_data_path=data.get_path_name())
    for name in ['vertex_color_import_option','combine_meshes','convert_scene','convert_scene_unit',
                 'force_front_x_axis','normal_import_method','normal_generation_method',
                 'auto_generate_collision','generate_lightmap_u_vs']:
        try:result[name]=str(data.get_editor_property(name))
        except Exception as error:result[name]={'unavailable':str(error)}
    result['source_files']=[str(p) for p in data.extract_filenames()]
    result['has_vertex_colors']=u.get_editor_subsystem(u.StaticMeshEditorSubsystem).has_vertex_colors(mesh)
    result['materials']=[dict(role=str(s.get_editor_property('imported_material_slot_name')),
        material=s.material_interface.get_path_name() if s.material_interface else None) for s in mesh.static_materials]
    sm=u.get_editor_subsystem(u.StaticMeshEditorSubsystem)
    result.update(simple_collision_count=sm.get_simple_collision_count(mesh),convex_collision_count=sm.get_convex_collision_count(mesh),
        render_triangles=mesh.get_num_triangles(0),render_vertices=mesh.get_num_vertices(0),lod_count=sm.get_lod_count(mesh),
        nanite_enabled=sm.get_nanite_settings(mesh).enabled)
    settings=sm.get_lod_build_settings(mesh,0)
    result['lod0_build_settings']={key:str(settings.get_editor_property(key)) for key in
        ['generate_lightmap_u_vs','use_full_precision_u_vs','recompute_normals','recompute_tangents']}
    return result


def inspect_metadata(u=None, *, root=ROOT):
    root=Path(root).resolve();out=root/transport.OUTPUT
    report=out/'transport_color_metadata.json'
    transport.require(not report.exists(),'Metadata evidence already exists; do not overwrite')
    result=dict(success=False,mode='metadata_read_only',assets_saved=False)
    try:
        if u is None:import unreal as u
        package=transport.guard.DEST+'/Site/Meshes/'+TARGET
        path=transport.validation.package_file(root,package);before=transport.sha(path)
        world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
        result.update(map=world.get_path_name().split('.')[0],map_sha256=transport.sha(root/transport.MAP_FILE),
            mesh_package=package,mesh_sha256=before,
            dirty_maps=[p.get_path_name() for p in u.EditorLoadingAndSavingUtils.get_dirty_map_packages()],
            dirty_content=[p.get_path_name() for p in u.EditorLoadingAndSavingUtils.get_dirty_content_packages()],
            interchange_fbx_flag=u.SystemLibrary.get_console_variable_int_value('Interchange.FeatureFlags.Import.FBX'))
        mesh=u.EditorAssetLibrary.load_asset(package)
        transport.require(mesh is not None,'Failed mesh is unavailable')
        result['metadata']=metadata(u,mesh)
        result['geometry_script_apis']={name:bool(hasattr(u,name)) for name in
            ['GeometryScript_AssetUtils','GeometryScript_MeshQueries','GeometryScriptLibrary_StaticMeshFunctions',
             'GeometryScriptLibrary_MeshQueryFunctions','DynamicMesh','GeometryScriptMeshReadLOD']}
        for cls,method in [('GeometryScript_AssetUtils','copy_mesh_from_static_mesh'),
                           ('GeometryScript_MeshQueries','get_triangle_positions'),
                           ('GeometryScript_MeshQueries','get_triangle_vertex_colors')]:
            if hasattr(u,cls) and hasattr(getattr(u,cls),method):
                result.setdefault('api_docs',{})[cls+'.'+method]=getattr(getattr(u,cls),method).__doc__
        transport.require(transport.sha(path)==before,'Read-only metadata inspection changed mesh bytes')
        result['success']=True
    except Exception:result['error']=traceback.format_exc()
    transport.write(report,result);print('MPR_TRANSPORT_COLOR_META',result,flush=True)
    return result


def current_scene_contract(u,root):
    out=root/transport.OUTPUT
    base=transport.read(root/transport.SOURCE/'manifest.json')
    ownership=transport.read(root/transport.SOURCE/'scene_ownership.json')
    revised=transport.read(root/transport.REVISION/'manifest.json')
    before=transport.read(out/'transport_before.json')
    changes=transport.planned_effective_material_changes(before,revised['meshes'],base,ownership)
    state=transport.guard.capture(u,root,transport.guard.MAP)
    transport.require(not state['dirty_content'],'Unexpected unsaved Content before color inspection/probe')
    transport.require(set(state['dirty_maps'])<={transport.guard.MAP},'Unrelated unsaved map before color probe')
    contract=dict(success=True,map_sha256_before=before['map_file_sha256'],map_sha256_after=state['map_file_sha256'],
        removed_actor_guids=[],added_actor_guids=[],actor_material_changes=changes)
    transport.validation.compare_snapshot(before,state,ownership,base,contract,revised)
    return state,base,ownership,revised


def inspect_all_imports(u=None, *, root=ROOT):
    root=Path(root).resolve();out=root/transport.OUTPUT;report=out/'transport_import_settings_audit.json'
    transport.require(not report.exists(),'Import settings audit already exists; do not overwrite')
    result=dict(success=False,mode='all_transport_import_settings_read_only',assets_saved=False,meshes=[])
    try:
        if u is None:import unreal as u
        state,_,_,manifest=current_scene_contract(u,root)
        contents,_=transport.retirement.inventory(root)
        for row in manifest['meshes']:
            package=transport.guard.DEST+'/Site/Meshes/'+row['name']
            mesh=u.EditorAssetLibrary.load_asset(package)
            result['meshes'].append(dict(name=row['name'],package=package,metadata=metadata(u,mesh),
                source_triangles=row['triangles'],has_fade=bool(row.get('vertex_color_fade')),
                mesh_sha256=transport.sha(transport.validation.package_file(root,package))))
        after=transport.guard.capture(u,root,transport.guard.MAP)
        transport.require(state==after,'Import settings audit changed live scene')
        transport.require(contents==transport.retirement.inventory(root)[0],'Import settings audit changed Content')
        result.update(success=True,content_digest=transport.guard.digest(contents),scene_digest=transport.guard.digest(state))
    except Exception:result['error']=traceback.format_exc()
    transport.write(report,result);print('MPR_TRANSPORT_IMPORT_AUDIT',result['success'],str(report),flush=True)
    if result.get('error'):print(result['error'],flush=True)
    return result


def inspect_colors(u=None, *, root=ROOT):
    root=Path(root).resolve();out=root/transport.OUTPUT;report=out/'transport_color_inspection_v2.json'
    transport.require(not report.exists(),'Color inspection evidence already exists; do not overwrite')
    result=dict(success=False,mode='colors_read_only',assets_saved=False,assets_modified=False)
    try:
        if u is None:import unreal as u
        state,_,_,manifest=current_scene_contract(u,root)
        row=next(r for r in manifest['meshes'] if r['name']==TARGET)
        contents,_=transport.retirement.inventory(root)
        package=transport.guard.DEST+'/Site/Meshes/'+TARGET
        mesh=u.EditorAssetLibrary.load_asset(package)
        result.update(mesh_package=package,mesh_sha256=transport.sha(transport.validation.package_file(root,package)),
            map_sha256=state['map_file_sha256'],dirty_maps=state['dirty_maps'],metadata=metadata(u,mesh),
            manifest_sha256=transport.sha(root/transport.REVISION/'manifest.json'),source_fbx_sha256=transport.sha(root/row['fbx']))
        frame=transport.read(root/transport.REVISION/'layout.json')['frame']
        result['vertex_colors']=vertex_color_audit(u,mesh,frame)
        after=transport.guard.capture(u,root,transport.guard.MAP)
        transport.require(state==after,'Read-only vertex color inspection changed live scene state')
        final,_=transport.retirement.inventory(root)
        transport.require(contents==final,'Read-only vertex color inspection changed Content files')
        transport.write(out/'transport_color_inspection_v2_scene.json',state)
        transport.write(out/'transport_color_inspection_v2_content.json',contents)
        result.update(success=True,content_digest=transport.guard.digest(contents),scene_digest=transport.guard.digest(state))
    except Exception:result['error']=traceback.format_exc()
    transport.write(report,result);print('MPR_TRANSPORT_COLOR_INSPECTION',result['success'],str(report),flush=True)
    if result.get('error'):print(result['error'],flush=True)
    return result


def probe_one(u=None, *, root=ROOT):
    """Explicit one-mesh experiment, only after successful read-only color capture."""
    root=Path(root).resolve();out=root/transport.OUTPUT;report=out/'transport_color_probe.json'
    transport.require(not report.exists(),'One-mesh probe evidence already exists; do not overwrite')
    result=dict(success=False,mode='one_mesh_probe',mesh_name=TARGET,map_saved=False,
                materials_modified=False,actors_modified=False,assets_saved=[])
    old_core=None
    try:
        if u is None:import unreal as u
        inspected=transport.read(out/'transport_color_inspection_v2.json')
        transport.require(inspected.get('success') is True,'Inspect actual vertex colors before any new import')
        state,base,ownership,manifest=current_scene_contract(u,root)
        transport.require(transport.guard.digest(state)==inspected['scene_digest'],'Scene changed since read-only color inspection')
        contents,_=transport.retirement.inventory(root)
        transport.require(transport.guard.digest(contents)==inspected['content_digest'],'Content changed since color inspection')
        transport.require(transport.sha(root/transport.REVISION/'manifest.json')==inspected['manifest_sha256'],
                          'Revision manifest changed since color inspection')
        row=next(r for r in manifest['meshes'] if r['name']==TARGET)
        transport.require(transport.sha(root/row['fbx'])==row['sha256']==inspected['source_fbx_sha256'],'Probe FBX changed')
        package=inspected['mesh_package'];path=transport.validation.package_file(root,package)
        mesh=u.EditorAssetLibrary.load_asset(package);import_data=mesh.get_editor_property('asset_import_data')
        transport.require(isinstance(import_data,u.FbxStaticMeshImportData),'One-mesh probe requires current legacy import data')
        result.update(before_metadata=metadata(u,mesh),before_sha256=transport.sha(path),
            inspection_sha256=transport.sha(out/'transport_color_inspection_v2.json'),map_sha256=state['map_file_sha256'],
            initial_failure_sha256=transport.sha(out/'transport_apply.json'),
            resume_failure_sha256=transport.sha(out/'transport_resume_apply.json'))
        backup=out/'transport_color_probe_backup';transport.require(not backup.exists(),'Probe backup already exists')
        backup.mkdir(parents=True)
        for source in transport.package_files(root,package):
            target=backup/source.name;shutil.copy2(source,target)
            transport.require(transport.sha(target)==transport.sha(source),'Probe backup is not exact')
        import import_mpr_scene as core
        old_core={key:getattr(core,key) for key in ('ROOT','DEST','MATS','MESHES','result','material')}
        core.ROOT=root;core.DEST=transport.guard.DEST;core.MESHES={};core.result=dict(meshes=[])
        materials={role:core.load(transport.guard.DEST+'/Materials/MI_'+role) for role in row['material_roles']}
        core.MATS=materials
        def readonly_material(role):
            transport.require(role in materials,'Unplanned probe material');return materials[role]
        core.material=readonly_material
        transport.write(report,result)
        # Reimport reads the asset's saved metadata, not task's static data.
        result['saved_import_settings_changes']=transport.configure_saved_import_data(u,mesh,row)
        with transport.legacy_fbx_import(u):mesh=core.import_mesh(row,'Site')
        result['assets_saved'].append(package)
        result['performance_settings']=transport.finalize_transport_mesh(u,mesh)
        transport.require(not transport.configure_saved_import_data(u,mesh,row),'Import settings were unexpectedly reverted')
        result['after_metadata']=metadata(u,mesh)
        transport.require(mesh.get_editor_property('asset_import_data').get_editor_property('vertex_color_import_option')
                          ==u.VertexColorImportOption.REPLACE,'Reimport did not preserve explicit color policy')
        frame=transport.read(root/transport.REVISION/'layout.json')['frame']
        result['vertex_colors']=vertex_color_audit(u,mesh,frame)
        transport.require(result['vertex_colors']['matches_original_fade'],'Probe colors do not match original exported fade')
        after=transport.guard.capture(u,root,transport.guard.MAP)
        transport.require(state==after,'One-mesh probe changed live scene/dirty state')
        final,_=transport.retirement.inventory(root)
        allowed={p.relative_to(root).as_posix() for p in transport.package_files(root,package)}
        result['modified_files']=transport.content_scope(contents,final,allowed)
        transport.require(transport.sha(out/'transport_apply.json')==result['initial_failure_sha256'] and
            transport.sha(out/'transport_resume_apply.json')==result['resume_failure_sha256'],'Failure evidence was modified')
        result.update(success=True,after_sha256=transport.sha(path),content_digest_after=transport.guard.digest(final),
                      imported_meshes=core.result['meshes'],interchange_flag_restored=True)
        transport.write(out/'transport_color_probe_content_after.json',final)
    except Exception:
        result['error']=traceback.format_exc();print(result['error'],flush=True)
    finally:
        if old_core is not None:
            for key,value in old_core.items():setattr(core,key,value)
    transport.write(report,result);print('MPR_TRANSPORT_SINGLE_COLOR_PROBE',result['success'],str(report),flush=True)
    return result


if __name__=='__main__':inspect_metadata()
