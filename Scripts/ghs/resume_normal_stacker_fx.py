"""Validate the already-created live effects and save only the Normal map."""
import sys,traceback
from pathlib import Path
sys.path.insert(0,r'D:\UEPro\Test\Scripts\ghs')
import add_normal_stacker_fx as f
assert f.E.get_editor_world().get_path_name().split('.')[0]==f.MAP
report=f.read(f.REPORT);assert not report['success']
backup=Path(report['backup_root'])
old=f.read(backup/'content_hashes.json');assert f.content()==old,'Disk content changed since the checkpoint'
before=f.read(backup/'live_before.json');rows=report['effects']
f.shutil.copy2(f.REPORT,backup/'first_attempt_report.json')
try:
 materials=f.validate(before,rows,f.labels())
 assert f.L.save_current_level()
 now=f.content();assert set(now)==set(old)
 changed=[p for p,h in old.items() if now[p]!=h];assert changed==[f.FILE],changed
 for p,h in f.read(backup/'history_hashes.json').items():assert f.sha(f.ROOT/p)==h,p
 report.pop('error',None)
 report.update(success=True,effect_count=24,actor_count=len(f.labels()),materials=materials,
  changed_content=changed,map_sha256=f.sha(f.ROOT/f.FILE),new_material_assets=0,new_lights=0,effect_meshes=0,
  projection_depth_cm=1,projection_z_range_cm=[-.25,.75],unchanged_original_objects=True,
  direction_validation='World basis vectors; Euler angles are ambiguous at pitch -90')
 f.unreal.log('GHS_NORMAL_STACKER_FX_SAVED: 24 green animated decals, verified world axes and saved Normal only')
except Exception:
 report['error']=traceback.format_exc();raise
finally:f.write(f.REPORT,report)
