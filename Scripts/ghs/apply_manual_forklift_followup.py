"""Preserve user placements, repair duplicated IDs, and add four checked vehicles."""
import sys,shutil,traceback
from datetime import datetime
from pathlib import Path
import unreal
ROOT=Path('D:/UEPro/Test');sys.path.insert(0,str(ROOT/'Scripts/ghs'))
import import_manned_forklift_fleet as f
u=f.util;u.LABEL='__no_vehicle_exclusion__'
REPORT=ROOT/'Saved/GHS_ManualForkliftFollowup.json'
PLAN=ROOT/'Saved/GHS_ManualForkliftAdditionsPlan.json'
PROBE=ROOT/'Saved/GHS_ManualFollowupProbe.json'
BASELINE=ROOT/'Saved/GHS_ManualFollowupBaseline.json'

def run():
    assert not REPORT.exists(),'Inspect existing follow-up report before retry'
    assert f.E.get_editor_world().get_path_name().split('.')[0]==f.MAP and not f.E.get_game_world()
    assert not unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
    by=u.labels();before=f.snapshot(by);assert before==u.read(BASELINE),'Scene changed since probe'
    plan=u.read(PLAN);assert plan['success'] and len(plan['placements'])==4
    assert plan['source_probe_sha256']==u.sha(PROBE)
    mesh=f.LIB.load_asset(f.MESH_PATH);assert mesh
    checked=f.check_placements(by,mesh,plan)
    copies=['GHN_MannedForklift_9','GHN_MannedForklift_8','GHN_MannedForklift_10','GHN_MannedForklift_11']
    assert all(n in by for n in copies)
    for n in range(1,9):
        assert 'TwinId=GHN_MannedForklift_%02d'%n in [str(t) for t in by['GHN_MannedForklift_%02d'%n].tags]
    backup=ROOT/'Saved/Backups'/('GHS_ManualFollowup_'+datetime.now().strftime('%Y%m%d_%H%M%S'));backup.mkdir(parents=True)
    hashes=u.content_hashes();u.write(backup/'content_before.json',hashes);u.write(backup/'live_before.json',before)
    shutil.copy2(ROOT/f.MAP_FILE,backup/'disk_before.umap')
    assert f.L.save_current_level();shutil.copy2(ROOT/f.MAP_FILE,backup/'user_live_before.umap')
    r=dict(success=False,backup_root=str(backup),baseline_path=str(BASELINE),actor_count_before=len(by),repaired=[],added=[],geometry=checked)
    u.write(REPORT,r)
    with unreal.ScopedEditorTransaction('Repair copied manual forklift HUD IDs and add four vehicles'):
        for number,label in enumerate(copies,9):
            a=by[label];old=[str(t) for t in a.tags]
            assert a.static_mesh_component.static_mesh==mesh
            new=[t for t in old if not t.startswith('TwinId=')]+['TwinId=GHN_MannedForklift_%02d'%number]
            a.tags=[unreal.Name(t) for t in new]
            r['repaired'].append(dict(label=label,old_tags=old,new_tags=new,position_cm=f.xyz(a.get_actor_location())))
        for number,row in enumerate(plan['placements'],13):
            label='GHN_MannedForklift_%02d'%number;assert label not in by
            a=f.A.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector(*row['position_cm']),unreal.Rotator(yaw=row['yaw_deg']))
            assert a;a.set_actor_label(label);a.set_folder_path('GHS_Normal/Vehicles/MannedForklifts')
            a.tags=[unreal.Name(t) for t in ['NormalWarehouseMannedForklift','TwinId='+label,'FloorStorageWork','ModelScale=1to1']]
            c=a.static_mesh_component;c.set_static_mesh(mesh);c.set_mobility(unreal.ComponentMobility.MOVABLE)
            c.set_collision_profile_name('NoCollision');c.set_editor_property('receives_decals',False);c.set_editor_property('cast_shadow',True)
            r['added'].append(dict(label=label,position_cm=row['position_cm'],yaw_deg=row['yaw_deg']))
    after=u.labels();snap=f.snapshot(after);assert len(after)==len(before)+4
    for label,state in before.items():
        actual=dict(snap[label]);expected=dict(state)
        if label in copies:actual.pop('tags');expected.pop('tags')
        assert actual==expected,('Existing object changed',label)
    fleet=[a for a in after.values() if a.actor_has_tag('NormalWarehouseMannedForklift')]
    ids=[str(t) for a in fleet for t in a.tags if str(t).startswith('TwinId=')]
    assert len(fleet)==len(ids)==len(set(ids))==16
    assert f.L.save_current_level()
    newhash=u.content_hashes();changed=[p for p,h in hashes.items() if newhash[p]!=h];assert changed==[f.MAP_FILE]
    assert set(newhash)==set(hashes)
    u.write(backup/'live_after.json',snap);shutil.copy2(ROOT/f.MAP_FILE,backup/'repaired_and_expanded.umap')
    r.update(success=True,actor_count_after=len(after),manual_count=16,all_existing_transforms_preserved=True,
        only_four_existing_tags_changed=True,changed_content=changed,map_sha256=u.sha(ROOT/f.MAP_FILE))
    u.write(REPORT,r)
    unreal.log('MANUAL_FOLLOWUP_SAVED 4 repaired + 4 added = 16 independent forklifts')
    unreal.SystemLibrary.quit_editor()

if __name__=='__main__':run()
