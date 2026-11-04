"""Archive final new-map evidence, retaining the original scene protection chain."""
from pathlib import Path
import gzip,hashlib,json,shutil
import rebuild_preservation as guard
ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'SourceAssets/MPR/rebuild_b50b57'
CACHE=ROOT/'Saved/MPR/rebuild_20261104'
OUT=SRC/'validation'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    imported=read(CACHE/'import_report.json');reload=read(CACHE/'reload_report.json')
    blender=read(CACHE/'blender_validation.json');views=read(CACHE/'runtime_views/capture_report.json')
    perf=read(CACHE/'performance/performance.json');roads=read(CACHE/'road_validation.json')
    clearance=read(CACHE/'surface_clearance.json');cpu=read(CACHE/'cpu_import_preflight.json')
    native_tests=read(CACHE/'render_profile_tests/index.json')
    solar_native=read(SRC/'solar/blender_validation.json')
    solar_geometry=read(SRC/'solar/source_fbx_validation.json')
    assert native_tests['succeeded']==3 and native_tests['failed']==0 and native_tests['notRun']==0
    assert all(r['success'] is True for r in (imported,reload,blender,views,perf,clearance,cpu))
    assert roads['status']=='passed'
    assert reload['render_profile_lifecycle']['success'] is True
    assert solar_native['success'] is True and solar_geometry['success'] is True
    assert reload['retained_geometry_unchanged_except_approved_solar_meshes'] is True
    assert reload['retained_transforms_instances_exact'] is True
    assert len(reload['mesh_changes'])==5 and len(reload['solar_mesh_audit'])==5
    solar_sha=sha(SRC/'solar/manifest.json')
    assert read(SRC/'manifest.json')['solar_rebuild']['sha256']==solar_sha
    assert solar_native['manifest_sha256']==solar_geometry['fbx_checks']['manifest_sha256']==solar_sha
    assert solar_native['blend_sha256']==solar_geometry['fbx_checks']['blend_sha256']==sha(SRC/'solar/MPR_B50B57_Solar.blend')
    assert solar_geometry['layout_sha256']==sha(SRC/'solar/layout.json')
    assert solar_geometry['payload_sha256']==sha(SRC/'solar/geometry_payload.json.gz')
    _,solar_files=guard.solar_source_contract(ROOT,read(SRC/'manifest.json'))
    ownership=read(SRC/'scene_ownership.json')
    assert guard.assert_old_files(ROOT,read(CACHE/'old_content_hashes.json'))==ownership['new_files']
    for name,digest in ownership['source_files'].items():assert sha(ROOT/name)==digest
    for name,digest in read(CACHE/'old_ownership_hashes.json').items():assert sha(ROOT/name)==digest
    assert all(ownership['source_files'].get(name)==digest for name,digest in solar_files.items())
    assert ownership['mesh_changes']==reload['mesh_changes']==imported['mesh_changes']
    assert ownership['solar_mesh_audit']==reload['solar_mesh_audit']==imported['solar_mesh_audit']
    map_sha=sha(ROOT/'Content/Maps/MPR_CAD_Warehouse_B50B57.umap')
    assert map_sha==imported['map_sha256']==reload['map_sha256']==views['map_sha256']==perf['map_sha256_after']
    manifest_sha=sha(SRC/'manifest.json')
    assert manifest_sha==blender['manifest_sha256']==reload['source_manifest_sha256']==imported['source_manifest_sha256']
    assert manifest_sha==clearance['manifest_sha256']==cpu['manifest_sha256']
    assert clearance['blend_sha256']==blender['blend_sha256']==sha(ROOT/read(SRC/'manifest.json')['blend'])
    assert clearance['blend_unchanged'] is True and clearance['manifest_unchanged'] is True
    assert cpu['map']==imported['map']==reload['map']=='/Game/Maps/MPR_CAD_Warehouse_B50B57'
    assert sha(ROOT/'Content/Maps/MPR_CAD_Warehouse.umap')==reload['original_map_sha256']
    OUT.mkdir(parents=True,exist_ok=True);files={}
    def copy(path,name,compress=False):
        target=OUT/name;target.parent.mkdir(parents=True,exist_ok=True)
        if compress:
            with target.open('wb') as stream:
                with gzip.GzipFile(filename='',fileobj=stream,mode='wb',mtime=0) as z:z.write(path.read_bytes())
        else:shutil.copy2(path,target)
        files[name]=dict(sha256=sha(target),source_sha256=sha(path),bytes=target.stat().st_size)
    for n in ['import_report.json','reload_report.json','blender_validation.json','road_validation.json','cpu_import_preflight.json','surface_clearance.json']:
        copy(CACHE/n,n)
    for n in ['source_snapshot.json','old_content_hashes.json','old_ownership_hashes.json','after_import.json','after_reload_observed.json','after_reload_normalized.json']:
        copy(CACHE/n,n+'.gz',True)
    copy(CACHE/'runtime_views/capture_report.json','runtime_views/capture_report.json')
    for row in views['captures']:
        path=Path(row['path']);assert sha(path)==row['sha256']
        copy(path,'runtime_views/'+row['name']+'.png')
    copy(CACHE/'performance/performance.json','performance.json')
    copy(CACHE/'render_profile_tests/index.json','render_profile_tests.json')
    copy(CACHE/'build.log','build.log')
    for n in ['geometry_validation.json','blender_validation.json','source_fbx_validation.json']:
        copy(SRC/'solar'/n,'solar/'+n)
    for name,row in perf['performance'].items():
        path=Path(row['native_csv']['path']);assert sha(path)==row['native_csv']['sha256']
        copy(path,'csv/'+name+'.csv.gz',True)
    review=OUT/'visual_review.md'
    assert review.is_file() and map_sha in review.read_text(encoding='utf8'),'Visual review must name the final map hash'
    files['visual_review.md']=dict(sha256=sha(review),source_sha256=sha(review),bytes=review.stat().st_size)
    index=dict(success=True,map_sha256=map_sha,source_manifest_sha256=manifest_sha,
        original_map_unchanged=True,old_content_files_unchanged=reload['unchanged_original_content_files'],
        retained_actor_count=reload['retained']['retained_actor_count'],files=files,
        approved_solar_mesh_replacements=5,solar_manifest_sha256=solar_sha,
        source_tools={p.relative_to(ROOT).as_posix():sha(p) for p in sorted((ROOT/'Tools/MPRWarehouse').glob('*rebuild*.py'))},
        renderer_sources={p.relative_to(ROOT).as_posix():sha(p) for p in sorted((ROOT/'Source/Test').rglob('EnvironmentRenderProfile*')) if p.is_file()},
        scope='Native UE5.8 1920x1080 single-instance validation, not Pixel Streaming/network validation')
    (OUT/'index.json').write_text(json.dumps(index,ensure_ascii=False,indent=2),encoding='utf8')
    print('MPR_REBUILD_ARCHIVED',len(files),map_sha)
if __name__=='__main__':main()
