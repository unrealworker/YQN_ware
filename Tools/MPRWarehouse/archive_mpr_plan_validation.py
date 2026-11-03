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
}
INPUTS=['site/plan_registration_v5.json','site/road_outline_v5.json','site/plan_railway_v5.json',
 'site/plan_vegetation_v5.json','site/plan_landscape_islands_v5.json','site/plan_site_details_v5.json','site/manifest.json',
 'context/manifest.json','context/reference_context_ground_layout.json','context/reference_context_layout.json','context/reference_context_plan_v5.json',
 'architecture/reference_shell_manifest.json','architecture/plan_solar_v5.json','props/manifest.json',
 'references/building-road-outline-20261103.png','references/all-elements-outline-20261103.png',
 'architecture/mpr_reference_shell.blend','site/MPR_ReferenceSite.blend',
 'context/mpr4_reference_context.blend','props/MPR_ReferenceV4_Props.blend']


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


def gate():
 context=read(CONTEXT);current=inputs();original=context['sources']
 assert set(current)==set(original),'Source file set changed after begin-run'
 assert all(current[p]['sha256']==original[p]['sha256']for p in original),'Source content changed after begin-run'
 map_sha=sha(MAP);assert map_sha==context['map_sha256'],'Saved map changed after begin-run'
 assert sha(REPORTS['import'])==context['import_report_sha256'],'Import report changed during the validation run'
 reports={k:read(path)for k,path in REPORTS.items()}
 for name in ['import','reload','performance','runtime_views','plan_views','runtime_capture','blender','package_dependencies','spatial_audit','context_geometry','site_fbx']:
  assert reports[name].get('success')is True,(name,'not successful')
 for name in ['reload','performance','runtime_views','plan_views','runtime_capture','package_dependencies']:
  assert REPORTS[name].stat().st_mtime_ns>=context['started_ns'],(name,'stale report predates begin-run')
 for name in ['runtime_views','plan_views','runtime_capture']:
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
 geometry=reports['context_geometry'];assert geometry.get('source_manifest_sha256')==sha(manifests['Context']),'Context geometry source hash mismatch'
 assert geometry.get('saved_blender_checked')is True and not geometry.get('errors'),'Saved context Blender geometry not verified'
 context_blend=BASE/'context/mpr4_reference_context.blend'
 assert REPORTS['context_geometry'].stat().st_mtime_ns>=max(context_blend.stat().st_mtime_ns,manifests['Context'].stat().st_mtime_ns),'Context geometry audit predates saved source'
 assert geometry['checked_buildings']>0 and geometry['max_right_angle_error_deg']<=1e-5
 assert geometry['minimum_complete_house_clearance_m']>=2.999 and geometry['mesh_checks'],'Context complete geometry clearance missing or failed'
 site_fbx=reports['site_fbx'];site_manifest=read(manifests['Site'])
 assert site_fbx.get('source_manifest_sha256')==sha(manifests['Site']),'Site FBX source manifest mismatch'
 expected_site_meshes={row['name']:row for row in site_manifest['meshes']}
 assert site_fbx.get('mesh_count')==len(expected_site_meshes)==26,'Site FBX mesh count mismatch'
 assert {row['name']for row in site_fbx['checks']}==set(expected_site_meshes)and len(site_fbx['checks'])==26,'Site FBX checks incomplete'
 for row in site_fbx['checks']:
  expected=expected_site_meshes[row['name']]
  assert row.get('triangle_match')is True and row['triangles']==row['source_triangles']==expected['triangles'],('Site FBX triangle mismatch',row['name'])
  assert row['bounds_error_m']<.0003 and row['material_slots']==len(expected['material_roles']),('Site FBX boundary/material mismatch',row['name'])
 assert site_fbx['max_bounds_error_m']<.0003
 assert REPORTS['site_fbx'].stat().st_mtime_ns>=max([manifests['Site'].stat().st_mtime_ns]+[inside(row['fbx']).stat().st_mtime_ns for row in site_manifest['meshes']]),'Site FBX audit predates exported source'
 for field in ['preservation','preservation_after_capture']:assert reload[field]['success']is True,(field,'failed')
 assert reload['preservation']['protected_digest']==reports['import']['interior_preservation']['protected_digest']
 assert reload['preservation_after_capture']['protected_digest']==reload['preservation']['protected_digest'],'Interior digest changed during reload captures'
 for name in ['runtime_views','plan_views']:
  assert reports[name].get('assets_saved')is False
  required=['01-overall','02-yard-corner','03-roof','04-docks','05-yard','06-pond','07-railway','08-interior-preserved']if name=='runtime_views'else['09-plan-overview','10-houses-close','11-houses-reverse','12-neighbor-docks','13-east-context']
  assert sorted(row['name']for row in reports[name]['captures'])==sorted(required),(name,'incomplete or duplicate views')
  for row in reports[name]['captures']:
   path=png(row['path'],[1920,1080]);assert sha(path)==row['sha256'],(name,row['name'],'image hash mismatch')
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
 current_images={row['name']:row['sha256']for group in ['runtime_views','plan_views']for row in reports[group]['captures']}
 assert {row['name']:row['sha256']for row in visual['images']}==current_images,'Native visual review does not bind all current images'
 context['_verified_report_hashes']={k:sha(path)for k,path in REPORTS.items()}
 return context,reports,map_sha


