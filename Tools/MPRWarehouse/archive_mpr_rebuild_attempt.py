"""Archive exactly one validated new-map attempt; old project assets never move.

Preview: python archive_mpr_rebuild_attempt.py
Archive: python archive_mpr_rebuild_attempt.py --apply
Restore preview/apply: python archive_mpr_rebuild_attempt.py --restore ARCHIVE [--apply]

This is a disk-only operation. Close project UE processes before --apply.
Source FBXs and the current builder outputs stay in place for the next build.
"""
import argparse
from datetime import datetime,timezone
import json,os,shutil,subprocess
from pathlib import Path
import rebuild_preservation as guard

ROOT=Path(__file__).resolve().parents[2]
OUT='Saved/MPR/rebuild_20261104'
SOURCE='SourceAssets/MPR/rebuild_b50b57'
ARCHIVES='Saved/MPR/rebuild_attempts'
OWNERSHIP=SOURCE+'/scene_ownership.json'
AUDITS=['source_snapshot.json','old_content_hashes.json','old_ownership_hashes.json',
        'after_import.json','imported_manifest.json','import_report.json','reload_report.json',
        'after_reload_observed.json','after_reload_normalized.json','source_map_backup.umap']
OPTIONAL_AUDITS=['import.log','reload.log','views.log']
require=guard.require
sha=guard.sha

def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))

def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    tmp.replace(path)

def inside(root,relative):
    require(isinstance(relative,str) and '\\' not in relative,'Expected canonical relative path: '+str(relative))
    path=Path(relative)
    require(not path.is_absolute() and '..' not in path.parts,'Unsafe relative path: '+relative)
    target=(root/path).resolve()
    require(target.is_relative_to(root.resolve()),'Path escaped project/archive: '+relative)
    return target

def allowed_content(relative):
    return relative.startswith('Content/MPRWarehouse/RebuildB50B57/') and Path(relative).suffix.lower() in guard.SUFFIXES or \
        Path(relative).with_suffix('').as_posix()=='Content/Maps/MPR_CAD_Warehouse_B50B57' and Path(relative).suffix.lower() in guard.SUFFIXES

def assert_old(root,old_files,old_ownership):
    changed=[name for name,h in old_files.items() if not inside(root,name).is_file() or sha(inside(root,name))!=h]
    require(not changed,'Original Content changed/missing: '+', '.join(changed[:10]))
    for name,h in old_ownership.items():
        require(inside(root,name).is_file() and sha(inside(root,name))==h,'Original ownership changed: '+name)

def ensure_project_closed(root):
    if os.name!='nt':raise guard.ERROR('Apply is supported only on the Windows project host')
    script="Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('UnrealEditor.exe','UnrealEditor-Cmd.exe') } | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
    run=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],
                       capture_output=True,text=True,check=True)
    processes=json.loads(run.stdout) if run.stdout.strip() else []
    if isinstance(processes,dict):processes=[processes]
    needles=[str(root.resolve()).replace('\\','/').lower(),*[p.name.lower() for p in root.glob('*.uproject')]]
    active=[p['ProcessId'] for p in processes if not p.get('CommandLine') or
            any(n in p['CommandLine'].replace('\\','/').lower() for n in needles)]
    require(not active,'Close project UE processes before moving package files; PID(s): '+str(active))

def prepare(root):
    ownership=read(inside(root,OWNERSHIP));imported=read(inside(root,OUT+'/import_report.json'))
    reloaded=read(inside(root,OUT+'/reload_report.json'))
    require(ownership['owner']==guard.TAG and ownership['map']==guard.MAP and ownership['namespace']==guard.DEST,
            'Ownership is not this independent rebuild')
    require(imported.get('success') is True and reloaded.get('success') is True,'Only a validated import/reload may be archived')
    require(imported['ownership_sha256']==sha(inside(root,OWNERSHIP)),'Ownership has changed since successful import')
    require(imported['map_sha256']==reloaded['map_sha256']==ownership['map_sha256'],'Import/reload map hashes disagree')
    old=read(inside(root,OUT+'/old_content_hashes.json'))
    old_ownership=read(inside(root,OUT+'/old_ownership_hashes.json'))
    require(sha(inside(root,OUT+'/old_content_hashes.json'))==ownership['old_content_hashes_sha256'],'Original package audit changed')
    require(sha(inside(root,OUT+'/old_ownership_hashes.json'))==ownership['old_ownership_hashes_sha256'],'Original ownership audit changed')
    assert_old(root,old,old_ownership)
    new=ownership['new_files']
    require(new and all(allowed_content(p) for p in new),'Ownership includes files outside new namespace/map')
    require(not set(new)&set(old),'Archive would include an original Content file')
    require('Content/Maps/MPR_CAD_Warehouse_B50B57.umap' in new,'New map missing from ownership')
    require(guard.assert_old_files(root,old)==new,'New asset set/hash differs from the validated ownership')
    checks={'source_snapshot.json':'source_snapshot_sha256','after_import.json':'after_import_sha256',
            'imported_manifest.json':'source_manifest_sha256'}
    for filename,key in checks.items():require(sha(inside(root,OUT+'/'+filename))==ownership[key],'Audit changed: '+filename)
    require(sha(inside(root,OUT+'/source_map_backup.umap'))==ownership['source_map_sha256'],'Original-map backup changed')
    require(sha(inside(root,SOURCE+'/protection_plan.json'))==ownership['protection_plan_sha256'],'Retention plan changed')
    files=dict(new)
    for name in [OWNERSHIP,*[OUT+'/'+s for s in AUDITS]]:
        path=inside(root,name);require(path.is_file(),'Missing successful audit: '+name);files[name]=sha(path)
    for suffix in OPTIONAL_AUDITS:
        name=OUT+'/'+suffix
        if inside(root,name).is_file():files[name]=sha(inside(root,name))
    # The imported manifest is the immutable historical source record. The
    # builder may already be replacing the current source manifest/FBXs.
    backups={SOURCE+'/protection_plan.json':ownership['protection_plan_sha256']}
    return dict(schema_version=1,operation='archive_mpr_rebuild_attempt',status='prepared',
        map=guard.MAP,namespace=guard.DEST,map_sha256=ownership['map_sha256'],
        source_manifest_sha256=ownership['source_manifest_sha256'],
        new_content_files=new,files=files,copy_only=backups,
        original_content_hashes=old,original_ownership_hashes=old_ownership,
        moved=[],created_utc=datetime.now(timezone.utc).isoformat())

