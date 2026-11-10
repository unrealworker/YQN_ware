"""Owned game-only GHS driver acceptance; no asset/map saves."""
from pathlib import Path
exec(Path(__file__).resolve().with_name('verify_order_replay_runtime.py').read_text(encoding='utf8').split('steps=run()')[0])
OUT=ROOT/'Saved/MannyForklift/runtime';OUT.mkdir(parents=True,exist_ok=True)
report=dict(success=False,checks=[],captures=[],states={})
cam=None
def view(transform,offset):
 global cam
 target=unreal.MathLibrary.transform_location(transform,unreal.Vector(-30,0,125));loc=unreal.MathLibrary.transform_location(transform,unreal.Vector(*offset));rot=unreal.MathLibrary.find_look_at_rotation(loc,target)
 pawn.cancel_pose_transition();pawn.set_replay_follow_enabled(False)
 pawn.get_component_by_class(unreal.CameraComponent).set_field_of_view(42)
 pawn.focus_on_target(target,(loc-target).length(),rot,unreal.Vector2D(1400,1000),unreal.Vector2D(700,500),0)
 pawn.freeze_current_pose()
def native_shot(name):
 path=OUT/(name+'.png');stamp=path.stat().st_mtime_ns if path.exists() else 0;unreal.SystemLibrary.execute_console_command(world,'Shot filename="'+path.as_posix()+'" -nosuffix',pc)
 yield from wait(name,lambda:path.exists() and path.stat().st_mtime_ns!=stamp);report['captures'].append(str(path));write()
def verify_mesh(c):
 m=c.static_mesh;names=[s.material_interface.get_name()for s in m.static_materials]
 for name in ['MI_Manny_01_New','MI_Manny_02_New']:
  idx=names.index(name);assert c.get_material(idx).get_name()==name,(c.get_name(),idx)
 assert m.get_num_lods()==4
 return m.get_path_name()
def run():
 yield from wait('discover',discover,120);yield from wait('initial camera',lambda:not pawn.is_pose_transition_active())
 unreal.SystemLibrary.execute_console_command(world,'DisableAllScreenMessages',pc)
 allactors=unreal.GameplayStatics.get_all_actors_of_class(world,unreal.Actor)
 fleet=[]
 for a in allactors:
  for c in a.get_components_by_class(unreal.StaticMeshComponent):
   if c.static_mesh and c.static_mesh.get_name()=='SM_GHN_MannedForklift50k':verify_mesh(c);fleet.append((a,c))
 assert len(fleet)==16,len(fleet)
 a,c=fleet[0];view(a.get_actor_transform(),(270,430,260));yield from pause(5);yield from native_shot('01-fleet-driver')
 view(a.get_actor_transform(),(240,-270,240));yield from pause(2);yield from native_shot('02-fleet-driver-opposite-side')
 record('all_16_fleet_manny_materials_and_lods',count=len(fleet))
 command('navigate',page='trace');hud.navigate('trace');command('replayStart',orderId='TEST-OUT-001',startUtc='2026-11-10T12:00:00.000Z',endUtc='2026-11-10T13:00:00.000Z')
 yield from wait('replay prepared',lambda:state()['active'] and not state()['preparing']);command('replayPause');command('replaySeek',time=230);yield from pause(1)
 replay=next(a for a in unreal.GameplayStatics.get_all_actors_of_class(world,unreal.Actor)if a.get_class().get_name()=='GHSOrderReplayActor')
 bodies=[c for c in replay.get_components_by_class(unreal.StaticMeshComponent)if c.static_mesh and c.static_mesh.get_name()=='SM_Replay_ForkliftBody']
 assert len(bodies)==5,len(bodies)
 for c in bodies:verify_mesh(c)
 c=bodies[0];view(c.get_world_transform(),(280,420,250));yield from pause(3);yield from native_shot('03-replay-driver-loaded')
 record('replay_5_manny_drivers',count=len(bodies),active=state()['active'])
 command('replayEndRequest');command('replayExitConfirm');yield from pause(1);assert not state()['active'];assert json.loads(session.get_restoration_report())['verified'];assert hashlib.sha256(MAP.read_bytes()).hexdigest()==map_hash;record('map_unchanged_and_replay_restored')
steps=run()
def tick(delta):
 try:
  assert time.monotonic()-started<200,'Timeout';next(steps)
 except StopIteration:finish()
 except Exception:finish(traceback.format_exc())
write();handle=unreal.register_slate_post_tick_callback(tick)
