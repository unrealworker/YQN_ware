"""Read-only protection for a new MPR map; no dependency on the extension tools."""
from collections import Counter
from copy import deepcopy
import hashlib,json,math,re
from pathlib import Path
import mpr_interior_preservation as interior

SOURCE_MAP='/Game/Maps/MPR_CAD_Warehouse'
MAP='/Game/Maps/MPR_CAD_Warehouse_B50B57'
DEST='/Game/MPRWarehouse/RebuildB50B57'
FOLDER='MPR/RebuildB50B57'
TAG='mpr-rebuild-b50b57'
ERROR=interior.PreservationError
digest=interior.canonical_digest
SUFFIXES={'.uasset','.umap','.uexp','.ubulk','.uptnl'}
LIGHT_LABELS={'MPR4_ReferenceStyle','MPR4_Ambient','MPR4_StudioSky','MPR4_KeyLight'}
RETAINED_MATERIAL_ROLES={'MPR4_'+name for name in ['RoofMembrane','FacadeWhite','IndustrialBlue','SolarCells','SolarMid','SolarFar']}
MATERIAL_COMPONENT_CLASSES={'/Script/Engine.'+name for name in
    ['StaticMeshComponent','InstancedStaticMeshComponent','HierarchicalInstancedStaticMeshComponent']}
SOLAR_IDENTITIES={
    'BC217E8B43B202CB7FE238B6F4B6556B':('StaticMeshActor_41','00_0'),
    'C7BD2BEB41095B0B59873AA3D64DD765':('StaticMeshActor_42','01_0'),
    '3D07E0584AE579B3F87A44B617CBFF87':('StaticMeshActor_43','01_1'),
    'CBE6448C453AE125A1FA0899147E45A5':('StaticMeshActor_44','02_0'),
    'B68AC22E4D4B120213C6FF93AEA28E06':('StaticMeshActor_45','02_1'),
}
SOLAR_ROLES=['MPR4_Solar'+name for name in ['Frame','Cells','Mid','Far']]
SOLAR_ROOT='SourceAssets/MPR/rebuild_b50b57/solar'
KEEP_PROP_MESHES={'SM_MPR4_'+x for x in ['Bollard','DockLeveller','DockNumberPlate','DockShelter',
    'RollerDock','RollerDriveIn','WallLamp',*['Digit_'+str(i) for i in range(10)]]}
REMOVE_PROP_MESHES={'SM_MPR4_'+x for x in ['Car_0','Car_1','Tractor','Trailer_Blue',
    'Trailer_Coral','Trailer_White','Tree_Oak','FreightBoxcar','Locomotive']}
# Exact engine-created auxiliary shapes observed in the native coverage probe.
# WaterSubsystem.cpp:323; World.cpp:6848; GameplayDebuggerModule.cpp:132;
# ChaosDebugDrawComponent.cpp:387; NavigationSystem.cpp:1085.
ENGINE_AUX={
    'water_buoyancy_manager':('/Script/Water.BuoyancyManager',r'BuoyancyManager_\d+',[]),
    'default_physics_volume':('/Script/Engine.DefaultPhysicsVolume',r'DefaultPhysicsVolume_\d+',
        [('BrushComponent0','/Script/Engine.BrushComponent')]),
    'gameplay_debugger_manager':('/Script/GameplayDebugger.GameplayDebuggerPlayerManager',r'GameplayDebuggerPlayerManager_\d+',
        [('GameplayDebug_Input','/Script/Engine.InputComponent')]),
    'chaos_debug_draw':('/Script/Engine.Actor',r'ChaosDebugDrawActor',
        [(r'ChaosDebugDrawComponent_\d+','/Script/ChaosSolverEngine.ChaosDebugDrawComponent')]),
    'abstract_navigation':('/Script/NavigationSystem.AbstractNavData',r'AbstractNavData-Default(?:_\d+)?',
        [('SceneComp','/Script/Engine.SceneComponent')]),
}

def require(ok,message):
    if not ok:raise ERROR(message)

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def content_hashes(root):
    root=Path(root).resolve()
    return {p.relative_to(root).as_posix():sha(p) for p in sorted((root/'Content').rglob('*'))
            if p.is_file() and p.suffix.lower() in SUFFIXES}

def assert_old_files(root,before):
    current=content_hashes(root)
    changed=[p for p,h in before.items() if current.get(p)!=h]
    require(not changed,'Pre-existing Content package bytes changed/missing: '+', '.join(changed[:10]))
    allowed='Content/MPRWarehouse/RebuildB50B57/'
    allowed_map='Content/Maps/MPR_CAD_Warehouse_B50B57'
    unexpected=[p for p in set(current)-set(before)
                if not p.startswith(allowed) and not (Path(p).with_suffix('').as_posix()==allowed_map)]
    require(not unexpected,'Unexpected package created outside rebuild namespace: '+', '.join(unexpected[:10]))
    return {p:current[p] for p in sorted(set(current)-set(before))}

