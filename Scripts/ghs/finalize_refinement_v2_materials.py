"""Persist the 14 new truck materials' HISM usage after actual map placement."""
from pathlib import Path
import unreal,json,hashlib
ROOT=Path(r'D:\UEPro\Test')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
report_path=ROOT/'Saved/GHS_RefinementV2.json';report=json.loads(report_path.read_text(encoding='utf-8'))
assert report['success'] and 'truck_material_usage_finalized' not in report
for relative,entry in report['changed_files'].items():assert sha(ROOT/relative)==entry['after_sha256']
palette_paths=[p for p in report['new_assets'] if p.startswith('Content/GHSRefinementV2/Materials/')]
assert len(palette_paths)==14
before={p:sha(ROOT/p) for p in palette_paths}
for relative in palette_paths:
    material=unreal.EditorAssetLibrary.load_asset('/Game/'+relative[len('Content/'):-len('.uasset')])
    material.set_editor_property('used_with_instanced_static_meshes',True)
    unreal.MaterialEditingLibrary.recompile_material(material)
    assert unreal.EditorAssetLibrary.save_loaded_asset(material,only_if_is_dirty=False)
    assert material.get_editor_property('used_with_instanced_static_meshes')
    report['new_assets'][relative]=sha(ROOT/relative)
report['truck_material_usage_finalized']=dict(material_count=14,before_sha256=before)
report_path.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
unreal.log('GHS_V2_TRUCK_MATERIALS_SAVED 14')
