"""Change only the MPR volume's two fixed exposure limits, with a scene audit."""
from pathlib import Path
from copy import deepcopy
import gzip,hashlib,json,re,shutil,sys
import unreal as u

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).parent))
import rebuild_preservation as guard
import mpr_scene_patch_guard as patch
MAP='/Game/Maps/MPR_CAD_Warehouse_B50B57'
MAP_FILE=ROOT/'Content/Maps/MPR_CAD_Warehouse_B50B57.umap'
OUT=ROOT/'Saved/MPR/exposure_20261106'
TARGET=.6

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run():
 assert '-run=pythonscript' in u.SystemLibrary.get_command_line().lower(),'Owned commandlet only'
 verify='-mprexposurereload' in u.SystemLibrary.get_command_line().lower()
 assert not u.EditorLoadingAndSavingUtils.get_dirty_map_packages()
 assert not u.EditorLoadingAndSavingUtils.get_dirty_content_packages()
 world=u.EditorLoadingAndSavingUtils.load_map(MAP)
 assert world and world.get_path_name().split('.')[0]==MAP
 current=guard.capture(u,ROOT,MAP)
 guard.assert_clean(current)
 actors=u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors()
 matches=[a for a in actors if isinstance(a,u.PostProcessVolume) and a.get_actor_label()=='MPR4_ReferenceStyle']
 assert len(matches)==1
 volume=matches[0];settings=volume.get_editor_property('settings')
 guid=u.GuidLibrary.conv_guid_to_string(volume.get_editor_property('actor_guid'))
 if verify:
  expected=patch.read(OUT/'after.json.gz')
  assert [guard.canonical_actor(a) for a in current['actors']]==[guard.canonical_actor(a) for a in expected['actors']]
  assert current['world_settings']==expected['world_settings']
  assert guard.canonical_coverage(current['world_actor_coverage'])==guard.canonical_coverage(expected['world_actor_coverage'])
  assert abs(settings.get_editor_property('auto_exposure_min_brightness')-TARGET)<1e-5
  assert abs(settings.get_editor_property('auto_exposure_max_brightness')-TARGET)<1e-5
  patch.write(OUT/'reload_validation.json',dict(success=True,actor_count=len(actors),fixed_ev100=TARGET,map_sha256=sha(MAP_FILE)))
  return
 assert abs(settings.get_editor_property('auto_exposure_min_brightness')+.1)<1e-5
 assert abs(settings.get_editor_property('auto_exposure_max_brightness')+.1)<1e-5
 patch.write(OUT/'before.json.gz',current)
 shutil.copy2(MAP_FILE,OUT/'before_MPR.umap')
 # Scope the disk guard to MPR/GHS sources, excluding the parallel globe task.
 packages=list((ROOT/'Content/MPRWarehouse').rglob('*.uasset'))+list((ROOT/'Content/GHSZcoolSmartFactory').rglob('*.uasset'))
 package_hashes={p.as_posix():sha(p) for p in packages}
 old_text=settings.export_text()
 settings.set_editor_property('auto_exposure_min_brightness',TARGET)
 settings.set_editor_property('auto_exposure_max_brightness',TARGET)
 new_text=settings.export_text()
 replace=lambda text:re.sub(r'(AutoExposure(?:Min|Max)Brightness=)[^,)]+',r'\1EXPOSURE_LIMIT',text)
 assert old_text!=new_text and replace(old_text)==replace(new_text),'Unexpected post-process changes'
 volume.modify();volume.set_editor_property('settings',settings)
 after=guard.capture(u,ROOT,MAP)
 expected=deepcopy(current)
 expected_row=next(r for r in expected['actors'] if r['guid']==guid)
 actual_row=next(r for r in after['actors'] if r['guid']==guid)
 assert actual_row['render_settings']['settings']==new_text
 expected_row['render_settings']['settings']=new_text
 assert expected['actors']==after['actors'],'Unrelated actor, mesh, camera, material or lighting change'
 assert expected['world_settings']==after['world_settings']
 assert guard.canonical_coverage(expected['world_actor_coverage'])==guard.canonical_coverage(after['world_actor_coverage'])
 assert sha(MAP_FILE)==current['map_file_sha256'],'Map changed concurrently'
 assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level()
 saved=guard.capture(u,ROOT,MAP);guard.assert_clean(saved)
 assert saved['actors']==after['actors']
 assert all(sha(Path(p))==digest for p,digest in package_hashes.items())
 patch.write(OUT/'after.json.gz',saved)
 patch.write(OUT/'apply_validation.json',dict(success=True,actor_count=len(actors),volume=volume.get_path_name(),
  changed_fields=['AutoExposureMinBrightness','AutoExposureMaxBrightness'],before_ev100=-.1,after_ev100=TARGET,
  exposure_reduction_stops=.7,map_before=current['map_file_sha256'],map_after=sha(MAP_FILE),
  preserved_asset_count=len(package_hashes),geometry_materials_cameras_lights_preserved=True))
run()