def classify(row):
    folder=row['folder'];label=row['label'];tags=set(row['tags'])
    if 'MPRWarehouse' in tags:
        if folder in {'MPR/Architecture','MPR/Architecture/Columns','MPR/Equipment',
                      'MPR/Operations','MPR/Storage/Floor','MPR/Storage/Racks'}:
            return 'keep_interior'
        if folder=='MPR/Cameras' and label in {'MPR_WarehouseCamera','MPR_ReviewCamera'}:
            return 'keep_camera'
    if 'mpr-reference-exterior-v4' in tags:
        if folder in {'MPR/ReferenceV4/Architecture','MPR/ReferenceV4/Architecture/RemovableRoof'}:
            return 'keep_main_shell'
        if folder=='MPR/ReferenceV4/Lighting' and label in LIGHT_LABELS:return 'keep_lighting'
        if folder in {'MPR/ReferenceV4/Context','MPR/ReferenceV4/Site'}:return 'remove_old_exterior'
        if folder=='MPR/ReferenceV4/Props':
            meshes={c['mesh'].split('.')[-1] for c in row['components'] if c.get('mesh')}
            if meshes and meshes<=KEEP_PROP_MESHES:return 'keep_main_attachments'
            if meshes and meshes<=REMOVE_PROP_MESHES:return 'remove_old_exterior'
    if 'mpr-extension-b50b57' in tags and folder in {
            'MPR/ExtensionB50B57/Geometry','MPR/ExtensionB50B57/Vegetation'}:
        return 'remove_old_exterior'
    raise ERROR('Unclassified source actor must be reviewed: '+label+' ['+folder+']')

def make_plan(snapshot):
    rows=[dict(guid=r['guid'],name=r['name'],label=r['label'],folder=r['folder'],
               action=classify(r),record_digest=digest(r)) for r in snapshot['actors']]
    counts=dict(Counter(r['action'] for r in rows))
    require(sum(v for k,v in counts.items() if k.startswith('keep_'))==256 and
            counts.get('remove_old_exterior')==353,'Reviewed 256/353 source actor set changed')
    return dict(schema_version=1,source_map=SOURCE_MAP,new_map=MAP,namespace=DEST,
                source_map_sha256=snapshot['map_file_sha256'],
                source_actor_digest=digest(snapshot['actors']),counts=counts,actors=rows)

def assert_source_plan(plan,snapshot):
    require(snapshot['map']==SOURCE_MAP,'Source map identity changed')
    require(plan['source_map']==SOURCE_MAP and plan['new_map']==MAP and plan['namespace']==DEST,
            'Protection plan identity changed')
    require(plan['source_map_sha256']==snapshot['map_file_sha256'],'Source map changed after retention review')
    require(plan['source_actor_digest']==digest(snapshot['actors']),'Source actors changed after retention review')
    current={r['guid']:r for r in snapshot['actors']}
    require(len(current)==len(plan['actors']) and len({r['guid'] for r in plan['actors']})==len(current),
            'Protection plan actor set is incomplete')
    for row in plan['actors']:
        actual=current.get(row['guid'])
        require(actual is not None and digest(actual)==row['record_digest'] and classify(actual)==row['action'],
                'Protection plan actor changed: '+row['name'])

def _value(v):
    if v is None or isinstance(v,(str,int,float,bool)):return v
    if hasattr(v,'export_text'):return v.export_text()
    if hasattr(v,'get_path_name'):return v.get_path_name()
    return str(v)

def engine_aux_role(class_path,name,components):
    for role,(cls,pattern,expected) in ENGINE_AUX.items():
        if class_path!=cls or not re.fullmatch(pattern,name) or len(components)!=len(expected):continue
        if all(any(re.fullmatch(n,c['name']) and c['class']==k for c in components) for n,k in expected):return role
    return None

def canonical_coverage(rows):
    """Keep raw observations; only generated engine actor/component names vary."""
    answer=[]
    for original in rows:
        row=deepcopy(original);role=row.get('engine_role')
        if role in ENGINE_AUX:
            require(engine_aux_role(row['class'],row['name'],row['components'])==role,'Invalid automatic engine auxiliary shape')
            old_path=row['path'];new_name='__Engine_'+role+'__'
            new_path=old_path.rsplit('.',1)[0]+'.'+new_name
            def replace_paths(v):
                if isinstance(v,str) and (v==old_path or v.startswith(old_path+'.')):return new_path+v[len(old_path):]
                if isinstance(v,dict):return {k:replace_paths(x) for k,x in v.items()}
                if isinstance(v,list):return [replace_paths(x) for x in v]
                return v
            row=replace_paths(row)
            if row.get('label')==row['name'] or re.fullmatch(ENGINE_AUX[role][1],row.get('label','')):
                row['label']=new_name
            row['name']=new_name
            if role=='chaos_debug_draw':row['components'][0]['name']='ChaosDebugDrawComponent'
        answer.append(row)
    return sorted(answer,key=lambda r:(r.get('engine_role',''),r['path']))

