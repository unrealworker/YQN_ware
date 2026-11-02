"""Eight actual game-view captures, with temporal history; no asset saves.

Run in an isolated -game -RenderOffscreen process at 1920x1080.
This complements the independent editor transform/preservation audit.
"""
from pathlib import Path
import sys,json,time,hashlib,struct,traceback
import unreal as u
ROOT=Path(u.Paths.convert_relative_path_to_full(u.Paths.project_dir())).resolve()
sys.path.insert(0,str(Path(__file__).parent))
import profile_mpr_runtime as base
from validate_mpr_reference_exterior import VIEWS
OUT=ROOT/'Saved/MPR/reference_v4/runtime_views';OUT.mkdir(parents=True,exist_ok=True)
start=time.monotonic();ready=None;index=0;pending=None;done=False;handle=None
report=dict(success=False,renderer='Actual UE game viewport with temporal warmup',captures=[],map_sha256=hashlib.sha256(base.MAP_FILE.read_bytes()).hexdigest(),assets_saved=False)

def finish(error=None):
 global done
 done=True;u.unregister_slate_post_tick_callback(handle)
 report.update(success=error is None,error=error,map_unchanged=hashlib.sha256(base.MAP_FILE.read_bytes()).hexdigest()==report['map_sha256'])
 if not report['map_unchanged']:report['success']=False
 (OUT/'capture_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
 base.console('quit')

def set_view():
 global ready
 name,xyz,distance,pitch,yaw,hidden=VIEWS[index]
 for a in base.roofs:a.set_actor_hidden_in_game(hidden)
 rot=u.Rotator(pitch=pitch,yaw=yaw);target=u.Vector(xyz[0]*100,-xyz[1]*100,xyz[2]*100)
 base.camera.set_actor_location_and_rotation(target-u.MathLibrary.get_forward_vector(rot)*distance,rot,False,True)
 base.pc.set_view_target_with_blend(base.camera,0);ready=time.monotonic()

def tick(dt):
 global ready,index,pending
 if done:return
 try:
  assert time.monotonic()-start<120,'Runtime view capture deadline'
  if ready is None:
   if not base.discover():return
   assert list(base.pc.get_viewport_size())==[1920,1080]
   c=base.camera.get_component_by_class(u.CameraComponent);c.set_editor_property('constrain_aspect_ratio',False)
   c.set_editor_property('override_aspect_ratio_axis_constraint',True);c.set_editor_property('aspect_ratio_axis_constraint',u.AspectRatioAxisConstraint.ASPECT_RATIO_MAINTAIN_XFOV)
   base.pawn.cancel_pose_transition();base.pawn.freeze_current_pose()
   base.console('r.ScreenPercentage 100');base.console('r.SetNearClipPlane 100');base.console('DisableAllScreenMessages')
   set_view();return
  if pending:
   if not pending.exists() or pending.stat().st_size<10000:return
   data=pending.read_bytes()
   if data[-12:]!=b'\x00\x00\x00\x00IEND\xaeB\x60\x82':return
   assert data[:8]==b'\x89PNG\r\n\x1a\n' and struct.unpack('>II',data[16:24])==(1920,1080)
   report['captures'].append(dict(name=VIEWS[index][0],path=str(pending),sha256=hashlib.sha256(data).hexdigest(),camera=base.view(),roof_hidden=VIEWS[index][-1]))
   pending=None;index+=1
   if index==len(VIEWS):finish();return
   set_view()
  elif time.monotonic()-ready>(12 if index==0 else 3):
   pending=OUT/(VIEWS[index][0]+'_'+str(time.time_ns())+'.png')
   base.console('Shot filename="'+pending.as_posix()+'" -nosuffix')
 except Exception:finish(traceback.format_exc())

handle=u.register_slate_post_tick_callback(tick)
