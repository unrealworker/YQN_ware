"""Build a separate MPR map; source map and every existing Content file are read-only."""
import hashlib,json,math,re,shutil,sys,traceback
from collections import defaultdict
from pathlib import Path
import unreal as u
ROOT=Path(u.Paths.convert_relative_path_to_full(u.Paths.project_dir())).resolve()
sys.path.insert(0,str(ROOT/'Tools/MPRWarehouse'))
import rebuild_preservation as guard
import import_mpr_scene as core
SRC=ROOT/'SourceAssets/MPR/rebuild_b50b57'
OUT=ROOT/'Saved/MPR/rebuild_20261104'
REPORT=OUT/'import_report.json'
DEST=guard.DEST
result=dict(success=False,source_map=guard.SOURCE_MAP,map=guard.MAP,namespace=DEST,
            phase='preflight',created_packages=[],created_actors=[],source_map_saved=False,
            final_map_saved=False)
require=guard.require
sha=guard.sha

def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))

def write_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    temp.replace(path)

def write():write_json(REPORT,result)

def source_path(name):
    path=(ROOT/name).resolve()
    require(path.is_relative_to(SRC.resolve()) and path.is_file(),'Source outside rebuild or missing: '+name)
    return path

def validate_manifest(manifest):
    namespaces=[manifest[k] for k in ('namespace','rebuild_namespace','extension_namespace') if k in manifest]
    require(namespaces and all(n==DEST for n in namespaces),'Incorrect/missing rebuild namespace')
    require(manifest.get('map',guard.MAP)==guard.MAP,'Incorrect rebuild map')
    require(not manifest.get('allowed_replacements'),'Independent rebuild must not replace original-map meshes')
    guard.retained_material_spec_map(manifest.get('retained_material_overrides',[]),manifest['materials'])
    rows=manifest['meshes'];require(bool(rows),'Empty rebuilt mesh list')
    names=[r['name'] for r in rows]
    require(len(set(n.lower() for n in names))==len(names),'Duplicate rebuild mesh names')
    for row in rows:
        require(re.fullmatch(r'SM_[A-Za-z0-9_-]+',row['name']) is not None,'Invalid mesh name')
        require(re.fullmatch(r'[A-Za-z0-9_]+',row['category']) is not None,'Invalid category')
        require(not row.get('replacement_only') and not row.get('lod_files'),'Unexpected replacement/LOD contract')
        require(source_path(row['fbx']).suffix.lower()=='.fbx','Expected FBX source')
        require(sha(source_path(row['fbx']))==row['sha256'],'FBX hash mismatch: '+row['name'])
        require(row['material_roles'] and set(row['material_roles'])<=set(manifest['materials']),
                'Unspecified mesh material: '+row['name'])
    for role,spec in manifest['materials'].items():
        require(re.fullmatch(r'[A-Za-z0-9_]+',role) is not None,'Invalid material role')
        color=spec.get('color',spec.get('base_color'))
        if color is not None:require(len(color)>=3 and all(math.isfinite(float(c)) and 0<=c<=1 for c in color),
                                   'Invalid material color: '+role)
    for name,instances in manifest.get('instances',{}).items():
        require(name in names or name in manifest.get('reused_meshes',{}),'Missing instance mesh: '+name)
        for row in instances:
            values=[*row['position_m'],row.get('rotation_deg',0),row.get('pitch_deg',0),*row.get('scale',[1,1,1])]
            require(len(row['position_m'])==3 and len(row.get('scale',[1,1,1]))==3 and
                    all(math.isfinite(float(v)) for v in values),'Invalid instance transform')
    return rows

def ensure_new_destination(package):
    require(package.startswith(DEST+'/'),'New asset escaped rebuild namespace: '+package)
    base=ROOT/('Content/'+package.removeprefix('/Game/'))
    require(not any(base.with_suffix(s).exists() for s in guard.SUFFIXES),'Rebuild destination already exists: '+package)
    require(not core.LIB.does_asset_exist(package),'Rebuild asset is already registered: '+package)