def validate_actor_coverage(recorded_paths,raw_rows):
    """Fail closed for actors omitted by EditorActorSubsystem's UI filter."""
    paths={r['path'] for r in raw_rows}
    require(len(paths)==len(raw_rows),'Duplicate actors in unfiltered world enumeration')
    require(set(recorded_paths)<=paths,'Recorded actor missing from unfiltered world enumeration')
    auxiliary=[];unreviewed=[]
    for row in raw_rows:
        if row['path'] in recorded_paths:continue
        role=row.get('engine_role')
        if role not in {'world_settings','level_script','builder_brush',*ENGINE_AUX} or \
                (role in ENGINE_AUX and engine_aux_role(row.get('class'),row.get('name',''),row.get('components',[]))!=role):
            unreviewed.append(row['path']+' ['+str(row.get('class'))+']')
        auxiliary.append(row)
    require(not unreviewed,'Unrecorded/noneditable world actors must be reviewed:\n'+'\n'.join(unreviewed))
    counts=Counter(r['engine_role'] for r in auxiliary)
    require(counts['world_settings']==1 and counts['level_script']<=1 and counts['builder_brush']<=1 and
            all(counts[role]<=1 for role in ENGINE_AUX),
            'Unexpected engine auxiliary actor set: '+str(counts))
    return sorted(auxiliary,key=lambda r:r['path'])

def assert_single_world_layout(u,world):
    # UE 5.8 does not expose World.StreamingLevels/PersistentLevel to Python.
    # get_levels is reflected. Loaded levels alone are insufficient: unfiltered
    # UObject iteration also detects a LevelStreaming with an unloaded level,
    # or a WorldPartition owned through WorldSettings, without loading either.
    levels=list(u.EditorLevelUtils.get_levels(world))
    require(len(levels)==1 and levels[0].get_outer()==world,
            'Multiple/unexpected loaded levels require a separate retention review')
    for cls,label in [(u.LevelStreaming,'Streaming levels'),(u.WorldPartition,'Partitioned worlds')]:
        owned=[]
        for obj in u.ObjectIterator(cls):
            current=obj
            while current is not None and current!=world:current=current.get_outer()
            if current==world:owned.append(obj.get_path_name())
        require(not owned,label+' require a separate retention review: '+str(owned))
    return levels[0]

def brush_type_value(actor):
    try:
        return actor.get_editor_property('brush_type').value
    except TypeError as exc:
        # UE5.8 excludes hidden Brush_Default (0) from the Python enum. The
        # native converter still identifies the exact raw value in its error.
        # Accept that one value only; authored additive/subtractive brushes
        # and every unrelated reflection/conversion failure remain rejected.
        if "Cannot pythonize '0' (int64) as 'BrushType'" in str(exc):return 0
        raise

