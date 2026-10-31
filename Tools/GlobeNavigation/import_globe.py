"""Run in UE 5.8 Python: import atlas assets and author the dedicated entry map.

Only /Game/GlobeNavigation and /Game/Maps/GHS_GlobalWarehouse are written.
The existing warehouse map is loaded asynchronously at runtime and never resaved here.
"""
import json
import math
from pathlib import Path
import unreal as u

ROOT = Path(u.Paths.project_dir())
SOURCE = ROOT / 'SourceAssets/GlobeNavigation'
DEST = '/Game/GlobeNavigation'
MAP = '/Game/Maps/GHS_GlobalWarehouse'
axis_report = json.loads((SOURCE/'ue-axis-report.json').read_text(encoding='utf-8'))
axis_checks = {}
for marker, expected in [
    ('Greenwich', (100.3, 0, 0)),
    ('East90', (0, -100.3, 0)),
    ('North', (0, 0, 100.3)),
    ('GHS', (-38.48258, 74.15034, 56.75477)),
]:
    matches = [v['center'] for k, v in axis_report.items() if k.endswith('CAL_'+marker)]
    if len(matches) != 1 or len(matches[0]) != 3:
        raise RuntimeError('Missing or duplicate FBX calibration marker: '+marker)
    actual = matches[0]
    if any(not math.isfinite(a) or abs(a-b) > .01 for a, b in zip(actual, expected)):
        raise RuntimeError('FBX axis convention changed; recalibrate globe before import: '+marker)
    axis_checks[marker] = actual

lod_sources = [SOURCE/('SM_Earth_LOD%d.fbx' % index) for index in range(3)]
for filename in lod_sources:
    if not filename.is_file():
        raise FileNotFoundError(filename)
tools = u.AssetToolsHelpers.get_asset_tools()
assets = u.EditorAssetLibrary
mesh_editor = u.get_editor_subsystem(u.StaticMeshEditorSubsystem)
level_editor = u.get_editor_subsystem(u.LevelEditorSubsystem)
actors = u.get_editor_subsystem(u.EditorActorSubsystem)
if not mesh_editor or not level_editor or not actors:
    raise RuntimeError('Use full UnrealEditor -ExecutePythonScript, not the PythonScript commandlet')

def import_file(filename, name, options=None):
    filename = Path(filename).resolve()
    if not filename.is_file():
        raise FileNotFoundError(filename)
    task = u.AssetImportTask()
    task.filename = str(filename)
    task.destination_path = DEST
    task.destination_name = name
    task.automated = True
    task.replace_existing = True
    task.replace_existing_settings = True
    task.save = True
    if options:
        task.options = options
        task.factory = u.FbxFactory()
    tools.import_asset_tasks([task])
    result = assets.load_asset(DEST + '/' + name)
    if not result:
        raise RuntimeError('Import failed: ' + name)
    return result