def save_new(asset):
    package=asset.get_path_name().split('.')[0]
    require(package.startswith(DEST+'/'),'Refusing to save original asset: '+package)
    require(core.LIB.save_loaded_asset(asset,only_if_is_dirty=False),'Could not save new asset: '+package)
    if package not in result['created_packages']:result['created_packages'].append(package)

def sync_registry(packages):
    files=[str(ROOT/('Content/'+p.removeprefix('/Game/')+'.uasset')) for p in packages]
    require(all(Path(f).is_file() for f in files),'New asset save incomplete')
    registry=u.AssetRegistryHelpers.get_asset_registry()
    registry.scan_modified_asset_files(files);registry.scan_paths_synchronous([DEST],True)
    registry.wait_for_completion()
    options=u.AssetRegistryDependencyOptions(include_soft_package_references=True,
        include_hard_package_references=True,include_searchable_names=False,
        include_soft_management_references=False,include_hard_management_references=False)
    for package in packages:
        require(registry.get_dependencies(package,options) is not None,
                'New dependency node unavailable after synchronous scan: '+package)

def create_materials(specs):
    copied={};solar_parent=None
    def clone(asset):
        source=asset.get_path_name().split('.')[0]
        if source in copied:return copied[source]
        name=asset.get_name();path=DEST+'/Materials/'+name
        ensure_new_destination(path)
        duplicate=core.TOOLS.duplicate_asset(name,DEST+'/Materials',asset)
        require(duplicate is not None,'Cannot duplicate material: '+source)
        copied[source]=duplicate
        if isinstance(duplicate,u.MaterialInstanceConstant):
            parent=asset.get_editor_property('parent')
            require(parent is not None,'Copied material has no parent: '+source)
            core.MATLIB.set_material_instance_parent(duplicate,clone(parent))
        require(isinstance(duplicate,(u.Material,u.MaterialInstanceConstant)),'Unsupported material parent: '+source)
        save_new(duplicate)
        return duplicate
    # Ground instances must exist before terminal instances bind their read-only
    # texture references and matching color; a new grass tint must not reveal
    # the old parent's default color at the outside fade.
    ordered=sorted(specs.items(),key=lambda item:(bool(item[1].get('vertex_color_fade')),item[0]))
    for role,spec in ordered:
        path='/Game/MPRWarehouse/ReferenceV4/Materials/MI_'+role
        if core.LIB.does_asset_exist(path):
            mat=clone(core.load(path))
        else:
            master=clone(core.load('/Game/MPRWarehouse/ReferenceV4/Materials/M_MPR4_PBRSolid'))
            name='MI_'+role;ensure_new_destination(DEST+'/Materials/'+name)
            mat=core.TOOLS.create_asset(name,DEST+'/Materials',u.MaterialInstanceConstant,u.MaterialInstanceConstantFactoryNew())
            require(mat is not None,'Cannot create new solid material: '+role)
            core.MATLIB.set_material_instance_parent(mat,master)
        if spec.get('solar_surface'):
            from mpr_rebuild_materials import make_solar_parent
            original=core.load(path)
            textures={param:core.MATLIB.get_material_instance_texture_parameter_value(original,param)
                      for param in ('Albedo','Normal')}
            require(all(textures.values()),'Original solar texture missing: '+role)
            if solar_parent is None:solar_parent=make_solar_parent(u,core,DEST,save_new,original)
            core.MATLIB.set_material_instance_parent(mat,solar_parent)
            for param,texture in textures.items():core.MATLIB.set_material_instance_texture_parameter_value(mat,param,texture)
            core.MATLIB.set_material_instance_scalar_parameter_value(mat,'AlbedoLuminanceReference',spec['albedo_luminance_reference'])
        color=spec.get('color',spec.get('base_color'))
        if color is not None:
            core.MATLIB.set_material_instance_vector_parameter_value(mat,'Tint',u.LinearColor(*color[:3],1.))
            actual=core.MATLIB.get_material_instance_vector_parameter_value(mat,'Tint')
            require(max(abs(a-b) for a,b in zip([actual.r,actual.g,actual.b],color))<1e-5,'Tint override failed: '+role)
        for key,param in [('roughness','Roughness'),('metallic','Metallic'),('specular','Specular'),
                          ('emission','Emission'),('normal_strength','NormalStrength')]:
            if key in spec:
                core.MATLIB.set_material_instance_scalar_parameter_value(mat,param,float(spec[key]))
                require(abs(core.MATLIB.get_material_instance_scalar_parameter_value(mat,param)-float(spec[key]))<1e-5,
                        'Scalar override failed: '+role+'/'+param)
        if 'two_sided' in spec:
            overrides=mat.get_editor_property('base_property_overrides')
            overrides.set_editor_property('override_two_sided',True)
            overrides.set_editor_property('two_sided',bool(spec['two_sided']))
            mat.set_editor_property('base_property_overrides',overrides)
        fade=spec.get('vertex_color_fade')
        if fade:
            require(core.LIB.does_asset_exist(path),'A new fade role requires an existing authored terminal master')
            require(fade.get('channel')=='R' and fade.get('opaque') is True,'Unsupported vertex fade contract')
            ground_role=fade['ground_role'];require(ground_role in core.MATS,'Missing fade ground material: '+ground_role)
            ground=specs[ground_role];ground_mat=core.MATS[ground_role]
            color=ground.get('color',ground.get('base_color'))
            require(color is not None,'Fade ground has no explicit color')
            core.MATLIB.set_material_instance_vector_parameter_value(mat,'GroundTint',u.LinearColor(*color[:3],1.))
            core.MATLIB.set_material_instance_vector_parameter_value(mat,'GroundUVScale',u.LinearColor(1/600,-1/600,0,1))
            for key,param,default in [('roughness','GroundRoughness',.98),('metallic','GroundMetallic',0.),
                                     ('specular','GroundSpecular',.25),('normal_strength','GroundNormalStrength',.06)]:
                core.MATLIB.set_material_instance_scalar_parameter_value(mat,param,float(ground.get(key,default)))
            for param,ground_param in [('GroundAlbedo','Albedo'),('GroundNormal','Normal')]:
                texture=core.MATLIB.get_material_instance_texture_parameter_value(ground_mat,ground_param)
                require(texture is not None,'Missing read-only fade texture: '+ground_role+'/'+ground_param)
                core.MATLIB.set_material_instance_texture_parameter_value(mat,param,texture)
        core.MATLIB.update_material_instance(mat);save_new(mat)
        core.MATS[role]=mat
    result['material_copies']={k:v.get_path_name() for k,v in copied.items()}