def capture_actor_coverage(u,world,recorded_rows):
    level=assert_single_world_layout(u,world)
    settings=world.get_world_settings()
    recorded={r['path'] for r in recorded_rows};rows=[]
    for actor in u.GameplayStatics.get_all_actors_of_class(world,u.Actor):
        path=actor.get_path_name();row=dict(path=path)
        if path not in recorded:
            components=list(actor.get_components_by_class(u.ActorComponent))
            shapes=[dict(name=c.get_name(),**{'class':c.get_class().get_path_name()}) for c in components]
            role=None
            if actor==settings:role='world_settings'
            elif isinstance(actor,u.LevelScriptActor) and actor.get_outer()==level:role='level_script'
            elif actor.get_class().get_path_name()=='/Script/Engine.Brush' and \
                    actor.get_outer()==level and brush_type_value(actor)==0:
                # EBrushType explicitly documents value 0 as "Default/builder
                # brush". This editable enum is exposed to Python; internal
                # bNotForClientOrServer is not relied on. Additive/subtractive
                # authored geometry is never exempt from the actor review.
                role='builder_brush'
            elif actor.get_outer()==level:
                role=engine_aux_role(actor.get_class().get_path_name(),actor.get_name(),shapes)
            row.update(engine_role=role,name=actor.get_name(),**{'class':actor.get_class().get_path_name()},
                transform=interior._transform(actor.get_actor_transform()),
                hidden=bool(actor.get_editor_property('hidden')),tick_enabled=actor.is_actor_tick_enabled(),
                collision_enabled=actor.get_actor_enable_collision(),tags=[str(t) for t in actor.tags])
            if role in ENGINE_AUX:
                row.update(label=actor.get_actor_label(),folder=str(actor.get_folder_path()),
                           attachment_parent=interior._path(actor.get_attach_parent_actor()),components=[])
                for component in components:
                    c=dict(name=component.get_name(),**{'class':component.get_class().get_path_name()},
                           tags=[str(t) for t in component.component_tags])
                    if isinstance(component,u.SceneComponent):
                        c.update(transform=interior._transform(component.get_relative_transform()),
                            attach_parent=interior._path(component.get_attach_parent()),mobility=str(component.mobility),
                            visible=bool(component.visible),hidden_in_game=bool(component.hidden_in_game))
                    if isinstance(component,u.StaticMeshComponent):
                        c.update(mesh=interior._path(component.static_mesh),
                            materials=[interior._path(component.get_material(i)) for i in range(component.get_num_materials())],
                            collision_profile=str(component.get_collision_profile_name()),cast_shadow=bool(component.cast_shadow))
                    if isinstance(component,u.InstancedStaticMeshComponent):
                        count=component.get_instance_count()
                        c.update(instance_count=count,
                            instance_transforms=[interior._transform(component.get_instance_transform(i,world_space=False)) for i in range(count)],
                            num_custom_data_floats=int(component.get_editor_property('num_custom_data_floats')),
                            custom_data=[float(v) for v in component.get_editor_property('per_instance_sm_custom_data')])
                    row['components'].append(c)
                row['components'].sort(key=lambda c:c['name'])
        rows.append(row)
    return validate_actor_coverage(recorded,rows)

def capture(u,root,expected_map):
    state=interior.capture_editor_snapshot(u,project_root=root,expected_map=expected_map,hash_assets=False)
    actors=u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors()
    lookup={u.GuidLibrary.conv_guid_to_string(a.get_editor_property('actor_guid')):a for a in actors}
    require(set(lookup)=={r['guid'] for r in state['actors']},'Actor set changed during capture')
    def props(obj,names):return {n:_value(obj.get_editor_property(n)) for n in names}
    for row in state['actors']:
        actor=lookup[row['guid']]
        if isinstance(actor,u.PostProcessVolume):
            row['render_settings']=props(actor,['settings','enabled','unbound','priority','blend_radius','blend_weight'])
        if actor.get_class().get_path_name()=='/Script/Test.EnvironmentRenderProfile':
            row['render_settings']=props(actor,['lumen_clipmap_extent'])
        components={c['name']:c for c in row['components']}
        for c in actor.get_components_by_class(u.ActorComponent):
            names=[]
            if isinstance(c,u.LightComponentBase):names+=['intensity','light_color','cast_shadows','indirect_lighting_intensity','volumetric_scattering_intensity']
            if isinstance(c,u.LightComponent):names+=['temperature','use_temperature','light_function_material','ies_texture','shadow_bias','shadow_slope_bias']
            if isinstance(c,u.DirectionalLightComponent):names+=['light_source_angle','light_source_soft_angle']
            if isinstance(c,u.SkyLightComponent):names+=['source_type','cubemap','source_cubemap_angle','real_time_capture','lower_hemisphere_is_black','lower_hemisphere_color']
            if isinstance(c,u.CameraComponent):names+=['projection_mode','field_of_view','aspect_ratio','constrain_aspect_ratio','ortho_width','post_process_blend_weight','post_process_settings']
            if isinstance(c,u.CineCameraComponent):names+=['current_focal_length','current_aperture','filmback','focus_settings','lens_settings']
            if names:components[c.get_name()]['render_settings']=props(c,names)
    world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    state['world_actor_coverage']=capture_actor_coverage(u,world,state['actors'])
    settings=world.get_world_settings()
    state['world_settings']=props(settings,['default_game_mode','world_to_meters','kill_z',
        'global_gravity_z','global_gravity_set','enable_world_bounds_checks','force_no_precomputed_lighting'])
    state['map_file_sha256']=sha(Path(root)/('Content/'+expected_map.removeprefix('/Game/')+'.umap'))
    return state

def assert_clean(snapshot,*,allow_new_map=False):
    require(not snapshot['dirty_content'],'Unsaved Content packages: '+str(snapshot['dirty_content']))
    allowed={MAP} if allow_new_map else set()
    require(set(snapshot['dirty_maps'])<=allowed,'Unrelated/unsaved maps: '+str(snapshot['dirty_maps']))

