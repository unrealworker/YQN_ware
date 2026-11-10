"""Reimport only the two GHS forklift meshes. Never save a map or other assets."""
import unreal,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];TMP=ROOT/'Saved/MannyForklift'
TMP.mkdir(parents=True,exist_ok=True)
FBX_CVAR='Interchange.FeatureFlags.Import.FBX'
previous_fbx_mode=unreal.SystemLibrary.get_console_variable_int_value(FBX_CVAR)
before=json.loads((ROOT/'SourceAssets/GHS_Normal/MannedForklift/manny_driver_import_baseline.json').read_text());report=[]
unreal.load_module('StaticMeshEditor')
SM=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem);LIB=unreal.EditorAssetLibrary
specs=[('/Game/GHSNormalWarehouse/MannedForklift/Meshes/SM_GHN_MannedForklift50k','SourceAssets/GHS_Normal/MannedForklift/manned_forklift_50k.fbx'),('/Game/GHSOrderReplay/Meshes/SM_Replay_ForkliftBody','SourceAssets/GHS/OrderReplay/SM_Replay_ForkliftBody.fbx')]
try:
 unreal.SystemLibrary.execute_console_command(None,FBX_CVAR+' 0')
 for path,src in specs:
  mesh=unreal.load_asset(path); old=before['meshes'][path];original_slots=list(mesh.static_materials)
  slot_paths={s['name']:s['material']for s in old['slots']}
  for n in ['MI_Manny_01_New','MI_Manny_02_New']:slot_paths[n]='/Game/Characters/Mannequins/Materials/Manny/'+n+'.'+n
  t=unreal.AssetImportTask();t.filename=str(ROOT/src);t.destination_path=path.rsplit('/',1)[0];t.destination_name=path.rsplit('/',1)[1];t.automated=True;t.replace_existing=True;t.replace_existing_settings=False;t.save=False
  opt=unreal.FbxImportUI();opt.import_mesh=True;opt.import_as_skeletal=False;opt.mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH;opt.automated_import_should_detect_type=False;opt.import_materials=False;opt.import_textures=False;opt.import_animations=False
  d=opt.static_mesh_import_data;d.combine_meshes=True;d.generate_lightmap_u_vs=False;d.auto_generate_collision=False;d.normal_import_method=unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS;d.normal_generation_method=unreal.FBXNormalGenerationMethod.BUILT_IN
  t.options=opt;t.factory=unreal.FbxFactory();unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([t]);mesh=unreal.load_asset(path)
  slots=list(mesh.static_materials);names=[str(s.get_editor_property('imported_material_slot_name'))for s in slots]
  (TMP/'slots_imported.json').write_text(json.dumps({'path':path,'old':[s['name']for s in old['slots']],'new':names},indent=2));print('SLOTS',path,names)
  assert names[:len(old['slots'])]==[s['name']for s in old['slots']], 'Material slot ordering must preserve placed actor overrides'
  assert all(n in names for n in ['MI_Manny_01_New','MI_Manny_02_New'])
  for i,s in enumerate(slots):
   n=str(s.get_editor_property('imported_material_slot_name'));assert n in slot_paths,n;s.material_interface=unreal.load_asset(slot_paths[n]);assert s.material_interface;slots[i]=s
  mesh.static_materials=slots
  assert mesh.get_num_lods()==old['lods']
  assert mesh.get_editor_property('nanite_settings').enabled==old['nanite']
  box=mesh.get_bounding_box();actual=[box.min.x,box.min.y,box.min.z,box.max.x,box.max.y,box.max.z];assert all(abs(a-b)<.03 for a,b in zip(actual,old['boundsCm'])),(actual,old['boundsCm'])
  assert LIB.save_loaded_asset(mesh,only_if_is_dirty=False)
  report.append({'mesh':path,'triangles':[mesh.get_num_triangles(i)for i in range(mesh.get_num_lods())],'slots':names,'bounds':str(mesh.get_bounding_box()),'uv_channels':SM.get_num_uv_channels(mesh,0)})
 (TMP/'import_result.json').write_text(json.dumps(report,indent=2),encoding='utf8');print('MANNY_IMPORT_PASS',[(r['mesh'],r['triangles'])for r in report])
finally:
 unreal.SystemLibrary.execute_console_command(None,FBX_CVAR+' '+str(previous_fbx_mode))
