"""Archive one verified MPR plan build without launching UE/Blender or using Git.

1. After the final UE import/save, run --begin-run before reload/game tests.
2. Rebuild/reopen Blender composition and run all validation/capture tools.
3. Run --check-only to inspect the complete proposed archive; then --archive.

Raw evidence is copied byte-for-byte. Only comparisons/contact sheets are
derived. Stale or mixed-source reports fail before formal files are replaced.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,math,os,shutil,time
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'SourceAssets/MPR/reference_v4'
DEST=BASE/'validation'
SAVED=ROOT/'Saved/MPR/road_v5'
CONTEXT=SAVED/'validation_run_context.json'
MAP=ROOT/'Content/Maps/MPR_CAD_Warehouse.umap'
MAP_NAME='/Game/Maps/MPR_CAD_Warehouse'
REPORTS={
 'import':ROOT/'Saved/MPR/reference_v4_build.json',
 'reload':ROOT/'Saved/MPR/reference_v4/validation.json',
 'performance':ROOT/'Saved/MPR/performance.json',
 'runtime_views':ROOT/'Saved/MPR/reference_v4/runtime_views/capture_report.json',
 'plan_views':SAVED/'runtime_views/capture_report.json',
 'outside_views':SAVED/'outside_views/capture_report.json',
 'detail_views':ROOT/'Saved/MPR/feedback_v7/detail_views/capture_report.json',
 'runtime_capture':ROOT/'Saved/MPR/reference_v4/runtime_calibrated_capture.json',
 'blender':BASE/'validation_blender/composition_validation.json',
 'blender_manifest':BASE/'validation_blender/composition_manifest.json',
 'plan_alignment':DEST/'plan_alignment.json',
 'package_dependencies':DEST/'package_dependencies.json',
 'spatial_audit':DEST/'spatial_audit.json',
 'context_geometry':SAVED/'context_geometry_validation.json',
 'native_visual_review':SAVED/'native_visual_review.json',
 'site_fbx':BASE/'validation_blender/site_fbx_validation.json',
 'road_smoothing':SAVED/'road_smoothing_review.json',
 'outside_geometry':SAVED/'outside_road_review.json',
 'campus_surfaces':SAVED/'campus_surface_review.json',
 'transport_geometry':BASE/'props/transport_validation.json',
 'pv_source':ROOT/'Saved/MPR/pv_v6/source_audit.json',
 'solar_motion':ROOT/'Saved/MPR/solar_motion/review/solar_motion_review.json',
 'motion_baseline':ROOT/'Saved/MPR/solar_motion/baseline/capture_report.json',
 'motion_final':ROOT/'Saved/MPR/solar_motion/final/capture_report.json',
 'motion_far':ROOT/'Saved/MPR/solar_motion/far/capture_report.json',
}
INPUTS=['site/plan_registration_v5.json','site/road_outline_v5.json','site/plan_railway_v5.json',
 'site/outside_road_connections_v5.json',
 'site/plan_vegetation_v5.json','site/plan_landscape_islands_v5.json','site/plan_site_details_v5.json','site/manifest.json',
 'context/manifest.json','context/reference_context_ground_layout.json','context/reference_context_layout.json','context/reference_context_plan_v5.json',
 'architecture/reference_shell_manifest.json','architecture/plan_solar_v5.json','props/manifest.json',
 'references/building-road-outline-20261103.png','references/all-elements-outline-20261103.png',
 'references/style-focus-20261103.png',
 'references/solar-roof-aerial-20261103.png',
 'architecture/mpr_reference_shell.blend','site/MPR_ReferenceSite.blend',
 'context/mpr4_reference_context.blend','props/MPR_ReferenceV4_Props.blend']
MOTION_SCRIPTS=['Tools/MPRWarehouse/capture_mpr_solar_motion.py',
 'Tools/MPRWarehouse/review_mpr_solar_motion.py','Tools/MPRWarehouse/profile_mpr_runtime.py',
 'Tools/MPRWarehouse/capture_mpr_solar_far.py','Tools/MPRWarehouse/capture_mpr_detail_views.py']
MOTION_DIAGNOSTICS=['final_panel_interior_mask.png','analysis_rectified_000.png',
 'analysis_rectified_048.png','analysis_rectified_095.png','shared_support_048.png']
VIEW_NAMES={
 'runtime_views':['01-overall','02-yard-corner','03-roof','04-docks','05-yard','06-pond','07-railway','08-interior-preserved'],
 'plan_views':['09-plan-overview','10-houses-close','11-houses-reverse','12-neighbor-docks','13-east-context'],
 'outside_views':['14-complete-context','15-northwest-context','16-southwest-context','17-northeast-context','18-southeast-context'],
 'detail_views':['19-truck-whole','20-truck-cab-wheel','21-locomotive-whole','22-rail-coupling-wheel','23-train-consist','24-pond-paving','25-campus-planting'],
}


def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):
 h=hashlib.sha256()
 with path.open('rb')as stream:
  for part in iter(lambda:stream.read(1024*1024),b''):h.update(part)
 return h.hexdigest()


def inside(path,root=ROOT):
 path=Path(path);path=path if path.is_absolute()else root/path;path=path.resolve()
 if not path.is_relative_to(root.resolve()):raise ValueError('Evidence escapes project: '+str(path))
 return path


def inputs():
 files={inside(BASE/p)for p in INPUTS}
 files.update(inside(ROOT/p)for p in MOTION_SCRIPTS)
 for relative in ['architecture/reference_shell_manifest.json','site/manifest.json','context/manifest.json','props/manifest.json']:
  manifest=read(BASE/relative)
  for mesh in manifest['meshes']:
   if mesh.get('fbx'):files.add(inside(mesh['fbx']))
  for mat in manifest['materials'].values():
   for texture in mat.get('textures',{}).values():files.add(inside(texture))
 return {p.relative_to(ROOT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size,mtime_ns=p.stat().st_mtime_ns)for p in sorted(files)}


def begin_run():
 imported=read(REPORTS['import']);assert imported.get('success')is True and imported.get('map')==MAP_NAME,'Final successful import required'
 source=inputs();latest=max(row['mtime_ns']for row in source.values())
 assert REPORTS['import'].stat().st_mtime_ns>=latest,'Import predates current source generation; import/save final sources first'
 result=dict(schema_version=1,started_utc=datetime.now(timezone.utc).isoformat(),started_ns=time.time_ns(),
  map=MAP_NAME,map_sha256=sha(MAP),map_mtime_ns=MAP.stat().st_mtime_ns,
  sources=source,import_report_sha256=sha(REPORTS['import']),
  policy='Map/source snapshot taken after import and before reload/runtime/performance. Native reload, package-dependency and game reports must match this map; reload and source-geometry reports must also match current source manifest hashes.')
 SAVED.mkdir(parents=True,exist_ok=True);CONTEXT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps(dict(context=str(CONTEXT),map_sha256=result['map_sha256'],source_files=len(source),started_utc=result['started_utc'])))


def png(path,expected=None):
 path=inside(path)
 with Image.open(path)as im:
  assert im.format=='PNG',path
  if expected:assert im.size==tuple(expected),(path,im.size,expected)
  im.verify()
 return path


def current_hashes(report,field,required,label):
 values=report.get(field)
 assert isinstance(values,dict)and values,(label,'source hashes missing')
 bound_paths={inside(path)for path in values}
 assert {inside(path)for path in required}.issubset(bound_paths),(label,'required source hash binding missing')
 for path,digest in values.items():assert sha(inside(path))==digest,(label,'source changed',path)


def outside_geometry_gate(report):
 assert report.get('status')=='passed_source_geometry','Outside geometry audit did not pass'
 current_hashes(report,'input_sha256',[
  'Tools/MPRWarehouse/mpr_plan_site.py','Tools/MPRWarehouse/validate_mpr_outside_roads.py',
  'SourceAssets/MPR/reference_v4/site/outside_road_connections_v5.json',
  'SourceAssets/MPR/reference_v4/site/road_outline_v5.json',
  'SourceAssets/MPR/reference_v4/site/plan_registration_v5.json',
  'SourceAssets/MPR/reference_v4/site/plan_landscape_islands_v5.json',
  'SourceAssets/MPR/reference_v4/site/plan_railway_v5.json',
  'SourceAssets/MPR/reference_v4/site/manifest.json','SourceAssets/MPR/reference_v4/context/manifest.json',
  'SourceAssets/MPR/reference_v4/props/manifest.json','SourceAssets/MPR/mpr_cad_layout.json'],'Outside geometry')
 assert 0<=report['source_image_area_change_m2']<1e-7,'Outside completion changed the source-image roads'
 assert report['road_components_before']==report['road_components_after']==2,'Outside completion joined the networks across railway'
 for field in ['unplanned_centerline_crossings','uncovered_path_segments','tree_contacts','vehicle_contacts','tiny_outside_islands_m2']:
  assert not report[field],('Outside geometry issue',field)
 for field in ['building_overlap_m2','rail_4m_bed_overlap_m2','road_edge_paint_outside_m2']:
  assert 0<=report[field]<1e-6,('Outside geometry collision',field)
 assert report['closest_road_to_rail_center_m']>=2,'Outside road rail clearance failed'
 config=read(BASE/'site/outside_road_connections_v5.json')
 policy='source_tangent_terminal_fade_no_authored_connections'
 assert report.get('policy')==config.get('status')==policy and report.get('no_authored_connections')is True,'Outside road policy must preserve independent source-directed ends'
 assert not any(key in config for key in ['groups','branches','collectors']),'Invented outside connections remain in source config'
 assert report['terminal_count']==report['source_exit_count']==report['intentionally_open_faded_endpoints']==29,'Source exits are missing or were joined'
 assert report['authored_junction_count']==report['authored_closed_connection_count']==0,'Outside roads must not invent junctions or closed connections'
 assert report['maximum_tangent_endpoint_error_m']<1e-8 and report['fade_monotonic']is True,'Terminal tangent or fade continuity failed'
 assert len(report['terminal_fade'])==report['terminal_count']
 for row in report['terminal_fade']:
  assert 0<row['length_m']<=config['extension_m'] and 0<=row['fade_start_m']<row['length_m']
  assert abs(row['range'][0])<1e-8 and abs(row['range'][1]-1)<1e-8,'Terminal must fade fully to ground'


def pv_source_gate(report):
 # This is auxiliary CPU/source evidence. It is not a final Blender/UE mesh,
 # LOD, mip, temporal or visual acceptance report.
 assert report.get('success')is True and report.get('scope'),'PV source audit missing or unsuccessful'
 current_hashes(report,'source_sha256',[
  'Tools/MPRWarehouse/build_mpr_reference_shell_v4.py','Tools/MPRWarehouse/mpr_reference_shell_v4_lib.py',
  'SourceAssets/MPR/reference_v4/architecture/plan_solar_v5.json'],'PV source audit')
 assert report.get('unchanged_macro_outlines')is True and report['preserved_cad_apertures']>0,'PV source changed preserved CAD layout'


def campus_surfaces_gate(report,manifests):
 assert report.get('success')is True,'Campus source audit failed'
 current_hashes(report,'source_sha256',['Tools/MPRWarehouse/build_mpr_reference_v4_site.py','Tools/MPRWarehouse/mpr_plan_site.py',manifests['Site'],manifests['Context'],
  'SourceAssets/MPR/mpr_cad_layout.json',BASE/'site/road_outline_v5.json',BASE/'site/plan_landscape_islands_v5.json',
  BASE/'site/plan_site_details_v5.json',BASE/'site/outside_road_connections_v5.json',BASE/'site/plan_registration_v5.json'],'Campus surfaces')
 required={'road_overlap_m2','portal_overlap_m2','building_overlap_m2','planting_paved_overlap_m2',
  'pond_water_changed_m2','pond_walk_road_overlap_m2','pond_walk_water_overlap_m2',
  'parked_car_planting_overlap_m2','pond_walk_preserved_tree_root_overlap_m2',
  'north_dock_apron_planting_overlap_m2','north_dock_apron_unpaved_m2'}
 checks=report.get('checks');assert isinstance(checks,dict)and required.issubset(checks),'Campus checks missing'
 assert all(isinstance(v,(int,float))and not isinstance(v,bool)and math.isfinite(v)and 0<=v<1e-7 for v in checks.values()),'Campus planting/paving intrudes into access or leaves a gap'
 coverage=report['terminal_emitted_road_coverage_error_m2']
 assert isinstance(coverage,(int,float))and not isinstance(coverage,bool)and math.isfinite(coverage)and 0<=coverage<1e-7,'Terminal mesh does not cover the source road extension'
 assert report['terminal_surface_pieces']>0 and report['open_access_portals']==4
 expected={'MPR4_TerminalAsphalt','MPR4_TerminalCurb','MPR4_TerminalWhiteLine'}
 colors=report.get('terminal_color_ranges');assert isinstance(colors,dict)and set(colors)==expected,'Terminal surface fade roles incomplete'
 for role,values in colors.items():
  assert len(values)==2 and all(isinstance(v,(int,float))and not isinstance(v,bool)and math.isfinite(v)for v in values),(role,'Invalid terminal color range')
  assert abs(values[0])<1e-8 and abs(values[1]-1)<1e-8,(role,'Terminal does not fade from source to ground')
 assert 0<report['main_parcel_green_fraction']<.15
 site=read(manifests['Site']);assert abs(site['campus_planting']['area_m2']-report['campus_planting_area_m2'])<1e-6,'Campus mesh/source planting area mismatch'
 assert site['campus_planting']['access_portals_preserved']is True
 assert site['pond_walk_repair']==report['pond_walk_repair'],'Pond paving audit differs from generated site'


def transport_geometry_gate(report,props_path):
 props=read(props_path);assert report==props['transport_validation'],'Transport report differs from generated props source'
 expected={'SM_MPR4_Trailer_White','SM_MPR4_Trailer_Blue','SM_MPR4_Trailer_Coral',
  'SM_MPR4_Tractor','SM_MPR4_FreightBoxcar','SM_MPR4_Locomotive'}
 checks=report.get('source_checks');assert isinstance(checks,list)and len(checks)==len(expected),'Transport source checks incomplete'
 assert {row['name']for row in checks}==expected,'Transport source checks missing or duplicated'
 meshes={row['name']:row for row in props['meshes']}
 assert report.get('reviewed_tree_unchanged')is True
 assert sha(BASE/'props/SM_MPR4_Tree_Oak.fbx')==report['tree_fbx_sha256']
 for check in checks:
  mesh=meshes[check['name']]
  assert sha(inside(mesh['fbx']))==check['sha256']==mesh['sha256'] and mesh['triangles']==check['triangles']>0
  error,z=check['bounds_error_m'],check['minimum_z_m']
  assert all(isinstance(v,(int,float))and not isinstance(v,bool)and math.isfinite(v)for v in [error,z])
  assert 0<=error<.0003 and abs(z)<.001,('Transport bounds or ground contact invalid',check['name'])


def solar_render_conditions_gate(baseline,final):
 # Baseline predates timestamped capture naming and may have no tool hash;
 # only the final capture must bind the currently delivered capture tool.
 assert final.get('capture_tool_sha256')==sha(ROOT/'Tools/MPRWarehouse/capture_mpr_solar_motion.py'),'Final motion capture tool changed or hash missing'
 required={'r.ScreenPercentage','r.AntiAliasingMethod','r.TemporalAA.Upsampling','r.Nanite.MaxPixelsPerEdge'}
 for label,report in [('baseline',baseline),('final',final)]:
  values=report.get('cvars')
  assert isinstance(values,dict)and required.issubset(values),(label,'Motion rendering conditions missing')
  assert all(isinstance(values[key],(int,float))and not isinstance(values[key],bool)and math.isfinite(values[key])for key in required),(label,'Motion rendering conditions invalid')
 assert baseline['cvars']==final['cvars'],'Motion rendering conditions differ between baseline and final'


def solar_motion_gate(reports,context,map_sha):
 # Pair checking is the same reviewed CPU routine used to produce the report;
 # no Unreal import or runtime capture is triggered by importing this module.
 import importlib.util
 tool=ROOT/'Tools/MPRWarehouse/review_mpr_solar_motion.py'
 spec=importlib.util.spec_from_file_location('_mpr_motion_pair_audit',tool)
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 review=reports['solar_motion'];baseline=reports['motion_baseline'];final=reports['motion_final']
 solar_render_conditions_gate(baseline,final)
 assert review.get('success')is True and review.get('audit_complete')is True,'Motion review incomplete'
 assert review.get('camera_pairing_verified')is True and review.get('input_hashes_verified')is True,'Motion input/pose verification missing'
 assert review.get('flicker_free_claim')is False and review.get('limitations'),'Motion metric success must not claim absence of flicker'
 assert review.get('tool_sha256')==sha(tool),'Motion review tool changed after analysis'
 assert REPORTS['motion_final'].stat().st_mtime_ns>=context['started_ns'],'Final motion capture predates current run'
 assert REPORTS['solar_motion'].stat().st_mtime_ns>=max(context['started_ns'],REPORTS['motion_final'].stat().st_mtime_ns),'Motion review predates final capture'
 module.check_reports(baseline,final,96)
 assert final['map_sha256']==review['map_sha256']['final']==map_sha,'Final motion map mismatch'
 assert baseline['map_sha256']==review['map_sha256']['baseline'],'Baseline motion map mismatch'
 assert review['source_png_count']==192 and len(review['frames'])==96,'Motion review lacks the full paired sample set'
 current_hashes(review,'sources',[
  'SourceAssets/MPR/reference_v4/architecture/plan_solar_v5.json',
  'SourceAssets/MPR/reference_v4/site/plan_registration_v5.json',
  'SourceAssets/MPR/reference_v4/architecture/reference_shell_manifest.json'],'Motion final-source binding')
 verified={};pairs=[]
 for label,report in [('baseline',baseline),('final',final)]:
  report_path=REPORTS['motion_'+label];binding=review['captures'][label]
  assert inside(binding['path'])==report_path.resolve()and binding['sha256']==sha(report_path),(label,'motion report hash mismatch')
  assert report.get('label')==label,(label,'wrong motion capture label')
  for i,row in enumerate(report['captures']):
   expected_group='static'if i<12 else 'pan'if i<48 else 'zoom'
   assert row['group']==expected_group and row['index']==i,'Unexpected deterministic motion sequence'
   assert row['camera']['viewport']==[1920,1080]and row['camera']['view_target'].startswith(MAP_NAME+'.'),'Motion camera map/viewport mismatch'
   image_path=png(row['path'],[1920,1080]);digest=sha(image_path)
   assert digest==row['sha256'],(label,i,'native motion PNG changed')
   assert review['frames'][i]['index']==i and review['frames'][i]['group']==expected_group
   assert review['frames'][i]['source_images'][label]==digest,(label,i,'review frame does not bind native image')
   if label=='final':assert image_path.stat().st_mtime_ns>=context['started_ns'],(i,'final motion PNG predates current run')
   verified[image_path.relative_to(ROOT).as_posix()]=digest
 assert set(review['groups'])=={'static','pan','zoom'}and all(r['analyzed_pairs']>0 for r in review['groups'].values()),'Motion groups lack usable comparison samples'
 preview=review['preview'];video=inside(preview['path'])
 assert video.suffix.lower()=='.mp4'and video.stat().st_size>1000,'Motion comparison MP4 missing or empty'
 assert preview['sha256']==sha(video)and preview['frames']==96,'Motion comparison MP4 binding mismatch'
 assert preview['actual_capture_fps']is None and preview['resolution']==[1920,580],'Sampled comparison must not be presented as real-time capture'
 assert video.stat().st_mtime_ns>=REPORTS['motion_final'].stat().st_mtime_ns,'Motion MP4 predates final capture'
 verified[video.relative_to(ROOT).as_posix()]=preview['sha256'];pairs.append((video,DEST/'solar_motion/native_sampled_comparison.mp4'))
 for name in MOTION_DIAGNOSTICS:
  path=png(REPORTS['solar_motion'].parent/name)
  assert REPORTS['motion_final'].stat().st_mtime_ns<=path.stat().st_mtime_ns<=REPORTS['solar_motion'].stat().st_mtime_ns,('Motion diagnostic from another review run',name)
  verified[path.relative_to(ROOT).as_posix()]=sha(path);pairs.append((path,DEST/'solar_motion'/name))
 context['_verified_motion_files']=verified
 # Persist only the reports, actual sampled comparison and five diagnostics.
 # All 192 original PNGs remain in Saved; each is hash-checked again at publish.
 context['_motion_archive_pairs']=[(str(a),str(b))for a,b in pairs]


def solar_far_gate(report,context,map_sha):
 """Verify all 24 native far poses; archive only start/apex/end originals."""
 assert report.get('success')is True and report.get('map_unchanged')is True,'Far capture failed or changed map'
 assert report.get('assets_saved')is False and report.get('map_sha256')==map_sha,'Far capture map or asset-save mismatch'
 assert report.get('label')=='far'and report.get('run_id'),'Far capture label/run identity missing'
 assert REPORTS['motion_far'].stat().st_mtime_ns>=context['started_ns'],'Far report predates current run'
 assert report.get('capture_tool_sha256')==sha(ROOT/'Tools/MPRWarehouse/capture_mpr_solar_far.py'),'Far wrapper changed after capture'
 assert report.get('base_capture_tool_sha256')==sha(ROOT/'Tools/MPRWarehouse/capture_mpr_solar_motion.py'),'Far base capture tool changed after capture'
 captures=report.get('captures',[])
 assert report.get('pose_count')==len(captures)==24,'Far capture must contain 24 poses'
 assert report.get('distance_path_cm')==[70000.,125000.,70000.],'Far capture range is incomplete'
 assert report.get('frame_settle_seconds')==.15 and report.get('first_warmup_seconds')==12.,'Far capture sampling timing changed'
 assert report.get('orientation_deg')==dict(pitch=-58.,yaw=-82.),'Far camera orientation metadata changed'
 pitch,yaw=map(math.radians,[-58.,-82.]);forward=[math.cos(pitch)*math.cos(yaw),math.cos(pitch)*math.sin(yaw),math.sin(pitch)]
 target=[6500.,0.,1400.];verified={};distances=[];paths=set()
 for i,row in enumerate(captures):
  assert row['index']==i and row['group']=='far_zoom','Far frame sequence/group mismatch'
  camera=row['camera'];distance=70000.+55000.*(i/11 if i<=11 else (23-i)/12)
  expected=[p-v*distance for p,v in zip(target,forward)]
  assert len(camera['position_cm'])==3 and math.dist(camera['position_cm'],expected)<.05,(i,'Far camera position differs from deterministic source pose')
  assert len(camera['rotation_deg'])==3 and all(math.isclose(a,b,abs_tol=1e-6,rel_tol=0)for a,b in zip(camera['rotation_deg'],[-58.,-82.,0.])),(i,'Far camera rotation mismatch')
  assert math.isclose(row['fov'],56.,abs_tol=1e-6,rel_tol=0),'Far camera FOV mismatch'
  assert camera['viewport']==[1920,1080]and camera['view_target'].startswith(MAP_NAME+'.'),'Far camera map/viewport mismatch'
  assert len(row['roof_quad_px'])==4 and all(len(p)==2 and all(math.isfinite(v)for v in p)for p in row['roof_quad_px']),'Far roof projection invalid'
  # Timestamped capture filenames are intentionally read from each report row.
  path=png(row['path'],[1920,1080]);assert path not in paths,'Far capture reused a PNG path';paths.add(path)
  assert path.stat().st_mtime_ns>=context['started_ns'],(i,'Far PNG predates current run')
  digest=sha(path);assert digest==row['sha256'],(i,'Far native PNG hash mismatch')
  verified[path.relative_to(ROOT).as_posix()]=digest;distances.append(math.dist(camera['position_cm'],target))
 assert math.isclose(distances[0],70000.,abs_tol=.05)and math.isclose(distances[11],125000.,abs_tol=.05)and math.isclose(distances[23],70000.,abs_tol=.05),'Far near/apex/return coverage failed'
 context['_verified_motion_files'].update(verified)
 context['_far_motion_files']=verified


def gate():
 context=read(CONTEXT);current=inputs();original=context['sources']
 assert set(current)==set(original),'Source file set changed after begin-run'
 assert all(current[p]['sha256']==original[p]['sha256']for p in original),'Source content changed after begin-run'
 map_sha=sha(MAP);assert map_sha==context['map_sha256'],'Saved map changed after begin-run'
 assert sha(REPORTS['import'])==context['import_report_sha256'],'Import report changed during the validation run'
 reports={k:read(path)for k,path in REPORTS.items()}
 for name in ['import','reload','performance','runtime_views','plan_views','outside_views','detail_views','runtime_capture','blender','package_dependencies','spatial_audit','context_geometry','site_fbx','campus_surfaces']:
  assert reports[name].get('success')is True,(name,'not successful')
 for name in ['reload','performance','runtime_views','plan_views','outside_views','detail_views','runtime_capture','package_dependencies']:
  assert REPORTS[name].stat().st_mtime_ns>=context['started_ns'],(name,'stale report predates begin-run')
 for name in ['runtime_views','plan_views','outside_views','detail_views','runtime_capture']:
  assert reports[name]['map_sha256']==map_sha and reports[name].get('map_unchanged')is True,(name,'map mismatch')
 perf=reports['performance'];assert perf['map_sha256_before']==perf['map_sha256_after']==map_sha and perf.get('map_unchanged')is True
 assert perf.get('assets_saved')is False and reports['reload'].get('map_saved_by_validator')is False
 reload=reports['reload'];assert reload.get('reload_verified')is True and reload.get('map')==MAP_NAME
 assert reload.get('map_sha256')==map_sha,'Reload map hash mismatch'
 manifests={category:BASE/relative for category,relative in [('Architecture','architecture/reference_shell_manifest.json'),('Props','props/manifest.json'),('Site','site/manifest.json'),('Context','context/manifest.json')]}
 assert reload.get('source_manifest_hashes')=={category:sha(path)for category,path in manifests.items()},'Reload source manifest hashes mismatch'
 dependencies=reports['package_dependencies']
 assert dependencies.get('map_sha256')==map_sha,'Package-dependency map hash mismatch'
 assert dependencies.get('assets_modified')is False and dependencies.get('v3_dependencies')==0
 assert MAP_NAME in dependencies['recursive_map_dependencies'],'Dependency traversal lacks target map'
 assert not any(p.startswith('/Game/MPRWarehouse/ReferenceV3/')for p in dependencies['recursive_map_dependencies'])
 spatial=reports['spatial_audit']
 assert spatial.get('source_manifest_sha256')==sha(manifests['Site'])and spatial.get('context_manifest_sha256')==sha(manifests['Context']),'Spatial audit source hashes mismatch'
 for path,digest in spatial['reconstructed_source_hashes'].items():assert sha(inside(path))==digest,('Spatial reconstruction source changed',path)
 for field in ['buildings_on_roads','vehicles_outside_standing_surfaces','vehicle_collisions','boxcar_collisions','tree_clearance_violations']:assert not spatial[field],('Spatial audit issue',field)
 smoothing=reports['road_smoothing']
 # The source auditor's actual schema uses status/input_sha256 rather than
 # success/source_inputs. Empty current-manifest contacts also enforce the
 # --require-current-placements result without inventing an absent flag.
 assert smoothing.get('status')=='passed','Road smoothing audit did not pass current placements'
 assert smoothing.get('input_sha256'),'Road smoothing source hashes missing'
 for path,digest in smoothing['input_sha256'].items():assert sha(inside(path))==digest,('Road smoothing audit source changed',path)
 assert not smoothing['old_manifest_tree_contacts']and not smoothing['vehicle_road_contacts'],'Current trees or vehicles contact smoothed roads'
 assert smoothing['building_overlap_m2']<1e-6 and smoothing['island_overlap_m2']<1e-6 and smoothing['road_paint_outside_m2']<1e-6
 outside_geometry_gate(reports['outside_geometry'])
 campus_surfaces_gate(reports['campus_surfaces'],manifests)
 transport_geometry_gate(reports['transport_geometry'],manifests['Props'])
 assert not spatial['vehicle_wheel_support_issues'],'Vehicle wheels do not touch their standing surface'
 site_consists=read(manifests['Site']).get('rail_consist_audit');assert site_consists,'Missing train consist source audit'
 pv_source_gate(reports['pv_source'])
 solar_motion_gate(reports,context,map_sha)
 solar_far_gate(reports['motion_far'],context,map_sha)
 geometry=reports['context_geometry'];assert geometry.get('source_manifest_sha256')==sha(manifests['Context']),'Context geometry source hash mismatch'
 assert geometry.get('saved_blender_checked')is True and not geometry.get('errors'),'Saved context Blender geometry not verified'
 context_blend=BASE/'context/mpr4_reference_context.blend'
 assert REPORTS['context_geometry'].stat().st_mtime_ns>=max(context_blend.stat().st_mtime_ns,manifests['Context'].stat().st_mtime_ns),'Context geometry audit predates saved source'
 assert geometry['checked_buildings']>0 and geometry['max_right_angle_error_deg']<=1e-5
 assert geometry['minimum_complete_house_clearance_m']>=2.999 and geometry['mesh_checks'],'Context complete geometry clearance missing or failed'
 site_fbx=reports['site_fbx'];site_manifest=read(manifests['Site'])
 assert site_fbx.get('source_manifest_sha256')==sha(manifests['Site']),'Site FBX source manifest mismatch'
 expected_site_meshes={row['name']:row for row in site_manifest['meshes']}
 assert len(expected_site_meshes)==len(site_manifest['meshes'])>0,'Site manifest has duplicate or missing meshes'
 assert site_fbx.get('mesh_count')==len(expected_site_meshes),'Site FBX mesh count mismatch'
 assert {row['name']for row in site_fbx['checks']}==set(expected_site_meshes)and len(site_fbx['checks'])==len(expected_site_meshes),'Site FBX checks incomplete or duplicated'
 for row in site_fbx['checks']:
  expected=expected_site_meshes[row['name']]
  assert row.get('triangle_match')is True and row['triangles']==row['source_triangles']==expected['triangles'],('Site FBX triangle mismatch',row['name'])
  assert row['bounds_error_m']<.0003 and row['material_slots']==len(expected['material_roles']),('Site FBX boundary/material mismatch',row['name'])
  if expected.get('vertex_color_fade'):
   fade=row.get('vertex_color_fade');assert fade and fade['range'][0]<.005 and fade['range'][1]>.99 and fade['intermediate_color_count']>0,('Missing terminal gradient in FBX',row['name'])
 assert site_fbx['max_bounds_error_m']<.0003
 assert REPORTS['site_fbx'].stat().st_mtime_ns>=max([manifests['Site'].stat().st_mtime_ns]+[inside(row['fbx']).stat().st_mtime_ns for row in site_manifest['meshes']]),'Site FBX audit predates exported source'
 for field in ['preservation','preservation_after_capture']:assert reload[field]['success']is True,(field,'failed')
 assert reload['preservation']['protected_digest']==reports['import']['interior_preservation']['protected_digest']
 assert reload['preservation_after_capture']['protected_digest']==reload['preservation']['protected_digest'],'Interior digest changed during reload captures'
 for name,required in VIEW_NAMES.items():
  assert reports[name].get('assets_saved')is False
  assert sorted(row['name']for row in reports[name]['captures'])==sorted(required),(name,'incomplete or duplicate views')
  for row in reports[name]['captures']:
   path=png(row['path'],[1920,1080]);assert sha(path)==row['sha256'],(name,row['name'],'image hash mismatch')
   assert path.stat().st_mtime_ns>=context['started_ns'],(name,row['name'],'image predates current run')
   assert row['camera']['view_target'].startswith(MAP_NAME+'.'),(name,row['name'],'capture camera is not in target map')
 assert reports['detail_views']['detail_source_manifest_sha256']==sha(manifests['Site'])
 assert reports['detail_views']['capture_tool_sha256']==sha(ROOT/'Tools/MPRWarehouse/capture_mpr_detail_views.py')
 capture=reports['runtime_capture'];assert sha(png(capture['raw_image'],capture['overscan_size']))==capture['raw_image_sha256']
 x,y,w,h=capture['crop'];assert min(x,y)>=0 and min(w,h)>0 and x+w<=capture['overscan_size'][0]and y+h<=capture['overscan_size'][1],'Invalid overscan crop'
 for state in ['exterior','interior']:
  csv=perf['performance'][state]['native_csv'];assert csv.get('gpu_verified')is True and csv.get('frame_count',0)>0
  assert sha(inside(csv['path']))==csv['sha256'],(state,'native CSV mismatch')
 assert sorted(row['state']for row in perf['captures'])==['exterior','interior'],'Incomplete performance captures'
 for row in perf['captures']:assert sha(png(row['path'],[1920,1080]))==row['sha256']
 blender=reports['blender'];assert blender.get('sources_unchanged')is True and blender.get('reopened_blend')is True
 assert blender.get('no_temporary_tree_proxies')is True and blender.get('no_interior_assets')is True
 composition=reports['blender_manifest'];assert sha(inside(composition['output']))==blender['output_sha256']
 for group,row in composition['sources'].items():
  for field in ['manifest','blend']:
   assert sha(inside(row[field]))==row[field+'_sha256'],('Blender',group,field,'source mismatch')
 assert sha(inside(composition['reference_camera_calibration']))==composition['reference_camera_sha256']
 alignment=reports['plan_alignment'];assert alignment.get('all_inputs_current')is True
 for row in alignment['inputs'].values():assert sha(inside(row['path']))==row['sha256'],('Plan alignment stale',row['path'])
 assert sha(BASE/'references/all-elements-outline-20261103.png')==alignment['source_sha256']
 assert sha(png(alignment['output_image']['path'],[1728,910]))==alignment['output_image']['sha256'],'Plan alignment image stale'
 visual=reports['native_visual_review']
 assert visual.get('status')=='review_complete_with_visual_residuals'and visual.get('map_sha256')==map_sha,'Native visual review is pending or refers to a previous map'
 for path,digest in visual['source_report_hashes'].items():assert sha(inside(path))==digest,('Native visual review report binding stale',path)
 for path in ['Saved/MPR/style_review/final_tone_metrics.json','Saved/MPR/pv_v6/native_review/review.json']:
  assert path in visual['source_report_hashes'],'Native supporting review is not bound: '+path
  assert read(inside(path)).get('map_sha256')==map_sha,'Supporting review belongs to another map: '+path
 current_images={row['name']:row['sha256']for group in VIEW_NAMES for row in reports[group]['captures']}
 assert {row['name']:row['sha256']for row in visual['images']}==current_images,'Native visual review does not bind all current images'
 context['_verified_report_hashes']={k:sha(path)for k,path in REPORTS.items()}
 return context,reports,map_sha


def archive_plan(reports):
 pairs=[(REPORTS['import'],DEST/'import_report.json'),(REPORTS['reload'],DEST/'reload_validation.json'),
  (REPORTS['performance'],DEST/'performance.json'),(REPORTS['runtime_capture'],DEST/'runtime_calibrated_capture.json'),
  (REPORTS['runtime_views'],DEST/'runtime_views/capture_report.json'),(REPORTS['plan_views'],DEST/'plan_views/capture_report.json'),
  (REPORTS['outside_views'],DEST/'outside_views/capture_report.json'),
  (REPORTS['detail_views'],DEST/'detail_views/capture_report.json'),
  (REPORTS['package_dependencies'],DEST/'package_dependencies.json'),(REPORTS['spatial_audit'],DEST/'spatial_audit.json'),
  (REPORTS['context_geometry'],DEST/'context_geometry_validation.json'),
  (REPORTS['native_visual_review'],DEST/'native_visual_review.json'),
  (ROOT/'Saved/MPR/style_review/final_tone_metrics.json',DEST/'final_tone_metrics.json'),
  (ROOT/'Saved/MPR/pv_v6/native_review/review.json',DEST/'solar_motion/native_pv_review.json'),
  (REPORTS['site_fbx'],DEST/'site_fbx_validation.json'),
  (REPORTS['road_smoothing'],DEST/'road_smoothing_review.json'),
  (REPORTS['outside_geometry'],DEST/'outside_road_review.json'),
  (REPORTS['campus_surfaces'],DEST/'campus_surface_review.json'),
  (REPORTS['transport_geometry'],DEST/'transport_geometry_validation.json'),
  (REPORTS['pv_source'],DEST/'pv_source_audit.json'),
  (REPORTS['solar_motion'],DEST/'solar_motion/solar_motion_review.json'),
  (REPORTS['motion_baseline'],DEST/'solar_motion/baseline_capture_report.json'),
  (REPORTS['motion_final'],DEST/'solar_motion/final_capture_report.json'),
  (REPORTS['motion_far'],DEST/'solar_motion/far/capture_report.json'),
  (CONTEXT,DEST/'validation_run_context.json')]
 preview=reports['solar_motion']['preview']
 pairs.append((inside(preview['path']),DEST/'solar_motion/native_sampled_comparison.mp4'))
 for name in MOTION_DIAGNOSTICS:pairs.append((REPORTS['solar_motion'].parent/name,DEST/'solar_motion'/name))
 far_captures={row['index']:row for row in reports['motion_far']['captures']}
 for index in [0,11,23]:pairs.append((inside(far_captures[index]['path']),DEST/'solar_motion/far'/f'{index:03d}.png'))
 for key,directory in [(name,name) for name in VIEW_NAMES]:
  for row in reports[key]['captures']:pairs.append((inside(row['path']),DEST/directory/(row['name']+'.png')))
 pairs.append((inside(reports['runtime_capture']['raw_image']),DEST/'runtime_overscan.png'))
 for state in ['exterior','interior']:
  pairs.append((inside(reports['performance']['performance'][state]['native_csv']['path']),DEST/f'performance_{state}.csv'))
 for row in reports['performance']['captures']:pairs.append((inside(row['path']),DEST/f"performance_{row['state']}.png"))
 # Only include optional diagnostics that bind themselves to the current
 # source JSON. Older unbound PNGs remain in Saved, not the formal archive.
 optional=[('solar_polygon_validation.json','plan_solar_polygon_validation.json','source_json_sha256',BASE/'architecture/plan_solar_v5.json'),
           ('railway_validation.json','plan_railway_validation.json','json_sha256',BASE/'site/plan_railway_v5.json'),
           ('site_paint_refinement_validation.json','plan_site_paint_validation.json','source_details_sha256',BASE/'site/plan_site_details_v5.json')]
 for source,target,field,current in optional:
  path=SAVED/source
  if path.exists()and read(path).get(field)==sha(current):pairs.append((path,DEST/target))
 return pairs


def contact_sheet(paths,target,title):
 columns=2;cell_w=640;cell_h=392;sheet=Image.new('RGB',(columns*cell_w,50+math.ceil(len(paths)/columns)*cell_h),'#edf1f4');d=ImageDraw.Draw(sheet)
 try:font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',18)
 except OSError:font=ImageFont.load_default()
 d.text((16,12),title,font=font,fill='#183349')
 for i,(name,path)in enumerate(paths):
  image=Image.open(path).convert('RGB');image.thumbnail((624,351),Image.Resampling.LANCZOS)
  x=(i%columns)*cell_w+8;y=50+(i//columns)*cell_h
  d.text((x,y+3),name,font=font,fill='#183349');sheet.paste(image,(x,y+30))
 sheet.save(target)


def obsolete_candidates(planned):
 keep={d.resolve()for s,d in planned};candidates=[]
 for path in DEST.rglob('*'):
  if not path.is_file()or path.resolve()in keep:continue
  if path.name.startswith(('MPR_2026','performance_2026'))or path.name in {'surface_texture_review.json','trailer_resize_review.json'}or 'ghs_quality_regression'in path.parts:
   candidates.append(path.relative_to(ROOT).as_posix())
 for name in ['reference_color_samples.json','reference_render_comparison.png','vehicle_bounds_audit.json']:
  path=BASE/'validation_blender'/name
  if path.exists():candidates.append(path.relative_to(ROOT).as_posix())
 return candidates


def write_visual_review(path,reports,map_sha):
 alignment=reports['plan_alignment'];count=alignment['counts'];perf=reports['performance']
 lines=[
 '# MPR 新平面依据与实际游戏画面复核',
 '',f'本轮地图 SHA-256：`{map_sha}`。本记录绑定本轮导入、保存重载、UE 游戏截图、原生 CSV 性能数据及重新打开 Blender 的来源验证。',
 '', '本轮位置标准是用户新提供的 `building-road-outline-20261103.png` 与 `all-elements-outline-20261103.png`。最新 `style-focus-20261103.png` 作为材质、明暗、建筑细节风格及最终并排对照依据；不再用旧透视画面的四角反投影塑造周边房屋。光伏位置与设备以新增实景 solar-roof-aerial-20261103.png 注册到 CAD 后重测，照片约 2.10 m 注册残差保留记录。主仓内部、CAD 接口和门洞尺度保持原有约束。',
 '', f'数据层叠图 `plan_alignment.png` 包含 {count.get("context_buildings",0)} 个周边建筑、{count.get("trees",0)} 株实际落地树、{count.get("trailers",0)} 辆拖车、{count.get("railcars",0)} 节铁路车厢、{count.get("solar_strips",0)} 条光伏带和 {count.get("roof_fixtures",0)} 个屋顶设备。源树冠数量与实际落地数量可因道路、建筑、铁路及车辆避让不同；拒绝与偏移明细保存在 JSON 中。',
 '', '`plan_views/09-plan-overview.png` 是真实正交游戏视口；其余新增视图从正反两侧检查住宅、邻仓月台和东侧环境。`runtime_views/` 保留传统八视角原图，联系图仅缩略排版，不替代原图。',
 '', '`outside_views/14–18` 是本轮额外采集的实际游戏视图，用于检查参考图外的完整道路和四个方向环境。图外道路只按原切线和原宽度延伸，以 GHS 同类顶点色渐变结束；没有自行闭合或新增连接。其源数据、碰撞与连接检查见 `outside_road_review.json`；`style-focus-20261103.png` 已绑定本轮输入。',
 '', '`pv_source_audit.json` 仅是绑定当前生成脚本和光伏布局 JSON 的 CPU 源审计，不能替代最终 Blender/FBX 几何、UE LOD/mip 或动态画面检查。',
 '', '`solar_motion/` 归档基线与最终各 96 个相同姿态的采样报告、原生 PNG 并排对比 MP4 和精选平面对齐诊断。每个姿态停留 0.15 秒；视频是采样演示，不是实时录屏、连续动态性能或没有闪烁的证明。完整 192 张原图保留在 Saved，归档前逐张复核哈希；指标应结合空间细节和原生画面审查。',
 '', '`solar_motion/far/` 另外检查 24 个 700→1250→700 米远景姿态，保存起点、最远点和返回点三张原生图。全部 24 张原图在归档及发布前均核验哈希；采样范围覆盖远距离切换区间，不能据此宣称实际 LOD 已逐帧读回或画面完全无闪烁。',
 '', '新平面示意图的 X/Y 像素比例不相等。三维建筑使用真实直角和独立局部坐标，树冠保持自然圆形，因此真实正交截图与示意图不会逐像素重叠；不得通过重新剪切房屋、变形相机或拉伸截图来伪造一致。二维叠图仅验证布局数据，不能证明模型、材质、光照、遮挡或动态镜头达到视觉 1:1。',
 '', '旧相机的 `runtime_calibrated.png` 与 `reference_vs_ue_runtime.png` 仅保留材质/风格对照。相机标定点误差是主仓投影验证，不是对整场外观的一致性评分。',
 '', '本轮性能数据限于本机单个 UE Editor 游戏离屏进程、1920×1080、外部与内部静态视角。它不包含像素流编码/网络延迟、并发访问、长时运行或低配硬件验收。',
 '', '归档自动检查只证明来源、哈希、保存重载、截图有效性及报告成功。最终视觉差异应结合本轮原图人工复核；本文件不自动宣布用户已接受、完美还原或全角度视觉合格。',
 '', f'空间检查 `spatial_audit.json` 与建筑几何检查 `context_geometry_validation.json` 绑定当前源文件。已检查 {reports["context_geometry"]["checked_buildings"]} 个直角建筑；住宅完整屋顶与门廊几何的最小净距为 {reports["context_geometry"]["minimum_complete_house_clearance_m"]:.2f} m。`package_dependencies.json` 来自本轮保存地图的递归依赖检查。树冠边缘允许少量悬挑，树干与道路、主体树冠与建筑/铁路的避让规则和明细均保留在空间报告中。',
 ]
 for state,label in [('exterior','外部'),('interior','内部')]:
  row=perf['performance'][state]['native_csv'];metric=row['metrics']['FrameTime']
  lines.append(f'\n{label}样本 {row["frame_count"]} 帧：FrameTime 均值 {metric["mean_ms"]:.3f} ms，P95 {metric["p95_ms"]:.3f} ms。原生 CSV 与截图按本轮固定路径归档。')
 residual_labels=dict(curb_local_kinks='部分住宅支路与直路路缘仍有局部折点、细小突刺。',context_simplification='北侧邻仓月台与储罐采用简化模型，近景细节和层次弱于主仓。',
  pale_foliage='UE 实际树冠比 Blender 预览更浅，叶片纹理较细碎。',reference_external_tails='参考范围外的部分延长道路端头在低角度视图中仍可见。',
  close_pond_faceting='池塘及步道周界在近景下仍可见多边形折面。',high_key_interior='保留的主仓内部在当前俯视光照下仍偏亮、对比度较低。')
 lines.extend(['','本轮人工审图记录见 `native_visual_review.json`。以下可见差距仍保留，不把结构校验通过写成视觉完全一致：',''])
 for row in reports['native_visual_review'].get('residuals',[]):
  lines.append('- '+row.get('description_zh',residual_labels.get(row['id'],row['description']))+' 对应视图：'+', '.join(row['views'])+'。')
 path.write_text('\n'.join(lines)+'\n',encoding='utf8')


def archive(context,reports,map_sha,pairs):
 # All gates run before any formal mutation. Prepare a complete staging tree
 # first, then replace only explicit destinations. No delete/Git/map mutation.
 stage=SAVED/('archive_stage_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f'));stage.mkdir(parents=True)
 records={}
 for source,target in pairs:
  source=inside(source);target=inside(target,BASE);relative=target.relative_to(DEST)
  copy=stage/relative;copy.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,copy)
  assert sha(source)==sha(copy)
  records[relative.as_posix()]=dict(source=source.relative_to(ROOT).as_posix(),sha256=sha(copy),bytes=copy.stat().st_size)
 raw=Image.open(stage/'runtime_overscan.png').convert('RGB');x,y,w,h=reports['runtime_capture']['crop'];crop=raw.crop((x,y,x+w,y+h));crop.save(stage/'runtime_calibrated.png')
 style=Image.open(BASE/'references/style-focus-20261103.png').convert('RGB')
 assert style.size==crop.size
 comparison=Image.new('RGB',(style.width*2+32,style.height+96),'#eef2f4');cd=ImageDraw.Draw(comparison)
 cd.text((16,20),'LATEST STYLE REFERENCE / latest PLAN governs geometry',fill='#16334b');cd.text((style.width+48,20),'CURRENT UE RUNTIME / unedited original pixels',fill='#16334b')
 comparison.paste(style,(0,96));comparison.paste(crop,(style.width+32,96));comparison.save(stage/'reference_vs_ue_runtime.png')
 for key,directory,filename,title in [('runtime_views','runtime_views','runtime_views_contact_sheet.png','Current UE game views'),('plan_views','plan_views','plan_views_contact_sheet.png','Current UE plan / orthogonal-building review'),('outside_views','outside_views','outside_views_contact_sheet.png','Current UE outside-plan streets / four-sided review'),('detail_views','detail_views','detail_views_contact_sheet.png','Current UE transport / paving / planting detail review')]:
  contact_sheet([(row['name'],stage/directory/(row['name']+'.png'))for row in reports[key]['captures']],stage/filename,title)
 write_visual_review(stage/'visual_review.md',reports,map_sha)
 pipeline=[dict(name=name,report=REPORTS[name].relative_to(ROOT).as_posix(),sha256=sha(REPORTS[name]),success=True)for name in ['import','reload','performance','runtime_views','plan_views','outside_views','detail_views','runtime_capture','blender','package_dependencies','spatial_audit','context_geometry','site_fbx','road_smoothing','outside_geometry','campus_surfaces','transport_geometry']]
 pipeline.append(dict(name='pv_source',report=REPORTS['pv_source'].relative_to(ROOT).as_posix(),sha256=sha(REPORTS['pv_source']),success=True,evidence_scope='auxiliary_cpu_source_audit_not_final_geometry_or_runtime'))
 pipeline.append(dict(name='solar_motion',report=REPORTS['solar_motion'].relative_to(ROOT).as_posix(),sha256=sha(REPORTS['solar_motion']),success=True,evidence_scope='paired_native_pose_samples_not_realtime_video_or_flicker_free_claim'))
 pipeline.append(dict(name='motion_far',report=REPORTS['motion_far'].relative_to(ROOT).as_posix(),sha256=sha(REPORTS['motion_far']),success=True,evidence_scope='24_native_far_pose_samples_not_active_LOD_readback_or_flicker_free_claim'))
 (stage/'final_pipeline.json').write_text(json.dumps(pipeline,ensure_ascii=False,indent=2),encoding='utf8')
 details=dict(success=True,map_sha256=map_sha,source_snapshot_sha256=sha(CONTEXT),reports={k:dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p))for k,p in REPORTS.items()},archives=records,
  style_comparison_reference=dict(path=(BASE/'references/style-focus-20261103.png').relative_to(ROOT).as_posix(),sha256=sha(BASE/'references/style-focus-20261103.png'),resolution=list(style.size),resized=False),
  context_geometry_source_binding=dict(manifest_sha256=sha(BASE/'context/manifest.json'),blend_sha256=sha(BASE/'context/mpr4_reference_context.blend'),
   method='Native context report matches manifest hash and was produced after both saved source files; unchanged run envelope binds their current hashes. Native context report does not itself embed a blend hash.'),
  limits='Source/report/hash/archive consistency only; not visual acceptance, Pixel Streaming or performance equivalence.',
  motion_evidence=dict(source_pngs_verified=192,source_pngs_archived=0,selected_diagnostics=len(MOTION_DIAGNOSTICS),
   native_files_verified={p:h for p,h in context['_verified_motion_files'].items()if p not in context['_far_motion_files']},flicker_free_claim=False,
   scope='Paired native pose samples; MP4 is illustrative sampled playback, not real-time footage. Original frames remain in Saved.'),
  far_motion_evidence=dict(source_pngs_verified=24,source_pngs_archived=3,selected_indices=[0,11,23],
   native_files_verified=context['_far_motion_files'],capture_tool_sha256=reports['motion_far']['capture_tool_sha256'],
   base_capture_tool_sha256=reports['motion_far']['base_capture_tool_sha256'],flicker_free_claim=False,
   scope='Native samples at 700 to 1250 to 700 metres; coverage only, not actual per-frame LOD readback or continuous real-time footage.'),
  obsolete_candidates_not_deleted=obsolete_candidates(pairs),source_files_checked=len(context['sources']))
 for name in ['pipeline_archive_validation.json','performance_archive_validation.json','runtime_capture_archive_validation.json']:
  (stage/name).write_text(json.dumps(details,ensure_ascii=False,indent=2),encoding='utf8')
 for directory in VIEW_NAMES:(stage/directory/'archive_validation.json').write_text(json.dumps(details,ensure_ascii=False,indent=2),encoding='utf8')
 # Hash all generated outputs before writing the completion marker.
 details['derived_files']={p.relative_to(stage).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size)for p in stage.rglob('*')if p.is_file()and p.relative_to(stage).as_posix()not in records and p.name!='plan_validation_archive.json'}
 (stage/'plan_validation_archive.json').write_text(json.dumps(details,ensure_ascii=False,indent=2),encoding='utf8')
 # Recheck source/map immediately before publishing the staged archive.
 assert sha(MAP)==map_sha
 assert all(sha(ROOT/p)==row['sha256']for p,row in context['sources'].items())
 assert all(sha(REPORTS[name])==digest for name,digest in context['_verified_report_hashes'].items()),'Report changed while staging archive'
 assert all(sha(inside(path))==digest for path,digest in context['_verified_motion_files'].items()),'Motion source frame/video/diagnostic changed while staging archive'
 # Publish the completion marker last. Its hashes cover every preceding
 # file; it intentionally does not contain a self-referential hash.
 files=sorted(p for p in stage.rglob('*')if p.is_file()and p.name!='plan_validation_archive.json')
 files.append(stage/'plan_validation_archive.json')
 for file in files:
  target=DEST/file.relative_to(stage);target.parent.mkdir(parents=True,exist_ok=True)
  temp=target.with_name(target.name+'.pending');shutil.copyfile(file,temp);os.replace(temp,target);assert sha(target)==sha(file)
 print(json.dumps(dict(success=True,map_sha256=map_sha,archived_files=len(files),archive= str(DEST/'plan_validation_archive.json'),obsolete_candidates_not_deleted=details['obsolete_candidates_not_deleted']),ensure_ascii=False))


if __name__=='__main__':
 parser=argparse.ArgumentParser();mode=parser.add_mutually_exclusive_group(required=True)
 mode.add_argument('--begin-run',action='store_true');mode.add_argument('--check-only',action='store_true');mode.add_argument('--archive',action='store_true');args=parser.parse_args()
 if args.begin_run:begin_run()
 else:
  context,reports,map_sha=gate();pairs=archive_plan(reports)
  if args.check_only:print(json.dumps(dict(gates_passed=True,map_sha256=map_sha,replacements=[str(d.relative_to(ROOT))for s,d in pairs],obsolete_candidates_not_deleted=obsolete_candidates(pairs)),ensure_ascii=False,indent=2))
  else:archive(context,reports,map_sha,pairs)