def assert_independent_dependencies(u):
    registry=u.AssetRegistryHelpers.get_asset_registry()
    options=u.AssetRegistryDependencyOptions(include_soft_package_references=True,
        include_hard_package_references=True,include_searchable_names=False,
        include_soft_management_references=False,include_hard_management_references=False)
    pending=[MAP];visited=set()
    while pending:
        package=pending.pop()
        if package in visited:continue
        require(not package.startswith('/Game/MPRWarehouse/ExtensionB50B57/'),
                'New map still depends on cancelled extension assets: '+package)
        visited.add(package)
        dependencies=registry.get_dependencies(package,options)
        require(dependencies is not None,'Dependency node unavailable: '+package)
        pending.extend(str(p) for p in dependencies if str(p).startswith('/Game/'))
    return sorted(visited)

def remap(value,source_map,target_map):
    prefix=source_map+'.'+source_map.rsplit('/',1)[-1]
    target=target_map+'.'+target_map.rsplit('/',1)[-1]
    if isinstance(value,str) and (value in {prefix,prefix+'_C'} or value.startswith(prefix+':') or value.startswith(prefix+'.')):
        return target+value[len(prefix):]
    if isinstance(value,dict):return {k:remap(v,source_map,target_map) for k,v in value.items()}
    if isinstance(value,list):return [remap(v,source_map,target_map) for v in value]
    return value

def canonical_actor(row):
    """Only UE's transient DefaultSceneRoot editor-icon suffix is nondurable."""
    row=deepcopy(row)
    icons=[c for c in row['components'] if c.get('class')=='/Script/Engine.BillboardComponent']
    if len(icons)==1:
        c=icons[0]
        if re.fullmatch(r'BillboardComponent_\d+',c['name']) and c.get('hidden_in_game') is True and \
                c.get('attach_parent')==row['path']+'.DefaultSceneRoot' and \
                c.get('transform',{}).get('scale')==[.5,.5,.5] and any(
                    r.get('name')=='DefaultSceneRoot' and r.get('class')=='/Script/Engine.SceneComponent'
                    for r in row['components']):
            c['name']='__TransientDefaultSceneRootSprite__'
    row['components'].sort(key=lambda c:c['name'])
    return row

def retained_material_spec_map(specs,materials=None):
    require(isinstance(specs,list),'Retained material overrides must be a list')
    result={}
    for spec in specs:
        require(set(spec)=={'source','role'},'Retained material override requires only source and role')
        role=spec['role'];source=spec['source']
        require(role in RETAINED_MATERIAL_ROLES,'Unapproved retained material role: '+str(role))
        package='/Game/MPRWarehouse/ReferenceV4/Materials/MI_'+role
        object_path=package+'.MI_'+role
        require(source in {package,object_path},'Retained material source does not match approved role: '+str(source))
        require(object_path not in result,'Duplicate retained material source')
        require(materials is None or role in materials,'Missing new material definition: '+role)
        result[object_path]=role
    return result

def retained_mesh_spec_map(specs):
    """The user-approved exception is five known solar components, never a pattern."""
    require(isinstance(specs,list),'Retained mesh overrides must be a list')
    result={}
    for spec in specs:
        require(set(spec)=={'source_guid','component_name','source_mesh','target_mesh'},'Invalid solar mesh override fields')
        guid=spec['source_guid'];require(guid in SOLAR_IDENTITIES,'Unapproved solar source GUID')
        require(guid not in result,'Duplicate solar mesh override')
        suffix=SOLAR_IDENTITIES[guid][1]
        old='SM_MPR4_SolarBank_'+suffix;new='SM_MPRR_SolarBank_'+suffix
        require(spec['component_name']=='StaticMeshComponent0' and
                spec['source_mesh']=='/Game/MPRWarehouse/ReferenceV4/Architecture/Meshes/'+old+'.'+old and
                spec['target_mesh']==DEST+'/Architecture/Meshes/'+new+'.'+new,'Solar mesh identity/path mismatch')
        result[guid]=spec
    require(not result or set(result)==set(SOLAR_IDENTITIES),'Solar exception must include exactly the five reviewed banks')
    return result