def readonly_instance_material(mat):
    require(mat is not None and core.MATLIB.has_material_usage(mat,core.USAGE),
            'HISM material usage missing; refusing to modify an old parent: '+str(mat))
    return mat

def rebuild_instance_transform(row):
    # CAD uses +X forward, +Z up. Reflection of CAD Y into UE Y negates yaw;
    # pitch remains positive when the forward bogie is higher than the rear.
    # This wrapper affects only the new-map groups; the shared importer stays
    # unchanged and retained main-building transforms are never reconstructed.
    return u.Transform(location=core.pos(row['position_m']),
        rotation=u.Rotator(pitch=float(row.get('pitch_deg',0)),yaw=-float(row.get('rotation_deg',0))),
        scale=u.Vector(*row.get('scale',[1,1,1])))

def apply_retained_materials(manifest,source,plan,guid_map):
    changes=guard.expected_retained_material_changes(source,plan,guid_map,
        manifest.get('retained_material_overrides',[]))
    actors={u.GuidLibrary.conv_guid_to_string(a.get_editor_property('actor_guid')):a
            for a in core.A.get_all_level_actors()}
    for change in changes:
        actor=actors[change['actor_guid']]
        require(actor.get_name()==change['actor_name'],'Retained material actor identity mismatch')
        components=[c for c in actor.get_components_by_class(u.StaticMeshComponent)
                    if c.get_name()==change['component_name']]
        require(len(components)==1,'Retained material component is missing/ambiguous')
        component=components[0];slot=change['slot'];material=core.MATS[change['role']]
        require(slot<component.get_num_materials() and component.get_material(slot).get_path_name()==change['before'],
                'Retained material original slot changed before assignment')
        require(material.get_path_name()==change['after'] and change['after'].startswith(DEST+'/Materials/'),
                'Retained material replacement is not the approved new clone')
        component.set_material(slot,material)
        require(component.get_material(slot).get_path_name()==change['after'],'Retained material slot assignment failed')
    return changes

