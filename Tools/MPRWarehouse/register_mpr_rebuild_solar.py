"""Register five independently exported PV meshes; dry-run unless --apply is given."""
import argparse
from copy import deepcopy
import json
from pathlib import Path

import rebuild_preservation as guard

ROOT=Path(__file__).resolve().parents[2]


def register(root=ROOT,*,apply=False):
    root=Path(root).resolve();source=root/'SourceAssets/MPR/rebuild_b50b57'
    path=source/'manifest.json';before=path.read_bytes();before_hash=guard.sha(path)
    manifest=json.loads(before.decode('utf-8-sig'));updated=deepcopy(manifest)
    guard.require(manifest.get('rebuild_namespace')==guard.DEST and manifest.get('map')==guard.MAP,
                  'Registration requires the independently rebuilt MPR manifest')
    relative=guard.SOLAR_ROOT+'/manifest.json'
    updated['solar_rebuild']=dict(manifest=relative,sha256=guard.sha(root/relative))
    overrides=[]
    for guid,(_,suffix) in guard.SOLAR_IDENTITIES.items():
        old='SM_MPR4_SolarBank_'+suffix;new='SM_MPRR_SolarBank_'+suffix
        overrides.append(dict(source_guid=guid,component_name='StaticMeshComponent0',
            source_mesh='/Game/MPRWarehouse/ReferenceV4/Architecture/Meshes/'+old+'.'+old,
            target_mesh=guard.DEST+'/Architecture/Meshes/'+new+'.'+new))
    updated['retained_mesh_overrides']=overrides
    rows,files=guard.solar_source_contract(root,updated)
    changed=updated!=manifest
    guard.require(guard.sha(path)==before_hash,'Main manifest changed during registration')
    if apply and changed:
        guard.require(not (source/'scene_ownership.json').exists(),
                      'Archive the imported attempt before changing its registered source manifest')
        # Dict assignment preserves all existing key positions. Do not rewrite
        # already-bound manifests: their exact bytes are audit-chain evidence.
        text=json.dumps(updated,ensure_ascii=False,indent=2)
        if before.endswith(b'\n'):text+='\n'
        if b'\r\n' in before:text=text.replace('\n','\r\n')
        payload=text.encode('utf-8')
        if before.startswith(b'\xef\xbb\xbf'):payload=b'\xef\xbb\xbf'+payload
        temp=path.with_name(path.name+'.register.tmp')
        with temp.open('xb') as stream:stream.write(payload)
        guard.require(guard.sha(path)==before_hash,'Main manifest changed before registration save')
        temp.replace(path)
    return dict(success=True,mode='apply' if apply else 'dry-run',changed=changed,
        written=bool(apply and changed),manifest_sha256_before=before_hash,manifest_sha256_after=guard.sha(path),
        solar_manifest_sha256=updated['solar_rebuild']['sha256'],solar_meshes=len(rows),
        solar_fbx_files_verified=len(files)-1,retained_mesh_overrides=overrides)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true',help='Write only the two solar registration fields when their values differ')
    args=parser.parse_args()
    print(json.dumps(register(apply=args.apply),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