def solar_source_contract(root,manifest):
    """Hash every separate solar input without changing the main exterior manifest rows."""
    specs=retained_mesh_spec_map(manifest.get('retained_mesh_overrides',[]))
    reference=manifest.get('solar_rebuild')
    require(bool(reference)==bool(specs),'Solar source and five mesh exceptions must be declared together')
    if not reference:return [],{}
    require(set(reference)=={'manifest','sha256'} and reference['manifest']==SOLAR_ROOT+'/manifest.json',
            'Solar manifest must use its independent source namespace')
    root=Path(root).resolve();base=(root/SOLAR_ROOT).resolve();files={}
    def checked(name,expected):
        path=(root/name).resolve()
        require(path.is_relative_to(base) and path.is_file(),'Missing/outside solar source: '+str(name))
        require(name not in files,'Duplicate solar source file: '+name)
        require(sha(path)==expected,'Solar source hash mismatch: '+name)
        files[name]=expected
        return path
    path=checked(reference['manifest'],reference['sha256'])
    data=json.loads(path.read_text(encoding='utf-8-sig'));rows=data['meshes']
    names={'SM_MPRR_SolarBank_'+suffix for _,suffix in SOLAR_IDENTITIES.values()}
    require(len(rows)==5 and {r['name'] for r in rows}==names,'Solar source must contain exactly five LOD0 mesh rows')
    require(not names.intersection(r['name'] for r in manifest['meshes']),'Solar rows must remain separate from main meshes')
    require(set(SOLAR_ROLES[1:])<=set(manifest['materials']) and SOLAR_ROLES[0] not in manifest['materials'],
            'Solar frame must remain the original read-only material; other roles need new clones')
    for row in rows:
        name=row['name'];require(row['category']=='Architecture','Unexpected solar mesh category')
        require(row.get('full_precision_uvs') is True and not row.get('instance_only'),'Solar mesh requires precise UVs and retained actor')
        require(row['all_lod_material_roles']==SOLAR_ROLES and row['material_roles']==SOLAR_ROLES[:2] and
                row['lod_material_roles']==[[SOLAR_ROLES[0],role] for role in SOLAR_ROLES[1:]],'Solar LOD material order differs')
        require(len(row['lod_files'])==len(row['lod_sha256'])==2,'Solar mesh requires both hashed coarse LOD sources')
        require(len(row['lod_screen_sizes'])==3 and all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
                for v in row['lod_screen_sizes']) and 1==row['lod_screen_sizes'][0]>row['lod_screen_sizes'][1]>row['lod_screen_sizes'][2]>0,
                'Invalid solar LOD screen sizes')
        require(len(row['lod_triangles'])==3 and all(type(v) is int and v>0 for v in row['lod_triangles']) and
                row['triangles']==row['lod_triangles'][0],'Invalid solar LOD triangle counts')
        bounds=row['bounds_m']
        require(len(bounds)==3 and all(len(pair)==2 and all(isinstance(v,(int,float)) and math.isfinite(v) for v in pair)
                and pair[0]<pair[1] for pair in bounds),'Invalid solar bounds')
        paths=[row['fbx'],*row['lod_files']]
        expected_names=[name+'.fbx',name+'_LOD1.fbx',name+'_LOD2.fbx']
        for filename,expected,basename in zip(paths,[row['sha256'],*row['lod_sha256']],expected_names):
            require(Path(filename).name==basename,'Solar LOD filename mismatch')
            checked(filename,expected)
    require(len(files)==16,'All fifteen solar FBXs plus the manifest must be protected')
    return rows,files

def expected_retained_mesh_changes(source,plan,guid_map,specs):
    replacements=retained_mesh_spec_map(specs);old={r['guid']:r for r in source['actors']}
    actions={r['guid']:r['action'] for r in plan['actors']};changes=[]
    for guid,spec in replacements.items():
        require(guid in old and guid in guid_map and actions.get(guid)=='keep_main_shell','Solar override targets missing/non-shell actor')
        actor=old[guid];name,suffix=SOLAR_IDENTITIES[guid]
        require(actor['name']==name and actor['label']=='MPR4_SolarBank_'+suffix and
                actor['class']=='/Script/Engine.StaticMeshActor' and actor['folder']=='MPR/ReferenceV4/Architecture/RemovableRoof',
                'Reviewed solar actor identity changed')
        components=[c for c in actor['components'] if c['name']==spec['component_name']]
        require(len(components)==1 and components[0]['class']=='/Script/Engine.StaticMeshComponent' and
                components[0].get('mesh')==spec['source_mesh'] and not components[0].get('instance_count'),
                'Reviewed solar source component changed')
        require(components[0]['materials']==['/Game/MPRWarehouse/ReferenceV4/Materials/MI_'+role+'.MI_'+role for role in SOLAR_ROLES],
                'Reviewed solar source material order changed')
        changes.append(dict(actor_name=name,source_guid=guid,actor_guid=guid_map[guid],component_name=spec['component_name'],
                            before=spec['source_mesh'],after=spec['target_mesh']))
    return sorted(changes,key=lambda r:r['source_guid'])

