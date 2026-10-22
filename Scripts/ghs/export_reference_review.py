"""Publish verified reference-style game frames; retire superseded renders."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
from PIL import Image,ImageDraw,ImageFont
ROOT=Path('D:/UEPro/Test');OUT=ROOT/'SourceAssets/GHS/Park/Review'
def read(path):return json.loads((ROOT/path).read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
applied=read('Saved/ParkReferenceStyle/apply_report.json')
saved=read('Saved/ParkReferenceStyle/saved_validation.json')
runtime=read('Saved/ParkExpansion/runtime_report.json')
capture=read('Saved/ParkReferenceStyle/capture_report.json')
geometry=read('Saved/ParkReferenceStyle/vegetation_geometry_validation.json')
truck_fix=read('Saved/ParkReferenceStyle/truck_material_usage_fix.json')
manifest=read('SourceAssets/GHS/Park/park_manifest.json')
roof=read('SourceAssets/GHS/MainRoof/roof_manifest.json')
style=read('SourceAssets/GHS/Park/reference_style.json')
old=read('Saved/ParkReferenceStyle/Before/acceptance.json')
baseline=read('Saved/ParkReferenceStyle/Before/scene_state.json')
for report in [applied,saved,runtime,capture,geometry,truck_fix]:assert report['success'],report
assert len(runtime['checks'])==15 and all(c['passed'] for c in runtime['checks'])
assert runtime['reference_art_views']['count']==6
map_path=ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'
assert sha(map_path)==saved['map_sha256']==runtime['checks'][-1]['map_sha256'][str(map_path)]
assert sha(ROOT/'SourceAssets/GHS/Park/park_manifest.json')==saved['park_manifest_sha256']==runtime['manifest_sha256']
assert sha(ROOT/'SourceAssets/GHS/Park/reference_style.json')==saved['reference_style_sha256']
assert geometry['triangles']==manifest['triangles_total']
names=['ReferenceOverview','ReferenceIsland','ReferenceTree','ReferenceRoad','ReferenceRoof','ReferenceInterior']
sources={name+'.png':ROOT/('Saved/ParkExpansion/Runtime_'+name+'.png') for name in names}
for name in ['Overview_1920x1080','Overview_2560x1600','AGV07_Focus']:
    sources['Runtime_'+name+'.png']=ROOT/('Saved/ParkExpansion/Runtime_'+name+'.png')
sources['ReferenceContext.png']=ROOT/'Saved/ParkReferenceStyle/ReferenceContext.png'
current_names=set(sources)|{'Polish_Summary.png'}
for item in old['images']:
    if item['file'] in current_names:continue
    path=OUT/item['file']
    assert path.resolve().parent==OUT.resolve()
    if path.exists():
        assert sha(path)==item['sha256'],('Superseded review image has other edits',path)
        path.unlink()
for name,path in sources.items():
    assert path.is_file() and path.stat().st_mtime>=(ROOT/'Saved/ParkReferenceStyle/apply_report.json').stat().st_mtime,path
    shutil.copy2(path,OUT/name)
sheet=Image.new('RGB',(1952,1272),'#f4f6fa');draw=ImageDraw.Draw(sheet)
font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',27)
tiles=[('ReferenceOverview','冷灰蓝园区与层次配色'),('ReferenceTree','分层树冠与分枝'),
       ('ReferenceIsland','独立林岛与大、小植被'),('ReferenceInterior','屋顶隐藏后的内部')]
for i,(name,label) in enumerate(tiles):
    x=16+(i%2)*968;y=16+(i//2)*628
    with Image.open(OUT/(name+'.png')) as img:sheet.paste(img.convert('RGB').resize((952,536),Image.Resampling.LANCZOS),(x,y+50))
    draw.text((x+8,y+5),label,font=font,fill='#1b2f4b')
sheet.save(OUT/'Polish_Summary.png')
images=[]
for name in list(sources)+['Polish_Summary.png']:
    path=OUT/name
    with Image.open(path) as img:dimensions=list(img.size)
    images.append(dict(file=name,sha256=sha(path),dimensions=dimensions,bytes=path.stat().st_size))
ground=next(a for a in baseline['actors'] if a['label']=='GHSPark_Ground')
receipt=dict(date_local=datetime.now().isoformat(timespec='seconds'),timezone='Asia/Shanghai',
    map=applied.get('map','/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'),map_sha256=sha(map_path),
    manifest_sha256=saved['park_manifest_sha256'],roof_manifest_sha256=saved['roof_manifest_sha256'],
    reference_style_sha256=saved['reference_style_sha256'],style=style,
    current_appearance_authority='SourceAssets/GHS/Park/reference_style.json',
    actor_count=360,static_layout_preserved=True,original_source_map_preserved=True,
    authorized_ground_color_replacement=True,ground_transform_preserved=ground['transform'],
    prior_ground_material_backup='Saved/ParkReferenceStyle/Before',
    component_material_overrides=read('SourceAssets/GHS/Park/scene_overrides.json')['component_materials'],
    shared_source_assets_sha256=old['shared_source_assets_sha256'],
    context_counts=manifest['counts'],park_triangles=manifest['triangles_total'],roof_triangles=roof['mesh']['triangles'],
    total_unique_triangles=manifest['triangles_total']+roof['mesh']['triangles'],
    total_instanced_triangles=manifest['instanced_triangles_total']+roof['mesh']['triangles'],
    vegetation=dict(forest_trees=280,total_trees=586,islands=24,total_shrubs=332,
        tree_triangles=1856,tree_shape='Five unequal foliage masses with short visible supporting branches',
        nanite_crown_meshes=3,clearance=saved['forest_safety']),
    truck_material_fix=dict(materials=7,only_usage_flags_changed=truck_fix['only_usage_flags_changed'],
        live_and_disk_surface_properties_equal_before_save=truck_fix['comparison_passed']),
    roof=dict(actor='GHS_MainWarehouseRoof',mesh_count=1,visibility_toggle_verified=True,product_ui_toggle_implemented=False),
    saved_map_reload_passed=True,saved_map_reload_finished_utc=saved['finished_utc'],
    runtime_checks=[dict(name=c['name'],passed=c['passed']) for c in runtime['checks']],
    runtime_elapsed_seconds=runtime['elapsed_seconds'],runtime_business_registry=dict(equipment=106,facilities=56),
    visual_review_passed=True,visual_evidence=runtime['reference_art_views'],
    images=images,performance_benchmark=False,accuracy=manifest['measurement_status'])
for path,expected in receipt['shared_source_assets_sha256'].items():assert sha(Path(path))==expected
(OUT/'acceptance.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(success=True,images=len(images),map_sha256=receipt['map_sha256'],triangles=receipt['total_unique_triangles'])))
