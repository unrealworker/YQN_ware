"""Persist reconciled forklift ownership after the native module rebuild."""
import sys, json, shutil
from pathlib import Path
import unreal

ROOT=Path('D:/UEPro/Test');sys.path.insert(0,str(ROOT/'Scripts/ghs'))
import import_manned_forklift_fleet as f
u=f.util

def run():
    assert not f.E.get_game_world()
    assert f.L.load_level(f.MAP)
    world=f.E.get_editor_world();by=u.labels();before=f.snapshot(by)
    report=u.read(ROOT/'Saved/GHS_ManualForkliftFollowup.json');assert report['success']
    baseline=u.read(Path(report['backup_root'])/'live_after.json')
    assert before==baseline,'Saved scene changed after placement'
    changed=unreal.GHSMannedForkliftIdentityLibrary.reconcile_world(world)
    after=f.snapshot(u.labels());assert set(before)==set(after)
    fleet=[]
    for label,state in before.items():
        a=by[label];old=dict(state);new=dict(after[label])
        if a.actor_has_tag('NormalWarehouseMannedForklift'):
            fleet.append(a)
            old_tags=old.pop('tags');new_tags=new.pop('tags')
            assert [t for t in new_tags if not t.startswith('GHSManualIdentityOwner=')]==old_tags
            assert 'GHSManualIdentityOwner='+a.get_name() in new_tags
        elif isinstance(a,unreal.WorldSettings):
            old_tags=old.pop('tags');new_tags=new.pop('tags')
            assert [t for t in new_tags if not t.startswith('GHSManualIdentityHighWater=')]==old_tags
            assert 'GHSManualIdentityHighWater=16' in new_tags
        assert old==new,('Unexpected field change',label)
    assert len(fleet)==16 and changed==16
    assert unreal.GHSMannedForkliftIdentityLibrary.reconcile_world(world)==0
    assert f.L.save_current_level()
    assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
    ids=[str(t) for a in fleet for t in a.tags if str(t).startswith('TwinId=')]
    assert len(ids)==len(set(ids))==16
    out=dict(success=True,changed_identity_owners=changed,manual_count=16,actor_count=len(by),
        all_transforms_and_materials_preserved=True,map_sha256=u.sha(ROOT/f.MAP_FILE),ids=sorted(ids))
    u.write(ROOT/'Saved/GHS_ManualForkliftIdentityPersisted.json',out)
    shutil.copy2(ROOT/f.MAP_FILE,Path(report['backup_root'])/'identities_persisted.umap')
    unreal.log('MANUAL_IDENTITIES_PERSISTED 16 independent identities; no transform changes')

run()