def audit_solar_meshes(u,rows):
    """Independent readback using the UE 5.8 APIs already validated for old PV LODs."""
    sm=u.get_editor_subsystem(u.StaticMeshEditorSubsystem);audit={}
    for row in rows:
        name=row['name'];package=DEST+'/Architecture/Meshes/'+name
        mesh=u.EditorAssetLibrary.load_asset(package)
        require(isinstance(mesh,u.StaticMesh) and mesh.get_path_name()==package+'.'+name,'Missing new solar mesh')
        require(sm.get_lod_count(mesh)==3 and not sm.get_nanite_settings(mesh).enabled,'Solar mesh must use three authored non-Nanite LODs')
        slots=list(mesh.static_materials)
        require([str(s.get_editor_property('imported_material_slot_name')) for s in slots]==SOLAR_ROLES,'Solar slot order changed')
        materials=[]
        for index,slot in enumerate(slots):
            role=SOLAR_ROLES[index];base='/Game/MPRWarehouse/ReferenceV4' if index==0 else DEST
            expected=base+'/Materials/MI_'+role+'.MI_'+role
            require(slot.material_interface is not None and slot.material_interface.get_path_name()==expected,'Solar mesh default material changed')
            materials.append(expected)
        screens=list(sm.get_lod_screen_sizes(mesh))
        require(len(screens)==3 and max(abs(a-b) for a,b in zip(screens,row['lod_screen_sizes']))<1e-5,'Solar LOD screens changed')
        levels=[]
        for lod,wanted in enumerate(row['lod_material_roles']):
            roles=[];sections=[]
            for section in range(mesh.get_num_sections(lod)):
                index=sm.get_lod_material_slot(mesh,lod,section)
                require(0<=index<len(slots),'Invalid solar LOD slot index')
                role=SOLAR_ROLES[index];roles.append(role)
                sections.append(dict(section=section,slot_index=index,role=role,material=materials[index]))
            require(len(roles)==len(wanted) and set(roles)==set(wanted),'Solar LOD section roles changed')
            require(sm.get_lod_build_settings(mesh,lod).get_editor_property('use_full_precision_u_vs'),'Solar LOD lost precise UVs')
            levels.append(dict(lod=lod,screen_size=screens[lod],sections=sections,full_precision_uvs=True))
        bounds=mesh.get_bounds();actual=[[bounds.origin.x-bounds.box_extent.x,bounds.origin.x+bounds.box_extent.x],
            [bounds.origin.y-bounds.box_extent.y,bounds.origin.y+bounds.box_extent.y],
            [bounds.origin.z-bounds.box_extent.z,bounds.origin.z+bounds.box_extent.z]]
        b=row['bounds_m'];expected=[[b[0][0]*100,b[0][1]*100],[-b[1][1]*100,-b[1][0]*100],[b[2][0]*100,b[2][1]*100]]
        require(max(abs(a-b) for aa,bb in zip(actual,expected) for a,b in zip(aa,bb))<20,'Solar LOD bounds/axis mismatch')
        audit[name]=dict(mesh=mesh.get_path_name(),slot_roles=SOLAR_ROLES,materials=materials,lods=levels,bounds_cm=actual,nanite_enabled=False)
    return audit

def expected_retained_material_changes(source,plan,guid_map,specs):
    """Derive the entire allowed slot set from immutable original actor records."""
    replacements=retained_material_spec_map(specs);changes=[];matched=set()
    old={r['guid']:r for r in source['actors']}
    for item in plan['actors']:
        if item['action'] not in {'keep_main_shell','keep_main_attachments'}:continue
        actor=old[item['guid']]
        for component in actor['components']:
            if component['class'] not in MATERIAL_COMPONENT_CLASSES:continue
            for slot,before in enumerate(component.get('materials',[])):
                if before not in replacements:continue
                role=replacements[before];matched.add(before)
                changes.append(dict(actor_name=actor['name'],source_guid=actor['guid'],actor_guid=guid_map[actor['guid']],
                    component_name=component['name'],slot=slot,role=role,before=before,
                    after=DEST+'/Materials/MI_'+role+'.MI_'+role))
    require(matched==set(replacements),'Retained material source has no approved exterior slot: '+str(sorted(set(replacements)-matched)))
    return sorted(changes,key=lambda r:(r['source_guid'],r['component_name'],r['slot']))

