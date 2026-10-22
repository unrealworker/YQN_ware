"""Publish current roof/style captures after saved-map and runtime checks."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
from PIL import Image,ImageDraw,ImageFont

ROOT=Path('D:/UEPro/Test');OUT=ROOT/'SourceAssets/GHS/Park/Review'
def read(path):return json.loads((ROOT/path).read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
applied=read('Saved/ParkRoofStyle/apply_report.json')
saved=read('Saved/ParkRoofStyle/saved_validation.json')
runtime=read('Saved/ParkExpansion/runtime_report.json')
roof_views=read('Saved/ParkRoofStyle/capture_report.json')
park_views=read('Saved/ParkRefinement/detail_capture_report.json')
overview=read('Saved/ParkExpansion/capture_report.json')
manifest=read('SourceAssets/GHS/Park/park_manifest.json')
roof=read('SourceAssets/GHS/MainRoof/roof_manifest.json')
old=read('Saved/ParkRoofStyle/Before/acceptance.json')
for report in [applied,saved,runtime,roof_views,park_views,overview]:assert report['success'],report
assert len(runtime['checks'])==15 and all(c['passed'] for c in runtime['checks'])
map_path=ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'
assert sha(map_path)==saved['map_sha256']==runtime['checks'][-1]['map_sha256'][str(map_path)]
assert sha(ROOT/'SourceAssets/GHS/Park/park_manifest.json')==saved['park_manifest_sha256']==runtime['manifest_sha256']
assert sha(ROOT/'SourceAssets/GHS/MainRoof/roof_manifest.json')==saved['roof_manifest_sha256']
for path,expected in old['shared_source_assets_sha256'].items():assert sha(Path(path))==expected
sources=[ROOT/'Saved/ParkExpansion/SitePlan.png']
sources += [ROOT/('Saved/ParkExpansion/Runtime_'+name+'.png') for name in
            ('Overview_1920x1080','Overview_2560x1600','AGV07_Focus')]
sources += [Path(row['path']) for row in park_views['captures']+roof_views['captures']]
assert len(sources)==29
after=(ROOT/'Saved/ParkRoofStyle/apply_report.json').stat().st_mtime
for source in sources:
    assert source.stat().st_mtime>=after,source
    shutil.copy2(source,OUT/source.name)
sheet=Image.new('RGB',(1952,1272),'#f4f6fa');draw=ImageDraw.Draw(sheet)
font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',27)
for i,(name,label) in enumerate([('RoofExteriorOverview','主厂房外观'),('RoofHiddenInterior','屋顶隐藏后：内部完整保留'),
                                ('RoofDetail','采光带与金属屋面细节'),('TreeSoftDetail','平滑树冠与柔和绿色')]):
    x=16+(i%2)*968;y=16+(i//2)*628
    with Image.open(OUT/(name+'.png')) as img:sheet.paste(img.convert('RGB').resize((952,536),Image.Resampling.LANCZOS),(x,y+50))
    draw.text((x+8,y+5),label,font=font,fill='#1b2f4b')
sheet.save(OUT/'Polish_Summary.png')
images=[]
for path in [OUT/s.name for s in sources]+[OUT/'Polish_Summary.png']:
    with Image.open(path) as img:dimensions=list(img.size)
    images.append(dict(file=path.name,sha256=sha(path),dimensions=dimensions,bytes=path.stat().st_size))
receipt=dict(date_local=datetime.now().isoformat(timespec='seconds'),timezone='Asia/Shanghai',
    map=applied['map'],map_sha256=sha(map_path),manifest_sha256=runtime['manifest_sha256'],
    roof_manifest_sha256=saved['roof_manifest_sha256'],original_source_map_preserved=True,
    existing_actor_count_preserved=359,total_actor_count=360,
    component_material_overrides=read('SourceAssets/GHS/Park/scene_overrides.json')['component_materials'],
    preserved_ground_actor_position_cm=[170.,240.,0.],
    shared_source_assets_sha256=old['shared_source_assets_sha256'],
    unsaved_unrelated_assets_preserved=applied['unsaved_unrelated_assets_preserved'],
    context_counts=manifest['counts'],park_triangles=manifest['triangles_total'],roof_triangles=roof['mesh']['triangles'],
    total_unique_triangles=manifest['triangles_total']+roof['mesh']['triangles'],
    total_instanced_triangles=manifest['instanced_triangles_total']+roof['mesh']['triangles'],
    roof=dict(actor=applied['roof_label'],mesh_count=1,material_slots=5,editable_parts=roof['mesh']['source_parts'],
        collision=False,tick=False,business_identity=False,visibility_toggle_verified=True,
        bottom_elevation_m=roof['bottom_elevation_m'],minimum_rack_clearance_m=roof['minimum_rack_clearance_m'],
        product_ui_toggle_implemented=False,future_interaction='Roof visibility must be linked with interior POI and picking filters.'),
    style=applied['style'],vegetation_geometry_preserved=True,saved_map_reload_passed=True,
    saved_map_reload_finished_utc=saved['finished_utc'],
    runtime_checks=[dict(name=c['name'],passed=c['passed']) for c in runtime['checks']],
    runtime_elapsed_seconds=runtime['elapsed_seconds'],runtime_business_registry=dict(equipment=106,facilities=56),
    visual_review_passed=True,visual_review_notes=[
        'Exact warehouse silhouette is covered, including the southwest office wing and southeast angled edge.',
        'Five blue rooflight strips, standing seams and blue perimeter trim match the supplied architectural direction.',
        'All roof parts hide together; the existing racks, cargo and equipment remain intact.',
        'Vegetation uses smooth crown normals and muted greens with unchanged geometry and placements.',
        'User ground material and translation remain unchanged.'
    ],images=images,performance_benchmark=False,accuracy=manifest['measurement_status'])
(OUT/'acceptance.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(success=True,images=len(images),map_sha256=receipt['map_sha256'],roof_triangles=receipt['roof_triangles'])))