def archive_plan(reports):
 pairs=[(REPORTS['import'],DEST/'import_report.json'),(REPORTS['reload'],DEST/'reload_validation.json'),
  (REPORTS['performance'],DEST/'performance.json'),(REPORTS['runtime_capture'],DEST/'runtime_calibrated_capture.json'),
  (REPORTS['runtime_views'],DEST/'runtime_views/capture_report.json'),(REPORTS['plan_views'],DEST/'plan_views/capture_report.json'),
  (REPORTS['package_dependencies'],DEST/'package_dependencies.json'),(REPORTS['spatial_audit'],DEST/'spatial_audit.json'),
  (REPORTS['context_geometry'],DEST/'context_geometry_validation.json'),
  (REPORTS['native_visual_review'],DEST/'native_visual_review.json'),
  (REPORTS['site_fbx'],DEST/'site_fbx_validation.json'),
  (REPORTS['road_smoothing'],DEST/'road_smoothing_review.json'),
  (CONTEXT,DEST/'validation_run_context.json')]
 for key,directory in [('runtime_views','runtime_views'),('plan_views','plan_views')]:
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
 '', '本轮位置标准是用户新提供的 `building-road-outline-20261103.png` 与 `all-elements-outline-20261103.png`。旧彩色效果图继续作为材质、明暗、建筑细节风格参考；不再用旧透视画面的四角反投影塑造周边房屋。主仓内部、CAD 接口和门洞尺度保持原有约束。',
 '', f'数据层叠图 `plan_alignment.png` 包含 {count.get("context_buildings",0)} 个周边建筑、{count.get("trees",0)} 株实际落地树、{count.get("trailers",0)} 辆拖车、{count.get("railcars",0)} 节铁路车厢、{count.get("solar_strips",0)} 条光伏带和 {count.get("roof_fixtures",0)} 个屋顶设备。源树冠数量与实际落地数量可因道路、建筑、铁路及车辆避让不同；拒绝与偏移明细保存在 JSON 中。',
 '', '`plan_views/09-plan-overview.png` 是真实正交游戏视口；其余新增视图从正反两侧检查住宅、邻仓月台和东侧环境。`runtime_views/` 保留传统八视角原图，联系图仅缩略排版，不替代原图。',
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
 style=Image.open(BASE/'references/ChatGPT 图像 2026年11月2日 15_56_24.png').convert('RGB')
 assert style.size==crop.size
 comparison=Image.new('RGB',(style.width*2+32,style.height+96),'#eef2f4');cd=ImageDraw.Draw(comparison)
 cd.text((16,20),'STYLE REFERENCE / latest PLAN governs geometry',fill='#16334b');cd.text((style.width+48,20),'CURRENT UE RUNTIME / unedited original pixels',fill='#16334b')
 comparison.paste(style,(0,96));comparison.paste(crop,(style.width+32,96));comparison.save(stage/'reference_vs_ue_runtime.png')
 for key,directory,filename,title in [('runtime_views','runtime_views','runtime_views_contact_sheet.png','Current UE game views'),('plan_views','plan_views','plan_views_contact_sheet.png','Current UE plan / orthogonal-building review')]:
  contact_sheet([(row['name'],stage/directory/(row['name']+'.png'))for row in reports[key]['captures']],stage/filename,title)
 write_visual_review(stage/'visual_review.md',reports,map_sha)
 pipeline=[dict(name=name,report=REPORTS[name].relative_to(ROOT).as_posix(),sha256=sha(REPORTS[name]),success=True)for name in ['import','reload','performance','runtime_views','plan_views','runtime_capture','blender','package_dependencies','spatial_audit','context_geometry','site_fbx','road_smoothing']]
 (stage/'final_pipeline.json').write_text(json.dumps(pipeline,ensure_ascii=False,indent=2),encoding='utf8')
 details=dict(success=True,map_sha256=map_sha,source_snapshot_sha256=sha(CONTEXT),reports={k:dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p))for k,p in REPORTS.items()},archives=records,
  context_geometry_source_binding=dict(manifest_sha256=sha(BASE/'context/manifest.json'),blend_sha256=sha(BASE/'context/mpr4_reference_context.blend'),
   method='Native context report matches manifest hash and was produced after both saved source files; unchanged run envelope binds their current hashes. Native context report does not itself embed a blend hash.'),
  limits='Source/report/hash/archive consistency only; not visual acceptance, Pixel Streaming or performance equivalence.',
  obsolete_candidates_not_deleted=obsolete_candidates(pairs),source_files_checked=len(context['sources']))
 for name in ['pipeline_archive_validation.json','performance_archive_validation.json','runtime_capture_archive_validation.json']:
  (stage/name).write_text(json.dumps(details,ensure_ascii=False,indent=2),encoding='utf8')
 for directory in ['runtime_views','plan_views']:(stage/directory/'archive_validation.json').write_text(json.dumps(details,ensure_ascii=False,indent=2),encoding='utf8')
 # Hash all generated outputs before writing the completion marker.
 details['derived_files']={p.relative_to(stage).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size)for p in stage.rglob('*')if p.is_file()and p.relative_to(stage).as_posix()not in records and p.name!='plan_validation_archive.json'}
 (stage/'plan_validation_archive.json').write_text(json.dumps(details,ensure_ascii=False,indent=2),encoding='utf8')
 # Recheck source/map immediately before publishing the staged archive.
 assert sha(MAP)==map_sha
 assert all(sha(ROOT/p)==row['sha256']for p,row in context['sources'].items())
 assert all(sha(REPORTS[name])==digest for name,digest in context['_verified_report_hashes'].items()),'Report changed while staging archive'
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