opts = u.FbxImportUI()
opts.import_mesh = True
opts.import_materials = False
opts.import_textures = False
opts.import_animations = False
opts.mesh_type_to_import = u.FBXImportType.FBXIT_STATIC_MESH
opts.automated_import_should_detect_type = False
opts.static_mesh_import_data.combine_meshes = True
opts.static_mesh_import_data.auto_generate_collision = False
opts.static_mesh_import_data.generate_lightmap_u_vs = False
opts.static_mesh_import_data.convert_scene = True
opts.static_mesh_import_data.convert_scene_unit = True
opts.static_mesh_import_data.force_front_x_axis = False
opts.static_mesh_import_data.transform_vertex_to_absolute = True
opts.static_mesh_import_data.bake_pivot_in_vertex = False
opts.static_mesh_import_data.import_uniform_scale = 1.0
opts.static_mesh_import_data.import_translation = u.Vector(0,0,0)
opts.static_mesh_import_data.import_rotation = u.Rotator(0,0,0)
fbx_flag = 'Interchange.FeatureFlags.Import.FBX'
previous_fbx_flag = u.SystemLibrary.get_console_variable_int_value(fbx_flag)
try:
    u.SystemLibrary.execute_console_command(None, fbx_flag+' 0')
    if assets.does_asset_exist(DEST+'/SM_Earth'):
        previous_mesh = assets.load_asset(DEST+'/SM_Earth')
        if not isinstance(previous_mesh, u.StaticMesh):
            raise RuntimeError('Expected a StaticMesh at '+DEST+'/SM_Earth')
        previous_import = previous_mesh.get_editor_property('asset_import_data')
        if not isinstance(previous_import, u.FbxStaticMeshImportData):
            previous_import = u.FbxStaticMeshImportData(outer=previous_mesh)
            previous_mesh.set_editor_property('asset_import_data', previous_import)
        # The replacement ImportData must have an explicit source, otherwise the
        # reimport handler can open a missing-source file picker on later runs.
        previous_import.scripted_add_filename(str(lod_sources[0].resolve()), 0, '')
        # UE unattended FBX reimport prefers existing import data to task.options.
        for key, value in [('convert_scene',True),('convert_scene_unit',True),('force_front_x_axis',False),('transform_vertex_to_absolute',True),('bake_pivot_in_vertex',False),('import_uniform_scale',1.0),('import_translation',u.Vector(0,0,0)),('import_rotation',u.Rotator(0,0,0))]:
            previous_import.set_editor_property(key, value)
    mesh = import_file(lod_sources[0], 'SM_Earth', opts)
    if not isinstance(mesh.get_editor_property('asset_import_data'), u.FbxStaticMeshImportData):
        raise RuntimeError('Earth did not use the calibrated FBX importer')
    # ImportLOD does not accept a factory and may otherwise use Interchange,
    # so the same temporary feature flag covers the complete FBX operation.
    for index in (1, 2):
        if mesh_editor.import_lod(mesh, index, str(lod_sources[index].resolve())) != index:
            raise RuntimeError('FBX LOD import failed: '+str(index))
finally:
    u.SystemLibrary.execute_console_command(None, fbx_flag+' '+str(previous_fbx_flag))
if mesh_editor.get_lod_count(mesh)!=3:
    raise RuntimeError('Earth must have all three LODs')
lod_report = []
for index in range(3):
    build=mesh_editor.get_lod_build_settings(mesh,index)
    build.set_editor_property('generate_lightmap_u_vs',False)
    build.set_editor_property('build_scale3d',u.Vector(1,1,1))
    mesh_editor.set_lod_build_settings(mesh,index,build)
    vertices = mesh.get_num_vertices(index)
    triangles = mesh.get_num_triangles(index)
    if vertices <= 0 or triangles <= 0:
        raise RuntimeError('Earth LOD has no built geometry: '+str(index))
    actual_scale = mesh_editor.get_lod_build_settings(mesh,index).get_editor_property('build_scale3d')
    scale = [actual_scale.x, actual_scale.y, actual_scale.z]
    if any(not math.isfinite(value) or abs(value-1.0) > 1e-6 for value in scale):
        raise RuntimeError('Earth LOD build scale is not identity: '+str(index))
    lod_report.append({'index':index,'vertices':vertices,'triangles':triangles,'buildScale':scale,'source':str(lod_sources[index].resolve())})
if not 100 < mesh.get_bounds().sphere_radius < 105:
    raise RuntimeError('Globe mesh imported with wrong units: '+str(mesh.get_bounds().sphere_radius))

import_data = mesh.get_editor_property('asset_import_data')
import_settings = {}
for key, expected in [('convert_scene',True),('convert_scene_unit',True),('force_front_x_axis',False),('transform_vertex_to_absolute',True),('bake_pivot_in_vertex',False),('import_uniform_scale',1.0)]:
    value = import_data.get_editor_property(key)
    if value != expected:
        raise RuntimeError('Earth import setting did not persist: '+key)
    import_settings[key] = value
translation = import_data.get_editor_property('import_translation')
rotation = import_data.get_editor_property('import_rotation')
for key, values in [('import_translation',[translation.x,translation.y,translation.z]),('import_rotation',[rotation.pitch,rotation.yaw,rotation.roll])]:
    if any(not math.isfinite(value) or abs(value) > 1e-6 for value in values):
        raise RuntimeError('Earth import transform is not zero: '+key)
    import_settings[key] = values