def assert_retained(source,current,plan,*,guid_map=None,lighting_changes=(),material_changes=(),material_overrides=(),
                    mesh_changes=(),mesh_overrides=()):
    require(current['map']==MAP,'Retention validation requires the new map')
    old={r['name']:r for r in source['actors']};new={r['name']:r for r in current['actors']}
    require(len(new)==len(current['actors']),'Duplicate new-map actor object names')
    copy_guids={r['guid']:new[r['name']]['guid'] for r in source['actors'] if r['name'] in new}
    expected_materials=expected_retained_material_changes(source,plan,copy_guids,list(material_overrides))
    require(sorted(material_changes,key=lambda r:(r['source_guid'],r['component_name'],r['slot']))==expected_materials,
            'Material change record differs from approved exterior component slots')
    material_slots={(r['actor_name'],r['component_name'],r['slot']):r for r in expected_materials}
    expected_meshes=expected_retained_mesh_changes(source,plan,copy_guids,list(mesh_overrides))
    require(sorted(mesh_changes,key=lambda r:r['source_guid'])==expected_meshes,'Mesh change record differs from five approved solar components')
    allowed={}
    for change in lighting_changes:
        name=change['actor_name'];field=tuple(change['field'])
        require(name in old and old[name]['label'] in LIGHT_LABELS,'Lighting override targets a protected main-building actor')
        require((len(field)==2 and field[0]=='render_settings') or
                (len(field)==4 and field[0]=='components' and field[2]=='render_settings'),
                'Lighting allowlist must identify a render-settings property')
        require((name,field) not in allowed,'Duplicate lighting field authorization')
        allowed[(name,field)]=change
    mapping={};normalized=[]
    for item in plan['actors']:
        if not item['action'].startswith('keep_'):continue
        name=item['name'];original=old[name];actual=new.get(name)
        require(actual is not None,'Retained actor missing from new map: '+name)
        expected=remap(original,SOURCE_MAP,MAP)
        mapping[original['guid']]=actual['guid']
        if guid_map is not None:require(guid_map.get(original['guid'])==actual['guid'],'Copied actor GUID changed: '+name)
        expected['guid']=actual['guid']
        for change in expected_meshes:
            if change['actor_name']!=name:continue
            left=next(c for c in expected['components'] if c['name']==change['component_name'])
            right=next(c for c in actual['components'] if c['name']==change['component_name'])
            require(left['mesh']==change['before'] and right['mesh']==change['after'],'Approved solar mesh before/after mismatch')
            left['mesh']=change['after']
        for (target,component_name,slot),change in material_slots.items():
            if target!=name:continue
            left=next(c for c in expected['components'] if c['name']==component_name)
            right=next(c for c in actual['components'] if c['name']==component_name)
            require(left['materials'][slot]==change['before'] and right['materials'][slot]==change['after'],
                    'Approved material slot before/after mismatch: '+name+'/'+component_name+'/'+str(slot))
            left['materials'][slot]=change['after']
        for (target,field),change in allowed.items():
            if target!=name:continue
            left,right=expected,actual
            for segment in field[:-1]:
                if isinstance(left,list):left=next(c for c in left if c['name']==segment);right=next(c for c in right if c['name']==segment)
                else:left=left[segment];right=right[segment]
            require(left[field[-1]]==change['before'] and right[field[-1]]==change['after'],
                    'Lighting allowlist before/after mismatch: '+name)
            left[field[-1]]=deepcopy(change['after'])
        require(canonical_actor(expected)==canonical_actor(actual),'Retained actor geometry/component/state changed: '+original['label'])
        normalized.append(canonical_actor(actual))
    require(len(set(mapping.values()))==len(mapping),'Duplicate copied actor GUID mapping')
    require(remap(source['world_settings'],SOURCE_MAP,MAP)==current['world_settings'],'World settings changed in new map')
    require(canonical_coverage(remap(source.get('world_actor_coverage',[]),SOURCE_MAP,MAP))==
            canonical_coverage(current.get('world_actor_coverage',[])),
            'Unfiltered engine auxiliary actor state changed in new map')
    return dict(retained_actor_count=len(mapping),source_to_copy_guid=mapping,
                retained_actor_digest=digest(sorted(normalized,key=lambda r:r['name'])))

def assert_new_actor_scope(source,current,plan):
    retained={r['name'] for r in plan['actors'] if r['action'].startswith('keep_')}
    forbidden={r['name'] for r in plan['actors'] if r['action']=='remove_old_exterior'}
    allowed_classes={'/Script/Engine.StaticMeshActor',
        '/Game/GHSDigitalTwin/Blueprints/BP_GHS_InstanceGroup.BP_GHS_InstanceGroup_C',
        '/Script/Test.EnvironmentRenderProfile'}
    retained_paths={r['path'] for r in current['actors'] if r['name'] in retained}
    added=[]
    for row in current['actors']:
        require(row['name'] not in forbidden or TAG in row['tags'],'Old exterior survived in new map: '+row['label'])
        if row['name'] in retained:continue
        require(row['class'] in allowed_classes and TAG in row['tags'] and row['folder'].startswith(FOLDER+'/'),
                'Unexpected new scene actor: '+row['label'])
        require(row['attachment_parent'] is None,'New scene actor must not attach to retained building')
        require(not any(c.get('attach_parent') and any(c['attach_parent'].startswith(p+'.') for p in retained_paths)
                        for c in row['components']),'New component must not attach to retained building')
        added.append(row['guid'])
    return sorted(added)