def apply_retained_meshes(manifest,source,plan,guid_map):
    changes=guard.expected_retained_mesh_changes(source,plan,guid_map,manifest.get('retained_mesh_overrides',[]))
    actors={u.GuidLibrary.conv_guid_to_string(a.get_editor_property('actor_guid')):a
            for a in core.A.get_all_level_actors()}
    for change in changes:
        actor=actors[change['actor_guid']]
        require(actor.get_name()==change['actor_name'],'Retained solar actor identity mismatch')
        components=[c for c in actor.get_components_by_class(u.StaticMeshComponent) if c.get_name()==change['component_name']]
        require(len(components)==1,'Retained solar component is missing/ambiguous')
        component=components[0]
        require(component.static_mesh.get_path_name()==change['before'],'Solar source mesh changed before replacement')
        require(component.get_num_materials()==4,'Solar component lost its four material slots')
        materials=[component.get_material(slot) for slot in range(4)]
        paths=[m.get_path_name() for m in materials]
        mesh=core.MESHES[change['after'].rsplit('.',1)[1]]
        require(mesh.get_path_name()==change['after'],'Solar replacement escaped the exact destination')
        require(component.set_static_mesh(mesh),'Solar component rejected replacement mesh')
        # Preserve effective slots explicitly: default materials on the new mesh
        # must not silently change the retained component's material bindings.
        for slot,material in enumerate(materials):component.set_material(slot,material)
        require(component.get_num_materials()==4 and [component.get_material(i).get_path_name() for i in range(4)]==paths,
                'Solar replacement reordered effective component materials')
    return changes

def tag(actor,folder,extra=()):
    actor.set_folder_path(guard.FOLDER+'/'+folder)
    actor.tags=['MPRWarehouse',guard.TAG,*extra]
    actor.set_actor_tick_enabled(False);actor.set_actor_enable_collision(False)
    result['created_actors'].append(actor.get_actor_label())