source_files = import_data.extract_filenames()
if not source_files or Path(source_files[0]).resolve() != lod_sources[0].resolve():
    raise RuntimeError('Earth reimport source is not bound to LOD0')

textures = {}
for key, filename in [('color','T_Earth_BaseColor'),('normal','T_Earth_Normal_UE'),('roughness','T_Earth_Roughness')]:
    texture = import_file(SOURCE/'Textures'/(filename+'.png'), filename)
    texture.set_editor_property('srgb', key == 'color')
    texture.set_editor_property('max_texture_size', 4096 if key != 'roughness' else 2048)
    if key == 'normal':
        texture.set_editor_property('compression_settings', u.TextureCompressionSettings.TC_NORMALMAP)
    elif key == 'roughness':
        texture.set_editor_property('compression_settings', u.TextureCompressionSettings.TC_GRAYSCALE)
    assets.save_loaded_asset(texture)
    textures[key] = texture

mat = assets.load_asset(DEST+'/M_Earth') if assets.does_asset_exist(DEST+'/M_Earth') else tools.create_asset('M_Earth', DEST, u.Material, u.MaterialFactoryNew())
u.MaterialEditingLibrary.delete_all_material_expressions(mat)
for i,(key,prop) in enumerate([('color',u.MaterialProperty.MP_BASE_COLOR),('normal',u.MaterialProperty.MP_NORMAL),('roughness',u.MaterialProperty.MP_ROUGHNESS)]):
    node = u.MaterialEditingLibrary.create_material_expression(mat,u.MaterialExpressionTextureSample,-400,i*220)
    node.texture = textures[key]
    node.sampler_type = u.MaterialSamplerType.SAMPLERTYPE_COLOR if key=='color' else u.MaterialSamplerType.SAMPLERTYPE_NORMAL if key=='normal' else u.MaterialSamplerType.SAMPLERTYPE_LINEAR_GRAYSCALE
    u.MaterialEditingLibrary.connect_material_property(node,'RGB' if key!='roughness' else 'R',prop)
    if key == 'color':
        # Atlas navigation keeps the unlit hemisphere readable while the sun
        # and normal map still provide directional relief.
        ambient = u.MaterialEditingLibrary.create_material_expression(mat,u.MaterialExpressionMultiply,-150,-180)
        ambient.set_editor_property('const_b',.35)
        u.MaterialEditingLibrary.connect_material_expressions(node,'RGB',ambient,'A')
        u.MaterialEditingLibrary.connect_material_property(ambient,'',u.MaterialProperty.MP_EMISSIVE_COLOR)
u.MaterialEditingLibrary.recompile_material(mat)
mesh.set_material(0,mat)
assets.save_loaded_asset(mat)
assets.save_loaded_asset(mesh)

# A dedicated world keeps startup cost low and leaves the existing warehouse untouched.
if not (level_editor.load_level(MAP) if assets.does_asset_exist(MAP) else level_editor.new_level(MAP)):
    raise RuntimeError('Could not create globe world')
for previous in actors.get_all_level_actors():
    if previous.actor_has_tag('GHS_GlobeStage'):
        actors.destroy_actor(previous)
center=u.Vector(0,0,300000)
earth=actors.spawn_actor_from_class(u.StaticMeshActor,center)
earth.set_actor_label('GHS Earth · WGS84')
earth.tags=['GHS_GlobeRoot','GHS_GlobeStage']
earth.static_mesh_component.set_static_mesh(mesh)
earth.static_mesh_component.set_mobility(u.ComponentMobility.MOVABLE)
earth.static_mesh_component.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
# Preserve FBX's conversion to UE's left-handed frame. The runtime uses
# X=R*cos(lat)*cos(lon), Y=-R*cos(lat)*sin(lon), Z=R*sin(lat).
earth.set_actor_scale3d(u.Vector(100,100,100))

sun=actors.spawn_actor_from_class(u.DirectionalLight,center+u.Vector(0,0,30000),u.Rotator(-35,-120,0))
sun.set_actor_label('Globe · Soft daylight')
sun.tags=['GHS_GlobeStage']
sun.light_component.set_editor_property('intensity',2.5)
sun.light_component.set_editor_property('light_color',u.Color(239,246,255,255))
sun.light_component.set_editor_property('light_source_angle',5.0)
sun.light_component.set_mobility(u.ComponentMobility.MOVABLE)

