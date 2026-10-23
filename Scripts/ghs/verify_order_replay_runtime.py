"""Exercise the production replay in a disposable rendered game, never the editor world."""
import hashlib
import json
import math
import re
import statistics
import time
import traceback
from pathlib import Path
import unreal

ROOT=Path('D:/UEPro/Test');OUT=ROOT/'Saved/OrderReplay/Runtime';OUT.mkdir(parents=True,exist_ok=True)
CLI=unreal.SystemLibrary.get_command_line()
assert all(re.search(r'(?:^|\s)-'+flag+r'(?=\s|$)',CLI,re.I) for flag in ('game','RenderOffscreen','TwinDiagnostics'))
MAP=ROOT/'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'
map_hash=hashlib.sha256(MAP.read_bytes()).hexdigest()
world=pc=pawn=hud=session=handle=None
started=time.monotonic();stage='discover';report=dict(success=False,checks=[],captures=[],states={})
def write():
    report['stage']=stage;(OUT/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
def wait(name,predicate,timeout=60):
    global stage
    stage=name;write();end=time.monotonic()+timeout
    while not predicate():
        assert time.monotonic()<end,'Timeout: '+name
        yield
def pause(seconds):
    end=time.monotonic()+seconds
    while time.monotonic()<end:yield
def discover():
    global world,pc,pawn,hud,session
    for w in unreal.ObjectIterator(unreal.World):
        if not w.get_path_name().startswith('/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.'):continue
        c=unreal.GameplayStatics.get_player_controller(w,0);h=getattr(c,'twin_hud_widget',None) if c else None
        if h and h.browser_ready:
            world,pc,pawn,hud,session=w,c,c.get_controlled_pawn(),h,c.order_replay
            return session is not None
    return False
def command(action,**values):hud.command(json.dumps(dict(action=action,**values),ensure_ascii=False))
def state():return json.loads(hud.get_replay_state())
def record(name,**data):report['checks'].append(dict(name=name,passed=True,**data));write()
def capture(name):
    path=OUT/(name+'.png');stamp=path.stat().st_mtime_ns if path.exists() else 0
    unreal.SystemLibrary.execute_console_command(world,'Shot showui filename="'+path.as_posix()+'" -nosuffix',pc)
    yield from wait(name,lambda:path.exists() and path.stat().st_mtime_ns!=stamp)
    report['captures'].append(str(path));write()
def numeric(value, fields):return tuple(round(float(getattr(value,k)),6) for k in fields)
def snap_actor(a):
    t=a.get_actor_transform()
    return dict(name=a.get_name(),hidden=bool(a.get_editor_property('hidden')),tick=a.is_actor_tick_enabled(),
                transform=(numeric(t.translation,'xyz'),numeric(t.rotation,'xyzw'),numeric(t.scale3d,'xyz')),components=[dict(name=c.get_name(),tick=c.is_component_tick_enabled(),
                    mesh=c.static_mesh.get_path_name() if isinstance(c,unreal.StaticMeshComponent) and c.static_mesh else None)
                    for c in a.get_components_by_class(unreal.ActorComponent)])
def pose():return (numeric(pawn.get_actor_location(),'xyz'),numeric(pawn.get_actor_rotation(),('pitch','yaw','roll')),round(pawn.spring_arm_component.target_arm_length,6),numeric(pawn.spring_arm_component.socket_offset,'xyz'))
def run():
    yield from wait('discover',discover,100)
    yield from wait('initial camera',lambda:not pawn.is_pose_transition_active())
    data=json.loads((ROOT/'Content/GHSTwinUI/data/order-replay.json').read_text(encoding='utf8'))
    cycle=data['cycleDuration'];events=data['events'];assert len(data['tracks'])==18
    unreal.SystemLibrary.execute_console_command(world,'DisableAllScreenMessages',pc)
    originals=unreal.GameplayStatics.get_all_actors_of_class(world,unreal.Actor)
    tracked=[a for a in originals if any(str(t).startswith(('TwinId=GHN_MannedForklift','TwinId=GHS_DockTruck','TwinId=GHS_AGV_','TwinId=GHN_FloorStacker','TwinId=GHS_CH_')) for t in a.tags) or 'CampusTraffic' in a.get_class().get_name()]
    # Preserve an explicitly pre-hidden original, not just the default all-visible state.
    hidden=next(a for a in tracked if any(str(t).startswith('TwinId=GHN_MannedForklift') for t in a.tags));hidden.set_actor_hidden_in_game(True)
    # SceneData normally reapplies layer visibility; start in the same tick as this manual state.
    before={a.get_name():snap_actor(a) for a in tracked};camera_before=pose();roof_before=pc.warehouse_roof.get_transition_phase()
    command('navigate',page='trace');hud.navigate('trace')
    command('replayStart',orderId='TEST-OUT-001',startUtc='2026-10-23T12:00:00.000Z',endUtc='2026-10-23T13:00:00.000Z')
    assert state()['active'],state()
    yield from wait('roof open and scene prepared',lambda:not state()['preparing'])
    command('replayPause');yield from pause(.3)
    assert len(state()['devices'])==8
    assert all(a.get_editor_property('hidden') and not a.is_actor_tick_enabled() for a in tracked)
    assert pc.warehouse_roof.is_interior_available()
    record('isolated_eight_devices_and_open_roof',hidden_originals=len(tracked),sources=len(data['sourceInstances']))
    command('replaySeek',time=230);first=state();yield from pause(.6);second=state()
    assert first['time']==second['time']==230 and first['devices']==second['devices']
    command('replaySeek',time=900);command('replaySeek',time=230);assert state()['devices']==first['devices']
    record('paused_and_reverse_seek_deterministic')
    command('replayOverview');yield from wait('replay overview',lambda:not pawn.is_pose_transition_active());yield from pause(1)
    yield from capture('01-replay-overview')
    # Actual rendered captures around five pickups, a load, a fault and a departure.
    def event_find(kind,device=None):
        return next((e for e in events if kind in e['kind'] and (not device or e['deviceId']==device)),None)
    shots=[]
    for i in range(1,6):
        dev='REPLAY-FORK-%02d'%i;e=event_find('pickup',dev)
        if e:shots.append(('pickup-%02d'%i,e['time']+1,dev))
    for name,kind in [('dropoff','dropoff'),('fault','fault'),('truck-departure','depart')]:
        e=event_find(kind)
        if e:shots.append((name,e['time']+(12 if name=='truck-departure' else 1),e['deviceId']))
    lower=next(e for e in events if e['kind']=='pickup' and '下层' in e.get('text',''))
    shots.append(('lower-pickup',lower['time']+5,lower['deviceId']))
    drop=event_find('dropoff');shots.append(('loading-contact',drop['time']-1,drop['deviceId']))
    supply=next((e for e in events if '补给' in e.get('text','') and e['deviceId'].startswith('REPLAY-FORK')),None)
    if supply:shots.append(('supply-return',supply['time']+1,supply['deviceId']))
    assert len(shots)>=7,[(e['kind'],e['deviceId']) for e in events]
    for name,t,dev in shots:
        command('replaySeek',time=min(3599,t));command('replayFollow',id=dev)
        yield from wait('follow '+dev,lambda:not pawn.is_pose_transition_active());yield from pause(.5)
        report['states'][name]=state();yield from capture('02-'+name)
    # Full cycle/long range use the same fixed pools. No clock-dependent spawning.
    count=len(unreal.GameplayStatics.get_all_actors_of_class(world,unreal.Actor))
    command('replaySeek',time=3599);command('replayRate',rate=64);command('replayPlay')
    yield from wait('end exact',lambda:state()['completed'])
    assert state()['time']==3600 and not state()['playing']
    assert len(unreal.GameplayStatics.get_all_actors_of_class(world,unreal.Actor))==count
    record('interval_end_and_bounded_actor_pool',actors=count)
    command('replaySeek',time=230);command('replayRate',rate=8);command('replayPlay')
    command('navigate',page='inventory');assert state()['exitPending'] and not state()['playing'];saved=state()['time']
    yield from pause(.4);assert state()['time']==saved
    yield from capture('03-exit-confirmation')
    command('replayExitCancel');assert state()['playing'] and state()['rate']==8
    command('replayPause');command('replayEndRequest');command('replayExitConfirm')
    after={a.get_name():snap_actor(a) for a in tracked}
    assert before==after,[key for key in before if before[key]!=after[key]]
    assert pose()==camera_before,(pose(),camera_before)
    assert pc.warehouse_roof.get_transition_phase()==roof_before
    restoration=json.loads(session.get_restoration_report());assert restoration['verified'] and not restoration['replayActorExists']
    record('cancel_resume_and_exact_scene_restoration',restoration=restoration)
    # Every order and arbitrary date uses the same canonical relative dataset.
    for order,start,end in [('TEST-OUT-004','2040-07-01T00:00:00.000Z','2040-07-02T00:00:00.000Z')]:
        command('replayStart',orderId=order,startUtc=start,endUtc=end);assert state()['active'],state()
        command('replayPause');command('replaySeek',time=230);assert state()['devices']==first['devices']
        assert len(state()['markers'])<=96 and len(state()['events'])<=100
        record('arbitrary_date_order_same_data_bounded_events',markers=len(state()['markers']),events=len(state()['events']))
        yield from wait('second prepare',lambda:not state()['preparing'])
        command('replayFollow',id='');command('replayOverview');yield from wait('performance view',lambda:not pawn.is_pose_transition_active())
        command('replayRate',rate=1);command('replayPlay');yield from pause(2)
        frames=[];last=time.monotonic()
        for _ in range(300):
            yield
            now=time.monotonic();frames.append((now-last)*1000);last=now
        report['performance']=dict(frames=len(frames),mean_ms=statistics.mean(frames),median_ms=statistics.median(frames),p95_ms=sorted(frames)[int(len(frames)*.95)],max_ms=max(frames),render='1920x1080 offscreen same machine')
        command('replayEndRequest');command('replayExitConfirm')
    # Exercise the same native business entry points used by Home/middle reset,
    # search, selection, presets and navigation. Physical key dispatch has separate tests.
    original_id=next(x['id'] for x in json.loads(hud.get_snapshot())['equipment'] if x['id'].startswith('FORK-') and x['id']!='FORK-01')
    operations=[('overview',lambda:command('overview')),
        ('selection_without_camera',lambda:hud.select_object(original_id,False)),
        ('search',lambda:hud.call_method('SearchCommitted',args=(unreal.Text(original_id),unreal.TextCommit.ON_ENTER))),
        ('preset',lambda:command('preset',value='top')),
        ('inventory_navigation',lambda:hud.navigate('inventory'))]
    for name,operation in operations:
        command('replayStart',orderId='TEST-OUT-002',startUtc='2026-10-23T12:00:00.000Z',endUtc='2026-10-23T13:00:00.000Z')
        yield from wait(name+' prepared',lambda:not state()['preparing'] and not pawn.is_pose_transition_active())
        command('replayPause');command('replaySeek',time=230);command('replayRate',rate=8)
        operation();assert state()['exitPending'],name
        yield from pause(.2);assert state()['time']==230 and not state()['playing']
        command('replayExitCancel');assert state()['active'] and not state()['playing'] and state()['rate']==8
        operation();command('replayExitConfirm');assert not state()['active']
        yield from wait(name+' restored operation',lambda:not pawn.is_pose_transition_active() and not pc.warehouse_roof.is_opening() and not pc.warehouse_roof.is_closing())
        yield from pause(.8)
        assert json.loads(session.get_restoration_report())['verified']
        if name in ('search','selection_without_camera'):assert hud.selected_id==original_id,(name,hud.selected_id)
        if name=='overview':assert hud.selected_id=='' and pc.warehouse_roof.is_roof_closed()
        if name=='inventory_navigation':
            yield from wait('inventory visible',lambda:bool(hud.last_browser_report) and json.loads(hud.last_browser_report).get('page')=='inventory')
        saved_pose=pose();command('replayExitConfirm');assert pose()==saved_pose and not pawn.is_pose_transition_active()
        record('native_exit_guard_'+name)
    assert hashlib.sha256(MAP.read_bytes()).hexdigest()==map_hash
    record('saved_map_unchanged',sha256=map_hash)

def finish(error=None):
    report.update(success=error is None,elapsed_seconds=time.monotonic()-started,map_sha256=map_hash)
    if error:report['error']=error
    write();unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log_error if error else unreal.log)('GHS_ORDER_REPLAY_RUNTIME '+json.dumps({k:v for k,v in report.items() if k not in ('states',)},ensure_ascii=False))
    if world:unreal.SystemLibrary.quit_game(world,pc,unreal.QuitPreference.QUIT,False)
steps=run()
def tick(delta):
    try:
        assert time.monotonic()-started<600,'Runtime verification timeout'
        next(steps)
    except StopIteration:finish()
    except Exception:finish(traceback.format_exc())
write();handle=unreal.register_slate_post_tick_callback(tick)
