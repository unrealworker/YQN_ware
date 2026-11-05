"""Archive only final, matching extension validation; no scene/package writes."""
import gzip,hashlib,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'SourceAssets/MPR/extension_b50b57'
CACHE=ROOT/'Saved/MPR/extension_20261104'
OUT=SRC/'validation'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    imported=read(CACHE/'import_report.json')
    reloaded=read(CACHE/'reload_report.json')
    blender=read(CACHE/'blender_validation.json')
    roads=read(CACHE/'road_transition_validation.json')
    views=read(CACHE/'runtime_views/capture_report.json')
    before=read(CACHE/'performance_before/performance.json')
    after=read(CACHE/'performance_after/performance.json')
    assert all(r['success'] for r in (imported,reloaded,blender,views,before,after))
    assert roads['status']=='passed'
    current=sha(ROOT/'Content/Maps/MPR_CAD_Warehouse.umap')
    assert current==imported['map_sha256']==reloaded['map_sha256']==views['map_sha256']==after['map_sha256_after']
    assert before['map_sha256_after']==imported['baseline_map_sha256']
    assert sha(SRC/'manifest.json')==imported['source_manifest_sha256']==blender['manifest_sha256']
    assert sha(ROOT/'Tools/MPRWarehouse/mpr_extension_roads.py')==roads['module_sha256']
    OUT.mkdir(parents=True,exist_ok=True)
    files={}
    def archive(source,name,compress=False):
        target=OUT/name;target.parent.mkdir(parents=True,exist_ok=True)
        if compress:
            with target.open('wb') as stream:
                with gzip.GzipFile(filename='',fileobj=stream,mode='wb',mtime=0) as z:
                    z.write(source.read_bytes())
        else:shutil.copy2(source,target)
        files[name]=dict(sha256=sha(target),bytes=target.stat().st_size,source_sha256=sha(source))
    for name in ['baseline_report.json','import_report.json','reload_report.json',
                 'blender_validation.json','road_transition_validation.json','road_connections_review.json']:
        archive(CACHE/name,name)
    for name in ['baseline.json','after_import.json','after_reload.json',
                 'after_reload_observed.json','after_reload_digest_normalized.json']:
        archive(CACHE/name,name+'.gz',True)
    archive(CACHE/'runtime_views/capture_report.json','runtime_views/capture_report.json')
    for record in views['captures']:
        path=Path(record['path']);assert sha(path)==record['sha256']
        archive(path,'runtime_views/'+record['name']+'.png')
    comparison={}
    for label,report in [('before',before),('after',after)]:
        archive(CACHE/('performance_'+label)/'performance.json','performance_'+label+'.json')
        for view,record in report['performance'].items():
            csv=Path(record['native_csv']['path']);assert sha(csv)==record['native_csv']['sha256']
            archive(csv,'csv/'+label+'_'+view+'.csv.gz',True)
            comparison.setdefault(view,{})[label]=record['native_csv']['metrics']
    manifest=read(SRC/'manifest.json')
    audit=read(SRC/'geometry_audit.json')
    index=dict(success=True,map_sha256=current,source_manifest_sha256=sha(SRC/'manifest.json'),
        protected_scene=reloaded,generated_meshes=len(manifest['meshes']),
        generated_triangles=manifest['source_generated_triangles'],context=audit['context']['summary'],
        roads=dict(connected=roads['audit']['connected_count'],outer_preserved=roads['audit']['preserved_outer_count']),
        performance=comparison,files=files,
        scope='UE5.8 native 1920x1080 single process; not Pixel Streaming/network or multi-user performance')
    index['validation_tool_hashes']={p.relative_to(ROOT).as_posix():sha(p)
        for p in sorted((ROOT/'Tools/MPRWarehouse').glob('*extension*.py'))}
    (OUT/'index.json').write_text(json.dumps(index,ensure_ascii=False,indent=2),encoding='utf-8')
    print('MPR_EXTENSION_VALIDATION_ARCHIVED',len(files),current)
if __name__=='__main__':main()