# Pale enclosing sky, unlit so it does not require atmospheric scattering or a floor.
sky_mat=assets.load_asset(DEST+'/M_GlobeSky') if assets.does_asset_exist(DEST+'/M_GlobeSky') else tools.create_asset('M_GlobeSky',DEST,u.Material,u.MaterialFactoryNew())
u.MaterialEditingLibrary.delete_all_material_expressions(sky_mat)
sky_mat.set_editor_property('two_sided',True)
sky_mat.set_editor_property('shading_model',u.MaterialShadingModel.MSM_UNLIT)
color=u.MaterialEditingLibrary.create_material_expression(sky_mat,u.MaterialExpressionConstant3Vector)
color.set_editor_property('constant',u.LinearColor(1.7,3.2,5.0))
u.MaterialEditingLibrary.connect_material_property(color,'',u.MaterialProperty.MP_EMISSIVE_COLOR)
u.MaterialEditingLibrary.recompile_material(sky_mat)
assets.save_loaded_asset(sky_mat)
sky=actors.spawn_actor_from_class(u.StaticMeshActor,center)
sky.set_actor_label('Globe · Pale blue background')
sky.tags=['GHS_GlobeStage','GHS_GlobeBackground']
sky.static_mesh_component.set_static_mesh(assets.load_asset('/Engine/BasicShapes/Sphere'))
sky.static_mesh_component.set_material(0,sky_mat)
sky.static_mesh_component.set_cast_shadow(False)
sky.static_mesh_component.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
sky.set_actor_scale3d(u.Vector(8000,8000,8000))

fill=actors.spawn_actor_from_class(u.SkyLight,center)
fill.set_actor_label('Globe · Ambient fill')
fill.tags=['GHS_GlobeStage']
fill.light_component.set_mobility(u.ComponentMobility.MOVABLE)
fill.light_component.set_editor_property('intensity',.8)
fill.light_component.recapture_sky()

post=actors.spawn_actor_from_class(u.PostProcessVolume,center)
post.set_actor_label('Globe · Atlas exposure')
post.tags=['GHS_GlobeStage']
post.set_editor_property('unbound',True)
settings=post.get_editor_property('settings')
settings.set_editor_property('override_auto_exposure_method',True)
settings.set_editor_property('auto_exposure_method',u.AutoExposureMethod.AEM_MANUAL)
settings.set_editor_property('override_auto_exposure_bias',True)
settings.set_editor_property('auto_exposure_bias',0.0)
settings.set_editor_property('override_auto_exposure_apply_physical_camera_exposure',True)
settings.set_editor_property('auto_exposure_apply_physical_camera_exposure',False)
settings.set_editor_property('override_motion_blur_amount',True)
settings.set_editor_property('motion_blur_amount',0.0)
post.set_editor_property('settings',settings)
world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
gm=u.load_class(None,'/Script/Test.GHSGlobeGameMode')
if not gm:
    raise RuntimeError('Build TestEditor with GHSGlobeGameMode before authoring the map')
world.get_world_settings().set_editor_property('default_game_mode',gm)
level_editor.set_level_viewport_camera_info(center+u.Vector(2500,26000,9000),u.Rotator(-18,-96,0),level_editor.get_active_viewport_config_key())
level_editor.save_current_level()
result={'map':MAP,'mesh':mesh.get_path_name(),'lodCount':mesh_editor.get_lod_count(mesh),'lods':lod_report,'radius':mesh.get_bounds().sphere_radius,'radiusUnit':'cm','actors':len(actors.get_all_level_actors()),'importDataType':import_data.get_class().get_name(),'importSettings':import_settings,'sourceFiles':list(source_files),'calibrationCentersCm':axis_checks,'ueGeographicAxis':[1,-1,1],'geographicAxisCompensation':[1,1,1],'earthActorScale':[100,100,100]}
(SOURCE/'ue-import-report.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print('GHS_GLOBE_IMPORT '+json.dumps(result))
