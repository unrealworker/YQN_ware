"""Replace only MPR exterior actors, preserving interior actor identity/data.

Run in a separate UE editor process via -ExecutePythonScript. The live user's
editor must be clean and closed first. Shared GHS assets are never written.
"""
import sys,json,hashlib,shutil,traceback,math
from pathlib import Path
from collections import defaultdict
import unreal as u
ROOT=Path(u.Paths.convert_relative_path_to_full(u.Paths.project_dir())).resolve()
sys.path.insert(0,str(ROOT/'Tools/MPRWarehouse'))
import import_mpr_scene as base
from mpr_scene_ownership import verify_owned_scene,record_successful_build
from mpr_interior_preservation import capture_editor_snapshot,assert_preserved
from mpr_reference_transaction import begin_transaction,record_failure,record_success
from mpr_reference_catalog import load_catalog,material_name,DEST,TAG

SRC=ROOT/'SourceAssets/MPR/reference_v4';OUT=ROOT/'Saved/MPR';MAP=base.MAP
LIB=base.LIB;ML=base.MATLIB;TOOLS=base.TOOLS;A=base.A;L=base.L;E=base.E;SM=base.SM
REPORT=OUT/'reference_v4_build.json'
R=dict(success=False,owner=base.OWNER,map=MAP,meshes=[],materials_created=[],groups=[],stage='preflight')
NEW_PACKAGES=[]
TX=None
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def write():REPORT.write_text(json.dumps(R,ensure_ascii=False,indent=2),encoding='utf-8')
def package(path):return ROOT/('Content/'+path.split('.')[0].removeprefix('/Game/')+('.umap' if path==MAP else '.uasset'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(asset):assert LIB.save_loaded_asset(asset,only_if_is_dirty=False),asset.get_path_name()

def expression(mat,klass,**props):
 n=ML.create_material_expression(mat,klass)
 for k,v in props.items():n.set_editor_property(k,v)
 return n
def connect(a,out,b,inp):assert ML.connect_material_expressions(a,out,b,inp),(a,b,inp)
def material_graph(textured,defaults):
 name='M_MPR4_PBRTextured' if textured else 'M_MPR4_PBRSolid';path=DEST+'/Materials/'+name
 mat=base.load(path) if LIB.does_asset_exist(path) else TOOLS.create_asset(name,DEST+'/Materials',u.Material,u.MaterialFactoryNew())
 while ML.get_num_material_expressions(mat):
  count=ML.get_num_material_expressions(mat);ML.delete_all_material_expressions(mat);assert ML.get_num_material_expressions(mat)<count
 mat.set_editor_property('blend_mode',u.BlendMode.BLEND_OPAQUE);mat.set_editor_property('shading_model',u.MaterialShadingModel.MSM_DEFAULT_LIT)
 tint=expression(mat,u.MaterialExpressionVectorParameter,parameter_name='Tint',default_value=u.LinearColor(.7,.7,.7,1))
 color=tint
 if textured:
  albedo=expression(mat,u.MaterialExpressionTextureSampleParameter2D,parameter_name='Albedo',texture=defaults['albedo'])
  mul=expression(mat,u.MaterialExpressionMultiply);connect(albedo,'RGB',mul,'A');connect(tint,'RGB',mul,'B');color=mul
  normal=expression(mat,u.MaterialExpressionTextureSampleParameter2D,parameter_name='Normal',texture=defaults['normal'],sampler_type=u.MaterialSamplerType.SAMPLERTYPE_NORMAL)
  flat=expression(mat,u.MaterialExpressionConstant3Vector,constant=u.LinearColor(0,0,1,1))
  alpha=expression(mat,u.MaterialExpressionScalarParameter,parameter_name='NormalStrength',default_value=.2)
  lerp=expression(mat,u.MaterialExpressionLinearInterpolate);connect(flat,'',lerp,'A');connect(normal,'RGB',lerp,'B');connect(alpha,'',lerp,'Alpha')
  assert ML.connect_material_property(lerp,'',u.MaterialProperty.MP_NORMAL)
 assert ML.connect_material_property(color,'',u.MaterialProperty.MP_BASE_COLOR)
 for name,value,prop in [('Roughness',.8,u.MaterialProperty.MP_ROUGHNESS),('Metallic',0,u.MaterialProperty.MP_METALLIC),('Specular',.25,u.MaterialProperty.MP_SPECULAR)]:
  node=expression(mat,u.MaterialExpressionScalarParameter,parameter_name=name,default_value=value);assert ML.connect_material_property(node,'',prop)
 emission=expression(mat,u.MaterialExpressionScalarParameter,parameter_name='Emission',default_value=0.)
 em=expression(mat,u.MaterialExpressionMultiply);connect(tint,'RGB',em,'A');connect(emission,'',em,'B');assert ML.connect_material_property(em,'',u.MaterialProperty.MP_EMISSIVE_COLOR)
 ML.set_material_usage(mat,base.USAGE)
 mat.set_editor_property('used_with_nanite',True)
 ML.recompile_material(mat);save(mat)
 R['materials_created'].append(dict(path=path,kind='material_master',textured=textured));return mat

def import_textures(specs):
 paths={}
 for role,spec in specs.items():
  for channel,source in spec.get('textures',{}).items():
   path=DEST+'/Textures/'+Path(source).stem
   options=(channel,spec.get('normal_convention','DirectX'))
   if source in paths:assert paths[source]['options']==options;continue
   task=u.AssetImportTask();task.filename=str(ROOT/source);task.destination_path=DEST+'/Textures';task.destination_name=Path(source).stem
   task.automated=True;task.replace_existing=True;task.save=False;TOOLS.import_asset_tasks([task])
   tex=base.load(path);tex.set_editor_property('srgb',channel!='normal')
   if channel=='normal':
    tex.set_editor_property('compression_settings',u.TextureCompressionSettings.TC_NORMALMAP)
    tex.set_editor_property('flip_green_channel',options[1]=='OpenGL')
   tex.set_editor_property('max_texture_size',2048);save(tex)
   paths[source]=dict(asset=tex,options=options);R['materials_created'].append(dict(path=path,kind='texture',source=source))
 return paths

def create_materials(specs):
 textures=import_textures(specs)
 sample=next(s for s in specs.values() if s.get('textures',{}).get('normal'))
 defaults={k:textures[v]['asset'] for k,v in sample['textures'].items()}
 masters={False:material_graph(False,defaults),True:material_graph(True,defaults)}
 for role,spec in specs.items():
  name=material_name(role);path=DEST+'/Materials/'+name
  mi=base.load(path) if LIB.does_asset_exist(path) else TOOLS.create_asset(name,DEST+'/Materials',u.MaterialInstanceConstant,u.MaterialInstanceConstantFactoryNew())
  ML.set_material_instance_parent(mi,masters[bool(spec.get('textures'))])
  overrides=mi.get_editor_property('base_property_overrides')
  overrides.set_editor_property('override_two_sided',True)
  overrides.set_editor_property('two_sided',bool(spec.get('two_sided',False)))
  mi.set_editor_property('base_property_overrides',overrides)
  color=list(spec.get('color',spec.get('base_color')))[:3]
  ML.set_material_instance_vector_parameter_value(mi,'Tint',u.LinearColor(*color,1));v=ML.get_material_instance_vector_parameter_value(mi,'Tint')
  assert max(abs(a-b) for a,b in zip(color,[v.r,v.g,v.b]))<1e-5
  scalars=[('Roughness',spec.get('roughness',.8)),('Metallic',spec.get('metallic',0)),('Specular',spec.get('specular',.25)),('Emission',spec.get('emission',0))]
  if spec.get('textures'):scalars.append(('NormalStrength',spec.get('normal_strength',.3)))
  for key,value in scalars:
   ML.set_material_instance_scalar_parameter_value(mi,key,float(value))
   assert abs(ML.get_material_instance_scalar_parameter_value(mi,key)-value)<1e-5
  for channel,source in spec.get('textures',{}).items():
   key='Normal' if channel=='normal' else 'Albedo';ML.set_material_instance_texture_parameter_value(mi,key,textures[source]['asset'])
   assert ML.get_material_instance_texture_parameter_value(mi,key)==textures[source]['asset']
  ML.set_material_usage_override(mi,base.USAGE,True,True);ML.update_material_instance(mi);save(mi)
  base.MATS[role]=mi;R['materials_created'].append(dict(path=path,kind='material_instance',role=role,parameters=spec))

def tag(actor,folder,extra=()):
 tags=list(extra)
 if 'RemovableRoof' in folder and 'MPR_Roof' not in tags:tags.append('MPR_Roof')
 actor.set_folder_path('MPR/ReferenceV4/'+folder);actor.tags=['MPRWarehouse',base.OWNER,TAG,*tags]
 actor.set_actor_tick_enabled(False);actor.set_actor_enable_collision(False)

def instance_groups(name,items,folder):
 # HISM already culls individual instances. Exterior vegetation covers a broad
 # area: 60m cells would multiply mostly sparse four-material draw batches.
 # Keep module groups within the campus and vegetation in 150m spatial cells.
 tile=150 if any(k in name for k in ('Tree','Bush','Car','Freight')) else 250
 tiles=defaultdict(list)
 for row in items:
  x,y=row['position_m'][:2];tiles[math.floor(x/tile),math.floor(y/tile)].append(row)
 for (x,y),group in sorted(tiles.items()):
  base.group('MPR4_'+name.removeprefix('SM_')+'_%d_%d'%(x,y),base.MESHES[name],group,folder,cull=150000 if any(k in name for k in ('Tree','Bush','Car')) else 0)

def lighting():
 # Preserve the existing runtime camera actor and its input logic.
 sun=A.spawn_actor_from_class(u.DirectionalLight,u.Vector(0,0,18000));sun.set_actor_label('MPR4_KeyLight');tag(sun,'Lighting')
 sun.set_actor_rotation(u.Rotator(pitch=-53,yaw=145),False);c=sun.get_component_by_class(u.DirectionalLightComponent)
 c.set_mobility(u.ComponentMobility.MOVABLE);c.set_intensity(3.8);c.set_light_color(u.LinearColor(.98,.99,1.,1));c.set_editor_property('light_source_angle',12.)
 sky=A.spawn_actor_from_class(u.SkyLight,u.Vector());sky.set_actor_label('MPR4_Ambient');tag(sky,'Lighting')
 c=sky.get_component_by_class(u.SkyLightComponent);c.set_mobility(u.ComponentMobility.MOVABLE);c.set_intensity(.65)
 c.set_editor_property('source_type',u.SkyLightSourceType.SLS_SPECIFIED_CUBEMAP);c.set_cubemap(base.load('/Engine/EngineResources/GrayLightTextureCube'))
 c.set_light_color(u.LinearColor(.94,.97,1,1));c.set_editor_property('real_time_capture',False);c.set_editor_property('cast_shadows',False)
 c.set_editor_property('lower_hemisphere_is_black',False);c.set_editor_property('lower_hemisphere_color',u.LinearColor(.13,.15,.16,1))
 pp=A.spawn_actor_from_class(u.PostProcessVolume,u.Vector());pp.set_actor_label('MPR4_ReferenceStyle');tag(pp,'Lighting');pp.set_editor_property('unbound',True)
 s=pp.get_editor_property('settings')
 for k,v in dict(dynamic_global_illumination_method=u.DynamicGlobalIlluminationMethod.NONE,reflection_method=u.ReflectionMethod.NONE,vignette_intensity=0.,bloom_intensity=0.,ambient_occlusion_intensity=1.15,ambient_occlusion_radius=140.,ambient_occlusion_quality=85.,auto_exposure_min_brightness=0.,auto_exposure_max_brightness=0.,auto_exposure_bias=.45,motion_blur_amount=0.).items():
  s.set_editor_property('override_'+k,True);s.set_editor_property(k,v)
 pp.set_editor_property('settings',s)
 skyactor=base.spawn_mesh('MPR4_StudioSky',base.load('/Engine/BasicShapes/Sphere'),'Lighting',scale=[20000]*3,roles=['Sky'])
 skyactor.get_component_by_class(u.StaticMeshComponent).set_editor_property('cast_shadow',False)

def run():
 global NEW_PACKAGES,TX
 assert not L.is_in_play_in_editor()
 dirty=[p.get_path_name() for p in u.EditorLoadingAndSavingUtils.get_dirty_map_packages()+u.EditorLoadingAndSavingUtils.get_dirty_content_packages()]
 assert not dirty,('Preserve unsaved editor work',dirty)
 catalog=load_catalog(ROOT)
 specs=catalog['materials'];rows=catalog['rows'];instances=catalog['instances']
 owned=read(ROOT/'SourceAssets/MPR/scene_ownership.json');oldpackages=[r['package'] for r in owned['packages'] if r['package']!=MAP]
 planned=[DEST+'/'+c+'/Meshes/'+r['name'] for c,r in rows]
 planned += [DEST+'/Materials/'+material_name(role) for role in specs]
 planned += [DEST+'/Materials/M_MPR4_PBRTextured',DEST+'/Materials/M_MPR4_PBRSolid']
 planned += list({DEST+'/Textures/'+Path(p).stem for spec in specs.values() for p in spec.get('textures',{}).values()})
 token=verify_owned_scene(ROOT,planned_assets=sorted(set(oldpackages+planned)))
 NEW_PACKAGES=[p for p in planned if not package(p).exists()]
 assert L.load_level(MAP)
 before=capture_editor_snapshot(u,project_root=ROOT)
 beforefile=OUT/'reference_v3_interior_before.json'
 if beforefile.exists():
  original=read(beforefile);assert_preserved(original,before)
 else:beforefile.write_text(json.dumps(before,ensure_ascii=False,indent=2),encoding='utf-8')
 backup=OUT/'reference_v3_before.umap'
 if not backup.exists():shutil.copy2(package(MAP),backup)
 # Agent helper classifies exact GUIDs; the snapshot is the deletion contract.
 delete_guids={row['guid'] for row in before['actors'] if row['classification'] in ('old_exterior','new_exterior')}
 R['replaced_actor_guids']=sorted(delete_guids);R['before_snapshot']=str(beforefile)
 TX=begin_transaction(ROOT,planned_assets=planned,map_path=MAP,build_report=REPORT.relative_to(ROOT).as_posix());R['transaction']=TX
 base.DEST=DEST;base.result=R;base.REPORT=REPORT;base.tag=tag
 create_materials(specs);R['stage']='materials';write()
 oldflag=u.SystemLibrary.get_console_variable_int_value('Interchange.FeatureFlags.Import.FBX')
 u.SystemLibrary.execute_console_command(None,'Interchange.FeatureFlags.Import.FBX 0')
 try:
  for category,row in rows:
   row=dict(row)
   if category in ('Architecture','Site','Context'):row['full_precision_uvs']=True
   mesh=base.import_mesh(row,category)
   # Opaque foliage and detailed context benefit from Nanite clustering and
   # virtual-shadow culling; ground/paint are deliberately kept simple.
   if (category=='Props' and 'Tree' in row['name']) or category in ('Architecture','Context') or (category=='Site' and any(k in row['name'] for k in ('Rails','Sleepers'))):
    settings=SM.get_nanite_settings(mesh);settings.enabled=True
    settings.fallback_relative_error=0.
    if category=='Architecture':settings.position_precision=5
    if 'SolarBank' in row['name']:
     # Thin overlapping cell/frame surfaces must keep their authored topology.
     # Their modest triangle budget is cheaper than a global Nanite quality boost.
     settings.enabled=False
    if 'Tree' in row['name']:
     settings.shape_preservation=u.NaniteShapePreservation.PRESERVE_AREA
     settings.max_edge_length_factor=0.
     settings.fallback_target=u.NaniteFallbackTarget.PERCENT_TRIANGLES
     settings.fallback_percent_triangles=.25
    SM.set_nanite_settings(mesh,settings,True);save(mesh)
  # All imports finish before any actor is removed.
  R['stage']='imported';write()
  for actor in list(A.get_all_level_actors()):
   if u.GuidLibrary.conv_guid_to_string(actor.get_editor_property('actor_guid')) in delete_guids:assert A.destroy_actor(actor)
  for category,row in rows:
   if row.get('instance_only'):continue
   name=row['name'];a=base.spawn_mesh(name.removeprefix('SM_'),base.MESHES[name],category)
   if category=='Site' and not any(k in name for k in ('Rails','Sleepers','RaisedCurbs')):
    a.get_component_by_class(u.StaticMeshComponent).set_editor_property('cast_shadow',False)
   if category=='Architecture' and any(word in name for word in ['Roof','Solar','Skylight','HVAC']):tag(a,category+'/RemovableRoof',['MPR_Roof'])
  for name,items in instances.items():
   assert name in base.MESHES,('Unknown instanced model',name)
   roof=any(word in name for word in ['Roof','Solar','Skylight','HVAC']);folder='Architecture/RemovableRoof' if roof else 'Props'
   beforegroups=len(R['groups']);instance_groups(name,items,folder)
   if roof:
    labels={g['actor'] for g in R['groups'][beforegroups:]}
    # Setting tags after HISM fill reconstructs data; actor tags are restored
    # only through tag() before fill. Use folder for roof visibility instead.
    R.setdefault('roof_group_labels',[]).extend(sorted(labels))
  lighting()
 finally:u.SystemLibrary.execute_console_command(None,'Interchange.FeatureFlags.Import.FBX '+str(oldflag))
 after=capture_editor_snapshot(u,project_root=ROOT);comparison=assert_preserved(read(beforefile),after,require_old_exterior_removed=True)
 R['interior_preservation']=comparison
 A.set_selected_level_actors([]);L.editor_set_game_view(True);assert L.save_current_level()
 # Retain file ownership for legacy source assets still on disk without
 # pretending that they are rendered in the rebuilt exterior.
 current={r['path'] for r in R['meshes']+R['materials_created']}
 R['retained_owned_packages']=[p for p in oldpackages if p not in current]
 ownership_report=dict(R);ownership_report['meshes']=R['meshes']+[dict(path=p,retained_unchanged=True) for p in oldpackages if p not in current]
 R.update(success=True,actor_count=len(A.get_all_level_actors()),instance_count=sum(g['count'] for g in R['groups']),stage='saved')
 ownership_report['success']=True;record_successful_build(ROOT,ownership_report,token)
 write();record_success(TX);TX=None;print('MPR_REFERENCE_EXTERIOR_IMPORTED',R['actor_count'],R['instance_count'])

if __name__=='__main__':
 try:run()
 except Exception:
  error=traceback.format_exc()
  R.update(success=False,error=error,partial_new_packages={p:sha(package(p)) for p in NEW_PACKAGES if package(p).is_file()});write()
  if TX:print('MPR_REFERENCE_ROLLBACK',record_failure(TX,error))
  raise