def apply_lighting(manifest):
    def typed(value,current):
        if isinstance(value,dict) and set(value)=={'enum'}:
            family,member=value['enum'].split('.')
            require(family in {'AutoExposureMethod','DynamicGlobalIlluminationMethod','ReflectionMethod'},'Unsupported lighting enum')
            return getattr(getattr(u,family),member)
        if isinstance(value,list):return type(current)(*value)
        return value
    changes=[];seen=set()
    for spec in manifest.get('lighting_overrides',[]):
        label=spec['actor_label'];component_name=spec.get('component_name');prop=spec['property']
        require(label in guard.LIGHT_LABELS,'Lighting override outside copied style actors')
        key=(label,component_name,prop);require(key not in seen,'Duplicate lighting override');seen.add(key)
        actors=[a for a in core.A.get_all_level_actors() if a.get_actor_label()==label]
        require(len(actors)==1,'Lighting actor is ambiguous: '+label)
        actor=actors[0];before=guard.capture(u,ROOT,guard.MAP)
        record=next(r for r in before['actors'] if r['name']==actor.get_name())
        target=actor;field=['render_settings',prop]
        if component_name:
            matches=[c for c in actor.get_components_by_class(u.ActorComponent) if c.get_name()==component_name]
            require(len(matches)==1,'Unknown lighting component')
            target=matches[0];row=next(c for c in record['components'] if c['name']==component_name)
            field=['components',component_name,'render_settings',prop]
        else:row=record
        require(prop in row.get('render_settings',{}),'Property is not a recorded lighting/render field')
        previous=row['render_settings'][prop];value=spec['value'];existing=target.get_editor_property(prop)
        if isinstance(value,dict):
            for k,v in value.items():existing.set_editor_property(k,typed(v,existing.get_editor_property(k)))
            value=existing
        elif isinstance(value,list):value=type(existing)(*value)
        target.set_editor_property(prop,value)
        after=guard.capture(u,ROOT,guard.MAP)
        changed=next(r for r in after['actors'] if r['name']==actor.get_name())
        if component_name:changed=next(c for c in changed['components'] if c['name']==component_name)
        changes.append(dict(actor_name=actor.get_name(),field=field,before=previous,after=changed['render_settings'][prop]))
    return changes

