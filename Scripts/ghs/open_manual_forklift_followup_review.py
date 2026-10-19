"""Verify the saved follow-up and reopen an editable review view."""
import sys
from pathlib import Path
import unreal
sys.path.insert(0,'D:/UEPro/Test/Scripts/ghs')
import import_manned_forklift_fleet as f
u=f.util;root=Path('D:/UEPro/Test')
persist=u.read(root/'Saved/GHS_ManualForkliftIdentityPersisted.json')
changes=u.read(root/'Saved/GHS_ManualForkliftFollowup.json')
assert persist['success'] and changes['success']
assert f.E.get_editor_world().get_path_name().split('.')[0]==f.MAP
assert u.sha(root/f.MAP_FILE)==persist['map_sha256']
by=u.labels();now=f.snapshot(by);before=u.read(Path(changes['backup_root'])/'live_after.json')
assert len(by)==248 and set(now)==set(before)
for label,state in before.items():
    old=dict(state);new=dict(now[label]);a=by[label]
    if a.actor_has_tag('NormalWarehouseMannedForklift') or isinstance(a,unreal.WorldSettings):
        tags=new['tags'];new['tags']=[t for t in tags if not t.startswith(('GHSManualIdentityOwner=','GHSManualIdentityHighWater='))]
    assert old==new,('Unexpected saved change',label)
assert unreal.GHSMannedForkliftIdentityLibrary.reconcile_world(f.E.get_editor_world())==0
fleet=[a for a in by.values() if a.actor_has_tag('NormalWarehouseMannedForklift')]
assert len(fleet)==16
for a in fleet:
    assert a.get_attach_parent_actor() is None
    assert f.xyz(a.get_actor_scale3d())==[1.,1.,1.]
target=by['GHN_MannedForklift_9'];p=target.get_actor_location()
eye=unreal.Vector(p.x+850,p.y+650,650)
f.A.set_selected_level_actors([])
f.E.set_level_viewport_camera_info(eye,unreal.MathLibrary.find_look_at_rotation(eye,unreal.Vector(p.x,p.y,125)))
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
u.write(root/'Saved/GHS_ManualForkliftFollowup_FinalEditor.json',dict(success=True,manual_count=16,
    actor_count=248,map=f.MAP,map_sha256=persist['map_sha256'],all_saved_placements_preserved=True,
    independent_static_meshes=True,current_module_loaded=True))
unreal.log('MANUAL_FOLLOWUP_FINAL_EDITOR_VERIFIED')
