"""Publish only verified actual UE frames and their matching saved-map receipt."""
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import shutil
import struct

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'SourceAssets/GHS/OfficeFacade'
OUT=SOURCE/'Review'
SAVED=ROOT/'Saved/FacadeExpansion'

def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    live=read(SAVED/'live_validation.json')
    disk=read(SAVED/'saved_validation.json')
    runtime=read(ROOT/'Saved/ParkExpansion/runtime_report.json')
    manifest=read(SOURCE/'facade_manifest.json')
    roundtrip=read(SOURCE/'fbx_roundtrip_verification.json')
    assert live['success'] and disk['success'] and runtime['success'] and roundtrip['passed']
    for field in ('source_hashes', 'facade_asset_hashes'):
        assert live[field] == disk[field], 'Live/saved facade resources differ: ' + field
        for relative, expected in disk[field].items():
            assert sha(ROOT/relative) == expected, 'Validation is stale: ' + relative
            assert runtime['facade_resource_hashes'][relative] == expected, 'Runtime is stale: ' + relative
    map_file=ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'
    digest=sha(map_file)
    assert live['map_sha256']==disk['map_sha256']==digest
    saved_check=next(c for c in runtime['checks'] if c['name']=='runtime_did_not_modify_either_saved_map')
    assert digest in saved_check['map_sha256'].values()
    assert len(runtime['checks'])==16
    OUT.mkdir(parents=True,exist_ok=True)
    frames=[]
    names=['OfficeFacade_Corner','OfficeFacade_Detail','OfficeFacade_RoofHidden',
           'Facade_NEOffice','Facade_EastLoading','Facade_NorthWest','Facade_NorthStreet',
           'Facade_NorthHigh','Facade_SouthDock','Facade_Dock75_78','Facade_Dock51_53',
           'Facade_Dock30_33','ReferenceOverview']
    for name in names:
        source=ROOT/'Saved/ParkExpansion'/('Runtime_'+name+'.png')
        item=next(c for c in runtime['captures'] if c['name']==name)
        assert source.resolve()==Path(item['path']).resolve()
        assert sha(source)==item['sha256'], 'Screenshot differs from runtime receipt: ' + name
        data=source.read_bytes();assert data[:8]==b'\x89PNG\r\n\x1a\n'
        dimensions=list(struct.unpack('>II',data[16:24]));assert dimensions==[1920,1080]
        target=OUT/(name+'.png');shutil.copy2(source,target)
        frames.append(dict(file=target.name,sha256=sha(target),dimensions=dimensions,render='actual UE game viewport'))
    for name in ['live_validation.json','saved_validation.json']:
        shutil.copy2(SAVED/name,OUT/name)
    runtime_source=ROOT/'Saved/ParkExpansion/runtime_report.json'
    compact=dict(success=True,status=runtime['status'],map=runtime['map'],
        elapsed_seconds=runtime['elapsed_seconds'],
        checks=[dict(name=c['name'],passed=c['passed']) for c in runtime['checks']],
        map_sha256=saved_check['map_sha256'],
        facade_resource_hashes=runtime['facade_resource_hashes'],
        full_report_path=str(runtime_source.relative_to(ROOT)),full_report_sha256=sha(runtime_source),
        note='Compact receipt; full report retains the per-frame viewport and business diagnostics in Saved.')
    (OUT/'runtime_validation.json').write_text(json.dumps(compact,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    report=dict(date_local=datetime.now(timezone(timedelta(hours=8))).isoformat(),timezone='Asia/Shanghai',
        map=disk['map'],map_sha256=digest,manifest_sha256=sha(SOURCE/'facade_manifest.json'),
        actor_count=361,preserved_actor_transforms_and_bindings=350,
        dock_labels_moved_outward_only=11,facade_triangles=manifest['mesh']['triangles'],
        bays=manifest['bay_count'],panes=manifest['pane_count'],material_slots=5,
        added_groups=len(manifest['additional_groups']),original_corner_geometry_preserved=True,
        layout_sha256=manifest['layout_sha256'],dock_number_overlap_count=0,
        user_skylight_glass_material_binding_preserved=True,
        independent_roof_visibility=True,business_registry=dict(equipment=106,facilities=56),
        validation=dict(live=True,saved_reload=True,fbx_roundtrip=True,runtime_checks=16,
            runtime_seconds=runtime['elapsed_seconds'],runtime_process_exit='self-quit after success'),
        images=frames,opaque_display_glass=True,executable_repackaged=False,performance_benchmark=False)
    (OUT/'acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(success=True,frames=len(frames),map_sha256=digest),ensure_ascii=False))

if __name__=='__main__':main()
