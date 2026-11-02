"""Archive successful MPR evidence after visual review; never touch UE packages."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import struct
import zipfile
from mpr_scene_ownership import verify_owned_scene

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'Saved/MPR'
OUT=ROOT/'SourceAssets/MPR/validation'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    verify_owned_scene(ROOT)
    build=json.loads((SRC/'scene_build.json').read_text(encoding='utf-8'))
    capture=json.loads((SRC/'validation.json').read_text(encoding='utf-8'))
    profile=json.loads((SRC/'performance.json').read_text(encoding='utf-8'))
    assert all(d['success'] for d in (build,capture,profile))
    assert capture['reload_verified'] and len(capture['captures'])==11
    assert profile['map_unchanged'] and profile['map_sha256_after']==digest(ROOT/'Content/Maps/MPR_CAD_Warehouse.umap')
    assert build['ghs_map_sha256_before']==digest(ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap')
    log_path=SRC/'performance-verified.log'
    log=log_path.read_text(encoding='utf-8-sig',errors='replace')
    assert 'MPR_PERFORMANCE '+json.dumps({'success':True})[:-1] in log
    assert not re.search(r'missing usage flag|Default Material will be used in game',log,re.I), 'Runtime material fallback'
    assert all(state['native_csv']['gpu_verified'] for state in profile['performance'].values())
    OUT.mkdir(parents=True,exist_ok=True)
    artifacts=[]
    for item in capture['captures']+profile['captures']:
        source=Path(item['path']);raw=source.read_bytes()
        assert raw[:8]==b'\x89PNG\r\n\x1a\n' and struct.unpack('>II',raw[16:24])==(1920,1080)
        assert raw[-12:]==b'\x00\x00\x00\x00IEND\xaeB\x60\x82'
        if item.get('sha256'):assert digest(source)==item['sha256']
        target=OUT/source.name;shutil.copy2(source,target)
        artifacts.append(dict(path=target.relative_to(ROOT).as_posix(),sha256=digest(target),bytes=target.stat().st_size))
    for name in ('scene_build.json','validation.json','performance.json'):
        shutil.copy2(SRC/name,OUT/name)
    with zipfile.ZipFile(OUT/'native-profile.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for item in profile['performance'].values():
            evidence=item['native_csv'];path=Path(evidence['path'])
            assert digest(path)==evidence['sha256']
            archive.write(path,path.name)
    hardware=[line for line in log.splitlines() if 'LogInit: OS:' in line or 'Chosen D3D12 Adapter' in line]
    summary=dict(map=build['map'],date='2026-11-02',map_sha256=profile['map_sha256_after'],
                 saved_actor_count=build['actor_count'],hism_groups=len(build['groups']),instances=build['instance_count'],
                 mesh_count=len(build['meshes']),generated_material_packages=len(build['materials_created']),
                 compatibility_material_instances=sum('/MI_MPR_HISM_' in m['path'] for m in build['materials_created']),
                 exterior_material_instances=sum('/MI_MPR_Exterior_' in m['path'] for m in build['materials_created']),
                 exterior_surface_masters=sum('/M_MPR_ExteriorSurface' in m['path'] for m in build['materials_created']),
                 source_counts=dict(racks=2867,columns=164,dock_doors=72,drive_in_doors=2),
                 hardware_evidence=hardware,performance_log_sha256=digest(log_path),
                 missing_runtime_material_usage=False,ghs_map_preserved=True,images=artifacts,
                 scope=profile['scope'],camera_controls=profile.get('camera_control_checks',profile.get('camera_controls')),
                 performance={name:{metric:values for metric,values in state['native_csv']['metrics'].items()}
                              for name,state in profile['performance'].items()})
    (OUT/'acceptance.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('MPR_EVIDENCE_ARCHIVED',len(artifacts),'images',OUT)


if __name__=='__main__':main()
