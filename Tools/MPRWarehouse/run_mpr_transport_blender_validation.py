"""Run isolated, <=30-mesh native Blender FBX validation batches."""
import argparse,hashlib,json,os,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'SourceAssets/MPR/rebuild_b50b57/transport_revision_20261105'
OUTPUT=ROOT/'Saved/MPR/cleanup_20261105/transport/native_validation'
VERIFIER=ROOT/'Tools/MPRWarehouse/verify_mpr_transport_blender.py'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--blender',type=Path,required=True);parser.add_argument('--batch-size',type=int,default=30);args=parser.parse_args()
    assert args.blender.is_file()and 1<=args.batch_size<=30
    manifest=json.loads((SOURCE/'manifest.json').read_text(encoding='utf8'));rows=manifest['meshes'];verifier_hash=sha(VERIFIER)
    expected={'manifest_sha256':sha(SOURCE/'manifest.json'),'blend_sha256':sha(ROOT/manifest['blend'])}
    run=OUTPUT/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ');run.mkdir(parents=True)
    report={'success':False,'meshes':[],'batches':[],**expected,'verifier_sha256':verifier_hash}
    for start in range(0,len(rows),args.batch_size):
        stop=min(start+args.batch_size,len(rows));target=run/f'{start:03d}_{stop:03d}.json';log=target.with_suffix('.log')
        assert sha(VERIFIER)==verifier_hash
        cmd=[str(args.blender),'--background','--factory-startup','--disable-autoexec','--debug-memory','--threads','1','--python-exit-code','1','--python',str(VERIFIER),'--','--start',str(start),'--stop',str(stop),'--report',str(target)]
        print('MPR_TRANSPORT_VALIDATE_BATCH',start,stop,flush=True)
        with log.open('w',encoding='utf8')as f:
            done=subprocess.run(cmd,cwd=ROOT,env=dict(os.environ,PYTHONMALLOC='malloc'),stdout=f,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        result=json.loads(target.read_text(encoding='utf8'))if target.exists()else {'success':False,'error':'No native report'}
        report['batches'].append(dict(start=start,stop=stop,exit_code=done.returncode,report=str(target),log=str(log)))
        try:
            assert done.returncode==0 and result.get('success'),result.get('error')
            assert all(result[k]==v for k,v in expected.items())
            assert [r['name']for r in result['meshes']]==[r['name']for r in rows[start:stop]]
            assert result['fbx_roundtrip_meshes']==stop-start
            assert all(r['coordinate_color_roundtrip']['multiset_equal']for r in result['meshes'])
            report['meshes'].extend(result['meshes'])
        except Exception as e:
            report['error']=str(e);(OUTPUT/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf8');raise
    assert [r['name']for r in report['meshes']]==[r['name']for r in rows]
    assert sha(SOURCE/'manifest.json')==expected['manifest_sha256']and sha(ROOT/manifest['blend'])==expected['blend_sha256']
    report.update(success=True,fbx_roundtrip_meshes=len(rows),triangles=sum(r['triangles']for r in rows),assets_saved=False)
    (OUTPUT/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');print('MPR_TRANSPORT_NATIVE_VALIDATION_COMPLETE',len(rows),flush=True)
if __name__=='__main__':main()
