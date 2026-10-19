"""Save the current authorized scene, verify the new fleet, then restart for native code."""
import sys,shutil
sys.path.insert(0,'D:/UEPro/Test/Scripts/ghs')
import import_manned_forklift_fleet as f
import unreal
r=f.util.read(f.REPORT)
assert r['success'] and f.E.get_editor_world().get_path_name().split('.')[0]==f.MAP and not f.E.get_game_world()
by=f.util.labels();fleet=[a for a in by.values() if a.actor_has_tag('NormalWarehouseMannedForklift')]
assert len(fleet)==8
assert not unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
p=by['GHN_MannedForklift_02'].get_actor_location()
eye=unreal.Vector(p.x+800,p.y-850,650)
f.E.set_level_viewport_camera_info(eye,unreal.MathLibrary.find_look_at_rotation(eye,unreal.Vector(p.x,p.y,120)))
assert f.L.save_current_level()
backup=f.Path(r['backup_root'])
shutil.copy2(f.ROOT/f.MAP_FILE,backup/'GHS_CAD_NormalWarehouse.final_before_build.umap')
snap=f.snapshot(by)
f.util.write(backup/'final_before_build.json',snap)
f.util.write(f.ROOT/'Saved/GHS_MannedForkliftBuildPrepared.json',dict(saved=True,actor_count=len(by),
    manual_count=len(fleet),stacker_count=sum(a.actor_has_tag('NormalWarehouseFloorStacker') for a in by.values()),
    map_sha256=f.util.sha(f.ROOT/f.MAP_FILE),dirty_maps=[p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()]))
unreal.SystemLibrary.quit_editor()