def validate_move_scope(plan):
    allowed_metadata={OWNERSHIP,*[OUT+'/'+n for n in AUDITS+OPTIONAL_AUDITS]}
    require(plan.get('operation')=='archive_mpr_rebuild_attempt' and plan.get('map')==guard.MAP and
            plan.get('namespace')==guard.DEST,'Invalid archive identity')
    for name in plan['files']:
        require(allowed_content(name) or name in allowed_metadata,'Archive manifest includes an unauthorized file: '+name)
        require(name not in plan['original_content_hashes'],'Original Content file cannot be moved: '+name)
    require(set(plan['new_content_files'])=={p for p in plan['files'] if p.startswith('Content/')},'Content move set mismatch')

def archive(root,plan):
    validate_move_scope(plan);ensure_project_closed(root)
    folder=inside(root,ARCHIVES+'/'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-'+plan['map_sha256'][:12])
    require(not folder.exists(),'Archive destination already exists')
    folder.mkdir(parents=True);journal=folder/'archive_manifest.json'
    plan['archive_path']=str(folder);write(journal,plan)
    try:
        for name,h in plan['copy_only'].items():
            source=inside(root,name);target=inside(folder,name)
            require(sha(source)==h,'Copy-only audit changed: '+name)
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
            require(sha(target)==h,'Audit backup hash mismatch: '+name)
        # Every source was validated before the first move; recheck each file
        # immediately before its exact rename. No directories are removed.
        for name,h in plan['files'].items():
            source=inside(root,name);target=inside(folder,name)
            require(sha(source)==h and not target.exists(),'Changed source/existing archive destination: '+name)
            target.parent.mkdir(parents=True,exist_ok=True);source.replace(target)
            plan['moved'].append(name)
            require(sha(target)==h,'Archived file hash mismatch: '+name)
            write(journal,plan)
        assert_old(root,plan['original_content_hashes'],plan['original_ownership_hashes'])
        require(all(not inside(root,p).exists() for p in plan['files']),'An archived source remains in place')
        plan['status']='archived';write(journal,plan)
    except Exception as exc:
        plan['error']=repr(exc);failures=[]
        for name in reversed(plan['moved']):
            try:
                target=inside(root,name);source=inside(folder,name)
                require(not target.exists(),'Cannot rollback over a newly created file: '+name)
                require(sha(source)==plan['files'][name],'Cannot rollback a changed archive: '+name)
                target.parent.mkdir(parents=True,exist_ok=True);source.replace(target)
            except Exception as problem:failures.append(name+': '+repr(problem))
        plan['status']='rollback_incomplete' if failures else 'rolled_back';plan['rollback_errors']=failures;write(journal,plan)
        raise
    return folder

def restore(root,folder,apply=False):
    folder=Path(folder).resolve()
    require(folder.is_relative_to(inside(root,ARCHIVES)),'Restore path is outside rebuild archives')
    plan=read(folder/'archive_manifest.json');validate_move_scope(plan)
    require(plan['status']=='archived','Archive is not in a restorable state')
    assert_old(root,plan['original_content_hashes'],plan['original_ownership_hashes'])
    require(not guard.assert_old_files(root,plan['original_content_hashes']),
            'Restore requires an empty rebuild namespace/map; a newer attempt already exists')
    for name,h in plan['files'].items():
        require(not inside(root,name).exists(),'Restore refuses to overwrite any current file: '+name)
        require(inside(folder,name).is_file() and sha(inside(folder,name))==h,'Archived file changed/missing: '+name)
    if not apply:return plan
    ensure_project_closed(root);restored=[]
    try:
        for name in plan['files']:
            source=inside(folder,name);target=inside(root,name);target.parent.mkdir(parents=True,exist_ok=True)
            source.replace(target);restored.append(name)
        assert_old(root,plan['original_content_hashes'],plan['original_ownership_hashes'])
        for name,h in plan['files'].items():require(sha(inside(root,name))==h,'Restored file differs: '+name)
        plan['status']='restored';write(folder/'archive_manifest.json',plan)
    except Exception:
        for name in reversed(restored):
            target=inside(folder,name);require(not target.exists(),'Restore rollback destination exists: '+name)
            inside(root,name).replace(target)
        raise
    return plan

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true');parser.add_argument('--restore',type=Path)
    args=parser.parse_args()
    if args.restore:
        plan=restore(ROOT,args.restore,args.apply);folder=args.restore
    else:
        plan=prepare(ROOT);folder=archive(ROOT,plan) if args.apply else None
    print(json.dumps(dict(success=True,applied=args.apply,operation='restore' if args.restore else 'archive',
        archive=str(folder) if folder else None,new_content_files=len(plan['new_content_files']),
        total_move_files=len(plan['files']),original_content_files_verified=len(plan['original_content_hashes']),
        map_sha256=plan['map_sha256']),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
