"""Fixed-camera MPR exposure comparison in an owned native game; no asset saves."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib,json,re,sys,time,traceback
import unreal as u

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).parent))
import profile_mpr_runtime as timing
CLI=u.SystemLibrary.get_command_line()
assert all(re.search(r'(?:^|\s)-'+f+r'(?=\s|$)',CLI,re.I) for f in ('own','game','RenderOffscreen'))
FINAL=bool(re.search(r'(?:^|\s)-MPRExposureVerify(?=\s|$)',CLI,re.I))
OUT=ROOT/'Saved/MPR/exposure_20261106'/('final' if FINAL else 'comparison')
OUT.mkdir(parents=True,exist_ok=True)
MAP='/Game/Maps/MPR_CAD_Warehouse_B50B57'
MAP_FILE=ROOT/'Content/Maps/MPR_CAD_Warehouse_B50B57.umap'
STAMP=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
report=dict(success=False,run_id=STAMP,captures=[],assets_saved=False,map_before=hashlib.sha256(MAP_FILE.read_bytes()).hexdigest())
world=pc=pawn=roof=post=handle=None
original=None
done=busy=False
started=time.monotonic()
def write():(OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def console(value):u.SystemLibrary.execute_console_command(world,value,pc)
def pose():
 m=pc.player_camera_manager;p=m.get_camera_location();r=m.get_camera_rotation()
 return [p.x,p.y,p.z,r.pitch,r.yaw,r.roll]
def pause(seconds):
 until=time.monotonic()+seconds
 while time.monotonic()<until:yield
def wait(name,predicate,seconds=40):
 report['stage']=name;write();end=time.monotonic()+seconds
 while not predicate():
  assert time.monotonic()<end,name
  yield
def discover():
 global world,pc,pawn,roof,post,original
 for w in u.ObjectIterator(u.World):
  if not w.get_path_name().startswith(MAP+'.'):continue
  c=u.GameplayStatics.get_player_controller(w,0)
  if not c or not c.get_editor_property('twin_hud_widget'):continue
  world,pc,pawn,roof=w,c,c.get_controlled_pawn(),c.warehouse_roof
  matches=[a for a in u.GameplayStatics.get_all_actors_of_class(w,u.PostProcessVolume) if a.get_actor_label()=='MPR4_ReferenceStyle']
  assert len(matches)==1
  post=matches[0];original=post.get_editor_property('settings')
  return roof.has_roof()
 return False
def capture(name,ev):
 path=OUT/(name+'_'+STAMP+'.png')
 console('Shot showui filename="'+path.as_posix()+'" -nosuffix')
 yield from wait(name,lambda:timing.png_ready(path))
 report['captures'].append(dict(name=name,ev100=ev,camera=pose(),path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
 write()
def run():
 yield from wait('discover',discover)
 for cmd in ('DisableAllScreenMessages','t.MaxFPS 0','r.VSync 0','t.IdleWhenNotForeground 0','Slate.bAllowThrottling 0','csv.CompressionMode 0','r.GPUCsvStatsEnabled 1'):
  console(cmd)
 report['before_settings']={k:str(original.get_editor_property(k)) for k in ('auto_exposure_method','auto_exposure_min_brightness','auto_exposure_max_brightness','auto_exposure_bias','bloom_intensity')}
 report['lights']=[dict(label=a.get_actor_label(),intensity=a.get_component_by_class(u.LightComponentBase).get_editor_property('intensity')) for a in u.GameplayStatics.get_all_actors_of_class(world,u.Light)]
 baseline=original.get_editor_property('auto_exposure_min_brightness')
 assert abs(original.get_editor_property('auto_exposure_max_brightness')-baseline)<1e-6
 if FINAL:assert abs(baseline-.6)<1e-5
 else:assert abs(baseline+.1)<1e-5
 yield from pause(8)
 for title,ev in ([('final',baseline)] if FINAL else [('before',baseline),('ev035',.35),('ev060',.6)]):
  s=post.get_editor_property('settings')
  s.set_editor_property('auto_exposure_min_brightness',ev);s.set_editor_property('auto_exposure_max_brightness',ev)
  post.set_editor_property('settings',s)
  roof.restore_roof(False);pc.get_editor_property('twin_hud_widget').command('{"action":"overview"}')
  yield from wait('overview',lambda:not pawn.is_pose_transition_active())
  yield from pause(3)
  yield from capture(title+'_exterior',ev)
  assert roof.open_roof()
  yield from wait('open_roof',roof.is_interior_available)
  yield from pause(3)
  yield from capture(title+'_open_overview',ev)
  pawn.focus_on_target(u.Vector(1000,0,400),23000,u.Rotator(pitch=-52,yaw=-90),u.Vector2D(1920,1080),u.Vector2D(960,540),0)
  yield from pause(3)
  yield from capture(title+'_interior',ev)
 if FINAL:
  pawn.focus_on_target(u.Vector(-11200,1000,180),14000,u.Rotator(pitch=-50,yaw=-80),u.Vector2D(1920,1080),u.Vector2D(960,540),0)
  yield from pause(3)
  yield from capture('final_sorter_detail',baseline)
  yield from pause(8)
  filename='MPR_EXPOSURE_'+STAMP+'.csv';path=ROOT/'Saved/Profiling/CSV'/filename
  console('CsvProfile STARTFILE='+filename);console('CsvProfile START')
  yield from pause(15);console('CsvProfile STOP')
  yield from wait('native_csv',lambda:timing.csv_complete(path))
  report['performance']=timing.parse_csv(path)
  report['performance']['fps']=report['performance']['frame_count']/report['performance']['native_frame_time_seconds']
 report.update(success=True,stage='complete')
def finish(error=None):
 global done
 done=True
 if error:report.update(success=False,error=error)
 if post and original:post.set_editor_property('settings',original)
 if roof:roof.restore_roof(False)
 report['map_unchanged']=hashlib.sha256(MAP_FILE.read_bytes()).hexdigest()==report['map_before']
 report['success']=report['success'] and report['map_unchanged']
 write()
 if handle is not None:u.unregister_slate_post_tick_callback(handle)
 if world:console('CsvProfile STOP');u.SystemLibrary.quit_game(world,pc,u.QuitPreference.QUIT,False)
steps=run()
def tick(delta):
 global busy
 if done or busy:return
 busy=True
 try:
  assert time.monotonic()-started<180,'capture timeout'
  next(steps)
 except StopIteration:finish()
 except Exception:finish(traceback.format_exc())
 finally:busy=False
handle=u.register_slate_post_tick_callback(tick)