def run():
    OUT.mkdir(parents=True,exist_ok=True)
    require(not REPORT.exists(),'Rebuild report already exists; review prior attempt before a retry')
    manifest=read(SRC/'manifest.json');rows=validate_manifest(manifest)
    solar_rows,solar_files=guard.solar_source_contract(ROOT,manifest)
    source_files={r['fbx']:r['sha256'] for r in rows};source_files.update(solar_files)
    plan=read(SRC/'protection_plan.json')
    require(not (SRC/'scene_ownership.json').exists(),'New map already has ownership')
    new_map_file=ROOT/'Content/Maps/MPR_CAD_Warehouse_B50B57.umap'
    require(not any(new_map_file.with_suffix(s).exists() for s in guard.SUFFIXES),'New map destination already exists')
    require(not any((ROOT/'Content/MPRWarehouse/RebuildB50B57').glob('**/*.*')),'New namespace is not empty')
    source=guard.capture(u,ROOT,guard.SOURCE_MAP);guard.assert_clean(source);guard.assert_source_plan(plan,source)
    guard.expected_retained_mesh_changes(source,plan,{r['guid']:r['guid'] for r in source['actors']},
        manifest.get('retained_mesh_overrides',[]))
    old_files=guard.content_hashes(ROOT)
    ownership_paths=[ROOT/'SourceAssets/MPR/scene_ownership.json',ROOT/'SourceAssets/MPR/extension_b50b57/scene_ownership.json']
    old_manifests={p.relative_to(ROOT).as_posix():sha(p) for p in ownership_paths if p.exists()}
    write_json(OUT/'source_snapshot.json',source);write_json(OUT/'old_content_hashes.json',old_files)
    write_json(OUT/'old_ownership_hashes.json',old_manifests)
    shutil.copy2(ROOT/'Content/Maps/MPR_CAD_Warehouse.umap',OUT/'source_map_backup.umap')
    shutil.copy2(SRC/'manifest.json',OUT/'imported_manifest.json')
    result.update(source_map_sha256=source['map_file_sha256'],source_actor_digest=guard.digest(source['actors']),
        source_manifest_sha256=sha(SRC/'manifest.json'),protection_plan_sha256=sha(SRC/'protection_plan.json'),
        old_content_file_count=len(old_files),phase='duplicating_map')
    write()
    # Native NewLevelFromTemplate loads the source into an untitled package
    # (bLoadAsTemplate=true), then saves only the requested destination. Do not
    # AssetTools-duplicate a live UWorld: its RF_Standalone copy survives the
    # subsequent LoadLevel GC and UE 5.8 correctly aborts for a leaked world.
    # No source-world UObject is held across the native level transition.
    require(core.L.new_level_from_template(guard.MAP,guard.SOURCE_MAP),
            'Failed to create independent map from source template')
    guard.assert_old_files(ROOT,old_files)
    copy=guard.capture(u,ROOT,guard.MAP)
    retained=guard.assert_retained(source,copy,plan)
    by_name={a.get_name():a for a in core.A.get_all_level_actors()}
    removed=[]
    for row in plan['actors']:
        if row['action']!='remove_old_exterior':continue
        actor=by_name[row['name']]
        removed.append(dict(source_guid=row['guid'],copy_guid=u.GuidLibrary.conv_guid_to_string(actor.get_editor_property('actor_guid')),name=row['name']))
        require(core.A.destroy_actor(actor),'Failed to remove copied exterior: '+row['name'])
    result['removed_from_copy']=removed;result['retention']=retained;result['phase']='importing_new_assets';write()
    core.DEST=DEST;core.tag=tag;core.instance_material=readonly_instance_material
    core.transform=rebuild_instance_transform
    core.MATS.clear();core.MESHES.clear();core.INSTANCE_MATS.clear()
    core.result=dict(meshes=[],groups=[],materials_created=[],reused_assets=[])
    create_materials(manifest['materials'])
    if solar_rows:
        core.MATS['MPR4_SolarFrame']=core.load('/Game/MPRWarehouse/ReferenceV4/Materials/MI_MPR4_SolarFrame')
    material_changes=apply_retained_materials(manifest,source,plan,retained['source_to_copy_guid'])
    result['material_changes']=material_changes;write()
    for row in [*rows,*solar_rows]:
        destination=DEST+'/'+row['category']+'/Meshes/'+row['name'];ensure_new_destination(destination)
        mesh=core.import_mesh(row,row['category'])
        require(mesh.get_path_name().split('.')[0]==destination,'Imported mesh outside planned package')
        result['created_packages'].append(destination)
        if row in solar_rows:
            settings=core.SM.get_nanite_settings(mesh)
            if settings.enabled:
                settings.enabled=False;core.SM.set_nanite_settings(mesh,settings,True);save_new(mesh)
    sync_registry(result['created_packages'])
    mesh_changes=apply_retained_meshes(manifest,source,plan,retained['source_to_copy_guid'])
    result['mesh_changes']=mesh_changes;result['solar_mesh_audit']=guard.audit_solar_meshes(u,solar_rows);write()
    for row in rows:
        if row.get('instance_only'):continue
        actor=core.spawn_mesh(row['name'],core.MESHES[row['name']],folder=row['category'])
        if row.get('disable_shadow_casting'):actor.get_component_by_class(u.StaticMeshComponent).set_editor_property('cast_shadow',False)
    for name,instances in manifest.get('instances',{}).items():
        if not instances:continue
        mesh=core.MESHES.get(name) or core.load(manifest['reused_meshes'][name])
        for material in mesh.static_materials:readonly_instance_material(material.material_interface)
        tiles=defaultdict(list)
        for row in instances:
            tile=row.get('tile') or [math.floor(row['position_m'][0]/150),math.floor(row['position_m'][1]/150)]
            tiles[tuple(tile)].append(row)
        for (x,y),items in sorted(tiles.items()):
            core.group('MPRB_'+name+'_%d_%d'%(x,y),mesh,items,'Instances',
                roles=manifest.get('instance_material_roles',{}).get(name),cull=230000)
    changes=apply_lighting(manifest);result['lighting_changes']=changes
    profile_spec=manifest['render_profile']
    require(set(profile_spec)=={'lumen_clipmap_extent'} and 2500<=profile_spec['lumen_clipmap_extent']<=8000,
            'Invalid map-scoped render profile')
    profile=core.A.spawn_actor_from_class(u.EnvironmentRenderProfile,u.Vector(0,0,0))
    require(profile is not None,'Failed to create map-scoped render profile')
    profile.set_actor_label('MPRB_EnvironmentRenderProfile');tag(profile,'Lighting')
    profile.set_lumen_clipmap_extent(profile_spec['lumen_clipmap_extent'])
    require(abs(profile.get_editor_property('lumen_clipmap_extent')-profile_spec['lumen_clipmap_extent'])<.01,
            'Scene coverage profile did not persist requested extent')
    after=guard.capture(u,ROOT,guard.MAP)
    retained=guard.assert_retained(source,after,plan,guid_map=retained['source_to_copy_guid'],lighting_changes=changes,
        material_changes=material_changes,material_overrides=manifest.get('retained_material_overrides',[]),
        mesh_changes=mesh_changes,mesh_overrides=manifest.get('retained_mesh_overrides',[]))
    new_guids=guard.assert_new_actor_scope(source,after,plan)
    guard.assert_clean(after,allow_new_map=True);guard.assert_old_files(ROOT,old_files)
    require(sha(SRC/'manifest.json')==result['source_manifest_sha256'],'Build manifest changed during import')
    for filename,expected in source_files.items():require(sha(source_path(filename))==expected,'Source changed during import: '+filename)
    for filename,expected in old_manifests.items():require(sha(ROOT/filename)==expected,'Old ownership changed: '+filename)
    result['phase']='saving_new_map';write()
    require(core.L.save_current_level(),'Final save of new map failed');result['final_map_saved']=True
    registry=u.AssetRegistryHelpers.get_asset_registry()
    registry.scan_modified_asset_files([str(new_map_file)]);registry.wait_for_completion()
    result['independent_dependencies']=guard.assert_independent_dependencies(u)
    final=guard.capture(u,ROOT,guard.MAP);guard.assert_clean(final)
    require(after['actors']==final['actors'] and after['world_settings']==final['world_settings'] and
            guard.canonical_coverage(after['world_actor_coverage'])==guard.canonical_coverage(final['world_actor_coverage']),
            'Saving new map changed actor data')
    new_files=guard.assert_old_files(ROOT,old_files)
    write_json(OUT/'after_import.json',final)
    result.update(success=True,phase='complete',map_sha256=final['map_file_sha256'],
        source_map_unchanged=True,retention=retained,new_actor_guids=new_guids,
        after_import_sha256=sha(OUT/'after_import.json'),meshes=core.result['meshes'],groups=core.result['groups'])
    ownership=dict(schema_version=1,owner=guard.TAG,map=guard.MAP,namespace=DEST,source_map=guard.SOURCE_MAP,
        source_map_sha256=source['map_file_sha256'],map_sha256=final['map_file_sha256'],
        source_manifest_sha256=result['source_manifest_sha256'],protection_plan_sha256=result['protection_plan_sha256'],
        new_files=new_files,old_content_hashes_sha256=sha(OUT/'old_content_hashes.json'),
        old_ownership_hashes_sha256=sha(OUT/'old_ownership_hashes.json'),
        source_snapshot_sha256=sha(OUT/'source_snapshot.json'),after_import_sha256=result['after_import_sha256'],
        retention=retained,new_actor_guids=new_guids,lighting_changes=changes,material_changes=material_changes,
        mesh_changes=mesh_changes,solar_mesh_audit=result['solar_mesh_audit'],source_files=source_files,
        actor_digest=guard.digest([guard.canonical_actor(r) for r in final['actors']]))
    write_json(SRC/'scene_ownership.json',ownership)
    result['ownership_sha256']=sha(SRC/'scene_ownership.json');write()
    print('MPR_REBUILD_IMPORT_SUCCESS',len(rows),len(new_guids),retained['retained_actor_count'])

if __name__=='__main__':
    try:run()
    except Exception:
        result['error']=traceback.format_exc();write();u.log_error(result['error'])
