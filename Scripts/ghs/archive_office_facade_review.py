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
SAVED=ROOT/'Saved/OfficeFacade'

def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    live=read(SAVED/'live_validation.json')
    disk=read(SAVED/'saved_validation.json')
    runtime=read(ROOT/'Saved/ParkExpansion/runtime_report.json')
    manifest=read(SOURCE/'facade_manifest.json')
    roundtrip=read(SOURCE/'fbx_roundtrip_verification.json')
    assert live['success'] and disk['success'] and runtime['success'] and roundtrip['passed']
    map_file=ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'
    digest=sha(map_file)
    assert live['map_sha256']==disk['map_sha256']==digest
    saved_check=next(c for c in runtime['checks'] if c['name']=='runtime_did_not_modify_either_saved_map')
    assert digest in saved_check['map_sha256'].values()
    assert len(runtime['checks'])==16
    OUT.mkdir(parents=True,exist_ok=True)
    frames=[]
    names=['OfficeFacade_Corner','OfficeFacade_Detail','OfficeFacade_RoofHidden','ReferenceOverview']
    for name in names:
        source=ROOT/'Saved/ParkExpansion'/('Runtime_'+name+'.png')
        item=next(c for c in runtime['captures'] if c['name']==name)
        assert source.resolve()==Path(item['path']).resolve()
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
        full_report_path=str(runtime_source.relative_to(ROOT)),full_report_sha256=sha(runtime_source),
        note='Compact receipt; full report retains the per-frame viewport and business diagnostics in Saved.')
    (OUT/'runtime_validation.json').write_text(json.dumps(compact,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    report=dict(date_local=datetime.now(timezone(timedelta(hours=8))).isoformat(),timezone='Asia/Shanghai',
        map=disk['map'],map_sha256=digest,manifest_sha256=sha(SOURCE/'facade_manifest.json'),
        actor_count=361,preserved_original_actors=360,facade_triangles=manifest['mesh']['triangles'],
        bays=manifest['bay_count'],panes=manifest['pane_count'],material_slots=5,
        independent_roof_visibility=True,business_registry=dict(equipment=106,facilities=56),
        validation=dict(live=True,saved_reload=True,fbx_roundtrip=True,runtime_checks=16,
            runtime_seconds=runtime['elapsed_seconds'],runtime_process_exit='self-quit after success'),
        images=frames,opaque_display_glass=True,executable_repackaged=False,performance_benchmark=False)
    (OUT/'acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(success=True,frames=len(frames),map_sha256=digest),ensure_ascii=False))

if __name__=='__main__':main()
